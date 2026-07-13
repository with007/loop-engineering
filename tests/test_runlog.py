"""Tests for runlog module — write, query, filter."""

import os
import pytest


class TestWriteRunLog:
    def test_creates_file(self, tmp_project):
        from loop_engineering.runlog import write_run_log
        entry = {
            "task_id": "abc12345",
            "imp_round": 1,
            "vfy_round": 1,
            "phase": "verify",
            "result": "PASS",
        }
        path = write_run_log(tmp_project, entry)
        assert os.path.exists(path)
        assert "abc12345" in path
        assert "IMP1" in path
        assert "VFY1" in path

    def test_adds_defaults(self, tmp_project):
        from loop_engineering.runlog import write_run_log
        import json
        entry = {
            "task_id": "def67890",
            "imp_round": 2,
            "vfy_round": 1,
            "phase": "implement",
            "result": "FAIL",
        }
        path = write_run_log(tmp_project, entry)
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["whoami"] == ""
        assert saved["version"] == 1
        assert saved["task_desc"] == ""
        assert "completed" in saved
        assert "started" in saved


class TestListRuns:
    def test_returns_entries(self, tmp_project):
        from loop_engineering.runlog import write_run_log, list_runs
        for i in range(3):
            write_run_log(tmp_project, {
                "task_id": f"task{i:08d}",
                "imp_round": 1,
                "vfy_round": 1,
                "phase": "verify",
                "result": "PASS",
            })
        entries = list_runs(tmp_project)
        assert len(entries) == 3

    def test_empty_when_no_runs(self, tmp_project):
        from loop_engineering.runlog import list_runs
        entries = list_runs(tmp_project)
        assert entries == []

    def test_filters_by_whoami(self, tmp_project):
        from loop_engineering.runlog import write_run_log, list_runs
        write_run_log(tmp_project, {
            "task_id": "task00001",
            "imp_round": 1,
            "vfy_round": 1,
            "phase": "verify",
            "result": "PASS",
            "whoami": "alice",
        })
        write_run_log(tmp_project, {
            "task_id": "task00002",
            "imp_round": 1,
            "vfy_round": 1,
            "phase": "verify",
            "result": "PASS",
            "whoami": "bob",
        })
        alice = list_runs(tmp_project, whoami="alice")
        assert len(alice) == 1
        assert alice[0]["whoami"] == "alice"

    def test_filters_by_result(self, tmp_project):
        from loop_engineering.runlog import write_run_log, list_runs
        write_run_log(tmp_project, {
            "task_id": "task00001",
            "imp_round": 1,
            "vfy_round": 1,
            "phase": "verify",
            "result": "PASS",
        })
        write_run_log(tmp_project, {
            "task_id": "task00002",
            "imp_round": 1,
            "vfy_round": 1,
            "phase": "verify",
            "result": "FAIL",
        })
        passed = list_runs(tmp_project, result="PASS")
        assert len(passed) == 1
        assert passed[0]["result"] == "PASS"

    def test_orders_by_completed_desc(self, tmp_project):
        from loop_engineering.runlog import write_run_log, list_runs
        write_run_log(tmp_project, {
            "task_id": "task00001",
            "imp_round": 1,
            "vfy_round": 1,
            "phase": "verify",
            "result": "PASS",
        })
        import time
        time.sleep(0.1)
        write_run_log(tmp_project, {
            "task_id": "task00002",
            "imp_round": 1,
            "vfy_round": 1,
            "phase": "verify",
            "result": "PASS",
        })
        entries = list_runs(tmp_project)
        # Latest first
        assert entries[0]["task_id"] == "task00002"

    def test_respects_limit(self, tmp_project):
        from loop_engineering.runlog import write_run_log, list_runs
        for i in range(10):
            write_run_log(tmp_project, {
                "task_id": f"task{i:08d}",
                "imp_round": 1,
                "vfy_round": 1,
                "phase": "verify",
                "result": "PASS",
            })
        entries = list_runs(tmp_project, limit=3)
        assert len(entries) == 3
