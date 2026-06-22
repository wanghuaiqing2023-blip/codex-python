import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from pycodex.cloud_tasks import (
    AttemptDiffData,
    ApplyResultLevel,
    EnvironmentRow,
    collect_attempt_diffs,
    format_relative_time,
    format_task_list_lines,
    format_task_status_lines,
    level_from_status,
    parse_task_id,
    resolve_environment_id_from_rows,
    resolve_git_ref_with_git_info,
    resolve_query_input,
    select_attempt,
    summary_line,
    task_url,
)
from pycodex.cloud_tasks_client import (
    ApplyStatus,
    DiffSummary,
    TaskId,
    TaskStatus,
    TaskSummary,
)
from pycodex.cloud_tasks_mock_client import MockClient


class StubGitInfo:
    def __init__(self, default_branch=None, current_branch=None):
        self.default_branch = default_branch
        self.current_branch = current_branch

    async def default_branch_name(self):
        return self.default_branch

    async def current_branch_name(self):
        return self.current_branch


def test_resolve_git_ref_with_git_info_matches_branch_fallback_tests():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_git_ref_with_git_info.
    assert (
        asyncio.run(
            resolve_git_ref_with_git_info(
                "feature/override", StubGitInfo(None, None)
            )
        )
        == "feature/override"
    )
    assert (
        asyncio.run(
            resolve_git_ref_with_git_info(
                "  feature/spaces  ", StubGitInfo(None, None)
            )
        )
        == "feature/spaces"
    )
    assert (
        asyncio.run(
            resolve_git_ref_with_git_info(
                None, StubGitInfo("default-main", "feature/current")
            )
        )
        == "feature/current"
    )
    assert (
        asyncio.run(resolve_git_ref_with_git_info(None, StubGitInfo(None, "develop")))
        == "develop"
    )
    assert (
        asyncio.run(resolve_git_ref_with_git_info(None, StubGitInfo(None, None)))
        == "main"
    )


def test_parse_task_id_from_url_and_raw():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::parse_task_id_from_url_and_raw.
    assert parse_task_id("task_i_abc123").value == "task_i_abc123"
    assert (
        parse_task_id("https://chatgpt.com/codex/tasks/task_i_123456?foo=bar").value
        == "task_i_123456"
    )
    assert parse_task_id(" https://chatgpt.com/codex/tasks/T-1000#frag ").value == "T-1000"
    with pytest.raises(ValueError, match="^task id must not be empty$"):
        parse_task_id("   ")
    with pytest.raises(ValueError, match="^task id must not be empty$"):
        parse_task_id("https://chatgpt.com/codex/tasks/")


def test_resolve_environment_id_from_rows_matches_source_contract():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_environment_id.
    rows = [
        EnvironmentRow(id="env-1", label="Prod", is_pinned=False),
        EnvironmentRow(id="env-2", label="Staging", is_pinned=False),
    ]

    assert resolve_environment_id_from_rows(" env-1 ", rows) == "env-1"
    assert resolve_environment_id_from_rows("prod", rows) == "env-1"
    with pytest.raises(ValueError, match="^environment id must not be empty$"):
        resolve_environment_id_from_rows("   ", rows)
    with pytest.raises(
        ValueError, match="^no cloud environments are available for this workspace$"
    ):
        resolve_environment_id_from_rows("prod", [])
    with pytest.raises(
        ValueError,
        match=(
            "^environment 'missing' not found; "
            "run `codex cloud` to list available environments$"
        ),
    ):
        resolve_environment_id_from_rows("missing", rows)


def test_resolve_environment_id_label_ambiguity_rules():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_environment_id.
    same_id_rows = [
        EnvironmentRow(id="env-1", label="Prod", is_pinned=False),
        EnvironmentRow(id="env-1", label="prod", is_pinned=True),
    ]
    assert resolve_environment_id_from_rows("PROD", same_id_rows) == "env-1"

    ambiguous_rows = [
        EnvironmentRow(id="env-1", label="Prod", is_pinned=False),
        EnvironmentRow(id="env-2", label="prod", is_pinned=False),
    ]
    with pytest.raises(
        ValueError,
        match=(
            "^environment label 'Prod' is ambiguous; "
            "run `codex cloud` to pick the desired environment id$"
        ),
    ):
        resolve_environment_id_from_rows("Prod", ambiguous_rows)


def test_resolve_query_input_matches_argument_and_stdin_contracts():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_query_input.
    assert resolve_query_input("hello", stdin_text="ignored", stdin_is_terminal=True) == "hello"
    assert resolve_query_input("-", stdin_text="from stdin", stdin_is_terminal=True) == (
        "from stdin"
    )
    assert resolve_query_input(None, stdin_text="piped stdin", stdin_is_terminal=False) == (
        "piped stdin"
    )
    with pytest.raises(
        ValueError,
        match=(
            "^no query provided\\. Pass one as an argument or pipe it via stdin\\.$"
        ),
    ):
        resolve_query_input(None, stdin_text="", stdin_is_terminal=True)
    with pytest.raises(
        ValueError, match="^no query provided via stdin \\(received empty input\\)\\.$"
    ):
        resolve_query_input("-", stdin_text=" \n\t ", stdin_is_terminal=False)
    with pytest.raises(ValueError, match="^failed to read query from stdin: boom$"):
        resolve_query_input("-", read_error=OSError("boom"))


