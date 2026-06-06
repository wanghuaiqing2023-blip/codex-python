from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from pycodex.core.context import UserInstructions
from pycodex.core import (
    MAX_ASK_CHARS as CORE_MAX_ASK_CHARS,
    MAX_CURRENT_CWD_ASKS as CORE_MAX_CURRENT_CWD_ASKS,
    MAX_OTHER_CWD_ASKS as CORE_MAX_OTHER_CWD_ASKS,
    MAX_RECENT_WORK_GROUPS as CORE_MAX_RECENT_WORK_GROUPS,
    build_realtime_startup_context as core_build_realtime_startup_context,
)
from pycodex.core.realtime_context import (
    CURRENT_THREAD_SECTION_TOKEN_BUDGET,
    MAX_ASK_CHARS,
    MAX_CURRENT_CWD_ASKS,
    MAX_OTHER_CWD_ASKS,
    MAX_RECENT_WORK_GROUPS,
    STARTUP_CONTEXT_HEADER,
    WORKSPACE_SECTION_TOKEN_BUDGET,
    build_current_thread_section,
    build_recent_work_section,
    build_realtime_startup_context,
    build_workspace_section_with_user_root,
    format_section,
    format_startup_context_blob,
    render_tree,
    truncate_realtime_text_to_token_budget,
)
from pycodex.utils.string import approx_token_count
from pycodex.protocol import ContentItem, ResponseItem


