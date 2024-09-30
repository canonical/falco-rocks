#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import pytest
from k8s_test_harness.util import docker_util, env_util


@pytest.mark.parametrize("image_version", ["0.8.7"])
def test_falco_exporter_rock(image_version):
    """Test falco-exporter rock."""
    rock = env_util.get_build_meta_info_for_rock_version(
        "falco-exporter", image_version, "amd64"
    )
    image = rock.image

    # Check binary. It doesn't have a --help or --version option.
    process = docker_util.run_in_docker(
        image, ["falco-exporter", "--timeout", "1s"], False
    )
    msg = "connecting to gRPC server at unix:///run/falco/falco.sock (timeout 1s)"
    assert msg in process.stderr
