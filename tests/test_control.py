"""Tests for control module — heartbeat, throttle state machine."""

import os
import time
from datetime import datetime, timezone, timedelta
import pytest


class TestHeartbeat:
    def test_write_heartbeat_creates_file(self, tmp_project):
        from loop_engineering.control import write_heartbeat
        write_heartbeat(tmp_project)
        hb_path = os.path.join(tmp_project, ".loop-engineering", "control", "heartbeat")
        assert os.path.exists(hb_path)

    def test_read_heartbeat_returns_none_when_no_file(self, tmp_project):
        from loop_engineering.control import read_heartbeat
        assert read_heartbeat(tmp_project) is None

    def test_read_heartbeat_returns_datetime(self, tmp_project):
        from loop_engineering.control import write_heartbeat, read_heartbeat
        write_heartbeat(tmp_project)
        hb = read_heartbeat(tmp_project)
        assert hb is not None
        assert isinstance(hb, datetime)

    def test_is_loop_running_false_when_no_heartbeat(self, tmp_project):
        from loop_engineering.control import is_loop_running
        assert is_loop_running(tmp_project) is False

    def test_is_loop_running_true_with_recent_heartbeat(self, tmp_project):
        from loop_engineering.control import write_heartbeat, is_loop_running
        write_heartbeat(tmp_project)
        assert is_loop_running(tmp_project, threshold_minutes=10) is True


class TestThrottle:
    def test_get_throttle_returns_default(self, tmp_project):
        from loop_engineering.control import get_throttle
        assert get_throttle(tmp_project) == "2m"

    def test_get_throttle_custom_default(self, tmp_project):
        from loop_engineering.control import get_throttle
        assert get_throttle(tmp_project, default="5m") == "5m"

    def test_set_and_get_throttle(self, tmp_project):
        from loop_engineering.control import set_throttle, get_throttle
        set_throttle(tmp_project, "30s")
        assert get_throttle(tmp_project) == "30s"


class TestStatus:
    def test_get_status_returns_dict(self, tmp_project):
        from loop_engineering.control import get_status
        status = get_status(tmp_project)
        assert isinstance(status, dict)
        assert "running" in status
        assert "throttle" in status
        assert "heartbeat" in status
        assert "pid" in status

    def test_get_status_no_heartbeat(self, tmp_project):
        from loop_engineering.control import get_status
        status = get_status(tmp_project)
        assert status["running"] is False
        assert status["heartbeat"] is None


class TestLoopStartedAt:
    def test_write_loop_started_at_creates_file(self, tmp_project):
        from loop_engineering.control import write_loop_started_at
        write_loop_started_at(tmp_project)
        ls_path = os.path.join(tmp_project, ".loop-engineering", "control", "loop_started_at")
        assert os.path.exists(ls_path)

    def test_read_loop_started_at_returns_none_when_no_file(self, tmp_project):
        from loop_engineering.control import read_loop_started_at
        assert read_loop_started_at(tmp_project) is None
