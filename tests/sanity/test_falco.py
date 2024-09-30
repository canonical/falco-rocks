#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import pytest
from k8s_test_harness.util import docker_util, env_util

ROCK_EXPECTED_FILES = [
    "/docker-entrypoint.sh",
    "/etc/falco/falco_rules.local.yaml",
    "/etc/falco/falco_rules.yaml",
    "/etc/falco/falco.yaml",
    "/etc/falcoctl/falcoctl.yaml",
    "/usr/lib/modules",
    "/usr/bin/falco",
    "/usr/bin/falcoctl",
]


@pytest.mark.parametrize("rock_name", ["falco", "falco-driver-loader"])
@pytest.mark.parametrize("image_version", ["0.38.2"])
def test_falco_rock(rock_name, image_version):
    """Test falco rocks."""
    rock = env_util.get_build_meta_info_for_rock_version(
        rock_name, image_version, "amd64"
    )
    image = rock.image

    # check rock filesystem.
    docker_util.ensure_image_contains_paths(image, ROCK_EXPECTED_FILES)

    # check binaries.
    process = docker_util.run_in_docker(image, ["falco", "--version"])
    assert f"Falco version: {image_version}" in process.stdout

    process = docker_util.run_in_docker(image, ["falcoctl", "--help"])
    assert "The official CLI tool for working with Falco" in process.stdout
