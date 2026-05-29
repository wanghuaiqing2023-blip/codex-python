import unittest

from pycodex.core.extension_tools import (
    ExtensionToolAdapter,
    ExtensionTurnContext,
    to_extension_call,
)
from pycodex.core.tool_context import JsonToolOutput, ToolPayload
from pycodex.core.tool_registry import ToolExposure, ToolInvocation
from pycodex.protocol import ResponseItem, ToolName, TruncationPolicyConfig


class StubExtensionExecutor:
    def __init__(self) -> None:
        self.captured_call = None

    def tool_name(self) -> ToolName:
        return ToolName.plain("extension_echo")

    def spec(self):
        return {"type": "function", "name": "extension_echo"}

    def exposure(self) -> ToolExposure:
        return ToolExposure.DEFERRED

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def handle(self, call):
        self.captured_call = call
        return JsonToolOutput.new({"ok": True})


class CoreExtensionToolsTests(unittest.TestCase):
    def test_adapter_proxies_metadata(self) -> None:
        executor = StubExtensionExecutor()
        adapter = ExtensionToolAdapter.new(executor)

        self.assertEqual(adapter.tool_name(), ToolName.plain("extension_echo"))
        self.assertEqual(adapter.spec(), {"type": "function", "name": "extension_echo"})
        self.assertEqual(adapter.exposure(), ToolExposure.DEFERRED)
        self.assertTrue(adapter.supports_parallel_tool_calls())

    def test_adapter_normalizes_string_executor_names_through_tool_name_boundary(self) -> None:
        class StringNamedExecutor(StubExtensionExecutor):
            def tool_name(self):
                return "extension_echo"

        adapter = ExtensionToolAdapter.new(StringNamedExecutor())

        self.assertEqual(adapter.tool_name(), ToolName.plain("extension_echo"))

    def test_default_turn_context_supplies_non_optional_truncation_policy(self) -> None:
        context = ExtensionTurnContext()

        self.assertEqual(context.truncation_policy, TruncationPolicyConfig.tokens(10_000))

    def test_adapter_only_matches_function_payloads(self) -> None:
        adapter = ExtensionToolAdapter.new(StubExtensionExecutor())

        self.assertTrue(adapter.matches_kind(ToolPayload.function("{}")))
        self.assertFalse(adapter.matches_kind(ToolPayload.custom("raw")))
        with self.assertRaises(TypeError):
            adapter.matches_kind(object())

    def test_adapter_passes_invocation_fields_to_extension_call(self) -> None:
        executor = StubExtensionExecutor()
        policy = TruncationPolicyConfig.bytes(128)
        history_item = ResponseItem.message("user", [], id="msg-1")
        context = ExtensionTurnContext.from_items(
            turn_id="turn-1",
            truncation_policy=policy,
            items=(history_item,),
        )
        adapter = ExtensionToolAdapter.new(executor, turn_context=context)
        invocation = ToolInvocation(
            call_id="call-extension",
            tool_name=ToolName.plain("extension_echo"),
            payload=ToolPayload.function('{"message":"hello"}'),
        )

        output = adapter.handle(invocation)

        self.assertEqual(output.value, {"ok": True})
        self.assertEqual(executor.captured_call.turn_id, "turn-1")
        self.assertEqual(executor.captured_call.call_id, "call-extension")
        self.assertEqual(executor.captured_call.tool_name, ToolName.plain("extension_echo"))
        self.assertEqual(executor.captured_call.truncation_policy, policy)
        self.assertEqual(executor.captured_call.conversation_history.items, (history_item,))
        self.assertEqual(executor.captured_call.payload, ToolPayload.function('{"message":"hello"}'))

    def test_to_extension_call_rejects_non_rust_shapes(self) -> None:
        context = ExtensionTurnContext()
        with self.assertRaises(TypeError):
            to_extension_call(object(), context)
        with self.assertRaises(TypeError):
            to_extension_call(
                ToolInvocation("call", ToolName.plain("extension_echo"), ToolPayload.function("{}")),
                object(),
            )

    def test_handle_passes_payload_through_even_when_match_filter_rejects_it(self) -> None:
        executor = StubExtensionExecutor()
        adapter = ExtensionToolAdapter.new(executor)
        payload = ToolPayload.custom("raw")

        self.assertFalse(adapter.matches_kind(payload))
        output = adapter.handle(payload)

        self.assertEqual(output.value, {"ok": True})
        self.assertEqual(executor.captured_call.payload, payload)
        self.assertEqual(executor.captured_call.turn_id, "")
        self.assertEqual(executor.captured_call.truncation_policy, TruncationPolicyConfig.tokens(10_000))
        self.assertEqual(executor.captured_call.conversation_history.items, ())

    def test_adapter_rejects_non_invocation_or_payload(self) -> None:
        adapter = ExtensionToolAdapter.new(StubExtensionExecutor())
        with self.assertRaises(TypeError):
            adapter.handle(object())

    def test_executor_contract_is_strict(self) -> None:
        with self.assertRaises(TypeError):
            ExtensionToolAdapter.new(object())

        class BadParallel(StubExtensionExecutor):
            def supports_parallel_tool_calls(self):
                return 1

        with self.assertRaises(TypeError):
            ExtensionToolAdapter.new(BadParallel()).supports_parallel_tool_calls()


if __name__ == "__main__":
    unittest.main()
