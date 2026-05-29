import unittest
from pathlib import Path

from pycodex.core.compact import (
    COMPACT_USER_MESSAGE_MAX_TOKENS,
    SUMMARY_PREFIX,
    SUMMARIZATION_PROMPT,
    build_compacted_history,
    build_compacted_history_with_limit,
    collect_user_messages,
    content_items_to_text,
    insert_initial_context_before_last_real_user_or_summary,
    is_summary_message,
    should_use_remote_compact_task,
)
from pycodex.protocol import DEFAULT_IMAGE_DETAIL, ContentItem, ResponseItem


def user_message(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def developer_message(text: str) -> ResponseItem:
    return ResponseItem.message("developer", (ContentItem.input_text(text),))


class Provider:
    def __init__(self, supported: bool) -> None:
        self.supported = supported

    def supports_remote_compaction(self) -> bool:
        return self.supported


class CompactTests(unittest.TestCase):
    def test_template_constants_match_rust_include_files(self) -> None:
        root = Path(__file__).resolve().parents[1] / "codex" / "codex-rs" / "core"

        self.assertEqual(SUMMARIZATION_PROMPT, (root / "templates/compact/prompt.md").read_text(encoding="utf-8"))
        self.assertEqual(SUMMARY_PREFIX, (root / "templates/compact/summary_prefix.md").read_text(encoding="utf-8"))
        self.assertEqual(COMPACT_USER_MESSAGE_MAX_TOKENS, 20_000)

    def test_content_items_to_text_joins_non_empty_segments(self) -> None:
        joined = content_items_to_text(
            (
                ContentItem.input_text("hello"),
                ContentItem.output_text(""),
                ContentItem.output_text("world"),
            )
        )

        self.assertEqual(joined, "hello\nworld")

    def test_content_items_to_text_ignores_image_only_content(self) -> None:
        joined = content_items_to_text((ContentItem.input_image("file://image.png", DEFAULT_IMAGE_DETAIL),))

        self.assertIsNone(joined)

    def test_collect_user_messages_extracts_user_text_only(self) -> None:
        collected = collect_user_messages(
            (
                ResponseItem.message("assistant", (ContentItem.output_text("ignored"),), id="assistant"),
                user_message("first"),
                ResponseItem.other(),
            )
        )

        self.assertEqual(collected, ["first"])

    def test_collect_user_messages_filters_context_and_legacy_warnings(self) -> None:
        collected = collect_user_messages(
            (
                user_message(
                    "# AGENTS.md instructions for project\n\n<INSTRUCTIONS>\ndo things\n</INSTRUCTIONS>"
                ),
                user_message("<ENVIRONMENT_CONTEXT>cwd=/tmp</ENVIRONMENT_CONTEXT>"),
                user_message(
                    "Warning: The maximum number of unified exec processes you can keep open is 60 and you currently have 61 processes open. Reuse older processes or close them to prevent automatic pruning of old processes"
                ),
                user_message(
                    "Warning: apply_patch was requested via exec_command. Use the apply_patch tool instead of exec_command."
                ),
                user_message(
                    "Warning: Your account was flagged for potentially high-risk cyber activity and this request was routed to gpt-5.2 as a fallback. To regain access to gpt-5.3-codex, apply for trusted access: https://chatgpt.com/cyber or learn more: https://developers.openai.com/codex/concepts/cyber-safety"
                ),
                user_message("real user message"),
            )
        )

        self.assertEqual(collected, ["real user message"])

    def test_collect_user_messages_filters_compaction_summaries(self) -> None:
        self.assertTrue(is_summary_message(f"{SUMMARY_PREFIX}\nsummary text"))
        self.assertFalse(is_summary_message("summary text"))
        self.assertEqual(
            collect_user_messages((user_message(f"{SUMMARY_PREFIX}\nsummary text"), user_message("real"))),
            ["real"],
        )

    def test_build_compacted_history_appends_summary_message(self) -> None:
        history = build_compacted_history((), ("first user message",), "summary text")

        self.assertEqual(content_items_to_text(history[-1].content), "summary text")
        self.assertEqual(history[-1].role, "user")

    def test_build_compacted_history_uses_empty_summary_fallback(self) -> None:
        history = build_compacted_history((), (), "")

        self.assertEqual(content_items_to_text(history[-1].content), "(no summary available)")

    def test_build_token_limited_compacted_history_truncates_overlong_user_messages(self) -> None:
        big = "word " * 200
        history = build_compacted_history_with_limit((), (big,), "SUMMARY", 16)

        self.assertEqual(len(history), 2)
        truncated_text = content_items_to_text(history[0].content) or ""
        self.assertIn("tokens truncated", truncated_text)
        self.assertNotEqual(truncated_text, big)
        self.assertEqual(content_items_to_text(history[1].content), "SUMMARY")

    def test_insert_initial_context_before_last_real_user_or_summary_prefers_real_user(self) -> None:
        history = (
            user_message("older user"),
            user_message(f"{SUMMARY_PREFIX}\nsummary text"),
            user_message("latest user"),
        )
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary(history, context)

        self.assertEqual(
            refreshed,
            [
                user_message("older user"),
                user_message(f"{SUMMARY_PREFIX}\nsummary text"),
                developer_message("fresh permissions"),
                user_message("latest user"),
            ],
        )

    def test_insert_initial_context_before_summary_when_no_real_user(self) -> None:
        summary = user_message(f"{SUMMARY_PREFIX}\nsummary text")
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary((summary,), context)

        self.assertEqual(refreshed, [developer_message("fresh permissions"), summary])

    def test_insert_initial_context_before_compaction_when_no_user_message(self) -> None:
        compaction = ResponseItem.compaction("encrypted")
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary((compaction,), context)

        self.assertEqual(refreshed, [developer_message("fresh permissions"), compaction])

    def test_insert_initial_context_appends_when_no_anchor(self) -> None:
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary((), context)

        self.assertEqual(refreshed, [developer_message("fresh permissions")])

    def test_should_use_remote_compact_task_delegates_to_provider(self) -> None:
        self.assertTrue(should_use_remote_compact_task(Provider(True)))
        self.assertFalse(should_use_remote_compact_task(Provider(False)))
        with self.assertRaisesRegex(TypeError, "supports_remote_compaction"):
            should_use_remote_compact_task(object())


if __name__ == "__main__":
    unittest.main()
