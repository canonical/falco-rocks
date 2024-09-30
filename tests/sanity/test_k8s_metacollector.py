#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import pytest
from k8s_test_harness.util import docker_util, env_util


@pytest.mark.parametrize("image_version", ["0.1.1"])
def test_k8s_metacollector_rock(image_version):
    """Test k8s-metacollector rock."""
    rock = env_util.get_build_meta_info_for_rock_version(
        "k8s-metacollector", image_version, "amd64"
    )
    image = rock.image

    # check binary.
    process = docker_util.run_in_docker(image, ["/meta-collector", "version"])
    # the binary version doesn't contain the leading 'v'.
    assert image_version[1:] in process.stdout
