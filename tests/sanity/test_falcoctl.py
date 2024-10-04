#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import pytest
from k8s_test_harness.util import docker_util, env_util


@pytest.mark.parametrize("image_version", ["0.9.0"])
def test_falcoctl_rock(image_version):
    """Test falcoctl rock."""
    rock = env_util.get_build_meta_info_for_rock_version(
        "falcoctl", image_version, "amd64"
    )
    image = rock.image

    # check binary.
    process = docker_util.run_in_docker(image, ["falcoctl", "version"])
    assert image_version in process.stdout
