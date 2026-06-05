import json
import unittest

from pycodex.core.tools.handlers.multi_agents_common import (
    build_wait_agent_statuses,
    function_arguments,
    parse_collab_input,
    reject_full_fork_spawn_overrides,
    tool_output_code_mode_result,
    tool_output_json_text,
    tool_output_response_item,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentStatus, CollabAgentRef, ThreadId, UserInput


class CoreMultiAgentsCommonTests(unittest.TestCase):
    def test_function_arguments_accepts_only_function_payloads(self) -> None:
        self.assertEqual(function_arguments(ToolPayload.function("{}")), "{}")
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            function_arguments(ToolPayload.custom("raw"))
        with self.assertRaises(TypeError):
            function_arguments(object())

    def test_tool_output_json_text_serializes_mapping_dataclasses(self) -> None:
        status = AgentStatus.completed("done")
        self.assertEqual(tool_output_json_text(status, "wait_agent"), '{"completed":"done"}')
        self.assertEqual(tool_output_code_mode_result(status, "wait_agent"), {"completed": "done"})

    def test_tool_output_response_item_returns_function_output(self) -> None:
        item = tool_output_response_item(
            "call-1",
            ToolPayload.function("{}"),
            {"ok": True},
            True,
            "send_message",
        )
        self.assertEqual(item.type, "function_call_output")

    def test_build_wait_agent_statuses_preserves_receiver_order_then_sorts_extras(self) -> None:
        first = ThreadId.new()
        second = ThreadId.new()
        extra = ThreadId.new()
        statuses = {
            extra: AgentStatus.errored("boom"),
            second: AgentStatus.completed("done"),
            first: AgentStatus.running(),
        }
        entries = build_wait_agent_statuses(
            statuses,
            (
                CollabAgentRef(thread_id=second, agent_nickname="B", agent_role="worker"),
                CollabAgentRef(thread_id=first, agent_nickname="A"),
            ),
        )
        self.assertEqual([entry.thread_id for entry in entries[:2]], [second, first])
        self.assertEqual(entries[0].agent_nickname, "B")
        self.assertEqual(entries[0].agent_role, "worker")
        self.assertEqual(entries[2].thread_id, extra)

    def test_parse_collab_input_accepts_message_or_items_but_not_both(self) -> None:
        self.assertEqual(parse_collab_input("hello", None), (UserInput.text_input("hello"),))
        items = parse_collab_input(None, ({"type": "text", "text": "hi"},))
        self.assertEqual(items, (UserInput.text_input("hi"),))

        with self.assertRaisesRegex(FunctionCallError, "either message or items"):
            parse_collab_input("hello", (UserInput.text_input("hi"),))
        with self.assertRaisesRegex(FunctionCallError, "Provide one of"):
            parse_collab_input(None, None)
        with self.assertRaisesRegex(FunctionCallError, "Empty message"):
            parse_collab_input(" ", None)
        with self.assertRaisesRegex(FunctionCallError, "Items can't be empty"):
            parse_collab_input(None, ())

    def test_reject_full_fork_spawn_overrides_matches_rust_message(self) -> None:
        reject_full_fork_spawn_overrides(None, None, None)
        with self.assertRaisesRegex(FunctionCallError, "Full-history forked agents inherit"):
            reject_full_fork_spawn_overrides("worker", None, None)
        with self.assertRaises(TypeError):
            reject_full_fork_spawn_overrides(None, 1, None)

    def test_json_text_falls_back_to_string_error_for_unserializable_values(self) -> None:
        text = tool_output_json_text({"bad": object()}, "wait_agent")
        self.assertIsInstance(json.loads(text), str)
        self.assertIn("failed to serialize wait_agent result", json.loads(text))


if __name__ == "__main__":
    unittest.main()
