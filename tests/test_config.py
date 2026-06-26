"""Tests for config.py — deep_merge, merge/delete/change tracking."""

import os
import pytest
from loop_engineering.config import merge_config, write_config, read_config


@pytest.fixture
def config_project(tmp_dir):
    """Create a temp project dir with .loop-engineering/ and an initial config."""
    le_dir = os.path.join(tmp_dir, ".loop-engineering")
    os.makedirs(le_dir, exist_ok=True)
    return tmp_dir


class TestDeepMerge:
    """Tests for merge_config() — deep merge with change tracking."""

    def test_add_new_top_level_key(self, config_project):
        """Adding a new top-level key reports it as changed."""
        new_config, changed = merge_config(config_project, {
            "project": {"name": "test-project", "root": config_project}
        })
        assert "project" in changed or "project.name" in changed or "project.root" in changed
        assert new_config["project"]["name"] == "test-project"

    def test_add_nested_key(self, config_project):
        """Adding a nested key inside an existing dict."""
        # First set up a base config
        write_config(config_project, {"agent": {"name": "test-user"}})
        new_config, changed = merge_config(config_project, {
            "agent": {"mcp_port": 9999}
        })
        assert "agent.mcp_port" in changed
        assert new_config["agent"]["mcp_port"] == 9999
        assert new_config["agent"]["name"] == "test-user"  # preserved

    def test_update_existing_value(self, config_project):
        """Updating an existing value reports the key as changed."""
        write_config(config_project, {"agent": {"name": "old-name"}})
        new_config, changed = merge_config(config_project, {
            "agent": {"name": "new-name"}
        })
        assert "agent.name" in changed
        assert new_config["agent"]["name"] == "new-name"

    def test_no_change_when_values_equal(self, config_project):
        """Setting the same value should not report it as changed."""
        write_config(config_project, {"agent": {"name": "same-name"}})
        new_config, changed = merge_config(config_project, {
            "agent": {"name": "same-name"}
        })
        assert "agent.name" not in changed
        assert new_config["agent"]["name"] == "same-name"

    def test_delete_key_with_none(self, config_project):
        """Setting a key to None deletes it from the config."""
        write_config(config_project, {
            "agent": {"name": "user", "mcp_port": 9080},
            "main": {"mcp_port": 8080}
        })
        new_config, changed = merge_config(config_project, {
            "agent": {"mcp_port": None}
        })
        assert "agent.mcp_port" in changed
        assert "mcp_port" not in new_config["agent"]
        assert new_config["agent"]["name"] == "user"  # preserved

    def test_delete_top_level_key(self, config_project):
        """Deleting a top-level key."""
        write_config(config_project, {
            "agent": {"name": "user"},
            "data_repo": {"path": "/some/path"}
        })
        new_config, changed = merge_config(config_project, {
            "data_repo": None
        })
        assert "data_repo" in changed
        assert "data_repo" not in new_config

    def test_delete_nonexistent_key_no_change(self, config_project):
        """Deleting a key that does not exist should not report a change."""
        write_config(config_project, {"agent": {"name": "user"}})
        new_config, changed = merge_config(config_project, {
            "nonexistent": None
        })
        assert "nonexistent" not in changed

    def test_deep_merge_nested_dicts(self, config_project):
        """Deep merge should recurse into nested dicts."""
        write_config(config_project, {
            "project": {"name": "old-name", "root": "/old/root"}
        })
        new_config, changed = merge_config(config_project, {
            "project": {"name": "new-name", "type": "unity"}
        })
        assert "project.name" in changed
        assert "project.type" in changed
        assert "project.root" not in changed  # unchanged
        assert new_config["project"]["name"] == "new-name"
        assert new_config["project"]["type"] == "unity"
        assert new_config["project"]["root"] == "/old/root"  # preserved

    def test_empty_initial_config(self, config_project):
        """Merge into a project with no config file."""
        new_config, changed = merge_config(config_project, {
            "agent": {"name": "new-user", "workspace": "/ws"}
        })
        assert "agent" in changed or "agent.name" in changed or "agent.workspace" in changed
        assert new_config["agent"]["name"] == "new-user"
        assert new_config["agent"]["workspace"] == "/ws"

    def test_multiple_changes_tracked(self, config_project):
        """Multiple simultaneous changes should all be tracked."""
        write_config(config_project, {
            "agent": {"name": "old", "mcp_port": 9080},
            "main": {"mcp_port": 8080}
        })
        new_config, changed = merge_config(config_project, {
            "agent": {"name": "new", "mcp_port": 9999},
            "main": {"mcp_port": 7070}
        })
        assert "agent.name" in changed
        assert "agent.mcp_port" in changed
        assert "main.mcp_port" in changed
        assert len(changed) >= 3

    def test_read_back_merged_config(self, config_project):
        """Merge then read back should return the merged values."""
        write_config(config_project, {"agent": {"name": "base-user"}})
        new_config, changed = merge_config(config_project, {
            "agent": {"workspace": "/merged/ws"},
            "project": {"name": "test-proj"}
        })
        # Write the merged config to disk
        write_config(config_project, new_config)
        cfg = read_config(config_project)
        assert cfg["agent"]["name"] == "base-user"
        assert cfg["agent"]["workspace"] == "/merged/ws"
        assert cfg["project"]["name"] == "test-proj"

    def test_merge_config_does_not_mutate_original(self, config_project):
        """merge_config should return a deep copy, not mutate the original config on disk."""
        write_config(config_project, {"agent": {"name": "original"}})
        new_config, changed = merge_config(config_project, {
            "agent": {"name": "modified"}
        })
        # The on-disk config should still be the original
        disk_cfg = read_config(config_project)
        assert disk_cfg["agent"]["name"] == "original"
        # The returned new_config should have the modification
        assert new_config["agent"]["name"] == "modified"
