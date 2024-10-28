#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import pytest
from k8s_test_harness.util import docker_util, env_util

ROCK_EXPECTED_FILES = [
    "/home/falcosidekick/app/LICENSE",
    "/home/falcosidekick/app/falcosidekick",
]


@pytest.mark.parametrize("image_version", ["2.29.0"])
def test_falcosidekick_rock(image_version):
    """Test falcosidekick rock."""
    rock = env_util.get_build_meta_info_for_rock_version(
        "falcosidekick", image_version, "amd64"
    )
    image = rock.image

    # check rock filesystem.
    docker_util.ensure_image_contains_paths_bare(image, ROCK_EXPECTED_FILES)

    # check binary.
    process = docker_util.run_in_docker(
        image, ["/home/falcosidekick/app/falcosidekick", "--version"]
    )
    assert image_version in process.stdout
