#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import logging

import pytest
from k8s_test_harness import harness
from k8s_test_harness.util import env_util, k8s_util

LOG = logging.getLogger(__name__)


def _get_k8s_metacollector_helm_cmd(image_version: str):
    k8s_metacollector_rock = env_util.get_build_meta_info_for_rock_version(
        "k8s-metacollector", image_version, "amd64"
    )

    images = [
        k8s_util.HelmImage(k8s_metacollector_rock.image),
    ]

    return k8s_util.get_helm_install_command(
        "k8s-metacollector",
        "k8s-metacollector",
        namespace="metacollector",
        repository="https://falcosecurity.github.io/charts",
        images=images,
        split_image_registry=True,
    )


@pytest.mark.parametrize("image_version", ["0.1.1"])
def test_integration_k8s_metacollector(
    function_instance: harness.Instance, image_version
):
    # Deploy k8s-metacollector helm chart and wait for it to become active.
    function_instance.exec(_get_k8s_metacollector_helm_cmd(image_version))

    # Wait for the daemonset to become Active.
    k8s_util.wait_for_deployment(
        function_instance, "k8s-metacollector", "metacollector", retry_times=10
    )

    process = function_instance.exec(
        [
            "k8s",
            "kubectl",
            "--namespace",
            "metacollector",
            "get",
            "service",
            "k8s-metacollector",
            "-o",
            "jsonpath='{.spec.clusterIP}'",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # It may have quotes. Strip them.
    clusterIP = process.stdout.strip("'")

    process = function_instance.exec(
        ["curl", f"http://{clusterIP}:8081/healthz"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "ok" == process.stdout