def user_message(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def assistant_message(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def long_turn_text(index: int) -> str:
    return (
        f"turn-{index}-start "
        + "head filler " * 160
        + f"turn-{index}-middle "
        + "tail filler " * 240
        + f"turn-{index}-end"
    )


class RealtimeContextTests(unittest.TestCase):
    def test_recent_work_constants_match_rust_module_contract(self) -> None:
        # Rust source: realtime_context.rs recent-work constants.
        self.assertEqual(MAX_RECENT_WORK_GROUPS, 8)
        self.assertEqual(MAX_CURRENT_CWD_ASKS, 8)
        self.assertEqual(MAX_OTHER_CWD_ASKS, 5)
        self.assertEqual(MAX_ASK_CHARS, 240)
        self.assertEqual(CORE_MAX_RECENT_WORK_GROUPS, MAX_RECENT_WORK_GROUPS)
        self.assertEqual(CORE_MAX_CURRENT_CWD_ASKS, MAX_CURRENT_CWD_ASKS)
        self.assertEqual(CORE_MAX_OTHER_CWD_ASKS, MAX_OTHER_CWD_ASKS)
        self.assertEqual(CORE_MAX_ASK_CHARS, MAX_ASK_CHARS)
        self.assertIs(core_build_realtime_startup_context, build_realtime_startup_context)

    def test_current_thread_section_includes_short_turns_newest_first(self) -> None:
        items = [
            user_message("user turn 1"),
            assistant_message("assistant turn 1"),
            user_message("user turn 2"),
            assistant_message("assistant turn 2"),
        ]

        self.assertEqual(
            build_current_thread_section(items),
            "Most recent user/assistant turns from this exact thread. Use them for continuity when responding.\n\n"
            "### Latest turn\n"
            "User:\n"
            "user turn 2\n\n"
            "Assistant:\n"
            "assistant turn 2\n\n"
            "### Previous turn 1\n"
            "User:\n"
            "user turn 1\n\n"
            "Assistant:\n"
            "assistant turn 1",
        )

    def test_current_thread_section_includes_short_turns_newest_first_until_budget(self) -> None:
        # Rust test: current_thread_section_includes_short_turns_newest_first_until_budget
        items = [
            user_message("user turn 1"),
            assistant_message("assistant turn 1"),
            user_message("user turn 2"),
            assistant_message("assistant turn 2"),
            user_message("user turn 3"),
            assistant_message("assistant turn 3"),
            user_message("user turn 4"),
            assistant_message("assistant turn 4"),
        ]

        self.assertEqual(
            build_current_thread_section(items),
            "Most recent user/assistant turns from this exact thread. Use them for continuity when responding.\n\n"
            "### Latest turn\n"
            "User:\n"
            "user turn 4\n\n"
            "Assistant:\n"
            "assistant turn 4\n\n"
            "### Previous turn 1\n"
            "User:\n"
            "user turn 3\n\n"
            "Assistant:\n"
            "assistant turn 3\n\n"
            "### Previous turn 2\n"
            "User:\n"
            "user turn 2\n\n"
            "Assistant:\n"
            "assistant turn 2\n\n"
            "### Previous turn 3\n"
            "User:\n"
            "user turn 1\n\n"
            "Assistant:\n"
            "assistant turn 1",
        )

    def test_current_thread_section_ignores_contextual_user_fragments(self) -> None:
        contextual = UserInstructions("/repo", "prefer stdlib").into_response_item()
        self.assertEqual(
            build_current_thread_section((contextual, user_message("real ask"))),
            "Most recent user/assistant turns from this exact thread. Use them for continuity when responding.\n\n"
            "### Latest turn\n"
            "User:\n"
            "real ask",
        )

    def test_current_thread_turn_truncation_preserves_start_and_end(self) -> None:
        section = build_current_thread_section((user_message(long_turn_text(0)),))
        self.assertIsNotNone(section)
        assert section is not None
        self.assertIn("turn-0-start", section)
        self.assertNotIn("turn-0-middle", section)
        self.assertIn("turn-0-end", section)
        self.assertIn("tokens truncated", section)

    def test_current_thread_section_keeps_latest_turns_when_history_exceeds_budget(self) -> None:
        # Rust test: current_thread_section_keeps_latest_turns_when_history_exceeds_budget
        items: list[ResponseItem] = []
        for index in range(1, 9):
            items.append(user_message(long_turn_text(index)))
            items.append(assistant_message(f"assistant turn {index}"))

        section = build_current_thread_section(items)

        self.assertIsNotNone(section)
        assert section is not None
        self.assertIn("turn-8-start", section)
        self.assertIn("turn-8-end", section)
        self.assertIn("### Previous turn 2", section)
        self.assertNotIn("turn-1-start", section)
        self.assertNotIn("turn-1-end", section)

    def test_truncate_realtime_text_to_token_budget_fits_budget(self) -> None:
        truncated = truncate_realtime_text_to_token_budget("alpha " * 400 + "omega", 24)
        self.assertLessEqual(approx_token_count(truncated), 24)
        self.assertIn("tokens truncated", truncated)

    def test_startup_context_blob_and_sections_are_wrapped(self) -> None:
        body = [
            STARTUP_CONTEXT_HEADER,
            format_section("Current Thread", "current thread " * 2000, CURRENT_THREAD_SECTION_TOKEN_BUDGET),
            format_section("Machine / Workspace Map", "workspace map " * 2500, WORKSPACE_SECTION_TOKEN_BUDGET),
        ]
        joined = "\n\n".join(part for part in body if part is not None)

        wrapped = format_startup_context_blob(joined)

        self.assertTrue(wrapped.startswith("<startup_context>\n"))
        self.assertTrue(wrapped.endswith("\n</startup_context>"))
        self.assertIn("## Current Thread", wrapped)
        self.assertIn("tokens truncated", wrapped)

    def test_fixed_section_budgets_apply_without_total_blob_truncation(self) -> None:
        # Rust test: fixed_section_budgets_apply_per_section_without_total_blob_truncation
        body = [
            STARTUP_CONTEXT_HEADER,
            format_section("Current Thread", "current thread " * 2_000, CURRENT_THREAD_SECTION_TOKEN_BUDGET),
            format_section("Recent Work", "recent work " * 3_000, 2_200),
            format_section("Machine / Workspace Map", "workspace map " * 2_500, WORKSPACE_SECTION_TOKEN_BUDGET),
            format_section("Notes", "notes " * 500, 300),
        ]

        wrapped = format_startup_context_blob("\n\n".join(part for part in body if part is not None))

        self.assertTrue(wrapped.startswith("<startup_context>\n"))
        self.assertTrue(wrapped.endswith("\n</startup_context>"))
        self.assertIn("tokens truncated", wrapped)
        self.assertIn("## Current Thread", wrapped)
        self.assertIn("## Recent Work", wrapped)
        self.assertIn("## Machine / Workspace Map", wrapped)
        self.assertIn("## Notes", wrapped)

    def test_format_section_skips_missing_empty_or_budgetless_body_like_rust(self) -> None:
        # Rust source: format_section returns None for absent, blank, or budgetless section bodies.
        self.assertIsNone(format_section("Empty", None, 100))
        self.assertIsNone(format_section("Empty", "   \n\t", 100))
        self.assertIsNone(format_section("No Budget", "body", 1))

    def test_workspace_section_requires_meaningful_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(build_workspace_section_with_user_root(Path(tmpdir)))

    def test_workspace_section_includes_tree_when_entries_exist(self) -> None:
        # Rust test: workspace_section_includes_tree_when_entries_exist
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            (cwd / "docs").mkdir()
            (cwd / "README.md").write_text("hello", encoding="utf-8")

            section = build_workspace_section_with_user_root(cwd)

            self.assertIsNotNone(section)
            assert section is not None
            self.assertIn("Working directory tree:", section)
            self.assertIn("- docs/", section)
            self.assertIn("- README.md", section)

    def test_render_tree_sorts_dirs_first_and_filters_noisy_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text("hello", encoding="utf-8")
            (root / "README.md").write_text("hello", encoding="utf-8")
            (root / ".git").mkdir()
            (root / "node_modules").mkdir()

            self.assertEqual(render_tree(root), ["- docs/", "  - guide.md", "- README.md"])

    def test_render_tree_limits_entries_and_reports_remaining_count(self) -> None:
        # Rust source: collect_tree_lines applies DIR_ENTRY_LIMIT and appends a remaining-entry marker.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for index in range(22):
                (root / f"file-{index:02}.txt").write_text("hello", encoding="utf-8")

            tree = render_tree(root)

            self.assertIsNotNone(tree)
            assert tree is not None
            self.assertEqual(len(tree), 21)
            self.assertEqual(tree[-1], "- ... 2 more entries")
            self.assertIn("- file-00.txt", tree)
            self.assertIn("- file-19.txt", tree)
            self.assertNotIn("- file-20.txt", tree)

    def test_render_tree_stops_at_rust_max_depth(self) -> None:
        # Rust source: collect_tree_lines stops when depth >= TREE_MAX_DEPTH.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "docs" / "deep"
            nested.mkdir(parents=True)
            (nested / "hidden.md").write_text("hello", encoding="utf-8")

            tree = render_tree(root)

            self.assertEqual(tree, ["- docs/", "  - deep/"])

    def test_workspace_section_includes_user_root_tree_when_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cwd = root / "cwd"
            user_root = root / "home"
            (cwd / "docs").mkdir(parents=True)
            (cwd / "README.md").write_text("hello", encoding="utf-8")
            (user_root / "code").mkdir(parents=True)
            (user_root / ".zshrc").write_text("export TEST=1", encoding="utf-8")

            section = build_workspace_section_with_user_root(cwd, user_root)

            self.assertIsNotNone(section)
            assert section is not None
            self.assertIn("Working directory tree:", section)
            self.assertIn("- docs/", section)
            self.assertIn("- README.md", section)
            self.assertIn("User root tree:", section)
            self.assertIn("- code/", section)
            self.assertNotIn(".zshrc", section)

    def test_recent_work_section_groups_threads_by_cwd(self) -> None:
        # Rust test: recent_work_section_groups_threads_by_cwd
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "repo"
            workspace_a = repo / "workspace-a"
            workspace_b = repo / "workspace-b"
            outside = root / "outside"
            (repo / ".git").mkdir(parents=True)
            workspace_a.mkdir()
            workspace_b.mkdir()
            outside.mkdir()
            recent_threads = [
                SimpleNamespace(
                    cwd=workspace_a,
                    updated_at=3,
                    git_info=SimpleNamespace(branch="main"),
                    first_user_message="Log the startup context before sending it",
                ),
                SimpleNamespace(
                    cwd=workspace_b,
                    updated_at=2,
                    git_info=SimpleNamespace(branch="feature"),
                    first_user_message="Remove memories from the realtime startup context",
                ),
                SimpleNamespace(
                    cwd=outside,
                    updated_at=1,
                    git_info=None,
                    first_user_message="Inspect flaky test",
                ),
            ]

            section = build_recent_work_section(workspace_a, recent_threads)

            self.assertIsNotNone(section)
            assert section is not None
            self.assertIn(f"### Git repo: {repo}", section)
            self.assertIn("Recent sessions: 2", section)
            self.assertIn("User asks:", section)
            self.assertIn(f"- {workspace_a}: Log the startup context before sending it", section)
            self.assertIn(f"### Directory: {outside}", section)
            self.assertIn(f"- {outside}: Inspect flaky test", section)

    def test_recent_work_section_dedupes_skips_and_truncates_user_asks(self) -> None:
        # Rust source: format_thread_group normalizes whitespace, dedupes by cwd+ask,
        # skips empty asks, truncates long asks, and caps other-cwd asks at five.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current = root / "current"
            other = root / "other"
            current.mkdir()
            other.mkdir()
            long_ask = "x" * 260
            recent_threads = [
                SimpleNamespace(cwd=other, updated_at=10, git_info=None, first_user_message="  repeated\n\nask  "),
                SimpleNamespace(cwd=other, updated_at=9, git_info=None, first_user_message="repeated ask"),
                SimpleNamespace(cwd=other, updated_at=8, git_info=None, first_user_message=""),
                SimpleNamespace(cwd=other, updated_at=7, git_info=None, first_user_message=long_ask),
                SimpleNamespace(cwd=other, updated_at=6, git_info=None, first_user_message="ask 3"),
                SimpleNamespace(cwd=other, updated_at=5, git_info=None, first_user_message="ask 4"),
                SimpleNamespace(cwd=other, updated_at=4, git_info=None, first_user_message="ask 5"),
                SimpleNamespace(cwd=other, updated_at=3, git_info=None, first_user_message="ask 6"),
            ]

            section = build_recent_work_section(current, recent_threads)

            self.assertIsNotNone(section)
            assert section is not None
            self.assertEqual(section.count(f"- {other}: repeated ask"), 1)
            self.assertIn(f"- {other}: {'x' * 237}...", section)
            self.assertIn(f"- {other}: ask 5", section)
            self.assertNotIn(f"- {other}: ask 6", section)

    def test_recent_work_section_prioritizes_current_group_before_newer_other_groups(self) -> None:
        # Rust source: build_recent_work_section sorts current_group before newer other groups.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current = root / "current"
            other = root / "other"
            current.mkdir()
            other.mkdir()
            recent_threads = [
                SimpleNamespace(
                    cwd=other,
                    updated_at=99,
                    git_info=None,
                    first_user_message="newer other work",
                ),
                SimpleNamespace(
                    cwd=current,
                    updated_at=1,
                    git_info=None,
                    first_user_message="older current work",
                ),
            ]

            section = build_recent_work_section(current, recent_threads)

            self.assertIsNotNone(section)
            assert section is not None
            self.assertLess(section.index(f"### Directory: {current}"), section.index(f"### Directory: {other}"))
            self.assertLess(section.index("older current work"), section.index("newer other work"))

    def test_recent_work_section_caps_current_group_user_asks_at_eight(self) -> None:
        # Rust source: format_thread_group uses MAX_CURRENT_CWD_ASKS for current_group.
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir)
            recent_threads = [
                SimpleNamespace(
                    cwd=current,
                    updated_at=20 - index,
                    git_info=None,
                    first_user_message=f"current ask {index}",
                )
                for index in range(1, 10)
            ]

            section = build_recent_work_section(current, recent_threads)

            self.assertIsNotNone(section)
            assert section is not None
            self.assertIn(f"- {current}: current ask 8", section)
            self.assertNotIn(f"- {current}: current ask 9", section)

    def test_recent_work_section_limits_rendered_groups(self) -> None:
        # Rust source: build_recent_work_section takes MAX_RECENT_WORK_GROUPS groups.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current = root / "current"
            current.mkdir()
            recent_threads = []
            for index in range(10):
                cwd = root / f"project-{index}"
                cwd.mkdir()
                recent_threads.append(
                    SimpleNamespace(
                        cwd=cwd,
                        updated_at=100 - index,
                        git_info=None,
                        first_user_message=f"ask {index}",
                    )
                )

            section = build_recent_work_section(current, recent_threads)

            self.assertIsNotNone(section)
            assert section is not None
            self.assertEqual(section.count("### Directory:"), MAX_RECENT_WORK_GROUPS)
            self.assertIn(f"### Directory: {root / 'project-7'}", section)
            self.assertNotIn(f"### Directory: {root / 'project-8'}", section)

    def test_realtime_startup_context_combines_sections_in_rust_order(self) -> None:
        # Rust source: build_realtime_startup_context
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cwd = root / "repo"
            (cwd / ".git").mkdir(parents=True)
            (cwd / "README.md").write_text("hello", encoding="utf-8")
            recent_threads = [
                SimpleNamespace(
                    cwd=cwd,
                    updated_at=1,
                    git_info=SimpleNamespace(branch="main"),
                    first_user_message="Continue the realtime context port",
                )
            ]

            context = build_realtime_startup_context(
                current_thread_items=(user_message("current ask"), assistant_message("current answer")),
                recent_threads=recent_threads,
                cwd=cwd,
                user_root=None,
                budget_tokens=1,
            )

            self.assertIsNotNone(context)
            assert context is not None
            self.assertTrue(context.startswith("<startup_context>\n"))
            self.assertTrue(context.endswith("\n</startup_context>"))
            self.assertLess(context.index(STARTUP_CONTEXT_HEADER), context.index("## Current Thread"))
            self.assertLess(context.index("## Current Thread"), context.index("## Recent Work"))
            self.assertLess(context.index("## Recent Work"), context.index("## Machine / Workspace Map"))
            self.assertLess(context.index("## Machine / Workspace Map"), context.index("## Notes"))
            self.assertIn("current ask", context)
            self.assertIn("Continue the realtime context port", context)


if __name__ == "__main__":
    unittest.main()
