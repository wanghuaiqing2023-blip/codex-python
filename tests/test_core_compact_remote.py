import json
import unittest
from pathlib import Path

from pycodex.core.compact import InitialContextInjection, SUMMARY_PREFIX
from pycodex.core.compact_remote import (
    IMAGE_CONTENT_OMITTED_PLACEHOLDER,
    apply_remote_compaction_install_plan,
    build_compact_request_log_data,
    build_remote_compaction_install_plan,
    build_remote_compaction_success_plan,
    ensure_call_outputs_present,
    estimate_response_item_model_visible_bytes,
    is_codex_generated_item,
    normalize_call_outputs,
    normalize_history_for_prompt,
    process_compacted_history,
    remove_orphan_outputs,
    should_keep_compacted_history_item,
    strip_images_when_unsupported,
    trim_function_call_history_to_fit_context_window,
)
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.protocol import (
    AskForApproval,
    ContentItem,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ImageDetail,
    ResponseItem,
    SandboxPolicy,
    TurnContextItem,
)


def user_message(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def developer_message(text: str) -> ResponseItem:
    return ResponseItem.message("developer", (ContentItem.input_text(text),))


def assistant_message(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def function_call_output(call_id: str, output: str) -> ResponseItem:
    return ResponseItem.from_mapping({"type": "function_call_output", "call_id": call_id, "output": output})


def custom_tool_call_output(call_id: str, output: str) -> ResponseItem:
    return ResponseItem.from_mapping({"type": "custom_tool_call_output", "call_id": call_id, "output": output})


def tool_search_output(call_id: str | None, *, execution: str = "client") -> ResponseItem:
    return ResponseItem.from_mapping(
        {
            "type": "tool_search_output",
            "call_id": call_id,
            "status": "completed",
            "execution": execution,
            "tools": [],
        }
    )


def reference_context_item() -> TurnContextItem:
    return TurnContextItem(
        cwd=Path("C:/work/project"),
        approval_policy=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.danger_full_access(),
        model="gpt-test",
    )


class CompactRemoteTests(unittest.IsolatedAsyncioTestCase):
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

    def test_ensure_call_outputs_present_inserts_synthetic_outputs_after_calls(self) -> None:
        function_call = ResponseItem.function_call("shell", "{}", "call-1")
        tool_search_call = ResponseItem.tool_search_call("{}", call_id="search-1")
        custom_tool_call = ResponseItem.custom_tool_call("custom", "input", "custom-1")
        local_shell_call = ResponseItem.from_mapping(
            {
                "type": "local_shell_call",
                "call_id": "shell-1",
                "status": "completed",
                "action": {"type": "exec", "command": ["echo", "hi"]},
            }
        )
        existing_output = function_call_output("done-1", "ok")
        existing_call = ResponseItem.function_call("already", "{}", "done-1")

        normalized = ensure_call_outputs_present(
            (
                user_message("start"),
                function_call,
                tool_search_call,
                custom_tool_call,
                local_shell_call,
                existing_call,
                existing_output,
            )
        )

        self.assertEqual(
            [item.type for item in normalized],
            [
                "message",
                "function_call",
                "function_call_output",
                "tool_search_call",
                "tool_search_output",
                "custom_tool_call",
                "custom_tool_call_output",
                "local_shell_call",
                "function_call_output",
                "function_call",
                "function_call_output",
            ],
        )
        self.assertEqual(normalized[2].call_id, "call-1")
        self.assertEqual(normalized[2].output.to_text(), "aborted")
        self.assertEqual(normalized[4].call_id, "search-1")
        self.assertEqual(normalized[4].status, "completed")
        self.assertEqual(normalized[4].execution, "client")
        self.assertEqual(normalized[6].call_id, "custom-1")
        self.assertEqual(normalized[6].output.to_text(), "aborted")
        self.assertEqual(normalized[8].call_id, "shell-1")
        self.assertEqual(normalized[8].output.to_text(), "aborted")
        self.assertIs(normalized[-1], existing_output)

    def test_remove_orphan_outputs_keeps_only_outputs_with_matching_calls(self) -> None:
        function_call = ResponseItem.function_call("tool", "{}", "call-1")
        function_output = function_call_output("call-1", "ok")
        local_shell_call = ResponseItem.from_mapping(
            {
                "type": "local_shell_call",
                "call_id": "shell-1",
                "status": "completed",
                "action": {"type": "exec", "command": ["pwd"]},
            }
        )
        local_shell_output = function_call_output("shell-1", "ok")
        tool_search_call = ResponseItem.tool_search_call("{}", call_id="search-1")
        paired_search_output = tool_search_output("search-1")
        server_search_output = tool_search_output("server-1", execution="server")
        unpaired_search_output = tool_search_output(None)
        custom_tool_call = ResponseItem.custom_tool_call("custom", "input", "custom-1")
        custom_tool_output = custom_tool_call_output("custom-1", "ok")

        retained = remove_orphan_outputs(
            (
                function_call,
                function_output,
                function_call_output("orphan-function", "drop"),
                local_shell_call,
                local_shell_output,
                tool_search_call,
                paired_search_output,
                server_search_output,
                unpaired_search_output,
                tool_search_output("orphan-search"),
                custom_tool_call,
                custom_tool_output,
                custom_tool_call_output("orphan-custom", "drop"),
            )
        )

        self.assertEqual(
            retained,
            (
                function_call,
                function_output,
                local_shell_call,
                local_shell_output,
                tool_search_call,
                paired_search_output,
                server_search_output,
                unpaired_search_output,
                custom_tool_call,
                custom_tool_output,
            ),
        )

    def test_remove_orphan_outputs_drops_empty_function_output_without_matching_call(self) -> None:
        orphan_output = function_call_output("", "failed to parse tool_search arguments")

        retained = remove_orphan_outputs((orphan_output,))

        self.assertEqual(retained, ())

    def test_remove_orphan_outputs_keeps_empty_function_output_with_matching_call(self) -> None:
        function_call = ResponseItem.function_call("tool", "{}", "")
        function_output = function_call_output("", "ok")

        retained = remove_orphan_outputs((function_call, function_output))

        self.assertEqual(retained, (function_call, function_output))

    def test_normalize_call_outputs_inserts_missing_outputs_then_removes_orphans(self) -> None:
        function_call = ResponseItem.function_call("tool", "{}", "call-1")
        orphan = function_call_output("orphan", "drop")

        normalized = normalize_call_outputs((function_call, orphan))

        self.assertEqual([item.type for item in normalized], ["function_call", "function_call_output"])
        self.assertEqual(normalized[1].call_id, "call-1")
        self.assertEqual(normalized[1].output.to_text(), "aborted")

    def test_normalize_call_outputs_drops_bad_tool_search_error_output_and_inserts_search_output(self) -> None:
        tool_search_call = ResponseItem.tool_search_call({"limit": 3}, call_id="search-bad", execution="client")
        error_output = function_call_output("", "failed to parse tool_search arguments")

        normalized = normalize_call_outputs((tool_search_call, error_output))

        self.assertEqual([item.type for item in normalized], ["tool_search_call", "tool_search_output"])
        self.assertEqual(normalized[1].call_id, "search-bad")
        self.assertEqual(normalized[1].status, "completed")
        self.assertEqual(normalized[1].execution, "client")
        self.assertEqual(normalized[1].tools, ())

    def test_strip_images_when_unsupported_replaces_images_and_clears_image_generation_result(self) -> None:
        message = ResponseItem.message(
            "user",
            (
                ContentItem.input_text("look"),
                ContentItem.input_image("data:image/png;base64,AAA", detail=ImageDetail.HIGH),
            ),
        )
        function_output = ResponseItem(
            type="function_call_output",
            call_id="call-1",
            output=FunctionCallOutputPayload.from_content_items(
                (
                    FunctionCallOutputContentItem.input_text("before"),
                    FunctionCallOutputContentItem.input_image("data:image/png;base64,BBB", detail=ImageDetail.HIGH),
                )
            ),
        )
        custom_output = ResponseItem(
            type="custom_tool_call_output",
            call_id="custom-1",
            output=FunctionCallOutputPayload.from_content_items(
                (FunctionCallOutputContentItem.input_image("data:image/png;base64,CCC", detail=ImageDetail.HIGH),),
                success=True,
            ),
        )
        image_generation = ResponseItem.image_generation_call("img-1", "completed", "base64-result")

        normalized = strip_images_when_unsupported(
            ("text",),
            (message, function_output, custom_output, image_generation),
        )

        self.assertEqual(
            normalized[0].content,
            (
                ContentItem.input_text("look"),
                ContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),
            ),
        )
        self.assertEqual(
            normalized[1].output.content_items,
            (
                FunctionCallOutputContentItem.input_text("before"),
                FunctionCallOutputContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),
            ),
        )
        self.assertEqual(
            normalized[2].output.content_items,
            (FunctionCallOutputContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),),
        )
        self.assertTrue(normalized[2].output.success)
        self.assertEqual(normalized[3].result, "")

    def test_strip_images_when_supported_preserves_history(self) -> None:
        message = ResponseItem.message(
            "user",
            (ContentItem.input_image("data:image/png;base64,AAA", detail=ImageDetail.HIGH),),
        )

        self.assertEqual(strip_images_when_unsupported(("text", "image"), (message,)), (message,))

    def test_normalize_history_for_prompt_matches_context_manager_order(self) -> None:
        function_call = ResponseItem.function_call("tool", "{}", "call-1")
        orphan = function_call_output("orphan", "drop")
        image_message = ResponseItem.message(
            "user",
            (ContentItem.input_image("data:image/png;base64,AAA", detail=ImageDetail.HIGH),),
        )

        normalized = normalize_history_for_prompt((function_call, orphan, image_message), ("text",))

        self.assertEqual(
            [item.type for item in normalized],
            ["function_call", "function_call_output", "message"],
        )
        self.assertEqual(normalized[1].call_id, "call-1")
        self.assertEqual(normalized[2].content, (ContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),))

    def test_remote_compaction_success_plan_filters_injects_and_builds_install_plan(self) -> None:
        reference_context = reference_context_item()
        input_history = (user_message("before"),)
        old_user = user_message("old")
        fresh_context = developer_message("fresh rules")
        latest_user = user_message("latest")

        plan = build_remote_compaction_success_plan(
            input_history,
            (
                old_user,
                developer_message("stale rules"),
                ResponseItem.compaction_trigger(),
                latest_user,
            ),
            InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
            (fresh_context,),
            reference_context,
        )

        expected_history = (old_user, fresh_context, latest_user)
        self.assertEqual(plan.new_history, expected_history)
        self.assertIs(plan.reference_context_item, reference_context)
        self.assertEqual(
            plan.compacted_item.replacement_history,
            tuple(item.to_mapping() for item in expected_history),
        )
        self.assertEqual(
            plan.checkpoint_payload,
            {
                "input_history": [item.to_mapping() for item in input_history],
                "replacement_history": [item.to_mapping() for item in expected_history],
            },
        )

    async def test_remote_compaction_install_plan_applies_to_in_memory_session(self) -> None:
        reference_context = reference_context_item()
        input_history = (user_message("before"),)
        new_history = (user_message("after"), ResponseItem.compaction("encrypted"))
        plan = build_remote_compaction_install_plan(
            input_history,
            new_history,
            InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
            reference_context,
        )
        session = InMemoryCodexSession(cwd="C:/work/project")

        await apply_remote_compaction_install_plan(session, plan)

        self.assertEqual(session.history, list(new_history))
        self.assertEqual(await session.reference_context_item(), reference_context)
        self.assertEqual(session.compacted_items, [plan.compacted_item])
        self.assertEqual(
            plan.checkpoint_payload,
            {
                "input_history": [item.to_mapping() for item in input_history],
                "replacement_history": [item.to_mapping() for item in new_history],
            },
        )

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

    def test_trim_function_call_history_removes_only_same_kind_counterpart_for_tool_search_output(self) -> None:
        user = user_message("hello")
        same_id_function_call = ResponseItem.function_call("tool", "{}", "shared")
        tool_search_call = ResponseItem.tool_search_call({"query": "docs"}, call_id="shared")
        tool_output = tool_search_output("shared")
        estimates = [12, 5]

        result = trim_function_call_history_to_fit_context_window(
            (user, same_id_function_call, tool_search_call, tool_output),
            10,
            "instructions",
            lambda items, base: estimates.pop(0),
        )

        self.assertEqual(result.deleted_items, 1)
        self.assertEqual(result.items, (user, same_id_function_call))

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

