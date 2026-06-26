"""Tests for task_parser service — parse_tasks, filter_tasks, tasklines_to_dicts."""

import os
import pytest


class TestParseTasks:
    def test_empty_when_no_tasks_md(self, tmp_project):
        from loop_engineering.server.services.task_parser import parse_tasks
        tasks = parse_tasks(tmp_project)
        assert tasks == []

    def test_parses_pending_task(self, tmp_project):
        from loop_engineering.server.services.task_parser import parse_tasks
        _write_tasks_md(tmp_project, "- [ ] Fix login bug [abc12345]\n")
        tasks = parse_tasks(tmp_project)
        assert len(tasks) == 1
        assert tasks[0]["status"] == "pending"
        assert tasks[0]["task_id"] == "abc12345"
        assert "Fix login bug" in tasks[0]["description"]

    def test_parses_done_task(self, tmp_project):
        from loop_engineering.server.services.task_parser import parse_tasks
        _write_tasks_md(tmp_project, "- [x] Add new feature [def67890]\n")
        tasks = parse_tasks(tmp_project)
        assert len(tasks) == 1
        assert tasks[0]["status"] == "done"
        assert tasks[0]["task_id"] == "def67890"

    def test_parses_in_progress_task(self, tmp_project):
        from loop_engineering.server.services.task_parser import parse_tasks
        _write_tasks_md(tmp_project, "- [~] Working on it (→ alice) [11112222]\n")
        tasks = parse_tasks(tmp_project)
        assert len(tasks) == 1
        assert tasks[0]["status"] == "in_progress"
        assert tasks[0]["assignee"] == "alice"
        assert tasks[0]["task_id"] == "11112222"

    def test_parses_task_with_meta(self, tmp_project):
        from loop_engineering.server.services.task_parser import parse_tasks
        _write_tasks_md(tmp_project, "- [ ] Refactor module [aaabbbb1] — priority:high\n")
        tasks = parse_tasks(tmp_project)
        assert tasks[0]["meta"] == "priority:high"

    def test_parses_feedback_lines(self, tmp_project):
        from loop_engineering.server.services.task_parser import parse_tasks
        _write_tasks_md(tmp_project,
            "- [x] Old task [ccc11111]\n"
            "  Feedback line 1\n"
            "  Feedback line 2\n"
            "- [ ] New task [ddd22222]\n"
        )
        tasks = parse_tasks(tmp_project)
        assert len(tasks[0]["feedback"]) == 2
        assert tasks[0]["feedback"][0] == "Feedback line 1"

    def test_parses_multiple_tasks(self, tmp_project):
        from loop_engineering.server.services.task_parser import parse_tasks
        _write_tasks_md(tmp_project,
            "- [ ] Task one [11111111]\n"
            "- [~] Task two (→ bob) [22222222]\n"
            "- [x] Task three [33333333]\n"
        )
        tasks = parse_tasks(tmp_project)
        assert len(tasks) == 3


class TestFilterTasks:
    @pytest.fixture
    def sample_tasks(self):
        return [
            {"description": "Task A", "task_id": "11111111", "status": "pending", "assignee": "", "meta": "", "feedback": []},
            {"description": "Task B", "task_id": "22222222", "status": "done", "assignee": "alice", "meta": "", "feedback": []},
            {"description": "Task C", "task_id": "33333333", "status": "in_progress", "assignee": "bob", "meta": "", "feedback": []},
            {"description": "Task D", "task_id": "44444444", "status": "done", "assignee": "", "meta": "", "feedback": []},
        ]

    def test_filters_by_status(self, sample_tasks):
        from loop_engineering.server.services.task_parser import filter_tasks
        filtered = filter_tasks(sample_tasks, status="done")
        assert len(filtered) == 2
        assert all(t["status"] == "done" for t in filtered)

    def test_filters_multiple_status(self, sample_tasks):
        from loop_engineering.server.services.task_parser import filter_tasks
        filtered = filter_tasks(sample_tasks, status="pending,done")
        assert len(filtered) == 3

    def test_in_progress_includes_pending_merge_and_reopen(self):
        from loop_engineering.server.services.task_parser import filter_tasks
        tasks = [
            {"description": "A", "task_id": "1", "status": "in_progress", "assignee": "", "meta": "", "feedback": []},
            {"description": "B", "task_id": "2", "status": "pending_merge", "assignee": "", "meta": "", "feedback": []},
            {"description": "C", "task_id": "3", "status": "reopen", "assignee": "", "meta": "", "feedback": []},
        ]
        filtered = filter_tasks(tasks, status="in_progress")
        assert len(filtered) == 3

    def test_filters_by_agent_name(self, sample_tasks):
        from loop_engineering.server.services.task_parser import filter_tasks
        filtered = filter_tasks(sample_tasks, status="pending,in_progress,done", filter_name="alice")
        assert len(filtered) == 1
        assert filtered[0]["task_id"] == "22222222"

    def test_orders_desc(self, sample_tasks):
        from loop_engineering.server.services.task_parser import filter_tasks
        filtered = filter_tasks(sample_tasks, status="pending,in_progress,done", order="desc")
        assert filtered[0]["task_id"] == "44444444"
        assert filtered[-1]["task_id"] == "11111111"

    def test_orders_asc(self, sample_tasks):
        from loop_engineering.server.services.task_parser import filter_tasks
        filtered = filter_tasks(sample_tasks, status="pending,in_progress,done", order="asc")
        assert filtered[0]["task_id"] == "11111111"


class TestTasklinesToDicts:
    def test_empty_list(self):
        from loop_engineering.server.services.task_parser import tasklines_to_dicts
        assert tasklines_to_dicts([]) == []

    def test_pass_through_for_dicts(self):
        from loop_engineering.server.services.task_parser import tasklines_to_dicts
        tasks = [{"description": "Test", "task_id": "1", "status": "pending"}]
        assert tasklines_to_dicts(tasks) == tasks


def _write_tasks_md(project_root, content):
    path = os.path.join(project_root, "tasks.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
