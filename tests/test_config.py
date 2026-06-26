"""Tests for config module."""

import os
import pytest


class TestIsProjectDir:
    def test_with_config(self, tmp_project_with_config):
        from loop_engineering.config import is_project_dir
        assert is_project_dir(tmp_project_with_config) is True

    def test_without_config(self, tmp_project):
        from loop_engineering.config import is_project_dir
        assert is_project_dir(tmp_project) is False

    def test_empty_dir(self, tmp_dir):
        from loop_engineering.config import is_project_dir
        assert is_project_dir(tmp_dir) is False


class TestReadConfig:
    def test_reads_config(self, tmp_project_with_config):
        from loop_engineering.config import read_config
        cfg = read_config(tmp_project_with_config)
        assert cfg["project"]["name"] == "test-project"
        assert cfg["agent"]["name"] == "test-agent"

    def test_empty_when_no_config(self, tmp_project):
        from loop_engineering.config import read_config
        cfg = read_config(tmp_project)
        assert cfg == {}


class TestWriteConfig:
    def test_creates_file(self, tmp_project):
        from loop_engineering.config import write_config, read_config
        cfg = {"project": {"name": "written"}}
        path = write_config(tmp_project, cfg)
        assert os.path.exists(path)
        read_back = read_config(tmp_project)
        assert read_back["project"]["name"] == "written"


class TestMergeConfig:
    def test_adds_new_keys(self, tmp_project_with_config):
        from loop_engineering.config import merge_config
        new_cfg, changed = merge_config(
            tmp_project_with_config,
            {"project": {"description": "test desc"}}
        )
        assert "project.description" in changed
        assert new_cfg["project"]["description"] == "test desc"

    def test_updates_existing(self, tmp_project_with_config):
        from loop_engineering.config import merge_config
        new_cfg, changed = merge_config(
            tmp_project_with_config,
            {"agent": {"name": "updated-agent"}}
        )
        assert "agent.name" in changed
        assert new_cfg["agent"]["name"] == "updated-agent"

    def test_deletes_keys(self, tmp_project_with_config):
        from loop_engineering.config import merge_config
        new_cfg, changed = merge_config(
            tmp_project_with_config,
            {"agent": {"name": None}}
        )
        assert "agent.name" in changed
        assert "name" not in new_cfg["agent"]

    def test_nested_merge_preserves_siblings(self, tmp_project_with_config):
        from loop_engineering.config import merge_config
        new_cfg, changed = merge_config(
            tmp_project_with_config,
            {"agent": {"mcp_port": 9999}}
        )
        assert new_cfg["agent"]["name"] == "test-agent"  # preserved
        assert new_cfg["agent"]["mcp_port"] == 9999

    def test_no_change_returns_empty_set(self, tmp_project_with_config):
        from loop_engineering.config import merge_config
        new_cfg, changed = merge_config(
            tmp_project_with_config,
            {"agent": {"name": "test-agent"}}
        )
        assert changed == set()


class TestDetectConfig:
    def test_detects_project_name(self, tmp_project):
        from loop_engineering.config import detect_config
        cfg = detect_config(tmp_project)
        assert "project" in cfg
        assert "name" in cfg["project"]

    def test_detects_root(self, tmp_project):
        from loop_engineering.config import detect_config
        cfg = detect_config(tmp_project)
        assert cfg["project"]["root"] == tmp_project
