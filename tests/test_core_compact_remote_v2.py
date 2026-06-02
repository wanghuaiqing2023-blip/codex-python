import unittest
from pathlib import Path

from pycodex.core import (
    RemoteCompactionV2OutputError,
    RemoteCompactionV2StreamError,
    apply_remote_compaction_v2_install_plan,
    build_remote_compaction_v2_install_plan,
    build_remote_compaction_v2_prompt,
    build_remote_compaction_v2_success_plan,
    build_v2_compacted_history,
    collect_compaction_output,
    remote_compaction_v2_max_stream_retries,
    remote_compaction_v2_request_outcome,
    remote_compaction_v2_retry_decision,
    remote_compaction_v2_trace_attempt_payload,
    response_processed_request_for_remote_compaction_v2,
    truncate_retained_messages_for_remote_compaction,
)
from pycodex.core.compact import InitialContextInjection
from pycodex.core.features import Feature
from pycodex.core.session_runtime import InMemoryCodexSession
from pycodex.core.responses_retry import RetryableResponseStreamAction
from pycodex.protocol import AskForApproval, BaseInstructions, CodexErr, ContentItem, MessagePhase, ResponseItem, SandboxPolicy, TurnContextItem


def message(role: str, text: str, phase: MessagePhase | None = None) -> ResponseItem:
    return ResponseItem.message(role, (ContentItem.input_text(text),), phase=phase)


def reference_context_item() -> TurnContextItem:
    return TurnContextItem(
        cwd=Path("C:/work/project"),
        approval_policy=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.danger_full_access(),
        model="gpt-test",
    )


class FeatureSet:
    def __init__(self, *features: Feature) -> None:
        self.features = set(features)

    def enabled(self, feature: Feature) -> bool:
        return feature in self.features


class ProviderInfo:
    def __init__(self, retries: int) -> None:
        self.retries = retries

    def stream_max_retries(self) -> int:
        return self.retries


