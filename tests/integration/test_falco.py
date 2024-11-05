#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import logging
import time

import pytest
from k8s_test_harness import harness
from k8s_test_harness.util import constants, env_util, k8s_util

LOG = logging.getLogger(__name__)


_FALCOCTL_VERSIONS = {
    # Based on the Falco releases.
    # falco_version: falcoctl_version
    "0.38.2": "0.9.0",
    "0.39.0": "0.10.0",
}


def _get_event_generator_helm_cmd():
    return k8s_util.get_helm_install_command(
        "event-generator",
        "event-generator",
        namespace="event-generator",
        repository="https://falcosecurity.github.io/charts",
        set_configs=[
            "config.loop=false",
            "config.actions=''",
        ],
    )


def _get_falco_exporter_helm_cmd(instance: harness.Instance):
    falco_exporter_rock = env_util.get_build_meta_info_for_rock_version(
        "falco-exporter", "0.8.7", "amd64"
    )

    images = [
        k8s_util.HelmImage(falco_exporter_rock.image),
    ]

    return k8s_util.get_helm_install_command(
        "falco-exporter",
        "falco-exporter",
        namespace="falco",
        repository="https://falcosecurity.github.io/charts",
        images=images,
        runAsUser=0,
        split_image_registry=True,
    )


def _get_falcosidekick_helm_cmd():
    falcosidekick_rock = env_util.get_build_meta_info_for_rock_version(
        "falcosidekick", "2.29.0", "amd64"
    )

    falcosidekickui_rock = env_util.get_build_meta_info_for_rock_version(
        "falcosidekick-ui", "2.2.0", "amd64"
    )

    images = [
        k8s_util.HelmImage(falcosidekick_rock.image),
        k8s_util.HelmImage(falcosidekickui_rock.image, "webui"),
    ]

    set_configs = [
        "webui.enabled=true",
    ]

    return k8s_util.get_helm_install_command(
        "falcosidekick",
        "falcosidekick",
        namespace="falco",
        repository="https://falcosecurity.github.io/charts",
        images=images,
        set_configs=set_configs,
        split_image_registry=True,
    )


def _get_falco_helm_cmd(falco_version: str):
    falco_rock = env_util.get_build_meta_info_for_rock_version(
        "falco", falco_version, "amd64"
    )

    falcoctl_rock = env_util.get_build_meta_info_for_rock_version(
        "falcoctl", _FALCOCTL_VERSIONS[falco_version], "amd64"
    )

    driver_loader_rock = env_util.get_build_meta_info_for_rock_version(
        "falco-driver-loader", falco_version, "amd64"
    )

    images = [
        k8s_util.HelmImage(falco_rock.image),
        k8s_util.HelmImage(falcoctl_rock.image, "falcoctl"),
        k8s_util.HelmImage(driver_loader_rock.image, "driver.loader.initContainer"),
    ]

    set_configs = [
        "driver.kind=modern_ebpf",
        # required for the falco-exporter.
        # https://github.com/falcosecurity/charts/tree/master/charts/falco-exporter#falco-exporter-helm-chart
        "falco.grpc.enabled=true",
        "falco.grpc_output.enabled=true",
    ]

    return k8s_util.get_helm_install_command(
        "falco",
        "falco",
        namespace="falco",
        repository="https://falcosecurity.github.io/charts",
        images=images,
        runAsUser=0,
        set_configs=set_configs,
        split_image_registry=True,
    )


