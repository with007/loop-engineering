"""Tests for task_id.py — pure functions, zero dependencies."""

import pytest
from loop_engineering.task_id import (
    generate_task_id,
    make_readable_slug,
    parse_task_id,
    extract_task_id_from_branch,
    make_branch_name,
    TaskLine,
)


class TestGenerateTaskId:
    def test_deterministic(self):
        """Same input produces same output."""
        a = generate_task_id("hello")
        b = generate_task_id("hello")
        assert a == b
        assert len(a) == 8
        assert all(c in "0123456789abcdef" for c in a)

    def test_different_inputs_differ(self):
        """Different inputs produce different outputs."""
        a = generate_task_id("hello")
        b = generate_task_id("world")
        assert a != b

    def test_empty_input(self):
        """Empty input still produces 8-char hex."""
        tid = generate_task_id("")
        assert len(tid) == 8

    def test_chinese_input(self):
        """Chinese text produces valid hex."""
        tid = generate_task_id("修复登录页报错")
        assert len(tid) == 8


class TestMakeReadableSlug:
    def test_english(self):
        slug = make_readable_slug("Fix login bug")
        assert slug == "Fix-login-bug"

    def test_chinese_preserved(self):
        slug = make_readable_slug("修复登录页报错")
        assert "修复登录页报错" in slug
        assert len(slug) > 0

    def test_strips_invalid_chars(self):
        slug = make_readable_slug("fix [bug] {test}")
        assert "[" not in slug
        assert "]" not in slug
        assert "{" not in slug
        assert "}" not in slug

    def test_empty_falls_back(self):
        slug = make_readable_slug("[:]{}")
        assert len(slug) > 0
        # Should return 'task' as fallback
        assert slug == "task"

    def test_max_length(self):
        slug = make_readable_slug("a very long description that should be truncated", max_len=10)
        assert len(slug) <= 10

    def test_splits_on_em_dash(self):
        """Em-dash separates description from meta."""
        slug = make_readable_slug("Fix login — 14:30 IMP1 VFY1 PASS")
        assert "14:30" not in slug
        assert "Fix-login" == slug


class TestParseTaskId:
    def test_extracts_hex(self):
        tid = parse_task_id("- [ ] desc [a1b2c3d4]")
        assert tid == "a1b2c3d4"

    def test_returns_none_when_absent(self):
        tid = parse_task_id("- [ ] desc")
        assert tid is None

    def test_returns_none_for_non_hex(self):
        tid = parse_task_id("- [ ] desc [nothexg]")
        assert tid is None


class TestExtractTaskIdFromBranch:
    def test_full_branch_name(self):
        tid = extract_task_id_from_branch("agent/with/a1b2c3d4-fix-login")
        assert tid == "a1b2c3d4"

    def test_pure_hex_basename(self):
        tid = extract_task_id_from_branch("agent/with/a1b2c3d4")
        assert tid == "a1b2c3d4"

    def test_no_dash(self):
        tid = extract_task_id_from_branch("origin/agent/with/a1b2c3d4")
        assert tid == "a1b2c3d4"


class TestMakeBranchName:
    def test_standard(self):
        name = make_branch_name("with", "a1b2c3d4", "Fix login bug")
        assert name.startswith("agent/with/a1b2c3d4-")
        assert "Fix-login-bug" in name


class TestTaskLineParse:
    def test_parse_all_fields(self):
        tl = TaskLine.parse("- [ ] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS")
        assert tl is not None
        assert tl.status == " "
        assert tl.description == "Fix login"
        assert tl.assignee == "with"
        assert tl.task_id == "a1b2c3d4"
        assert tl.meta == "14:30 IMP1 VFY1 PASS"

    def test_parse_minimal(self):
        tl = TaskLine.parse("- [ ] Fix login")
        assert tl is not None
        assert tl.status == " "
        assert tl.description == "Fix login"
        assert tl.assignee == ""
        assert tl.task_id == ""
        assert tl.meta == ""

    def test_parse_in_progress(self):
        tl = TaskLine.parse("- [~] Fix login (→ with) [a1b2c3d4]")
        assert tl is not None
        assert tl.status == "~"
        assert tl.assignee == "with"

    def test_parse_done_with_meta(self):
        tl = TaskLine.parse("- [x] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS")
        assert tl is not None
        assert tl.status == "x"
        assert tl.meta == "14:30 IMP1 VFY1 PASS"

    def test_parse_reopen(self):
        tl = TaskLine.parse("- [r] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS · 15:00 IMP2 VFY1 PASS")
        assert tl is not None
        assert tl.status == "r"
        assert "PASS" in tl.meta

    def test_non_task_line_returns_none(self):
        assert TaskLine.parse("# Tasks") is None
        assert TaskLine.parse("") is None
        assert TaskLine.parse("   ") is None

    def test_chinese_description(self):
        tl = TaskLine.parse("- [ ] 修复登录页报错 (→ with) [a1b2c3d4]")
        assert tl is not None
        assert tl.description == "修复登录页报错"


class TestTaskLineFormat:
    def test_round_trip_all_fields(self):
        original = TaskLine(
            status=" ",
            description="Fix login",
            assignee="with",
            task_id="a1b2c3d4",
            meta="14:30 IMP1 VFY1 PASS",
        )
        formatted = original.format()
        reparsed = TaskLine.parse(formatted)
        assert reparsed is not None
        assert reparsed.status == original.status
        assert reparsed.description == original.description
        assert reparsed.assignee == original.assignee
        assert reparsed.task_id == original.task_id
        assert reparsed.meta == original.meta

    def test_round_trip_minimal(self):
        original = TaskLine(status=" ", description="Fix login")
        formatted = original.format()
        reparsed = TaskLine.parse(formatted)
        assert reparsed is not None
        assert reparsed.status == original.status
        assert reparsed.description == original.description
        assert reparsed.assignee == ""
        assert reparsed.task_id == ""
        assert reparsed.meta == ""

    def test_round_trip_done(self):
        original = TaskLine(status="x", description="Fix login", assignee="with", task_id="a1b2c3d4")
        formatted = original.format()
        reparsed = TaskLine.parse(formatted)
        assert reparsed is not None
        assert reparsed.status == "x"
        assert reparsed.description == original.description

    def test_format_with_assignee_only(self):
        tl = TaskLine(status=" ", description="Fix login", assignee="with")
        formatted = tl.format()
        assert "(→ with)" in formatted
        # No task_id bracket: after the description + assignee, there should be no [hex] pattern
        assert "[a1b2c3d4]" not in formatted

    def test_format_no_assignee(self):
        tl = TaskLine(status="x", description="Done task", meta="14:30 PASS")
        assert "(→" not in tl.format()
        assert "— 14:30 PASS" in tl.format()


class TestTaskLineEquality:
    def test_equal(self):
        a = TaskLine(" ", "Fix login", "with", "a1b2c3d4", "meta")
        b = TaskLine(" ", "Fix login", "with", "a1b2c3d4", "meta")
        assert a == b

    def test_not_equal(self):
        a = TaskLine(" ", "Fix login")
        b = TaskLine("~", "Fix login")
        assert a != b

    def test_feedback_not_in_equality(self):
        """Feedback is not part of format/equality."""
        a = TaskLine(" ", "Fix login", feedback=["  some note"])
        b = TaskLine(" ", "Fix login")
        assert a == b  # feedback ignored for equality
