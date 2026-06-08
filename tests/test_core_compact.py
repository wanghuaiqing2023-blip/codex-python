import unittest
from pathlib import Path

from pycodex.core.compact import (
    COMPACT_USER_MESSAGE_MAX_TOKENS,
    SUMMARY_PREFIX,
    SUMMARIZATION_PROMPT,
    CompactionStatus,
    build_compacted_history,
    build_compacted_history_with_limit,
    collect_user_messages,
    compaction_status_from_result,
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


class CodexLikeError(RuntimeError):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class CompactTests(unittest.TestCase):
    def test_template_constants_match_rust_include_files(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Behavior anchor: SUMMARIZATION_PROMPT, SUMMARY_PREFIX, and
        # COMPACT_USER_MESSAGE_MAX_TOKENS are direct module constants.
        root = Path(__file__).resolve().parents[1] / "codex" / "codex-rs" / "core"

        self.assertEqual(SUMMARIZATION_PROMPT, (root / "templates/compact/prompt.md").read_text(encoding="utf-8"))
        self.assertEqual(SUMMARY_PREFIX, (root / "templates/compact/summary_prefix.md").read_text(encoding="utf-8"))
        self.assertEqual(COMPACT_USER_MESSAGE_MAX_TOKENS, 20_000)

    def test_content_items_to_text_joins_non_empty_segments(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: content_items_to_text_joins_non_empty_segments.
        # Behavior anchor: non-empty input/output text segments join with newlines.
        joined = content_items_to_text(
            (
                ContentItem.input_text("hello"),
                ContentItem.output_text(""),
                ContentItem.output_text("world"),
            )
        )

        self.assertEqual(joined, "hello\nworld")

    def test_content_items_to_text_ignores_image_only_content(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: content_items_to_text_ignores_image_only_content.
        # Behavior anchor: image-only content has no textual compaction input.
        joined = content_items_to_text((ContentItem.input_image("file://image.png", DEFAULT_IMAGE_DETAIL),))

        self.assertIsNone(joined)

    def test_collect_user_messages_extracts_user_text_only(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: collect_user_messages_extracts_user_text_only.
        # Behavior anchor: only parsed user-message text contributes to compaction input.
        collected = collect_user_messages(
            (
                ResponseItem.message("assistant", (ContentItem.output_text("ignored"),), id="assistant"),
                user_message("first"),
                ResponseItem.other(),
            )
        )

        self.assertEqual(collected, ["first"])

    def test_collect_user_messages_filters_context_and_legacy_warnings(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust tests: collect_user_messages_filters_session_prefix_entries and
        # collect_user_messages_filters_legacy_warnings.
        # Behavior anchor: session/context fragments and legacy warning user messages
        # are excluded from compaction user-message collection.
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
        # Rust source: codex-rs/core/src/compact.rs
        # Behavior anchor: collect_user_messages excludes messages starting with
        # the exact SUMMARY_PREFIX plus newline marker.
        self.assertTrue(is_summary_message(f"{SUMMARY_PREFIX}\nsummary text"))
        self.assertFalse(is_summary_message("summary text"))
        self.assertEqual(
            collect_user_messages((user_message(f"{SUMMARY_PREFIX}\nsummary text"), user_message("real"))),
            ["real"],
        )

    def test_build_compacted_history_appends_summary_message(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: build_token_limited_compacted_history_appends_summary_message.
        # Behavior anchor: build_compacted_history appends the summary as the final user message.
        history = build_compacted_history((), ("first user message",), "summary text")

        self.assertEqual(content_items_to_text(history[-1].content), "summary text")
        self.assertEqual(history[-1].role, "user")

    def test_build_compacted_history_uses_empty_summary_fallback(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Behavior anchor: an empty summary body becomes "(no summary available)".
        history = build_compacted_history((), (), "")

        self.assertEqual(content_items_to_text(history[-1].content), "(no summary available)")

    def test_build_compacted_history_preserves_initial_context_before_user_messages(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs::build_compacted_history_with_limit.
        # Behavior anchor: initial context is retained before selected user messages and summary.
        context = (developer_message("fresh permissions"),)

        history = build_compacted_history(context, ("first user message",), "SUMMARY")

        self.assertEqual(history[0], developer_message("fresh permissions"))
        self.assertEqual(content_items_to_text(history[1].content), "first user message")
        self.assertEqual(content_items_to_text(history[2].content), "SUMMARY")

    def test_build_compacted_history_zero_token_budget_keeps_only_summary_after_context(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs::build_compacted_history_with_limit.
        # Behavior anchor: max_tokens=0 skips user messages and still appends summary.
        context = (developer_message("fresh permissions"),)

        history = build_compacted_history_with_limit(context, ("first", "second"), "SUMMARY", 0)

        self.assertEqual(history, [developer_message("fresh permissions"), user_message("SUMMARY")])

    def test_build_token_limited_compacted_history_truncates_overlong_user_messages(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: build_token_limited_compacted_history_truncates_overlong_user_messages.
        # Behavior anchor: over-budget user messages are token-truncated before the summary.
        big = "word " * 200
        history = build_compacted_history_with_limit((), (big,), "SUMMARY", 16)

        self.assertEqual(len(history), 2)
        truncated_text = content_items_to_text(history[0].content) or ""
        self.assertIn("tokens truncated", truncated_text)
        self.assertNotEqual(truncated_text, big)
        self.assertEqual(content_items_to_text(history[1].content), "SUMMARY")

    def test_insert_initial_context_before_last_real_user_or_summary_keeps_summary_last(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: insert_initial_context_before_last_real_user_or_summary_keeps_summary_last.
        # Behavior anchor: canonical context is inserted before the last real user
        # message, so a trailing summary remains the final item.
        history = (
            user_message("older user"),
            user_message("latest user"),
            user_message(f"{SUMMARY_PREFIX}\nsummary text"),
        )
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary(history, context)

        self.assertEqual(
            refreshed,
            [
                user_message("older user"),
                developer_message("fresh permissions"),
                user_message("latest user"),
                user_message(f"{SUMMARY_PREFIX}\nsummary text"),
            ],
        )

    def test_insert_initial_context_before_summary_when_no_real_user(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Behavior anchor: with no real user message, context is inserted before
        # the summary user message so the summary remains last.
        summary = user_message(f"{SUMMARY_PREFIX}\nsummary text")
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary((summary,), context)

        self.assertEqual(refreshed, [developer_message("fresh permissions"), summary])

    def test_insert_initial_context_before_compaction_when_no_user_message(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: insert_initial_context_before_last_real_user_or_summary_keeps_compaction_last.
        # Behavior anchor: with no user message, context is inserted before the
        # final compaction item so that compaction remains last.
        compaction = ResponseItem.compaction("encrypted")
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary((compaction,), context)

        self.assertEqual(refreshed, [developer_message("fresh permissions"), compaction])

    def test_insert_initial_context_appends_when_no_anchor(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Behavior anchor: if there is no user/summary/compaction anchor, context appends.
        context = (developer_message("fresh permissions"),)

        refreshed = insert_initial_context_before_last_real_user_or_summary((), context)

        self.assertEqual(refreshed, [developer_message("fresh permissions")])

    def test_should_use_remote_compact_task_delegates_to_provider(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Rust test: should_use_remote_compact_task_for_azure_provider.
        # Behavior anchor: provider capability decides whether remote compact task is used.
        self.assertTrue(should_use_remote_compact_task(Provider(True)))
        self.assertFalse(should_use_remote_compact_task(Provider(False)))
        with self.assertRaisesRegex(TypeError, "supports_remote_compaction"):
            should_use_remote_compact_task(object())

    def test_compaction_status_from_result_matches_rust_error_buckets(self) -> None:
        # Rust source: codex-rs/core/src/compact.rs
        # Behavior anchor: compaction_status_from_result maps Ok(_) to
        # completed, Interrupted/TurnAborted errors to interrupted, and all
        # other errors to failed.
        self.assertEqual(compaction_status_from_result(object()), CompactionStatus.COMPLETED)
        self.assertEqual(
            compaction_status_from_result(CodexLikeError("interrupted")),
            CompactionStatus.INTERRUPTED,
        )
        self.assertEqual(
            compaction_status_from_result(CodexLikeError("turn_aborted")),
            CompactionStatus.INTERRUPTED,
        )
        self.assertEqual(compaction_status_from_result(RuntimeError("stream failed")), CompactionStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
