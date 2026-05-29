import json
import unittest

from pycodex.core.compact import InitialContextInjection, SUMMARY_PREFIX
from pycodex.core.compact_remote import (
    build_compact_request_log_data,
    estimate_response_item_model_visible_bytes,
    is_codex_generated_item,
    process_compacted_history,
    should_keep_compacted_history_item,
    trim_function_call_history_to_fit_context_window,
)
from pycodex.protocol import ContentItem, ResponseItem


def user_message(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def developer_message(text: str) -> ResponseItem:
    return ResponseItem.message("developer", (ContentItem.input_text(text),))


def assistant_message(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


class CompactRemoteTests(unittest.TestCase):
    def test_should_keep_compacted_history_item_filters_roles_and_kinds(self) -> None:
        self.assertFalse(should_keep_compacted_history_item(developer_message("rules")))
        self.assertFalse(
            should_keep_compacted_history_item(
                user_message("<ENVIRONMENT_CONTEXT>cwd=/tmp</ENVIRONMENT_CONTEXT>")
            )
        )
        self.assertTrue(should_keep_compacted_history_item(user_message("hello")))
        self.assertTrue(
            should_keep_compacted_history_item(
                user_message(f"{SUMMARY_PREFIX} previous work")
            )
        )
        self.assertTrue(should_keep_compacted_history_item(assistant_message("reply")))
        self.assertTrue(should_keep_compacted_history_item(ResponseItem.compaction("enc")))
        self.assertTrue(should_keep_compacted_history_item(ResponseItem.context_compaction()))
        self.assertFalse(should_keep_compacted_history_item(ResponseItem.compaction_trigger()))
        self.assertFalse(should_keep_compacted_history_item(ResponseItem.other()))

    def test_process_compacted_history_filters_and_injects_before_last_user(self) -> None:
        old_user = user_message("older")
        assistant = assistant_message("answer")
        summary = user_message(f"{SUMMARY_PREFIX} older summary")
        latest_user = user_message("latest")
        refreshed_context = developer_message("fresh rules")

        processed = process_compacted_history(
            (
                developer_message("stale rules"),
                old_user,
                user_message("<ENVIRONMENT_CONTEXT>cwd=/tmp</ENVIRONMENT_CONTEXT>"),
                assistant,
                summary,
                ResponseItem.compaction_trigger(),
                latest_user,
            ),
            InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
            (refreshed_context,),
        )

        self.assertEqual(processed, [old_user, assistant, summary, refreshed_context, latest_user])

    def test_process_compacted_history_can_skip_initial_context_injection(self) -> None:
        kept = user_message("hello")
        refreshed_context = developer_message("fresh rules")

        processed = process_compacted_history(
            (developer_message("stale"), kept),
            InitialContextInjection.DO_NOT_INJECT,
            (refreshed_context,),
        )

        self.assertEqual(processed, [kept])

    def test_build_compact_request_log_data_counts_instruction_bytes_and_items(self) -> None:
        first = user_message("one")
        second = assistant_message("two")

        log_data = build_compact_request_log_data(
            (first, second),
            "\u00e9",
            estimate_item_bytes=lambda item: 5 if item is first else 7,
        )

        self.assertEqual(log_data.failing_compaction_request_model_visible_bytes, 14)

    def test_estimate_response_item_model_visible_bytes_uses_json_mapping_bytes(self) -> None:
        item = user_message("\u00e9")
        expected = len(
            json.dumps(
                item.to_mapping(),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )

        self.assertEqual(estimate_response_item_model_visible_bytes(item), expected)

    def test_is_codex_generated_item_matches_remote_compact_trim_boundary(self) -> None:
        self.assertTrue(is_codex_generated_item(developer_message("rules")))
        self.assertTrue(
            is_codex_generated_item(
                ResponseItem.from_mapping(
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "ok",
                    }
                )
            )
        )
        self.assertFalse(is_codex_generated_item(user_message("hello")))
        self.assertFalse(
            is_codex_generated_item(
                ResponseItem.from_mapping(
                    {
                        "type": "function_call",
                        "name": "tool",
                        "arguments": "{}",
                        "call_id": "call-1",
                    }
                )
            )
        )

    def test_trim_function_call_history_removes_codex_generated_tail_until_under_window(self) -> None:
        user = user_message("hello")
        call = ResponseItem.from_mapping(
            {
                "type": "function_call",
                "name": "tool",
                "arguments": "{}",
                "call_id": "call-1",
            }
        )
        output = ResponseItem.from_mapping(
            {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": "ok",
            }
        )
        estimates = [12, 5]

        result = trim_function_call_history_to_fit_context_window(
            (user, call, output),
            10,
            "instructions",
            lambda items, base: estimates.pop(0),
        )

        self.assertEqual(result.deleted_items, 1)
        self.assertEqual(result.items, (user,))

    def test_trim_function_call_history_stops_at_non_codex_tail(self) -> None:
        user = user_message("hello")
        result = trim_function_call_history_to_fit_context_window(
            (developer_message("rules"), user),
            1,
            "instructions",
            lambda items, base: 99,
        )

        self.assertEqual(result.deleted_items, 0)
        self.assertEqual(result.items, (developer_message("rules"), user))

    def test_trim_function_call_history_returns_unchanged_without_context_window(self) -> None:
        history = (developer_message("rules"),)

        result = trim_function_call_history_to_fit_context_window(
            history,
            None,
            "instructions",
            lambda items, base: 99,
        )

        self.assertEqual(result.deleted_items, 0)
        self.assertEqual(result.items, history)


if __name__ == "__main__":
    unittest.main()
