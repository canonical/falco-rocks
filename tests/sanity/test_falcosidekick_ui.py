#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import pytest
from k8s_test_harness.util import docker_util, env_util

ROCK_EXPECTED_FILES = [
    "/app/LICENSE",
    "/app/falcosidekick-ui",
    "/app/frontend/dist",
]


@pytest.mark.parametrize("image_version", ["2.2.0"])
def test_falcosidekick_ui_rock(image_version):
    """Test falcosidekick-ui rock."""
    rock = env_util.get_build_meta_info_for_rock_version(
        "falcosidekick-ui", image_version, "amd64"
    )
    image = rock.image

    # check rock filesystem.
    docker_util.ensure_image_contains_paths_bare(image, ROCK_EXPECTED_FILES)

    # check binary.
    process = docker_util.run_in_docker(image, ["/app/falcosidekick-ui", "-v"])
    assert image_version in process.stdout