def test_level_from_status_maps_apply_status_to_modal_level():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::level_from_status.
    assert level_from_status(ApplyStatus.SUCCESS) is ApplyResultLevel.SUCCESS
    assert level_from_status(ApplyStatus.PARTIAL) is ApplyResultLevel.PARTIAL
    assert level_from_status(ApplyStatus.ERROR) is ApplyResultLevel.ERROR


def test_task_url_and_summary_line_contracts():
    # Rust crate/module: codex-cloud-tasks/src/util.rs::task_url and src/lib.rs::summary_line.
    assert (
        task_url("https://chatgpt.com/backend-api", "task_1")
        == "https://chatgpt.com/codex/tasks/task_1"
    )
    assert (
        task_url("https://example.test/api/codex", "task_1")
        == "https://example.test/codex/tasks/task_1"
    )
    assert task_url("https://example.test/codex", "task_1") == (
        "https://example.test/codex/tasks/task_1"
    )
    assert task_url("https://example.test/root", "task_1") == (
        "https://example.test/root/codex/tasks/task_1"
    )
    assert summary_line(DiffSummary()) == "no diff"
    assert summary_line(DiffSummary(files_changed=1, lines_added=5, lines_removed=2)) == (
        "+5/-2 \u2022 1 file"
    )
    assert summary_line(DiffSummary(files_changed=3, lines_added=5, lines_removed=2)) == (
        "+5/-2 \u2022 3 files"
    )


def test_format_relative_time_source_contracts():
    # Rust crate/module: codex-cloud-tasks/src/util.rs::format_relative_time.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    assert format_relative_time(now, now + timedelta(seconds=5)) == "0s ago"
    assert format_relative_time(now, now - timedelta(seconds=59)) == "59s ago"
    assert format_relative_time(now, now - timedelta(minutes=5)) == "5m ago"
    assert format_relative_time(now, now - timedelta(hours=3)) == "3h ago"


def test_format_task_status_lines_with_diff_and_label():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::format_task_status_lines_with_diff_and_label.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    task = TaskSummary(
        id=TaskId("task_1"),
        title="Example task",
        status=TaskStatus.READY,
        updated_at=now,
        environment_id="env-1",
        environment_label="Env",
        summary=DiffSummary(files_changed=3, lines_added=5, lines_removed=2),
        is_review=False,
        attempt_total=None,
    )

    assert format_task_status_lines(task, now, colorize=False) == [
        "[READY] Example task",
        "Env  \u2022  0s ago",
        "+5/-2 \u2022 3 files",
    ]


def test_format_task_status_lines_without_diff_falls_back():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::format_task_status_lines_without_diff_falls_back.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    task = TaskSummary(
        id=TaskId("task_2"),
        title="No diff task",
        status=TaskStatus.PENDING,
        updated_at=now,
        environment_id="env-2",
        environment_label=None,
        summary=DiffSummary(),
        is_review=False,
        attempt_total=1,
    )

    assert format_task_status_lines(task, now, colorize=False) == [
        "[PENDING] No diff task",
        "env-2  \u2022  0s ago",
        "no diff",
    ]


def test_format_task_list_lines_formats_urls():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::format_task_list_lines_formats_urls.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    tasks = [
        TaskSummary(
            id=TaskId("task_1"),
            title="Example task",
            status=TaskStatus.READY,
            updated_at=now,
            environment_id="env-1",
            environment_label="Env",
            summary=DiffSummary(files_changed=3, lines_added=5, lines_removed=2),
            is_review=False,
            attempt_total=None,
        ),
        TaskSummary(
            id=TaskId("task_2"),
            title="No diff task",
            status=TaskStatus.PENDING,
            updated_at=now,
            environment_id="env-2",
            environment_label=None,
            summary=DiffSummary(),
            is_review=False,
            attempt_total=1,
        ),
    ]

    assert format_task_list_lines(
        tasks,
        "https://chatgpt.com/backend-api",
        now,
        colorize=False,
    ) == [
        "https://chatgpt.com/codex/tasks/task_1",
        "  [READY] Example task",
        "  Env  \u2022  0s ago",
        "  +5/-2 \u2022 3 files",
        "",
        "https://chatgpt.com/codex/tasks/task_2",
        "  [PENDING] No diff task",
        "  env-2  \u2022  0s ago",
        "  no diff",
    ]


def test_collect_attempt_diffs_includes_sibling_attempts():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::collect_attempt_diffs_includes_sibling_attempts.
    task_id = parse_task_id("https://chatgpt.com/codex/tasks/T-1000")
    attempts = asyncio.run(collect_attempt_diffs(MockClient(), task_id))

    assert len(attempts) == 2
    assert attempts[0].placement == 0
    assert attempts[1].placement == 1
    assert attempts[0].diff
    assert attempts[1].diff


def test_select_attempt_validates_bounds():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::select_attempt_validates_bounds.
    attempts = [
        AttemptDiffData(
            placement=0,
            created_at=None,
            diff="diff --git a/file b/file\n",
        )
    ]
    assert select_attempt(attempts, 1).diff == "diff --git a/file b/file\n"
    assert select_attempt(attempts, None).diff == "diff --git a/file b/file\n"
    with pytest.raises(ValueError, match=r"^Attempt 2 not available; only 1 attempt\(s\) found$"):
        select_attempt(attempts, 2)
    with pytest.raises(ValueError, match="^attempt must be at least 1$"):
        select_attempt(attempts, 0)
    with pytest.raises(ValueError, match="^No attempts available$"):
        select_attempt([], 1)