def _curl_service_via_falco(
    instance: harness.Instance, svc_name: str, port: int, endpoint: str
):
    return instance.exec(
        [
            "k8s",
            "kubectl",
            "--namespace",
            "falco",
            "exec",
            f"{constants.K8S_DAEMONSET}/falco",
            "--",
            "curl",
            "-s",
            f"http://{svc_name}:{port}/{endpoint}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _assert_falco_exporter_up(instance: harness.Instance):
    # Assert that falco-exporter is responsive. The falco-exporter image is a bare image,
    # so, we're using the falco Pod to curl the falco-exporter endpoint instead.
    LOG.info("Checking if falco-exporter is being responsive.")
    process = _curl_service_via_falco(instance, "falco-exporter", 9376, "metrics")
    assert (
        "Total number of scrapes" in process.stdout
    ), "Expected falco-exporter to return metrics."


def _assert_falcosidekick_up(instance: harness.Instance):
    # Assert that falcosidekick is responsive. It has a ping method, to which we should get pong.
    # The falcosidekick image does not have curl or wget, but the falco image does.
    LOG.info("Checking if falcosidekick is being responsive.")
    process = _curl_service_via_falco(instance, "falcosidekick", 2801, "ping")
    assert (
        "pong" in process.stdout
    ), "Expected falcosidekick to respond with pong to ping."


def _assert_falcosidekick_ui_up(instance: harness.Instance):
    # Assert that falcosidekick-ui is responsive.
    # The falcosidekick-ui image does not have curl or wget, but the falco image does.
    LOG.info("Checking if falcosidekick-ui is being responsive.")
    process = _curl_service_via_falco(
        instance, "falcosidekick-ui", 2802, "api/v1/healthz"
    )
    assert "ok" in process.stdout, "Expected falcosidekick-ui to respond with ok."


def _assert_falco_logs(instance: harness.Instance):
    # Falco should have noticed the unexpected behaviour from the event-generator, and it should
    # have logged these events to stdout by default.
    # We might have to check a few times.
    assert_strings = [
        "Warning Symlinks created over sensitive files (target=/etc",
        "parent=event-generator command=ln -s /etc",
    ]
    for i in range(10):
        # Pebble is the container's entrypoint, and it doesn't contain Falco's logs.
        # We have to call pebble logs.
        LOG.info("Checking if Falco detected irregularities.")
        process = instance.exec(
            [
                "k8s",
                "kubectl",
                "--namespace",
                "falco",
                "exec",
                f"{constants.K8S_DAEMONSET}/falco",
                "--",
                # TODO(claudiub): We're currently building with rockcraft 1.3.0.
                # In rockcraft 1.3.1, pebble has moved to /usr/bin/pebble.
                # We'll have to update this when we update rockcraft.
                "/.rock/bin/pebble",
                "logs",
                "-n",
                "100",
                "falco",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        if all([s in process.stdout for s in assert_strings]):
            LOG.info("Falco detected the expected irregularities.")
            return

        LOG.info("Falco did not detect irregularities (yet). Sleeping.")
        time.sleep(60)

    assert False, "Expected Falco logs to contain Warnings, based on event-generator"


@pytest.mark.parametrize("image_version", ["0.38.2", "0.39.0"])
def test_integration_falco(function_instance: harness.Instance, image_version):
    # falcosidekick has readOnlyRootFilesystem=True, which means Pebble won't be able
    # to copy its necessary files. This mutating webhook solves this issue by adding
    # an emptydir volume to Pods for Pebble to use.
    k8s_util.install_mutating_pebble_webhook(function_instance)

    # Deploy Falco helm chart and wait for it to become active.
    function_instance.exec(_get_falco_helm_cmd(image_version))

    # Deploy falcosidekick helm chart and wait for it to become active.
    function_instance.exec(_get_falcosidekick_helm_cmd())

    # Deploy falco-exporter helm chart and wait for it to become active.
    function_instance.exec(_get_falco_exporter_helm_cmd(function_instance))

    # Wait for the daemonsets to become Active.
    for daemonset in ["falco", "falco-exporter"]:
        k8s_util.wait_for_daemonset(
            function_instance, daemonset, "falco", retry_times=10
        )

    # Wait for the deployments to become Active.
    for deployment in ["falcosidekick", "falcosidekick-ui"]:
        k8s_util.wait_for_deployment(
            function_instance, deployment, "falco", retry_times=10
        )

    # Deploy event-generator for Falco and wait for it to become active.
    function_instance.exec(_get_event_generator_helm_cmd())

    # Wait for the event-generator job to finish.
    k8s_util.wait_for_resource(
        function_instance,
        "job.batch",
        "event-generator",
        "event-generator",
        "Complete",
        retry_times=10,
    )

    _assert_falco_logs(function_instance)
    _assert_falcosidekick_up(function_instance)
    _assert_falcosidekick_ui_up(function_instance)
    _assert_falco_exporter_up(function_instance)
