"""Shared test fixtures."""

import os
import tempfile
import pytest


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for file-based tests. Cleans up after test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def tmp_project(tmp_dir):
    """Create a minimal loop project directory with .git and .loop-engineering/."""
    # Create .git directory
    git_dir = os.path.join(tmp_dir, ".git")
    os.makedirs(git_dir)

    # Create .loop-engineering directory
    le_dir = os.path.join(tmp_dir, ".loop-engineering")
    os.makedirs(le_dir)

    return tmp_dir


@pytest.fixture
def tmp_project_with_config(tmp_project):
    """Create a project with a minimal loop-config.yaml."""
    import yaml

    config = {
        "project": {"name": "test-project", "root": tmp_project},
        "agent": {
            "name": "test-agent",
            "workspace": os.path.join(os.path.dirname(tmp_project), "test-agent"),
            "mcp_port": 9080,
        },
        "main": {"mcp_port": 8080},
    }
    config_dir = os.path.join(tmp_project, ".loop-engineering")
    config_path = os.path.join(config_dir, "loop-config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    return tmp_project
