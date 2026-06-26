"""Tests for control.py — heartbeat, pause/resume, throttle state machine."""

import os
import time
import pytest
from loop_engineering.control import (
    write_heartbeat,
    read_heartbeat,
    is_loop_running,
    is_paused,
    set_pause,
    get_throttle,
    set_throttle,
    get_status,
)


@pytest.fixture
def ctrl_dir(tmp_dir):
    """Create a .loop-engineering/control/ directory in tmp_dir."""
    cdir = os.path.join(tmp_dir, ".loop-engineering", "control")
    os.makedirs(cdir, exist_ok=True)
    return tmp_dir


class TestHeartbeat:
    """Tests for heartbeat write/read/is_running."""

    def test_write_and_read_heartbeat(self, ctrl_dir):
        """Write heartbeat then read it back."""
        write_heartbeat(ctrl_dir)
        hb = read_heartbeat(ctrl_dir)
        assert hb is not None

    def test_read_heartbeat_when_none(self, ctrl_dir):
        """Reading heartbeat when none was written returns None."""
        hb = read_heartbeat(ctrl_dir)
        assert hb is None

    def test_is_running_after_write(self, ctrl_dir):
        """Immediately after writing heartbeat, is_running should be True."""
        write_heartbeat(ctrl_dir)
        # Use a small threshold to ensure it's recognized as running
        assert is_loop_running(ctrl_dir, threshold_minutes=10) is True

    def test_is_running_when_no_heartbeat(self, ctrl_dir):
        """Without any heartbeat file, is_running should be False."""
        assert is_loop_running(ctrl_dir, threshold_minutes=10) is False

    def test_read_heartbeat_returns_datetime(self, ctrl_dir):
        """Read heartbeat should return a datetime object."""
        write_heartbeat(ctrl_dir)
        from datetime import datetime
        hb = read_heartbeat(ctrl_dir)
        assert isinstance(hb, datetime)


class TestPause:
    """Tests for pause/resume."""

    def test_is_paused_default_false(self, ctrl_dir):
        """By default, pause flag should not exist."""
        assert is_paused(ctrl_dir) is False

    def test_set_pause_true(self, ctrl_dir):
        """Setting pause should create the flag."""
        set_pause(ctrl_dir, True)
        assert is_paused(ctrl_dir) is True

    def test_set_pause_false(self, ctrl_dir):
        """Unsetting pause should remove the flag."""
        set_pause(ctrl_dir, True)
        set_pause(ctrl_dir, False)
        assert is_paused(ctrl_dir) is False

    def test_set_pause_false_when_not_paused(self, ctrl_dir):
        """Unpausing when not paused should not error."""
        set_pause(ctrl_dir, False)
        assert is_paused(ctrl_dir) is False

    def test_pause_toggle(self, ctrl_dir):
        """Toggle pause multiple times."""
        set_pause(ctrl_dir, True)
        assert is_paused(ctrl_dir) is True
        set_pause(ctrl_dir, False)
        assert is_paused(ctrl_dir) is False
        set_pause(ctrl_dir, True)
        assert is_paused(ctrl_dir) is True


class TestThrottle:
    """Tests for throttle get/set."""

    def test_get_throttle_default(self, ctrl_dir):
        """When throttle is not set, default is returned."""
        assert get_throttle(ctrl_dir, "2m") == "2m"

    def test_set_and_get_throttle(self, ctrl_dir):
        """Set throttle then read it back."""
        set_throttle(ctrl_dir, "5m")
        assert get_throttle(ctrl_dir, "2m") == "5m"

    def test_get_throttle_custom_default(self, ctrl_dir):
        """Custom default is returned when throttle is not set."""
        assert get_throttle(ctrl_dir, "10m") == "10m"

    def test_throttle_persists(self, ctrl_dir):
        """Throttle value should persist on disk."""
        set_throttle(ctrl_dir, "30s")
        assert get_throttle(ctrl_dir, "2m") == "30s"


class TestGetStatus:
    """Tests for get_status() aggregated state."""

    def test_get_status_returns_dict(self, ctrl_dir):
        """get_status should return a dict with expected keys."""
        write_heartbeat(ctrl_dir)
        status = get_status(ctrl_dir)
        assert isinstance(status, dict)
        for key in ("paused", "throttle", "running", "heartbeat", "pid", "pid_alive"):
            assert key in status

    def test_get_status_no_heartbeat(self, ctrl_dir):
        """get_status without heartbeat shows not running."""
        status = get_status(ctrl_dir)
        assert status["running"] is False
        assert status["heartbeat"] is None

    def test_get_status_has_throttle(self, ctrl_dir):
        """get_status includes correct throttle value."""
        set_throttle(ctrl_dir, "1m")
        status = get_status(ctrl_dir)
        assert status["throttle"] == "1m"
