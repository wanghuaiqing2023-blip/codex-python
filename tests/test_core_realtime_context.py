from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pycodex.core.context import UserInstructions
from pycodex.core.realtime_context import (
    CURRENT_THREAD_SECTION_TOKEN_BUDGET,
    STARTUP_CONTEXT_HEADER,
    WORKSPACE_SECTION_TOKEN_BUDGET,
    build_current_thread_section,
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

    def test_workspace_section_requires_meaningful_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(build_workspace_section_with_user_root(Path(tmpdir)))

    def test_render_tree_sorts_dirs_first_and_filters_noisy_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text("hello", encoding="utf-8")
            (root / "README.md").write_text("hello", encoding="utf-8")
            (root / ".git").mkdir()
            (root / "node_modules").mkdir()

            self.assertEqual(render_tree(root), ["- docs/", "  - guide.md", "- README.md"])

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


if __name__ == "__main__":
    unittest.main()
