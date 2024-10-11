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


def _get_falcosidekick_helm_cmd():
    falcosidekick_rock = env_util.get_build_meta_info_for_rock_version(
        "falcosidekick", "2.29.0", "amd64"
    )

    images = [
        k8s_util.HelmImage(falcosidekick_rock.image),
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
        "falco-driver-loader", image_version, "amd64"
    )

    driver_loader_rock = env_util.get_build_meta_info_for_rock_version(
        "falco-driver-loader", image_version, "amd64"
    )

    images = [
        k8s_util.HelmImage(falco_rock.image),
        k8s_util.HelmImage(falcoctl_rock.image, "falcoctl"),
        k8s_util.HelmImage(driver_loader_rock.image, "driver.loader.initContainer"),
    ]

    set_configs = [
        "driver.kind=modern_ebpf",
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


def _assert_falcosidekick_up(instance: harness.Instance):
    # Assert that falcosidekick is responsive. It has a ping method, to which we should get pong.
    # The falcosidekick image does not have curl or wget, but the falco image does.
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
            "curl",
            "-s",
            "http://falcosidekick:2801/ping",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (
        "pong" in process.stdout
    ), "Expected falcosidekick to respond with pong to ping."


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

    # Wait for the daemonset to become Active.
    k8s_util.wait_for_daemonset(function_instance, "falco", "falco", retry_times=10)

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
