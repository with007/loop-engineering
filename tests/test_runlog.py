"""Tests for runlog.py — write_run_log, list_runs filtering, get_pass_rate calculation."""

import os
import pytest
from loop_engineering.runlog import write_run_log, list_runs, get_pass_rate


@pytest.fixture
def runs_project(tmp_dir):
    """Create a temp project dir with .loop-engineering/ directory."""
    le_dir = os.path.join(tmp_dir, ".loop-engineering")
    os.makedirs(le_dir, exist_ok=True)
    return tmp_dir


def _make_entry(task_id="a1b2c3d4", imp_round=1, vfy_round=1, phase="implement",
                result="PASS", whoami="with", task_desc="Test task", **kwargs):
    """Helper to create a minimal run log entry dict."""
    entry = {
        "task_id": task_id,
        "imp_round": imp_round,
        "vfy_round": vfy_round,
        "phase": phase,
        "result": result,
        "whoami": whoami,
        "task_desc": task_desc,
    }
    entry.update(kwargs)
    return entry


class TestWriteRunLog:
    """Tests for write_run_log()."""

    def test_write_creates_file(self, runs_project):
        """Writing a run log should create a JSON file on disk."""
        entry = _make_entry()
        fpath = write_run_log(runs_project, entry)
        assert os.path.exists(fpath)
        assert fpath.endswith(".json")

    def test_write_adds_defaults(self, runs_project):
        """write_run_log should add default fields like version, started, completed."""
        entry = _make_entry()
        fpath = write_run_log(runs_project, entry)
        import json
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "version" in data
        assert data["version"] == 1
        assert "started" in data
        assert "completed" in data

    def test_write_preserves_existing_fields(self, runs_project):
        """Fields explicitly set in the entry should be preserved."""
        entry = _make_entry(summary="Fixed a critical bug", files_changed=["a.py", "b.py"])
        fpath = write_run_log(runs_project, entry)
        import json
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["summary"] == "Fixed a critical bug"
        assert data["files_changed"] == ["a.py", "b.py"]


class TestListRuns:
    """Tests for list_runs() filtering."""

    def test_list_empty(self, runs_project):
        """Listing runs from an empty project returns empty list."""
        runs = list_runs(runs_project)
        assert runs == []

    def test_list_single_entry(self, runs_project):
        """Writing one entry and listing should return it."""
        write_run_log(runs_project, _make_entry())
        runs = list_runs(runs_project)
        assert len(runs) == 1
        assert runs[0]["task_id"] == "a1b2c3d4"

    def test_list_multiple_entries(self, runs_project):
        """Writing multiple entries should return all of them."""
        for i in range(5):
            write_run_log(runs_project, _make_entry(
                task_id=f"task{i:08d}", imp_round=i + 1, vfy_round=1
            ))
        runs = list_runs(runs_project, limit=100)
        assert len(runs) == 5

    def test_filter_by_whoami(self, runs_project):
        """Filter runs by whoami (agent name)."""
        write_run_log(runs_project, _make_entry(whoami="alice", task_id="aaa00001"))
        write_run_log(runs_project, _make_entry(whoami="bob", task_id="bbb00002"))
        write_run_log(runs_project, _make_entry(whoami="alice", task_id="aaa00003"))

        alice_runs = list_runs(runs_project, whoami="alice", limit=100)
        assert len(alice_runs) == 2
        assert all(r["whoami"] == "alice" for r in alice_runs)

        bob_runs = list_runs(runs_project, whoami="bob", limit=100)
        assert len(bob_runs) == 1

    def test_filter_by_result(self, runs_project):
        """Filter runs by result (PASS/FAIL)."""
        write_run_log(runs_project, _make_entry(task_id="aaa00001", result="PASS"))
        write_run_log(runs_project, _make_entry(task_id="bbb00002", result="FAIL"))
        write_run_log(runs_project, _make_entry(task_id="ccc00003", result="PASS"))

        pass_runs = list_runs(runs_project, result="PASS", limit=100)
        assert len(pass_runs) == 2

        fail_runs = list_runs(runs_project, result="FAIL", limit=100)
        assert len(fail_runs) == 1

    def test_filter_by_days(self, runs_project):
        """Filter runs by days — recent entries should be included."""
        write_run_log(runs_project, _make_entry(task_id="recent001"))
        runs = list_runs(runs_project, days=7)
        # Recent entry should be included (written just now)
        assert len(runs) >= 1
        assert any(r["task_id"] == "recent001" for r in runs)

    def test_limit_truncates(self, runs_project):
        """limit should truncate the results to the specified count."""
        for i in range(10):
            write_run_log(runs_project, _make_entry(task_id=f"task{i:08d}"))
        runs = list_runs(runs_project, limit=3)
        assert len(runs) == 3

    def test_sorted_by_completed_desc(self, runs_project):
        """Results should be sorted by completed time in descending order."""
        write_run_log(runs_project, _make_entry(task_id="first"))
        import time
        time.sleep(0.1)
        write_run_log(runs_project, _make_entry(task_id="second"))
        runs = list_runs(runs_project, limit=100)
        assert runs[0]["task_id"] == "second"
        assert runs[1]["task_id"] == "first"


class TestGetPassRate:
    """Tests for get_pass_rate()."""

    def test_pass_rate_empty(self, runs_project):
        """Pass rate on empty runs directory should be 0."""
        passed, total, rate = get_pass_rate(runs_project, days=7)
        assert passed == 0
        assert total == 0
        assert rate == 0.0

    def test_pass_rate_all_pass(self, runs_project):
        """When all verify phases pass, rate should be 1.0."""
        write_run_log(runs_project, _make_entry(task_id="a", phase="verify", result="PASS"))
        write_run_log(runs_project, _make_entry(task_id="b", phase="verify", result="PASS"))
        write_run_log(runs_project, _make_entry(task_id="c", phase="implement", result="PASS"))
        passed, total, rate = get_pass_rate(runs_project, days=7)
        assert passed == 2
        assert total == 2
        assert rate == 1.0

    def test_pass_rate_mixed(self, runs_project):
        """Mixed PASS/FAIL should produce correct rate."""
        write_run_log(runs_project, _make_entry(task_id="a", phase="verify", result="PASS"))
        write_run_log(runs_project, _make_entry(task_id="b", phase="verify", result="FAIL"))
        write_run_log(runs_project, _make_entry(task_id="c", phase="verify", result="PASS"))
        passed, total, rate = get_pass_rate(runs_project, days=7)
        assert passed == 2
        assert total == 3
        assert rate == pytest.approx(2 / 3)

    def test_pass_rate_only_counts_verify(self, runs_project):
        """Only verify phase entries should be counted in pass rate."""
        write_run_log(runs_project, _make_entry(task_id="a", phase="verify", result="PASS"))
        write_run_log(runs_project, _make_entry(task_id="b", phase="implement", result="PASS"))
        write_run_log(runs_project, _make_entry(task_id="c", phase="implement", result="FAIL"))
        passed, total, rate = get_pass_rate(runs_project, days=7)
        assert total == 1  # only verify phase
        assert passed == 1
        assert rate == 1.0

    def test_pass_rate_all_fail(self, runs_project):
        """When all verify phases fail, rate should be 0.0."""
        write_run_log(runs_project, _make_entry(task_id="a", phase="verify", result="FAIL"))
        write_run_log(runs_project, _make_entry(task_id="b", phase="verify", result="FAIL"))
        passed, total, rate = get_pass_rate(runs_project, days=7)
        assert passed == 0
        assert total == 2
        assert rate == 0.0