class CompactRemoteV2Tests(unittest.IsolatedAsyncioTestCase):
    def test_build_remote_compaction_v2_prompt_appends_compaction_trigger(self) -> None:
        user = message("user", "hello")
        base = BaseInstructions("base")

        prompt = build_remote_compaction_v2_prompt(
            (user,),
            ({"type": "function", "name": "demo"},),
            parallel_tool_calls=True,
            base_instructions=base,
        )

        self.assertEqual(prompt.input, [user, ResponseItem.compaction_trigger()])
        self.assertEqual(prompt.tools, [{"type": "function", "name": "demo"}])
        self.assertTrue(prompt.parallel_tool_calls)
        self.assertIs(prompt.base_instructions, base)
        self.assertIsNone(prompt.output_schema)
        self.assertTrue(prompt.output_schema_strict)

    def test_remote_compaction_v2_trace_attempt_payload_matches_rust_shape(self) -> None:
        prompt = build_remote_compaction_v2_prompt(
            (message("user", "hello"),),
            (),
            parallel_tool_calls=False,
            base_instructions=BaseInstructions("base"),
        )

        self.assertEqual(
            remote_compaction_v2_trace_attempt_payload("gpt-test", prompt),
            {
                "model": "gpt-test",
                "instructions": "base",
                "input": [item.to_mapping() for item in prompt.input],
                "parallel_tool_calls": False,
            },
        )

    def test_collect_compaction_output_accepts_additional_output_items(self) -> None:
        compaction = ResponseItem.compaction("encrypted")

        output, response_id = collect_compaction_output(
            (
                {"type": "output_item_done", "item": message("assistant", "ignored")},
                {"type": "output_item_done", "item": compaction},
                {"type": "completed", "response_id": "resp-compact"},
            )
        )

        self.assertEqual(output, compaction)
        self.assertEqual(response_id, "resp-compact")

    def test_collect_compaction_output_requires_completed_response(self) -> None:
        with self.assertRaises(CodexErr) as caught:
            collect_compaction_output(({"type": "output_item_done", "item": ResponseItem.compaction("enc")},))

        self.assertEqual(caught.exception.kind, "stream")
        self.assertTrue(caught.exception.is_retryable())
        self.assertIn("closed before response.completed", caught.exception.message)

    def test_collect_compaction_output_propagates_stream_errors_like_rust(self) -> None:
        err = CodexErr.stream("remote disconnect")

        with self.assertRaises(CodexErr) as caught:
            collect_compaction_output(
                (
                    {"type": "output_item_done", "item": ResponseItem.compaction("enc")},
                    err,
                    {"type": "completed", "response_id": "resp-compact"},
                )
            )

        self.assertIs(caught.exception, err)

    def test_collect_compaction_output_requires_exactly_one_compaction_item(self) -> None:
        with self.assertRaises(CodexErr) as caught_zero:
            collect_compaction_output(
                (
                    {"type": "output_item_done", "item": message("assistant", "ignored")},
                    {"type": "completed", "response_id": "resp-compact"},
                )
            )

        self.assertEqual(caught_zero.exception.kind, "fatal")
        self.assertFalse(caught_zero.exception.is_retryable())
        self.assertIn("got 0 from 1 output items", caught_zero.exception.message)

        with self.assertRaises(CodexErr) as caught_two:
            collect_compaction_output(
                (
                    {"type": "output_item_done", "item": ResponseItem.compaction("one")},
                    {"type": "output_item_done", "item": ResponseItem.compaction("two")},
                    {"type": "completed", "response_id": "resp-compact"},
                )
            )

        self.assertEqual(caught_two.exception.kind, "fatal")
        self.assertFalse(caught_two.exception.is_retryable())
        self.assertIn("got 2 from 2 output items", caught_two.exception.message)

    def test_response_processed_request_for_remote_compaction_v2_requires_feature(self) -> None:
        self.assertIsNone(
            response_processed_request_for_remote_compaction_v2(
                FeatureSet(),
                "resp-compact",
            )
        )
        self.assertEqual(
            response_processed_request_for_remote_compaction_v2(
                FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
                "resp-compact",
            ),
            {"type": "response.processed", "response_id": "resp-compact"},
        )

    def test_remote_compaction_v2_max_stream_retries_caps_provider_value(self) -> None:
        self.assertEqual(remote_compaction_v2_max_stream_retries(ProviderInfo(5)), 2)
        self.assertEqual(remote_compaction_v2_max_stream_retries(ProviderInfo(1)), 1)

    def test_remote_compaction_v2_retry_decision_uses_v2_request_kind_and_cap(self) -> None:
        decision = remote_compaction_v2_retry_decision(
            retries=1,
            provider_info=ProviderInfo(5),
            err=CodexErr.stream("disconnect"),
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertIs(decision.action, RetryableResponseStreamAction.RETRY)
        self.assertEqual(decision.retries, 2)
        self.assertEqual(decision.notify_message, "Reconnecting... 2/2")

    def test_remote_compaction_v2_retry_decision_can_fallback_after_capped_retries(self) -> None:
        decision = remote_compaction_v2_retry_decision(
            retries=2,
            provider_info=ProviderInfo(5),
            err=CodexErr.stream("disconnect"),
            fallback_transport_available=True,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertIs(decision.action, RetryableResponseStreamAction.FALLBACK_TRANSPORT)
        self.assertEqual(decision.retries, 0)

    def test_remote_compaction_v2_request_outcome_returns_success_for_compaction_result(self) -> None:
        result = (ResponseItem.compaction("encrypted"), "resp-compact")

        outcome = remote_compaction_v2_request_outcome(
            result,
            retries=0,
            provider_info=ProviderInfo(5),
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertEqual(outcome.action, "success")
        self.assertEqual(outcome.result, result)

    def test_remote_compaction_v2_request_outcome_fails_non_retryable_error(self) -> None:
        err = CodexErr.fatal("bad compact output")

        outcome = remote_compaction_v2_request_outcome(
            err,
            retries=0,
            provider_info=ProviderInfo(5),
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertEqual(outcome.action, "fail")
        self.assertIs(outcome.error, err)

    def test_remote_compaction_v2_request_outcome_delegates_retryable_error(self) -> None:
        outcome = remote_compaction_v2_request_outcome(
            CodexErr.stream("disconnect"),
            retries=1,
            provider_info=ProviderInfo(5),
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertEqual(outcome.action, "retry_or_fallback")
        self.assertIsNotNone(outcome.retry_decision)
        self.assertIs(outcome.retry_decision.action, RetryableResponseStreamAction.RETRY)
        self.assertEqual(outcome.retry_decision.retries, 2)

    def test_build_remote_compaction_v2_install_plan_matches_rust_install_payloads(self) -> None:
        input_history = (message("user", "before"),)
        new_history = (message("user", "after"), ResponseItem.compaction("encrypted"))

        plan = build_remote_compaction_v2_install_plan(
            input_history,
            new_history,
            InitialContextInjection.DO_NOT_INJECT,
        )

        self.assertEqual(plan.new_history, new_history)
        self.assertIsNone(plan.reference_context_item)
        self.assertEqual(plan.compacted_item.message, "")
        self.assertEqual(plan.compacted_item.replacement_history, tuple(item.to_mapping() for item in new_history))
        self.assertEqual(
            plan.checkpoint_payload,
            {
                "input_history": [item.to_mapping() for item in input_history],
                "replacement_history": [item.to_mapping() for item in new_history],
            },
        )

    def test_build_remote_compaction_v2_install_plan_keeps_reference_context_for_mid_turn_injection(self) -> None:
        reference_context = reference_context_item()

        plan = build_remote_compaction_v2_install_plan(
            (message("user", "before"),),
            (message("user", "after"),),
            InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
            reference_context,
        )

        self.assertIs(plan.reference_context_item, reference_context)

    def test_build_remote_compaction_v2_install_plan_requires_reference_context_for_mid_turn_injection(self) -> None:
        with self.assertRaisesRegex(TypeError, "reference_context_item must be provided"):
            build_remote_compaction_v2_install_plan(
                (message("user", "before"),),
                (message("user", "after"),),
                InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
            )

    def test_build_remote_compaction_v2_success_plan_composes_history_processing_and_install_payload(self) -> None:
        trace_input_history = (message("user", "before"), ResponseItem.function_call("tool", "{}", "call-1"))
        old = message("user", "old")
        latest = message("user", "latest")
        reference_context = reference_context_item()
        reference_message = message("developer", "fresh context")
        compaction_output = ResponseItem.compaction("encrypted")

        plan = build_remote_compaction_v2_success_plan(
            trace_input_history,
            (old, message("developer", "stale"), latest),
            compaction_output,
            InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
            (reference_message,),
            reference_context,
        )

        self.assertEqual(plan.new_history, (old, reference_message, latest, compaction_output))
        self.assertIs(plan.reference_context_item, reference_context)
        self.assertEqual(plan.compacted_item.replacement_history, tuple(item.to_mapping() for item in plan.new_history))
        self.assertEqual(
            plan.checkpoint_payload,
            {
                "input_history": [item.to_mapping() for item in trace_input_history],
                "replacement_history": [item.to_mapping() for item in plan.new_history],
            },
        )

    async def test_apply_remote_compaction_v2_install_plan_updates_in_memory_session(self) -> None:
        reference_context = reference_context_item()
        new_history = (message("user", "after"), ResponseItem.compaction("encrypted"))
        plan = build_remote_compaction_v2_install_plan(
            (message("user", "before"),),
            new_history,
            InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
            reference_context,
        )
        session = InMemoryCodexSession(cwd="C:/work/project")

        await apply_remote_compaction_v2_install_plan(session, plan)

        self.assertEqual(session.history, list(new_history))
        self.assertEqual(await session.reference_context_item(), reference_context)
        self.assertEqual(session.compacted_items, [plan.compacted_item])

    def test_build_v2_compacted_history_filters_to_installed_retention_shape(self) -> None:
        input_items = (
            message("developer", "dev"),
            message("system", "sys"),
            message("user", "user"),
            message("assistant", "commentary", MessagePhase.COMMENTARY),
            message("assistant", "final", MessagePhase.FINAL_ANSWER),
            ResponseItem.function_call("shell_command", "{}", "call_1"),
            ResponseItem.compaction("old"),
        )
        output = ResponseItem.compaction("new")

        self.assertEqual(build_v2_compacted_history(input_items, output), [message("user", "user"), output])

    def test_build_v2_compacted_history_discards_messages_before_truncating(self) -> None:
        old = message("user", "old")
        new = message("user", "new")
        huge_developer_message = "d" * ((64_000 + 1) * 4)
        huge_contextual_message = "<environment_context>\n" + ("c" * ((64_000 + 1) * 4)) + "\n</environment_context>"
        output = ResponseItem.compaction("new")

        history = build_v2_compacted_history(
            (
                old,
                message("developer", huge_developer_message),
                message("user", huge_contextual_message),
                new,
            ),
            output,
        )

        self.assertEqual(history, [old, new, output])

    def test_retained_history_truncation_keeps_newest_messages_first(self) -> None:
        middle = message("user", "middle1234")
        new = message("user", "new")

        truncated = truncate_retained_messages_for_remote_compaction(
            (message("user", "old-old"), middle, new),
            max_tokens=3,
        )

        self.assertEqual(len(truncated), 2)
        self.assertIn("tokens truncated", truncated[0].content[0].text or "")
        self.assertEqual(truncated[1], new)

    def test_retained_history_truncation_preserves_images_and_truncates_later_text_parts(self) -> None:
        item = ResponseItem.message(
            "user",
            (
                ContentItem.input_text("abcdef"),
                ContentItem.input_image("data:image/png;base64,abc"),
                ContentItem.output_text("uvwxyz"),
            ),
        )

        truncated = truncate_retained_messages_for_remote_compaction((item,), max_tokens=3)

        self.assertEqual(truncated[0].content[0], ContentItem.input_text("abcdef"))
        self.assertEqual(truncated[0].content[1], ContentItem.input_image("data:image/png;base64,abc"))
        self.assertEqual(truncated[0].content[2].type, "output_text")
        self.assertIn("tokens truncated", truncated[0].content[2].text or "")

    def test_retained_history_truncation_charges_image_only_messages(self) -> None:
        image_only = ResponseItem.message(
            "user",
            (ContentItem.input_image("data:image/png;base64,abc"),),
        )
        newest = message("user", "new")

        self.assertEqual(
            truncate_retained_messages_for_remote_compaction(
                (message("user", "old"), image_only, newest),
                max_tokens=2,
            ),
            [image_only, newest],
        )
        self.assertEqual(
            truncate_retained_messages_for_remote_compaction((image_only, newest), max_tokens=1),
            [newest],
        )

    def test_retained_history_truncation_drops_image_only_messages_after_budget_is_spent(self) -> None:
        image_only = ResponseItem.message(
            "user",
            (ContentItem.input_image("data:image/png;base64,abc"),),
        )
        newest = message("user", "new")

        self.assertEqual(
            truncate_retained_messages_for_remote_compaction((image_only, newest), max_tokens=1),
            [newest],
        )


if __name__ == "__main__":
    unittest.main()
