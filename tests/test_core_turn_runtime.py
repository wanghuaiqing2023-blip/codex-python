import asyncio
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.codex_thread import SETTINGS_UNSET, SessionSettingsUpdate
from pycodex.core.compact_remote import IMAGE_CONTENT_OMITTED_PLACEHOLDER
from pycodex.core.features import Feature
from pycodex.core.hook_runtime import HookRuntimeOutcome
from pycodex.core.session_runtime import InMemoryCodexSession
import pycodex.core.turn_runtime as turn_runtime
from pycodex.core.turn_sampler import sample_with_model_client_session
from pycodex.core.turn_runtime import (
    build_user_input_op_responses_request_from_session,
    build_user_turn_responses_request_from_session,
    run_user_input_op_sampling_from_session,
    run_user_turn_sampling_from_session,
)
from pycodex.core.turn_timing import TurnTimingState
from pycodex.core.tool_context import FunctionToolOutput
from pycodex.core.tool_router import FunctionCallError
from pycodex.core.tool_registry import ToolRegistry
from pycodex.core.tool_router import ToolRouter
from pycodex.protocol import (
    ApplyPatchToolType,
    BaseInstructions,
    CodexErr,
    ContentItem,
    EventMsg,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    HookPromptFragment,
    MessagePhase,
    Op,
    RateLimitSnapshot,
    RateLimitWindow,
    ReasoningEffort,
    ResponseItem,
    ThreadSettingsOverrides,
    TokenUsage,
    TurnEnvironmentSelection,
    UserInput,
    ToolName,
    UsageLimitReachedError,
)


class History:
    def __init__(self, items: list[ResponseItem]) -> None:
        self.items = items

    def for_prompt(self, _modalities: object) -> list[ResponseItem]:
        return list(self.items)


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return [{"type": "function", "name": "tool"}]


class EchoHandler:
    def __init__(self) -> None:
        self.invocations = []

    def tool_name(self) -> ToolName:
        return ToolName.plain("echo")

    def handle(self, invocation):
        self.invocations.append(invocation)
        return FunctionToolOutput.from_text("tool ok", True)


class ParallelEchoHandler:
    def __init__(self) -> None:
        self.started = []
        self.timed_out_waiting_for_parallel_peer = False
        self.release = asyncio.Event()

    def tool_name(self) -> ToolName:
        return ToolName.plain("parallel_echo")

    def supports_parallel_tool_calls(self) -> bool:
        return True

    async def handle(self, invocation):
        self.started.append(invocation.call_id)
        if len(self.started) == 3:
            self.release.set()
        else:
            try:
                await asyncio.wait_for(self.release.wait(), timeout=0.2)
            except TimeoutError:
                self.timed_out_waiting_for_parallel_peer = True
        return FunctionToolOutput.from_text(invocation.call_id, True)


class FatalHandler:
    def tool_name(self) -> ToolName:
        return ToolName.plain("fatal_tool")

    def handle(self, _invocation):
        raise FunctionCallError.fatal("tool exploded")


class DiffConsumer:
    def __init__(self) -> None:
        self.deltas = []

    def consume_diff(self, turn_context, call_id, delta):
        self.deltas.append((turn_context, call_id, delta))
        return {"type": "tool_call_input_delta", "call_id": call_id, "delta": delta}

    def finish(self):
        return {"type": "tool_call_input_done", "call_id": "call-1"}


class CustomDiffHandler:
    def __init__(self, consumer: DiffConsumer) -> None:
        self.consumer = consumer

    def tool_name(self) -> ToolName:
        return ToolName.plain("apply_patch")

    def matches_kind(self, payload) -> bool:
        return payload.type == "custom"

    def handle(self, _invocation):
        return FunctionToolOutput.from_text("patched", True)

    def create_diff_consumer(self):
        return self.consumer


class FeatureSet:
    def __init__(self, *features) -> None:
        self.features = set(features)

    def enabled(self, feature) -> bool:
        if not isinstance(feature, Feature):
            raise TypeError("feature must be Feature")
        return feature in self.features


class CancellationToken:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


class PendingInputQueue:
    def __init__(self) -> None:
        self.items = []
        self.calls = 0
        self.active_turns = []

    async def get_pending_input(self, _active_turn=None):
        self.calls += 1
        self.active_turns.append(_active_turn)
        items = tuple(self.items)
        self.items.clear()
        return items

    async def has_pending_input(self, _active_turn=None):
        return bool(self.items)


class StrictActiveTurnInputQueue:
    def __init__(self) -> None:
        self.items = []
        self.calls = 0
        self.active_turns = []

    async def get_pending_input(self, active_turn):
        self.calls += 1
        self.active_turns.append(active_turn)
        items = tuple(self.items)
        self.items.clear()
        return items

    async def has_pending_input(self, active_turn):
        self.calls += 1
        self.active_turns.append(active_turn)
        return bool(self.items)


class KeywordOnlyActiveTurnInputQueue:
    def __init__(self) -> None:
        self.items = []
        self.calls = 0
        self.active_turns = []

    async def get_pending_input(self, *, active_turn=None):
        self.calls += 1
        self.active_turns.append(active_turn)
        items = tuple(self.items)
        self.items.clear()
        return items

    async def has_pending_input(self, *, active_turn=None):
        self.calls += 1
        self.active_turns.append(active_turn)
        return bool(self.items)


class PendingMailboxQueue:
    def __init__(self, pending: bool = True) -> None:
        self.pending = pending
        self.calls = 0

    async def has_pending_mailbox_items(self) -> bool:
        self.calls += 1
        return self.pending


class TurnMetadataState:
    def __init__(self) -> None:
        self.responsesapi_client_metadata = None

    def set_responsesapi_client_metadata(self, value) -> None:
        self.responsesapi_client_metadata = dict(value)


class Telemetry:
    def __init__(self) -> None:
        self.durations = []

    def record_duration(self, metric: str, duration: object, tags: tuple[tuple[str, str], ...]) -> None:
        self.durations.append((metric, duration, tags))


def shell_join_for_test(args: list[str]) -> str:
    if sys.platform == "win32":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


class Session:
    def __init__(self) -> None:
        self.turn_metadata_state = TurnMetadataState()
        self.turn_context = SimpleNamespace(
            model_info=None,
            user_instructions="project instructions",
            cwd="C:/work/project",
            turn_metadata_state=self.turn_metadata_state,
        )
        self.history = [ResponseItem.message("developer", (ContentItem.input_text("context"),))]
        self.recorded: list[tuple[ResponseItem, ...]] = []
        self.context_recorded = False
        self.applied_thread_settings = None
        self.environments = None
        self._pending_environments = None
        self.final_output_json_schema = None
        self.total_tokens_full_turn_context = None
        self.updated_rate_limits = []
        self.recorded_rate_limits = []
        self.recorded_token_usage = []
        self.turn_error_lifecycle = []
        self.token_count_turn_contexts = []
        self.goal_runtime_events = []
        self.server_model_warnings = []
        self.model_verifications = []
        self.side_effect_order = []
        self.server_reasoning_included = None
        self.models_etags = []
        self.emitted_events = []
        self.stream_errors = []
        self.retry_sleeps = []
        self.features = FeatureSet()
        self.tail_calls = []
        self.unified_diff = None
        self.input_queue = None
        self.active_turn = object()

    async def new_default_turn(self) -> object:
        environments = self.environments
        if self._pending_environments is not None:
            environments = self._pending_environments
            self._pending_environments = None
        self.turn_context.environments = environments
        self.turn_context.final_output_json_schema = self.final_output_json_schema
        return self.turn_context

    async def update_settings(self, updates: SessionSettingsUpdate) -> None:
        if updates.environments is not None:
            self._pending_environments = tuple(updates.environments)
        if updates.final_output_json_schema is not SETTINGS_UNSET:
            self.final_output_json_schema = updates.final_output_json_schema

    async def apply_thread_settings_overrides(self, thread_settings: ThreadSettingsOverrides) -> None:
        self.applied_thread_settings = thread_settings
        self.turn_context.model_info = SimpleNamespace(
            slug=thread_settings.model or "gpt-test",
            input_modalities=("text",),
            supports_reasoning_summaries=True,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        self.turn_context.config = SimpleNamespace(
            model_reasoning_effort=thread_settings.effort,
            model_reasoning_summary=None,
            service_tier=thread_settings.service_tier,
        )

    async def record_context_updates_and_set_reference_context_item(self, turn_context: object) -> None:
        self.context_recorded = turn_context is self.turn_context

    async def record_conversation_items(self, _turn_context: object, items: tuple[ResponseItem, ...]) -> None:
        self.recorded.append(items)
        self.history.extend(items)

    async def clone_history(self) -> History:
        return History(self.history)

    async def get_base_instructions(self) -> BaseInstructions:
        return BaseInstructions("base")

    async def set_total_tokens_full(self, turn_context: object) -> None:
        self.total_tokens_full_turn_context = turn_context

    async def update_rate_limits(self, turn_context: object, rate_limits: RateLimitSnapshot) -> None:
        self.updated_rate_limits.append((turn_context, rate_limits))

    async def goal_runtime_apply(self, event: object) -> None:
        self.goal_runtime_events.append(event)

    async def emit_turn_error_lifecycle(self, turn_context: object, codex_error_info: object) -> None:
        self.turn_error_lifecycle.append((turn_context, codex_error_info))

    async def record_rate_limits_info(self, rate_limits: object) -> None:
        self.recorded_rate_limits.append(rate_limits)

    async def record_token_usage_info(self, turn_context: object, usage: TokenUsage) -> None:
        self.recorded_token_usage.append((turn_context, usage))

    async def send_token_count_event(self, turn_context: object) -> None:
        self.token_count_turn_contexts.append(turn_context)
        self.tail_calls.append(("token_count", turn_context))

    async def set_server_reasoning_included(self, included: bool) -> None:
        self.server_reasoning_included = included

    async def maybe_warn_on_server_model_mismatch(self, turn_context: object, server_model: str) -> bool:
        self.server_model_warnings.append((turn_context, server_model))
        self.side_effect_order.append(("server_model", server_model))
        return True

    async def emit_model_verification(self, turn_context: object, model_verifications: object) -> None:
        self.model_verifications.append((turn_context, model_verifications))
        self.side_effect_order.append(("model_verification", model_verifications))

    async def refresh_models_etag(self, etag: str) -> None:
        self.models_etags.append(etag)

    async def send_response_processed(self, response_id: str) -> None:
        self.tail_calls.append(("response_processed", response_id))

    async def drain_in_flight(self) -> None:
        self.tail_calls.append(("drain_in_flight",))

    async def get_unified_diff(self) -> str | None:
        return self.unified_diff

    async def send_event(self, _turn_context: object, event: EventMsg | dict) -> None:
        if isinstance(event, EventMsg):
            self.emitted_events.append(event)
        else:
            self.emitted_events.append(EventMsg.from_mapping(event))
        self.side_effect_order.append(("event", self.emitted_events[-1].type))
        if self.emitted_events[-1].type == "turn_diff":
            self.tail_calls.append(("turn_diff", self.emitted_events[-1].payload.unified_diff))

    async def notify_stream_error(self, turn_context: object, message: str, error: CodexErr) -> None:
        self.stream_errors.append((turn_context, message, error))

    async def sleep_for_sampling_retry(self, seconds: float) -> None:
        self.retry_sleeps.append(seconds)


def non_lifecycle_events(session: Session) -> tuple[EventMsg, ...]:
    return tuple(event for event in session.emitted_events if event.type not in {"task_started", "task_complete"})


def events_of_type(session: Session, event_type: str) -> tuple[EventMsg, ...]:
    return tuple(event for event in session.emitted_events if event.type == event_type)


class TurnRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_user_turn_responses_request_records_turn_and_builds_request(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
            service_tier="auto",
        )

        self.assertTrue(session.context_recorded)
        self.assertEqual(len(session.recorded), 1)
        self.assertEqual(plan.request["model"], "gpt-test")
        self.assertEqual(plan.request["instructions"], "base")
        self.assertEqual(plan.request["tools"], [{"type": "function", "name": "tool"}])
        self.assertEqual(plan.request["service_tier"], "auto")
        self.assertEqual(plan.request["input"][0].role, "developer")
        self.assertEqual(plan.request["input"][1].content[0].text, "hello")

    async def test_build_user_turn_request_normalizes_history_call_outputs_for_prompt(self) -> None:
        session = Session()
        function_call = ResponseItem.function_call("tool", "{}", "call-1")
        orphan_output = ResponseItem.from_mapping(
            {
                "type": "function_call_output",
                "call_id": "orphan",
                "output": "drop",
            }
        )
        session.history.extend((function_call, orphan_output))
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            input_modalities=("text",),
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        input_items = plan.request["input"]
        self.assertEqual(
            [item.type for item in input_items],
            ["message", "function_call", "function_call_output", "message"],
        )
        self.assertIs(input_items[1], function_call)
        self.assertEqual(input_items[2].call_id, "call-1")
        self.assertEqual(input_items[2].output.to_text(), "aborted")
        self.assertNotIn(orphan_output, input_items)

    async def test_build_user_turn_request_strips_unsupported_images_for_prompt(self) -> None:
        session = Session()
        image_message = ResponseItem.message(
            "user",
            (
                ContentItem.input_text("look"),
                ContentItem.input_image("data:image/png;base64,AAA"),
            ),
        )
        session.history.append(image_message)
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            input_modalities=("text",),
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        input_items = plan.request["input"]
        self.assertEqual(
            input_items[1].content,
            (
                ContentItem.input_text("look"),
                ContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER),
            ),
        )
        self.assertEqual(session.history[-2], image_message)

    async def test_build_user_turn_request_uses_turn_config_reasoning_and_service_tier_defaults(self) -> None:
        session = Session()
        session.turn_context.config = SimpleNamespace(
            model_reasoning_effort="high",
            model_reasoning_summary="concise",
            service_tier="priority",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=True,
            support_verbosity=False,
            default_reasoning_level="medium",
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(plan.request["reasoning"], {"effort": "high", "summary": "concise"})
        self.assertEqual(plan.request["service_tier"], "priority")

    async def test_build_user_turn_request_applies_thread_settings_before_turn_creation(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-stale",
            supports_reasoning_summaries=True,
            support_verbosity=False,
            default_reasoning_level="medium",
            service_tier_for_request=lambda tier: tier,
        )
        thread_settings = ThreadSettingsOverrides(
            model="gpt-thread",
            effort=ReasoningEffort.HIGH,
            service_tier="priority",
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
            thread_settings=thread_settings,
        )

        self.assertIs(session.applied_thread_settings, thread_settings)
        self.assertEqual(plan.request["model"], "gpt-thread")
        self.assertEqual(plan.request["reasoning"], {"effort": ReasoningEffort.HIGH})
        self.assertEqual(plan.request["service_tier"], "priority")

    async def test_build_user_input_op_request_applies_op_thread_settings(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-stale",
            supports_reasoning_summaries=True,
            support_verbosity=False,
            default_reasoning_level="medium",
            service_tier_for_request=lambda tier: tier,
        )
        thread_settings = ThreadSettingsOverrides(
            model="gpt-op",
            effort=ReasoningEffort.HIGH,
            service_tier="priority",
        )
        op = Op.user_input(
            (UserInput.text_input("hello"),),
            final_output_json_schema={"type": "object"},
            thread_settings=thread_settings,
        )

        plan = await build_user_input_op_responses_request_from_session(
            session,
            op,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIs(session.applied_thread_settings, thread_settings)
        self.assertEqual(plan.request["model"], "gpt-op")
        self.assertEqual(plan.request["service_tier"], "priority")
        self.assertEqual(session.turn_context.final_output_json_schema, {"type": "object"})
        self.assertEqual(plan.request["text"]["format"]["schema"], {"type": "object"})

    async def test_build_user_input_op_request_clears_previous_final_output_json_schema(self) -> None:
        session = Session()
        session.final_output_json_schema = {"type": "object"}
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),)),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIsNone(session.final_output_json_schema)
        self.assertIsNone(session.turn_context.final_output_json_schema)
        self.assertIsNone(plan.request["text"])

    async def test_build_user_input_op_request_records_responsesapi_client_metadata(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(
                (UserInput.text_input("hello"),),
                responsesapi_client_metadata={"fiber_run_id": "fiber-123"},
            ),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(
            session.turn_metadata_state.responsesapi_client_metadata,
            {"fiber_run_id": "fiber-123"},
        )

    async def test_build_user_input_op_request_records_additional_context_before_user_input(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(
                (UserInput.text_input("hello"),),
                additional_context={
                    "z_app": {"kind": "application", "value": "trusted context"},
                    "a_note": {"kind": "untrusted", "value": "untrusted context"},
                },
            ),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(session.recorded[0][0].role, "user")
        self.assertEqual(session.recorded[0][0].content[0].text, "<external_a_note>untrusted context</external_a_note>")
        self.assertEqual(session.recorded[0][1].role, "developer")
        self.assertEqual(session.recorded[0][1].content[0].text, "<z_app>trusted context</z_app>")
        self.assertEqual(session.recorded[1][0].content[0].text, "hello")
        self.assertIn("<external_a_note>untrusted context</external_a_note>", plan.request["input"][1].content[0].text)

    async def test_build_user_input_op_request_truncates_large_additional_context_values(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        max_expected_context_text_bytes = 5 * 1024
        long_browser_value = f"browser-head-{'x' * 40_000}-browser-tail"
        long_app_value = f"app-head-{'y' * 40_000}-app-tail"

        plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(
                (UserInput.text_input("hello"),),
                additional_context={
                    "browser_info": {"kind": "untrusted", "value": long_browser_value},
                    "app": {"kind": "application", "value": long_app_value},
                },
            ),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        developer_text = session.recorded[0][0].content[0].text
        user_text = session.recorded[0][1].content[0].text
        user_request_input = plan.request["input"]

        self.assertIn("tokens truncated", developer_text)
        self.assertIn("tokens truncated", user_text)
        self.assertLess(len(developer_text), len(long_app_value) + len("<app></app>"))
        self.assertLess(len(user_text), len(long_browser_value) + len("<external_browser_info></external_browser_info>"))
        self.assertIn("<app>", developer_text)
        self.assertIn("</app>", developer_text)
        self.assertIn("<external_browser_info>", user_text)
        self.assertIn("</external_browser_info>", user_text)
        request_app_text = None
        request_browser_text = None
        for item in user_request_input:
            text = item.content[0].text
            if "tokens truncated" in text and "<app>" in text:
                request_app_text = text
            if "tokens truncated" in text and "<external_browser_info>" in text:
                request_browser_text = text
        self.assertIsNotNone(request_app_text)
        self.assertIsNotNone(request_browser_text)
        self.assertIn("<app>", request_app_text)
        self.assertIn("</app>", request_app_text)
        self.assertIn("tokens truncated", request_app_text)
        self.assertIn("<external_browser_info>", request_browser_text)
        self.assertIn("</external_browser_info>", request_browser_text)
        self.assertIn("tokens truncated", request_browser_text)
        self.assertLessEqual(len(request_app_text), max_expected_context_text_bytes)
        self.assertLessEqual(len(request_browser_text), max_expected_context_text_bytes)
        self.assertIn("<app>app-head-" + ("y" * 1024), request_app_text)
        self.assertIn("<external_browser_info>browser-head-" + ("x" * 1024), request_browser_text)
        self.assertTrue(request_app_text.endswith("app-tail</app>"))
        self.assertTrue(request_browser_text.endswith("browser-tail</external_browser_info>"))
        self.assertTrue(
            any(item.role == "user" and item.content[0].text == "hello" for item in user_request_input),
            "user input should still appear in request input sequence",
        )

    async def test_build_user_input_op_request_rejects_unknown_additional_context_kind(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        with self.assertRaises(ValueError):
            await build_user_input_op_responses_request_from_session(
                session,
                Op.user_input(
                    (UserInput.text_input("hello"),),
                    additional_context={"app": {"kind": "internal", "value": "bad"}},
                ),
                client,
                provider,
                model_info,
                built_tools=lambda _sess, _turn: Router(),
            )

    async def test_build_user_input_op_request_rejects_non_string_additional_context_value(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        with self.assertRaises(TypeError):
            await build_user_input_op_responses_request_from_session(
                session,
                Op.user_input(
                    (UserInput.text_input("hello"),),
                    additional_context={"app": {"kind": "application", "value": 123}},
                ),
                client,
                provider,
                model_info,
                built_tools=lambda _sess, _turn: Router(),
            )

    async def test_build_user_input_op_request_applies_turn_environments_before_turn_creation(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        environments = (TurnEnvironmentSelection("env-1", "C:/work/project"),)

        await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),), environments=environments),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIsNone(session.environments)
        self.assertEqual(session.turn_context.environments, environments)

    async def test_build_user_turn_request_uses_default_environment_tool_router(self) -> None:
        session = Session()
        session.environments = (
            TurnEnvironmentSelection("local", "C:/work/project"),
            TurnEnvironmentSelection("remote", "C:/work/remote"),
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
            apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
            supports_image_detail_original=True,
        )
        session.turn_context.model_info = model_info
        session.turn_context.features = FeatureSet(Feature.EXEC_PERMISSION_APPROVALS)

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
        )

        specs_by_name = {spec["name"]: spec for spec in plan.request["tools"]}
        self.assertIn("environment_id", specs_by_name["exec_command"]["parameters"]["properties"])
        self.assertIn("additional_permissions", specs_by_name["exec_command"]["parameters"]["properties"])
        self.assertIn("Environment ID", specs_by_name["apply_patch"]["format"]["definition"])
        self.assertIn("environment_id", specs_by_name["view_image"]["parameters"]["properties"])
        self.assertEqual(specs_by_name["view_image"]["parameters"]["properties"]["detail"]["enum"], ["high", "original"])

    async def test_build_user_input_op_request_does_not_make_turn_environments_sticky(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),), environments=(TurnEnvironmentSelection("env-1", "C:/work/project"),)),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("next"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIsNone(session.turn_context.environments)

    async def test_build_user_input_op_request_records_only_changed_additional_context(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        first = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context v1"}},
        )
        same = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context v1"}},
        )
        changed = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context v2"}},
        )

        await build_user_input_op_responses_request_from_session(
            session,
            first,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        await build_user_input_op_responses_request_from_session(
            session,
            same,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        await build_user_input_op_responses_request_from_session(
            session,
            changed,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(session.recorded), 2)
        self.assertEqual(session.recorded[0][0].content[0].text, "<app>context v1</app>")
        self.assertEqual(session.recorded[1][0].content[0].text, "<app>context v2</app>")

    async def test_additional_context_removes_one_value_while_adding_another(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        first = Op.user_input(
            (UserInput.text_input("first turn"),),
            additional_context={
                "automation_info": {"kind": "untrusted", "value": "run one"},
                "browser_info": {"kind": "untrusted", "value": "tab one"},
            },
        )
        second = Op.user_input(
            (UserInput.text_input("second turn"),),
            additional_context={
                "automation_info": {"kind": "untrusted", "value": "run one"},
                "terminal_info": {"kind": "untrusted", "value": "pty one"},
            },
        )
        third = Op.user_input(
            (UserInput.text_input("third turn"),),
            additional_context={
                "automation_info": {"kind": "untrusted", "value": "run one"},
                "browser_info": {"kind": "untrusted", "value": "tab one"},
                "terminal_info": {"kind": "untrusted", "value": "pty one"},
            },
        )

        first_plan = await build_user_input_op_responses_request_from_session(
            session,
            first,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        second_plan = await build_user_input_op_responses_request_from_session(
            session,
            second,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        third_plan = await build_user_input_op_responses_request_from_session(
            session,
            third,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        def user_texts(plan):
            return [item.content[0].text for item in plan.request["input"] if item.role == "user"]

        self.assertEqual(
            user_texts(first_plan),
            [
                "<external_automation_info>run one</external_automation_info>",
                "<external_browser_info>tab one</external_browser_info>",
                "first turn",
            ],
        )
        self.assertEqual(
            user_texts(second_plan),
            [
                "<external_automation_info>run one</external_automation_info>",
                "<external_browser_info>tab one</external_browser_info>",
                "first turn",
                "<external_terminal_info>pty one</external_terminal_info>",
                "second turn",
            ],
        )
        self.assertEqual(
            user_texts(third_plan),
            [
                "<external_automation_info>run one</external_automation_info>",
                "<external_browser_info>tab one</external_browser_info>",
                "first turn",
                "<external_terminal_info>pty one</external_terminal_info>",
                "second turn",
                "<external_browser_info>tab one</external_browser_info>",
                "third turn",
            ],
        )

    async def test_additional_context_empty_map_clears_store_then_readds_values(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        with_context = Op.user_input(
            (UserInput.text_input("first"),),
            additional_context={"app": {"kind": "application", "value": "context"}},
        )
        cleared = Op.user_input((UserInput.text_input("cleared"),), additional_context={})
        restored = Op.user_input(
            (UserInput.text_input("restored"),),
            additional_context={"app": {"kind": "application", "value": "context"}},
        )

        first_plan = await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        cleared_plan = await build_user_input_op_responses_request_from_session(
            session,
            cleared,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        restored_plan = await build_user_input_op_responses_request_from_session(
            session,
            restored,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        first_user_texts = [item.content[0].text for item in first_plan.request["input"] if item.role == "user"]
        cleared_user_texts = [item.content[0].text for item in cleared_plan.request["input"] if item.role == "user"]
        restored_user_texts = [item.content[0].text for item in restored_plan.request["input"] if item.role == "user"]

        self.assertEqual(first_user_texts, ["first"])
        self.assertEqual(cleared_user_texts, ["first", "cleared"])
        self.assertEqual(restored_user_texts, ["first", "cleared", "restored"])

        self.assertIn("<app>context</app>", [item.content[0].text for item in first_plan.request["input"] if item.role == "developer"])
        self.assertTrue(any(item.role == "user" and item.content[0].text == "cleared" for item in cleared_plan.request["input"]))
        self.assertTrue(any(
            item.role == "developer" and item.content[0].text == "<app>context</app>"
            for item in cleared_plan.request["input"]
        ))
        self.assertIn("<app>context</app>", [item.content[0].text for item in restored_plan.request["input"] if item.role == "developer"])
        self.assertTrue(any(item.role == "user" and item.content[0].text == "restored" for item in restored_plan.request["input"]))

    async def test_build_user_input_op_request_clears_additional_context_when_absent(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        with_context = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context"}},
        )

        await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        first_plan = await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        second_plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),)),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        third_plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(()),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        fourth_plan = await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        def user_texts(plan):
            return [item.content[0].text for item in plan.request["input"] if item.role == "user"]

        self.assertEqual(user_texts(first_plan), [])
        self.assertEqual(user_texts(second_plan), ["hello"])
        self.assertEqual(user_texts(third_plan), ["hello"])
        self.assertEqual(user_texts(fourth_plan), ["hello"])
        additional_context_batches = [
            batch
            for batch in session.recorded
            if batch and batch[0].role == "developer" and batch[0].content[0].text == "<app>context</app>"
        ]
        self.assertEqual(len(additional_context_batches), 2)

    async def test_build_user_turn_request_uses_turn_context_model_info(self) -> None:
        session = Session()
        session.turn_context.model_info = SimpleNamespace(
            slug="gpt-collab",
            input_modalities=("text",),
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        stale_model_info = SimpleNamespace(
            slug="gpt-stale",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            stale_model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(plan.request["model"], "gpt-collab")

    async def test_run_user_turn_sampling_records_sampler_response_items(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 1)
        self.assertIs(seen_requests[0].session, session)
        self.assertIs(seen_requests[0].turn_context, session.turn_context)
        self.assertEqual(result.response_items[0].role, "assistant")
        self.assertEqual(session.recorded[-1], result.response_items)
        self.assertEqual(session.history[-1].content[0].text, "done")
        self.assertEqual(result.last_agent_message, "done")

    async def test_run_user_turn_sampling_user_prompt_submit_hook_blocks_input(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        hook_prompts = []

        async def hook(prompt):
            hook_prompts.append(prompt)
            return HookRuntimeOutcome(should_stop=True, additional_contexts=("blocked by policy",))

        async def sampler(_request):
            raise AssertionError("sampler should not run when user prompt submit hook blocks input")

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(hook_prompts, ["hello"])
        self.assertEqual(result.response_items, ())
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "task_complete"))
        self.assertEqual([item.role for item in session.history], ["developer", "developer"])
        self.assertEqual(session.history[-1].content[0].text, "blocked by policy")
        self.assertFalse(any(item.role == "user" for item in session.history))

    async def test_run_user_turn_sampling_user_prompt_submit_hook_records_context_after_input(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_inputs = []

        def hook(_turn_context, prompt):
            self.assertEqual(prompt, "hello")
            return {"additional_contexts": ("hook context",)}

        async def sampler(request):
            seen_inputs.append(tuple(request.request_plan.prompt.input))
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.last_agent_message, "done")
        self.assertEqual([item.content[0].text for item in session.history[:3]], ["context", "hello", "hook context"])
        self.assertEqual([item.content[0].text for item in seen_inputs[0][:3]], ["context", "hello", "hook context"])

    async def test_run_user_turn_sampling_user_prompt_submit_hook_keyword_only_prompt_blocks_input(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        hook_prompts = []

        async def hook(*, prompt):
            hook_prompts.append(prompt)
            return HookRuntimeOutcome(should_stop=True, additional_contexts=("blocked by policy",))

        async def sampler(_request):
            raise AssertionError("sampler should not run when user prompt submit hook blocks input")

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(hook_prompts, ["hello"])
        self.assertEqual(result.response_items, ())
        self.assertEqual(tuple(item.role for item in session.history[-2:]), ("developer", "developer"))
        self.assertEqual(session.history[-1].content[0].text, "blocked by policy")

    async def test_run_user_turn_sampling_user_prompt_submit_hook_keyword_only_full_signature(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        recorded = []

        async def hook(*, turn_context, user_input, prompt):
            recorded.append((turn_context, len(user_input), prompt))
            return {
                "additional_contexts": ("hook context",),
                "should_stop": False,
            }

        async def sampler(request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.last_agent_message, "done")
        self.assertEqual(recorded[0][0], session.turn_context)
        self.assertEqual(recorded[0][1], 1)
        self.assertEqual(recorded[0][2], "hello")
        self.assertEqual([item.content[0].text for item in session.history[:3]], ["context", "hello", "hook context"])

    async def test_run_user_turn_sampling_emits_turn_lifecycle_events(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.turn_context.trace_id = "trace-1"
        session.turn_context.started_at = 10
        session.turn_context.completed_at = 12
        session.turn_context.duration_ms = 2000
        session.turn_context.time_to_first_token_ms = 250
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            context_window=128000,
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        session.turn_context.model_info = model_info

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "task_complete"))
        started = session.emitted_events[0].payload
        completed = session.emitted_events[1].payload
        self.assertEqual(started.turn_id, "turn-1")
        self.assertEqual(started.trace_id, "trace-1")
        self.assertEqual(started.started_at, 10)
        self.assertEqual(started.model_context_window, 128000)
        self.assertEqual(completed.turn_id, "turn-1")
        self.assertEqual(completed.last_agent_message, "done")
        self.assertEqual(completed.completed_at, 12)
        self.assertEqual(completed.duration_ms, 2000)
        self.assertEqual(completed.time_to_first_token_ms, 250)
        self.assertFalse(session.server_reasoning_included)
        self.assertEqual(result.session_events, tuple(session.emitted_events))

    async def test_run_user_turn_sampling_records_ttft_from_stream_events(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.turn_context.turn_timing_state = TurnTimingState()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-1")

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(final,),
                stream_events=(
                    {"type": "output_item_added", "item": ResponseItem.message("assistant", (), id="msg-1")},
                    {"type": "output_text_delta", "delta": "done"},
                    {"type": "completed", "response_id": "resp-1"},
                ),
            )

        await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        completed = events_of_type(session, "task_complete")[-1].payload
        started = events_of_type(session, "task_started")[-1].payload
        self.assertIsInstance(started.started_at, int)
        self.assertIsInstance(completed.completed_at, int)
        self.assertIsInstance(completed.duration_ms, int)
        self.assertIsInstance(completed.time_to_first_token_ms, int)
        self.assertEqual(started.started_at, session.turn_context.started_at)
        self.assertEqual(completed.completed_at, session.turn_context.completed_at)
        self.assertEqual(completed.duration_ms, session.turn_context.duration_ms)
        self.assertEqual(completed.time_to_first_token_ms, session.turn_context.time_to_first_token_ms)

    async def test_run_user_turn_sampling_records_ttfm_for_agent_message(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.turn_context.turn_timing_state = TurnTimingState()
        session.turn_context.session_telemetry = Telemetry()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-1")

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(final,),
                stream_events=(
                    {"type": "output_item_done", "item": final},
                    {"type": "completed", "response_id": "resp-1"},
                ),
            )

        await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        telemetry = session.turn_context.session_telemetry
        self.assertEqual(len(telemetry.durations), 1)
        metric, duration, tags = telemetry.durations[0]
        self.assertEqual(metric, "codex.turn.ttfm.duration_ms")
        self.assertGreaterEqual(duration.total_seconds(), 0)
        self.assertEqual(tags, ())

    async def test_run_user_turn_sampling_after_agent_abort_emits_error_and_clears_last_message(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        after_agent_calls = []

        async def after_agent_hook(_turn_context, input_messages, last_agent_message):
            after_agent_calls.append((input_messages, last_agent_message))
            return {
                "hook_name": "lint-after-agent",
                "should_abort": True,
                "error": "final answer missing required note",
            }

        session.run_legacy_after_agent_hook = after_agent_hook

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(after_agent_calls, [(("hello",), "done")])
        self.assertEqual(result.response_items[-1].content[0].text, "done")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(
            tuple(event.type for event in session.emitted_events),
            ("task_started", "error", "task_complete"),
        )
        self.assertIn("lint-after-agent", session.emitted_events[1].payload.message)
        self.assertIn("final answer missing required note", session.emitted_events[1].payload.message)
        self.assertIsNone(session.emitted_events[2].payload.last_agent_message)

    async def test_run_user_turn_sampling_after_agent_abort_emits_error_and_clears_last_message_keyword_only(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        after_agent_calls = []

        async def after_agent_hook(*, input_messages, last_agent_message):
            after_agent_calls.append((input_messages, last_agent_message))
            return {
                "hook_name": "lint-after-agent-keyword",
                "should_abort": True,
                "error": "final answer missing required note",
            }

        session.run_legacy_after_agent_hook = after_agent_hook

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(after_agent_calls, [(("hello",), "done")])
        self.assertEqual(result.response_items[-1].content[0].text, "done")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(
            tuple(event.type for event in session.emitted_events),
            ("task_started", "error", "task_complete"),
        )
        self.assertIn("lint-after-agent-keyword", session.emitted_events[1].payload.message)
        self.assertIn("final answer missing required note", session.emitted_events[1].payload.message)
        self.assertIsNone(session.emitted_events[2].payload.last_agent_message)

    async def test_run_user_turn_sampling_returns_streamed_last_agent_message(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        assistant = ResponseItem.message("assistant", (ContentItem.output_text("streamed final"),), id="msg-1")

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(),
                stream_events=(
                    {"type": "output_item_added", "item": ResponseItem.message("assistant", (), id="msg-1")},
                    {"type": "output_text_delta", "delta": "streamed final"},
                    {"type": "output_item_done", "item": assistant},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.response_items, (assistant,))
        self.assertEqual(session.history[-1], assistant)
        self.assertEqual(result.last_agent_message, "streamed final")

    async def test_run_user_turn_sampling_mailbox_preemption_follows_up_after_commentary(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.input_queue = PendingMailboxQueue(True)
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        commentary = ResponseItem.message(
            "assistant",
            (ContentItem.output_text("working"),),
            id="msg-1",
            phase=MessagePhase.COMMENTARY,
        )
        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-2")
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(
                    response_items=(),
                    stream_events=(
                        {"type": "output_item_done", "item": commentary},
                        {"type": "completed", "response_id": "resp-1", "end_turn": True},
                    ),
                )
            return SimpleNamespace(response_items=(final,), stream_events=())

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        first_done_plan = result.stream_event_apply_plans[0].output_item_done_apply_plan
        self.assertEqual(len(seen_requests), 2)
        self.assertIsNotNone(first_done_plan.mailbox_preemption_plan)
        self.assertTrue(first_done_plan.mailbox_preemption_plan.needs_follow_up)
        self.assertEqual(first_done_plan.mailbox_preemption_plan.last_agent_message, "working")
        self.assertEqual(session.input_queue.calls, 1)
        self.assertEqual(result.last_agent_message, "done")

    async def test_run_user_turn_sampling_stop_hook_continuation_prompts_followup(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        stop_hook_calls = []
        stop_hook_outcomes = [
            SimpleNamespace(
                should_block=True,
                continuation_fragments=(HookPromptFragment.from_single_hook("Revise with tests.", "hook-run-1"),),
            ),
            SimpleNamespace(should_block=False, should_stop=True),
        ]

        async def stop_hook(_turn_context, stop_hook_active, last_agent_message):
            stop_hook_calls.append((stop_hook_active, last_agent_message))
            return stop_hook_outcomes.pop(0)

        session.run_turn_stop_hook = stop_hook
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [ResponseItem.message("assistant", (ContentItem.output_text("draft"),))]
            return [ResponseItem.message("assistant", (ContentItem.output_text("final"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(stop_hook_calls, [(False, "draft"), (True, "final")])
        self.assertEqual(result.last_agent_message, "final")
        hook_prompt = seen_requests[1].request_plan.request["input"][-1]
        self.assertEqual(hook_prompt.role, "user")
        self.assertIn("Revise with tests.", hook_prompt.content[0].text)
        self.assertIn("hook-run-1", hook_prompt.content[0].text)
        self.assertEqual(session.history[-1].content[0].text, "final")

    async def test_run_user_turn_sampling_stop_hook_block_without_prompt_warns_and_finishes(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def stop_hook(_turn_context, _stop_hook_active, _last_agent_message):
            return SimpleNamespace(should_block=True, continuation_fragments=())

        session.run_turn_stop_hook = stop_hook
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 1)
        self.assertEqual(result.last_agent_message, "done")
        warning = events_of_type(session, "warning")[-1]
        self.assertEqual(warning.type, "warning")
        self.assertEqual(
            warning.payload.message,
            "Stop hook requested continuation without a prompt; ignoring the block.",
        )

    async def test_run_user_turn_sampling_stop_hook_continuation_prompts_followup_with_keyword_only_signature(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        stop_hook_calls = []
        stop_hook_outcomes = [
            SimpleNamespace(
                should_block=True,
                continuation_fragments=(HookPromptFragment.from_single_hook("Revise with tests.", "hook-run-1"),),
            ),
            SimpleNamespace(should_block=False, should_stop=True),
        ]

        async def stop_hook(*, turn_context, stop_hook_active, last_agent_message):
            stop_hook_calls.append((turn_context, stop_hook_active, last_agent_message))
            return stop_hook_outcomes.pop(0)

        session.run_turn_stop_hook = stop_hook
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [ResponseItem.message("assistant", (ContentItem.output_text("draft"),))]
            return [ResponseItem.message("assistant", (ContentItem.output_text("final"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(stop_hook_calls[0][0], session.turn_context)
        self.assertEqual(
            [(stop_hook_active, last_agent_message) for _, stop_hook_active, last_agent_message in stop_hook_calls],
            [(False, "draft"), (True, "final")],
        )
        self.assertEqual(result.last_agent_message, "final")
        hook_prompt = seen_requests[1].request_plan.request["input"][-1]
        self.assertEqual(hook_prompt.role, "user")
        self.assertIn("Revise with tests.", hook_prompt.content[0].text)
        self.assertIn("hook-run-1", hook_prompt.content[0].text)
        self.assertEqual(session.history[-1].content[0].text, "final")

    async def test_run_user_turn_sampling_forwards_skill_injection_warnings_as_events(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        original_build = turn_runtime.build_skill_injections

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        try:
            turn_runtime.build_skill_injections = lambda _skills: SimpleNamespace(
                items=(),
                warnings=("Detected deprecated skill metadata format.",),
            )
            await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("check"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )
        finally:
            turn_runtime.build_skill_injections = original_build

        warnings = tuple(event.payload.message for event in events_of_type(session, "warning"))
        self.assertIn("Detected deprecated skill metadata format.", warnings)

    async def test_run_user_turn_sampling_forwards_multiple_skill_injection_warnings_in_order(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        original_build = turn_runtime.build_skill_injections
        warning_messages = (
            "Deprecated skill API usage detected.",
            "Skill metadata is missing optional field `short_description`.",
        )

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        try:
            turn_runtime.build_skill_injections = lambda _skills: SimpleNamespace(
                items=(),
                warnings=warning_messages,
            )
            await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("check"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )
        finally:
            turn_runtime.build_skill_injections = original_build

        warnings = tuple(event.payload.message for event in events_of_type(session, "warning"))
        self.assertEqual(warnings, warning_messages)

    async def test_run_user_turn_sampling_tracks_explicit_app_and_plugin_mentions_for_analytics(self) -> None:
        session = Session()
        session.conversation_id = "thread-123"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.config = SimpleNamespace(apps_enabled=True)
        session.turn_context.sub_id = "turn-abc"
        session.available_connectors = (SimpleNamespace(id="app://weather", name="Weather App", is_enabled=True),)

        class FakeAnalytics:
            def __init__(self) -> None:
                self.app_mentions = []
                self.plugin_used = []

            def track_app_mentioned(self, context, mentions):
                self.app_mentions.append((context, tuple(mentions)))

            def track_plugin_used(self, context, payload):
                self.plugin_used.append((context, payload))

        plugin_payload = SimpleNamespace(plugin_id="plugin-weather")
        mentioned_plugin = SimpleNamespace(
            display_name="WeatherPlugin",
            telemetry_metadata=lambda: plugin_payload,
        )
        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        original_collect_app_ids = turn_runtime.collect_explicit_app_ids
        original_collect_plugin_mentions = turn_runtime.collect_explicit_plugin_mentions

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        try:
            turn_runtime.collect_explicit_app_ids = lambda _user_input: ("weather",)
            turn_runtime.collect_explicit_plugin_mentions = (
                lambda _user_input, _plugins: (mentioned_plugin,)
            )
            await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("check"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )
        finally:
            turn_runtime.collect_explicit_app_ids = original_collect_app_ids
            turn_runtime.collect_explicit_plugin_mentions = original_collect_plugin_mentions

        analytics = session.services.analytics_events_client
        self.assertEqual(len(analytics.app_mentions), 1)
        app_context, app_mentions = analytics.app_mentions[0]
        self.assertEqual(len(app_mentions), 1)
        self.assertEqual(app_context["model"], "gpt-test")
        self.assertEqual(app_context["conversation_id"], "thread-123")
        self.assertEqual(app_context["sub_id"], "turn-abc")
        self.assertEqual(app_mentions[0].connector_id, "weather")
        self.assertEqual(app_mentions[0].app_name, "Weather App")
        self.assertEqual(app_mentions[0].invocation_type, "explicit")
        self.assertEqual(len(analytics.plugin_used), 1)
        self.assertIs(analytics.plugin_used[0][1], plugin_payload)

    async def test_run_user_turn_sampling_tracks_prefixed_app_mentions_with_normalization(self) -> None:
        session = Session()
        session.conversation_id = "thread-456"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.config = SimpleNamespace(apps_enabled=True)
        session.turn_context.sub_id = "turn-abc2"
        session.available_connectors = (
            SimpleNamespace(id="app://weather", name="Weather App", is_enabled=True),
        )

        class FakeAnalytics:
            def __init__(self) -> None:
                self.app_mentions = []

            def track_app_mentioned(self, context, mentions):
                self.app_mentions.append((context, tuple(mentions)))

            def track_plugin_used(self, context, payload):
                pass

        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        original_collect_app_ids = turn_runtime.collect_explicit_app_ids
        original_collect_plugin_mentions = turn_runtime.collect_explicit_plugin_mentions

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        try:
            turn_runtime.collect_explicit_app_ids = lambda _user_input: ("app://weather",)
            turn_runtime.collect_explicit_plugin_mentions = lambda _user_input, _plugins: tuple()
            await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("check"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )
        finally:
            turn_runtime.collect_explicit_app_ids = original_collect_app_ids
            turn_runtime.collect_explicit_plugin_mentions = original_collect_plugin_mentions

        analytics = session.services.analytics_events_client
        self.assertEqual(len(analytics.app_mentions), 1)
        app_context, app_mentions = analytics.app_mentions[0]
        self.assertEqual(app_context["conversation_id"], "thread-456")
        self.assertEqual(len(app_mentions), 1)
        self.assertEqual(app_mentions[0].connector_id, "weather")

    async def test_run_user_turn_sampling_tracks_turn_resolved_config_for_analytics(self) -> None:
        session = Session()
        session.conversation_id = "thread-789"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.sub_id = "turn-analytics"

        class FakePolicy:
            def is_enabled(self) -> bool:
                return True

        captured = []

        class FakeAnalytics:
            def track_turn_resolved_config(self, context, payload):
                captured.append((context, payload))

        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())
        session.turn_context.config = SimpleNamespace(
            model_provider_id="openai",
            service_tier="priority",
            approval_policy="on-request",
            approvals_reviewer="reviewer-1",
            permission_profile="perm-profile",
            reasoning_effort="high",
            reasoning_summary="concise",
            personality="pragmatic",
            collaboration_mode="collab",
        )

        thread_config = SimpleNamespace(
            model_provider_id="openai",
            service_tier="priority",
            approval_policy="ask",
            approvals_reviewer="reviewer-1",
            permission_profile="perm-profile",
            ephemeral=True,
            reasoning_effort="high",
            reasoning_summary="concise",
            personality="pragmatic",
            collaboration_mode="collab",
            session_source="cli",
            sandbox_policy=FakePolicy(),
        )

        async def snapshot():
            return thread_config

        async def get_next_turn_is_first():
            return True

        session.thread_config_snapshot = snapshot
        session.take_next_turn_is_first = get_next_turn_is_first
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        await run_user_turn_sampling_from_session(
            session,
            (
                UserInput.text_input("look"),
                UserInput.image("data:image/png;base64,AAAA"),
                UserInput.local_image(Path("photo.png")),
            ),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(captured), 1)
        analytics_context, payload = captured[0]
        self.assertEqual(analytics_context["model"], "gpt-test")
        self.assertEqual(analytics_context["conversation_id"], "thread-789")
        self.assertEqual(analytics_context["sub_id"], "turn-analytics")
        self.assertEqual(payload["turn_id"], "turn-analytics")
        self.assertEqual(payload["thread_id"], "thread-789")
        self.assertEqual(payload["num_input_images"], 2)
        self.assertEqual(payload["submission_type"], None)
        self.assertTrue(payload["ephemeral"])
        self.assertEqual(payload["session_source"], "cli")
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(payload["model_provider"], "openai")
        self.assertEqual(payload["permission_profile"], "perm-profile")
        self.assertEqual(payload["approval_policy"], "on-request")
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["reasoning_summary"], "concise")
        self.assertEqual(payload["service_tier"], "priority")
        self.assertEqual(payload["approvals_reviewer"], "reviewer-1")
        self.assertTrue(payload["sandbox_network_access"])
        self.assertEqual(payload["collaboration_mode"], "collab")
        self.assertEqual(payload["personality"], "pragmatic")
        self.assertTrue(payload["is_first_turn"])

    async def test_run_user_turn_sampling_tracks_turn_resolved_config_from_thread_attr_snapshot(self) -> None:
        session = Session()
        session.conversation_id = "thread-790"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.sub_id = "turn-analytics-thread"
        session.thread = SimpleNamespace(
            thread_config_snapshot=SimpleNamespace(
                model_provider="openai",
                service_tier="standard",
                ephemeral=False,
                permission_profile="thread-profile",
            )
        )
        session.turn_context.config = SimpleNamespace(
            model_provider_id="openai",
            service_tier="standard",
            permission_profile="cfg-perm-profile",
            approvals_reviewer="cfg-reviewer",
            approval_policy="on-request",
            reasoning_effort="minimal",
            reasoning_summary="auto",
            personality="none",
            collaboration_mode="default",
        )

        captured = []

        class FakeAnalytics:
            def track_turn_resolved_config(self, context, payload):
                captured.append((context, payload))

        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("check"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(captured), 1)
        analytics_context, payload = captured[0]
        self.assertEqual(analytics_context["conversation_id"], "thread-790")
        self.assertEqual(payload["turn_id"], "turn-analytics-thread")
        self.assertEqual(payload["thread_id"], "thread-790")
        self.assertEqual(payload["model_provider"], "openai")
        self.assertEqual(payload["service_tier"], "standard")
        self.assertFalse(payload["ephemeral"])
        self.assertEqual(payload["permission_profile"], "cfg-perm-profile")

    async def test_run_user_turn_sampling_tracks_turn_resolved_config_from_thread_callable_snapshot(self) -> None:
        session = Session()
        session.conversation_id = "thread-791"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.sub_id = "turn-analytics-thread-callable"
        thread_snapshot = SimpleNamespace(
            model_provider="openai",
            service_tier="standard",
            ephemeral=True,
            permission_profile="thread-callable-profile",
        )

        captured = []

        class FakeAnalytics:
            def track_turn_resolved_config(self, context, payload):
                captured.append((context, payload))

        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())
        session.turn_context.config = SimpleNamespace(
            model_provider_id="openai",
            service_tier="standard",
            permission_profile="cfg-callable-profile",
            approvals_reviewer="cfg-reviewer",
            approval_policy="on-request",
            reasoning_effort="minimal",
            reasoning_summary="auto",
            personality="none",
            collaboration_mode="default",
        )
        session.thread = SimpleNamespace(
            thread_config_snapshot=lambda: thread_snapshot,
        )

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("check"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(captured), 1)
        analytics_context, payload = captured[0]
        self.assertEqual(analytics_context["conversation_id"], "thread-791")
        self.assertEqual(payload["turn_id"], "turn-analytics-thread-callable")
        self.assertEqual(payload["thread_id"], "thread-791")
        self.assertEqual(payload["model_provider"], "openai")
        self.assertTrue(payload["ephemeral"])
        self.assertEqual(payload["permission_profile"], "cfg-callable-profile")

    async def test_run_user_turn_sampling_tracks_turn_resolved_config_from_turn_context_permission_profile(self) -> None:
        session = Session()
        session.conversation_id = "thread-792"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.sub_id = "turn-analytics-turn-profile"
        thread_config = SimpleNamespace(
            model_provider_id="openai",
            service_tier="standard",
            ephemeral=False,
            permission_profile="thread-profile",
            sandbox_policy=SimpleNamespace(enabled=False),
            session_source="cli",
        )

        class TurnPermissionProfile:
            def network_sandbox_policy(self) -> SimpleNamespace:
                return SimpleNamespace(is_enabled=lambda: True)

            def to_mapping(self) -> str:
                return "turn-profile"

        captured = []

        class FakeAnalytics:
            def track_turn_resolved_config(self, context, payload):
                captured.append((context, payload))

        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())
        session.thread = SimpleNamespace(thread_config_snapshot=lambda: thread_config)
        session.turn_context.config = SimpleNamespace(
            model_provider_id="openai",
            service_tier="standard",
            permission_profile="cfg-profile",
            approval_policy="on-request",
            approvals_reviewer="reviewer-1",
            reasoning_effort="high",
            reasoning_summary="auto",
            personality="none",
            collaboration_mode="default",
            model_reasoning_effort="high",
            model_reasoning_summary="auto",
            model="gpt-test",
        )
        session.turn_context.permission_profile = TurnPermissionProfile()

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("check"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(captured), 1)
        _analytics_context, payload = captured[0]
        self.assertEqual(payload["permission_profile"], "turn-profile")
        self.assertTrue(payload["sandbox_network_access"])

    async def test_run_user_turn_sampling_tracks_turn_resolved_config_from_turn_context_network_sandbox_policy(self) -> None:
        session = Session()
        session.conversation_id = "thread-793"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.sub_id = "turn-analytics-turn-network-policy"
        thread_snapshot = SimpleNamespace(
            model_provider_id="openai",
            service_tier="standard",
            ephemeral=False,
            session_source="cli",
            sandbox_policy=SimpleNamespace(enabled=False),
        )
        captured = []

        class FakeAnalytics:
            def track_turn_resolved_config(self, context, payload):
                captured.append((context, payload))

        class TurnNetworkPolicy:
            def is_enabled(self) -> bool:
                return True

        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())
        session.thread = SimpleNamespace(thread_config_snapshot=lambda: thread_snapshot)
        session.turn_context.config = SimpleNamespace(
            model_provider_id="openai",
            service_tier="standard",
            permission_profile="cfg-profile",
            approval_policy="on-request",
            approvals_reviewer="reviewer-1",
            reasoning_effort="high",
            reasoning_summary="auto",
            personality="none",
            collaboration_mode="default",
            model_reasoning_effort="high",
            model_reasoning_summary="auto",
            model="gpt-test",
        )
        session.turn_context.network_sandbox_policy = TurnNetworkPolicy()

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("check"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(captured), 1)
        _analytics_context, payload = captured[0]
        self.assertEqual(payload["permission_profile"], "cfg-profile")
        self.assertTrue(payload["sandbox_network_access"])

    async def test_run_user_turn_sampling_does_not_track_plugins_without_telemetry_metadata(self) -> None:
        session = Session()
        session.conversation_id = "thread-123"
        session.turn_context.model_info = SimpleNamespace(slug="gpt-test")
        session.turn_context.config = SimpleNamespace(apps_enabled=True)
        session.turn_context.sub_id = "turn-no-plugin-metadata"
        session.available_connectors = ()

        class FakeAnalytics:
            def __init__(self) -> None:
                self.app_mentions = []
                self.plugin_used = []

            def track_app_mentioned(self, context, mentions):
                self.app_mentions.append((context, tuple(mentions)))

            def track_plugin_used(self, context, payload):
                self.plugin_used.append((context, payload))

        plugin_without_metadata = SimpleNamespace(display_name="NoMetaPlugin")
        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        original_collect_app_ids = turn_runtime.collect_explicit_app_ids
        original_collect_plugin_mentions = turn_runtime.collect_explicit_plugin_mentions

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        try:
            turn_runtime.collect_explicit_app_ids = lambda _user_input: tuple()
            turn_runtime.collect_explicit_plugin_mentions = (
                lambda _user_input, _plugins: (plugin_without_metadata,)
            )
            await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("check"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )
        finally:
            turn_runtime.collect_explicit_app_ids = original_collect_app_ids
            turn_runtime.collect_explicit_plugin_mentions = original_collect_plugin_mentions

        analytics = session.services.analytics_events_client
        self.assertEqual(len(analytics.plugin_used), 0)

    async def test_run_user_turn_sampling_projects_sampler_stream_events(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        consumer = DiffConsumer()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([CustomDiffHandler(consumer)]), ())
        custom_call = ResponseItem.custom_tool_call(
            "apply_patch",
            "*** Begin Patch",
            "call-1",
            id="custom-1",
        )
        attempts = []

        async def sampler(_request):
            attempts.append(_request)
            if len(attempts) > 1:
                return SimpleNamespace(
                    response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
                    stream_events=(),
                )
            return SimpleNamespace(
                response_items=(),
                stream_events=(
                    {"type": "output_item_added", "item": custom_call},
                    {
                        "type": "tool_call_input_delta",
                        "item_id": "custom-1",
                        "call_id": "call-1",
                        "delta": "*** Begin Patch",
                    },
                    {"type": "output_item_done", "item": custom_call},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(attempts), 2)
        self.assertEqual(tuple(event["type"] for event in result.stream_events), (
            "output_item_added",
            "tool_call_input_delta",
            "output_item_done",
            "completed",
        ))
        self.assertEqual(
            tuple(plan.event_type for plan in result.stream_event_dispatch_plans),
            (
                "output_item_added",
                "tool_call_input_delta",
                "output_item_done",
                "completed",
            ),
        )
        self.assertEqual(
            tuple(plan.event_type for plan in result.stream_event_apply_plans),
            (
                "output_item_added",
                "tool_call_input_delta",
                "output_item_done",
                "completed",
            ),
        )
        self.assertIsNotNone(result.stream_event_dispatch_plans[0].output_item_added_plan)
        self.assertEqual(
            result.stream_event_dispatch_plans[1].tool_call_input_delta_plan.event,
            {"type": "tool_call_input_delta", "call_id": "call-1", "delta": "*** Begin Patch"},
        )
        self.assertEqual(result.stream_runtime_state_summary["applied_event_types"], (
            "output_item_added",
            "tool_call_input_delta",
            "output_item_done",
            "completed",
        ))
        self.assertEqual(result.stream_runtime_state_summary["completed_response_id"], "resp-1")
        self.assertTrue(result.stream_runtime_state_summary["result_needs_follow_up"])
        self.assertEqual(
            result.stream_runtime_state_summary["tool_call_input_delta_events"],
            (
                {
                    "call_id": "call-1",
                    "delta": "*** Begin Patch",
                    "should_send_event": True,
                    "has_event_to_emit": True,
                },
            ),
        )
        self.assertEqual(
            result.stream_runtime_state_summary["output_item_done_events"][0]["has_finished_tool_input_event"],
            True,
        )
        self.assertIsNone(result.stream_runtime_state_summary["active_tool_argument_diff_consumer"])
        self.assertEqual(consumer.deltas, [(session.turn_context, "call-1", "*** Begin Patch")])
        self.assertEqual(
            tuple(event.type for event in non_lifecycle_events(session)),
            ("tool_call_input_delta", "tool_call_input_done"),
        )
        self.assertEqual(non_lifecycle_events(session)[1].payload, {"call_id": "call-1"})
        self.assertEqual(result.session_events, tuple(session.emitted_events))

    async def test_run_user_turn_sampling_projects_reasoning_stream_events_with_protocol_ids(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        reasoning = ResponseItem.reasoning(id="reason-1")

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
                stream_events=(
                    {"type": "output_item_added", "item": reasoning},
                    {"type": "reasoning_summary_delta", "delta": "summary", "summary_index": 0},
                    {"type": "reasoning_content_delta", "delta": "raw", "content_index": 1},
                    {"type": "reasoning_summary_part_added", "summary_index": 2},
                    {"type": "output_item_done", "item": reasoning},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        emitted = result.stream_runtime_state_summary["emitted_stream_events"]
        self.assertEqual(
            emitted,
            (
                {
                    "type": "reasoning_content_delta",
                    "thread_id": "thread-1",
                    "turn_id": "turn-1",
                    "item_id": "reason-1",
                    "delta": "summary",
                    "summary_index": 0,
                },
                {
                    "type": "reasoning_raw_content_delta",
                    "thread_id": "thread-1",
                    "turn_id": "turn-1",
                    "item_id": "reason-1",
                    "delta": "raw",
                    "content_index": 1,
                },
                {
                    "type": "agent_reasoning_section_break",
                    "item_id": "reason-1",
                    "summary_index": 2,
                },
            ),
        )
        self.assertEqual(EventMsg.from_mapping(emitted[0]).payload.thread_id, "thread-1")
        self.assertEqual(EventMsg.from_mapping(emitted[1]).payload.turn_id, "turn-1")
        self.assertEqual(EventMsg.from_mapping(emitted[2]).payload.summary_index, 2)
        self.assertEqual(
            tuple(event.type for event in non_lifecycle_events(session)),
            (
                "reasoning_content_delta",
                "reasoning_raw_content_delta",
                "agent_reasoning_section_break",
            ),
        )
        reasoning_events = non_lifecycle_events(session)
        self.assertEqual(reasoning_events[0].payload.thread_id, "thread-1")
        self.assertEqual(reasoning_events[1].payload.turn_id, "turn-1")
        self.assertEqual(reasoning_events[2].payload.summary_index, 2)
        self.assertEqual(result.session_events, tuple(session.emitted_events))

    async def test_run_user_turn_sampling_applies_stream_completed_usage_to_session(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.features = FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED)
        session.unified_diff = "diff --git a/file b/file"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        usage = {
            "input_tokens": 5,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 12,
        }

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
                stream_events=(
                    {"type": "completed", "response_id": "resp-1", "token_usage": usage, "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(session.recorded_token_usage), 1)
        self.assertIs(session.recorded_token_usage[0][0], session.turn_context)
        self.assertEqual(session.recorded_token_usage[0][1].input_tokens, 5)
        self.assertEqual(session.recorded_token_usage[0][1].cached_input_tokens, 1)
        self.assertEqual(session.recorded_token_usage[0][1].output_tokens, 7)
        self.assertEqual(session.recorded_token_usage[0][1].reasoning_output_tokens, 2)
        self.assertEqual(session.recorded_token_usage[0][1].total_tokens, 12)
        self.assertEqual(session.token_count_turn_contexts, [session.turn_context])
        self.assertEqual(
            session.tail_calls,
            [
                ("response_processed", "resp-1"),
                ("drain_in_flight",),
                ("token_count", session.turn_context),
                ("turn_diff", "diff --git a/file b/file"),
            ],
        )
        self.assertIsNone(result.stream_runtime_state_summary["token_usage_to_record"])

    async def test_run_user_turn_sampling_applies_raw_response_completed_usage_to_session(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.features = FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED)
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
                stream_events=(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp-raw",
                            "usage": {
                                "input_tokens": 11,
                                "input_tokens_details": {"cached_tokens": 3},
                                "output_tokens": 13,
                                "output_tokens_details": {"reasoning_tokens": 5},
                                "total_tokens": 24,
                            },
                            "end_turn": True,
                        },
                    },
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(session.recorded_token_usage), 1)
        self.assertEqual(session.recorded_token_usage[0][1].input_tokens, 11)
        self.assertEqual(session.recorded_token_usage[0][1].cached_input_tokens, 3)
        self.assertEqual(session.recorded_token_usage[0][1].output_tokens, 13)
        self.assertEqual(session.recorded_token_usage[0][1].reasoning_output_tokens, 5)
        self.assertEqual(session.recorded_token_usage[0][1].total_tokens, 24)
        self.assertEqual(
            session.tail_calls,
            [
                ("response_processed", "resp-raw"),
                ("drain_in_flight",),
                ("token_count", session.turn_context),
            ],
        )
        self.assertEqual(result.stream_runtime_state_summary["completed_response_id"], "resp-raw")
        self.assertIsNone(result.stream_runtime_state_summary["token_usage_to_record"])

    async def test_run_user_turn_sampling_applies_stream_metadata_to_session(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        rate_limits = {"remaining": 10}

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
                stream_events=(
                    {"type": "server_reasoning_included", "server_reasoning_included": True},
                    {"type": "models_etag", "models_etag": "etag-1"},
                    {"type": "rate_limits", "rate_limits": rate_limits},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertTrue(session.server_reasoning_included)
        self.assertEqual(session.models_etags, ["etag-1"])
        self.assertEqual(session.recorded_rate_limits, [rate_limits])
        self.assertEqual(
            session.tail_calls,
            [
                ("drain_in_flight",),
                ("token_count", session.turn_context),
            ],
        )

    async def test_run_user_turn_sampling_applies_stream_server_model_and_verification_metadata(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        verifications = ({"model": "gpt-test", "verified": True},)
        calls = 0

        async def sampler(_request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return SimpleNamespace(
                    response_items=(ResponseItem.function_call("echo", "{}", "call-echo"),),
                    stream_events=(
                        {"type": "server_model", "server_model": "gpt-server"},
                        {"type": "model_verifications", "model_verifications": verifications},
                        {"type": "completed", "response_id": "resp-1", "end_turn": False},
                    ),
                )
            return SimpleNamespace(
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
                stream_events=(
                    {"type": "completed", "response_id": "resp-2", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: ToolRouter.from_parts(ToolRegistry.from_tools([EchoHandler()]), ()),
        )

        self.assertEqual(result.last_agent_message, "done")
        self.assertEqual(calls, 2)
        self.assertEqual(session.server_model_warnings, [(session.turn_context, "gpt-server")])
        self.assertTrue(session.turn_context.server_model_warning_emitted)
        self.assertEqual(session.model_verifications, [(session.turn_context, verifications)])
        self.assertTrue(session.turn_context.model_verification_emitted)
        self.assertEqual(
            tuple(event["event_type"] for event in result.stream_runtime_state_summary["metadata_events"]),
            ("server_model", "model_verifications"),
        )

    async def test_run_user_turn_sampling_prefers_stream_metadata_order_over_raw_metadata(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        verifications = ({"model": "gpt-test", "verified": True},)
        added = ResponseItem.message("assistant", (), id="msg-1")
        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-1")

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(final,),
                model_verifications=verifications,
                stream_events=(
                    {"type": "output_item_added", "item": added},
                    {"type": "output_text_delta", "delta": "streamed"},
                    {"type": "model_verifications", "model_verifications": verifications},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(session.model_verifications, [(session.turn_context, verifications)])
        self.assertIn(("event", "agent_message_content_delta"), session.side_effect_order)
        self.assertIn(("model_verification", verifications), session.side_effect_order)
        self.assertLess(
            session.side_effect_order.index(("event", "agent_message_content_delta")),
            session.side_effect_order.index(("model_verification", verifications)),
        )

    async def test_run_user_turn_sampling_turn_aborted_after_stream_tail_returns_partial_result(self) -> None:
        session = Session()
        session.features = FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED)
        session.unified_diff = "diff --git a/file b/file"
        session.turn_context.cancellation_token = CancellationToken(cancelled=True)
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        assistant = ResponseItem.message("assistant", (ContentItem.output_text("partial"),))

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(assistant,),
                stream_events=(
                    {
                        "type": "completed",
                        "response_id": "resp-1",
                        "token_usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                        "end_turn": True,
                    },
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.response_items, (assistant,))
        self.assertEqual(result.turn_status, "interrupted")
        self.assertEqual(
            session.tail_calls,
            [
                ("response_processed", "resp-1"),
                ("drain_in_flight",),
                ("token_count", session.turn_context),
            ],
        )
        self.assertEqual([event.type for event in session.emitted_events], ["task_started"])
        self.assertEqual(session.recorded_token_usage[0][1].total_tokens, 7)

    async def test_run_user_turn_sampling_turn_aborted_before_sampling_result_returns_interrupted(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            raise CodexErr.simple("turn_aborted")

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "interrupted")
        self.assertEqual(result.response_items, ())
        self.assertEqual(result.raw_results, ())
        self.assertIsNone(result.raw_result)
        self.assertEqual([event.type for event in session.emitted_events], ["task_started"])

    async def test_run_user_turn_sampling_turn_aborted_during_followup_returns_accumulated_interrupted(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        first = ResponseItem.message("assistant", (ContentItem.output_text("partial"),), id="msg-1")

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(
                    response_items=(first,),
                    stream_events=(
                        {"type": "completed", "response_id": "resp-1", "end_turn": False},
                    ),
                )
            raise CodexErr.simple("turn_aborted")

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(result.turn_status, "interrupted")
        self.assertEqual(result.response_items, (first,))
        self.assertEqual(len(result.request_plans), 2)
        self.assertEqual(len(result.raw_results), 1)
        self.assertEqual([event.type for event in session.emitted_events], ["task_started"])

    async def test_run_user_turn_sampling_emits_assistant_text_stream_deltas(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        assistant = ResponseItem.message(
            "assistant",
            (ContentItem.output_text("hello"),),
            id="msg-1",
        )

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(assistant,),
                stream_events=(
                    {"type": "output_item_added", "item": ResponseItem.message("assistant", (), id="msg-1")},
                    {"type": "output_text_delta", "delta": "hello"},
                    {"type": "output_item_done", "item": assistant},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(
            result.stream_runtime_state_summary["assistant_text_deltas"],
            (
                {
                    "item_id": "msg-1",
                    "visible_text_delta": "hello",
                    "has_plan_segments_plan": False,
                    "citations": (),
                    "ignored_citations": False,
                    "event_to_emit": {
                        "type": "agent_message_content_delta",
                        "thread_id": "thread-1",
                        "turn_id": "turn-1",
                        "item_id": "msg-1",
                        "delta": "hello",
                    },
                },
            ),
        )
        delta_events = events_of_type(session, "agent_message_content_delta")
        self.assertEqual(tuple(event.type for event in delta_events), ("agent_message_content_delta",))
        self.assertEqual(delta_events[0].payload.thread_id, "thread-1")
        self.assertEqual(delta_events[0].payload.turn_id, "turn-1")
        self.assertEqual(delta_events[0].payload.delta, "hello")

    async def test_run_user_turn_sampling_parses_streamed_citations_across_boundaries(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        assistant = ResponseItem.message(
            "assistant",
            (ContentItem.output_text("hello <oai-mem-citation>doc</oai-mem-citation> world"),),
            id="msg-1",
        )

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(assistant,),
                stream_events=(
                    {
                        "type": "output_item_added",
                        "item": ResponseItem.message(
                            "assistant",
                            (ContentItem.output_text("hello <oai-mem-"),),
                            id="msg-1",
                        ),
                    },
                    {"type": "output_text_delta", "delta": "citation>doc</oai-mem-citation> world"},
                    {"type": "output_item_done", "item": assistant},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(tuple(event.payload.delta for event in events_of_type(session, "agent_message_content_delta")), (" world",))
        self.assertEqual(result.stream_runtime_state_summary["assistant_text_deltas"][0]["citations"], ("doc",))

    async def test_run_user_turn_sampling_routes_plan_mode_segments_to_plan_events(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.turn_context.collaboration_mode = SimpleNamespace(mode="plan")
        client = ModelClient(
            session_id="session",
            thread_id="019e7f56-8d12-7a72-bc3a-50921c618fe7",
            installation_id="install",
        )
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        assistant = ResponseItem.message(
            "assistant",
            (ContentItem.output_text("<proposed_plan>\n- step\n</proposed_plan>\n"),),
            id="msg-1",
        )

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(assistant,),
                stream_events=(
                    {"type": "output_item_added", "item": ResponseItem.message("assistant", (), id="msg-1")},
                    {"type": "output_text_delta", "delta": "<proposed_plan>\n"},
                    {"type": "output_text_delta", "delta": "- step\n"},
                    {"type": "output_text_delta", "delta": "</proposed_plan>\n"},
                    {"type": "output_item_done", "item": assistant},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(
            tuple(event.type for event in non_lifecycle_events(session)),
            ("item_started", "plan_delta", "item_completed"),
        )
        plan_events = non_lifecycle_events(session)
        self.assertEqual(plan_events[0].payload.item.id(), "turn-1-plan")
        self.assertEqual(plan_events[1].payload.delta, "- step\n")
        self.assertEqual(plan_events[2].payload.item.item.text, "\n- step\n")
        self.assertTrue(result.stream_runtime_state_summary["plan_item_completed"])

    async def test_run_user_turn_sampling_completes_plan_mode_item_without_plan_deltas(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.turn_context.collaboration_mode = SimpleNamespace(mode="plan")
        thread_id = "019e7f56-8d12-7a72-bc3a-50921c618fe7"
        client = ModelClient(session_id="session", thread_id=thread_id, installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        assistant = ResponseItem.message(
            "assistant",
            (ContentItem.output_text("<proposed_plan>\n- final\n</proposed_plan>\n"),),
            id="msg-1",
        )

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(assistant,),
                stream_events=(
                    {"type": "output_item_added", "item": ResponseItem.message("assistant", (), id="msg-1")},
                    {"type": "output_item_done", "item": assistant},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        plan_events = non_lifecycle_events(session)
        self.assertEqual(tuple(event.type for event in plan_events), ("item_started", "item_completed"))
        self.assertEqual(str(plan_events[0].payload.thread_id), thread_id)
        self.assertEqual(plan_events[0].payload.turn_id, "turn-1")
        self.assertEqual(plan_events[0].payload.item.id(), "turn-1-plan")
        self.assertEqual(plan_events[1].payload.item.item.text, "\n- final\n")
        self.assertTrue(result.stream_runtime_state_summary["plan_item_completed"])

    async def test_run_user_turn_sampling_emits_non_agent_output_text_deltas(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        reasoning = ResponseItem.reasoning(id="reason-1")

        async def sampler(_request):
            return SimpleNamespace(
                response_items=(reasoning, ResponseItem.message("assistant", (ContentItem.output_text("done"),))),
                stream_events=(
                    {"type": "output_item_added", "item": reasoning},
                    {"type": "output_text_delta", "delta": "thinking"},
                    {"type": "output_item_done", "item": reasoning},
                    {"type": "completed", "response_id": "resp-1", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(
            result.stream_runtime_state_summary["raw_content_deltas"],
            (
                {
                    "item_id": "reason-1",
                    "raw_content_delta": "thinking",
                    "event_to_emit": {
                        "type": "agent_message_content_delta",
                        "thread_id": "thread-1",
                        "turn_id": "turn-1",
                        "item_id": "reason-1",
                        "delta": "thinking",
                    },
                },
            ),
        )
        delta_events = events_of_type(session, "agent_message_content_delta")
        self.assertEqual(tuple(event.type for event in delta_events), ("agent_message_content_delta",))
        self.assertEqual(delta_events[0].payload.item_id, "reason-1")
        self.assertEqual(delta_events[0].payload.delta, "thinking")

    async def test_run_user_turn_sampling_marks_context_window_full_on_terminal_error(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            raise CodexErr.simple("context_window_exceeded")

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        self.assertIs(session.total_tokens_full_turn_context, session.turn_context)
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "error", "task_complete"))
        self.assertEqual(events_of_type(session, "error")[-1].payload.codex_error_info.type, "context_window_exceeded")
        self.assertIsNone(events_of_type(session, "task_complete")[-1].payload.last_agent_message)

    async def test_run_user_turn_sampling_records_usage_limit_rate_limits_on_terminal_error(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        rate_limits = RateLimitSnapshot(
            limit_id="codex",
            primary=RateLimitWindow(used_percent=100.0, window_minutes=60),
        )

        async def sampler(_request):
            raise CodexErr.usage_limit_reached(UsageLimitReachedError(rate_limits=rate_limits))

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(session.updated_rate_limits, [(session.turn_context, rate_limits)])
        self.assertIn({"type": "usage_limit_reached", "turn_context": session.turn_context}, session.goal_runtime_events)
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "error", "task_complete"))
        self.assertEqual(events_of_type(session, "error")[-1].payload.codex_error_info.type, "usage_limit_exceeded")
        self.assertIsNone(events_of_type(session, "task_complete")[-1].payload.last_agent_message)

    async def test_run_user_turn_sampling_goal_runtime_usage_limit_errors_are_best_effort(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def goal_runtime_apply(_event):
            raise RuntimeError("goal runtime unavailable")

        session.goal_runtime_apply = goal_runtime_apply

        async def sampler(_request):
            raise CodexErr.simple("quota_exceeded")

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "error", "task_complete"))
        self.assertEqual(events_of_type(session, "error")[-1].payload.codex_error_info.type, "usage_limit_exceeded")

    async def test_run_user_turn_sampling_retries_retryable_stream_error(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(
            is_azure_responses_endpoint=lambda: False,
            info=lambda: SimpleNamespace(stream_max_retries=lambda: 2),
        )
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        session.turn_context.model_info = model_info
        attempts = []

        async def sampler(request):
            attempts.append(request)
            if len(attempts) == 1:
                raise CodexErr.stream("dropped SSE", retry_after=0)
            return [ResponseItem.message("assistant", (ContentItem.output_text("retry ok"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(attempts), 2)
        self.assertEqual(result.last_agent_message, "retry ok")
        self.assertEqual(result.response_items[0].content[0].text, "retry ok")
        self.assertEqual(len(session.stream_errors), 1)
        self.assertEqual(session.stream_errors[0][1], "Reconnecting... 1/2")
        self.assertIs(session.stream_errors[0][0], session.turn_context)
        self.assertEqual(str(session.stream_errors[0][2]), "stream disconnected before completion: dropped SSE")
        self.assertEqual(session.retry_sleeps, [0.0])
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "task_complete"))

    async def test_run_user_turn_sampling_falls_back_to_http_after_retry_limit(self) -> None:
        session = Session()

        class FallbackModelClient:
            def __init__(self) -> None:
                self.websocket_enabled = True
                self.fallback_calls = []

            def responses_websocket_enabled(self) -> bool:
                return self.websocket_enabled

            def force_http_fallback(self, session_telemetry=None, model_info=None) -> bool:
                self.fallback_calls.append((session_telemetry, model_info))
                was_enabled = self.websocket_enabled
                self.websocket_enabled = False
                return was_enabled

        fallback_client = FallbackModelClient()
        session.services = SimpleNamespace(model_client=fallback_client)
        session.turn_context.session_telemetry = SimpleNamespace(counter=lambda *_args: None)
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(
            is_azure_responses_endpoint=lambda: False,
            info=lambda: SimpleNamespace(stream_max_retries=lambda: 1),
        )
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        session.turn_context.model_info = model_info
        attempts = []

        async def sampler(request):
            attempts.append(request)
            if len(attempts) <= 2:
                raise CodexErr.stream("websocket dropped", retry_after=0)
            return [ResponseItem.message("assistant", (ContentItem.output_text("fallback ok"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(attempts), 3)
        self.assertEqual(result.last_agent_message, "fallback ok")
        self.assertFalse(fallback_client.responses_websocket_enabled())
        self.assertEqual(fallback_client.fallback_calls, [(session.turn_context.session_telemetry, model_info)])
        self.assertEqual(session.retry_sleeps, [0.0])
        self.assertEqual(session.stream_errors[0][1], "Reconnecting... 1/1")
        warnings = events_of_type(session, "warning")
        self.assertEqual(len(warnings), 1)
        self.assertIn("Falling back from WebSockets to HTTPS transport.", warnings[0].payload.message)

    async def test_run_user_turn_sampling_dispatches_and_records_tool_outputs(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [ResponseItem.function_call("echo", "{}", "call-echo")]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done after tool"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertTrue(
            any(
                item.type == "function_call_output" and item.call_id == "call-echo"
                for item in seen_requests[1].request_plan.request["input"]
            )
        )
        self.assertEqual(len(handler.invocations), 1)
        self.assertIs(handler.invocations[0].session, session)
        self.assertIs(handler.invocations[0].turn, session.turn_context)
        self.assertEqual(result.response_items[0].type, "function_call")
        self.assertEqual(result.response_items[1].content[0].text, "done after tool")
        self.assertEqual(result.tool_response_items[0].type, "function_call_output")
        self.assertEqual(result.tool_response_items[0].call_id, "call-echo")
        self.assertEqual(session.recorded[-2], result.tool_response_items)
        self.assertEqual(session.history[-1].content[0].text, "done after tool")
        self.assertEqual(len(result.request_plans), 2)

    async def test_run_user_turn_sampling_default_session_exec_command_uses_unified_exec_manager(self) -> None:
        cwd = Path.cwd()
        session = InMemoryCodexSession(
            cwd=cwd,
            environments=(TurnEnvironmentSelection("local", str(cwd)),),
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        command = shell_join_for_test(
            [
                sys.executable,
                "-c",
                "print('tool managed output')",
            ]
        )
        exec_args = {"cmd": command, "yield_time_ms": 1_000}
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [
                    ResponseItem.function_call(
                        "exec_command",
                        json.dumps(exec_args),
                        "call-exec",
                    )
                ]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done after exec"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("run the command"),),
            client,
            provider,
            model_info,
            sampler,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(result.last_agent_message, "done after exec")
        self.assertEqual(len(result.tool_response_items), 1)
        tool_output = result.tool_response_items[0]
        self.assertEqual(tool_output.type, "function_call_output")
        self.assertEqual(tool_output.call_id, "call-exec")
        output_text = tool_output.output.body.text
        self.assertIn("tool managed output", output_text)
        self.assertIn("Process exited with code 0", output_text)
        self.assertEqual(session.services.unified_exec_manager.process_count(), 0)

    async def test_run_user_turn_sampling_default_session_exec_command_then_write_stdin(self) -> None:
        cwd = Path.cwd()
        session = InMemoryCodexSession(
            cwd=cwd,
            environments=(TurnEnvironmentSelection("local", str(cwd)),),
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "interactive_exec.py"
            script_path.write_text(
                "import sys\n"
                "print('ready', flush=True)\n"
                "line = sys.stdin.readline()\n"
                "print('got:' + line.strip(), flush=True)\n",
                encoding="utf-8",
            )
            command = shell_join_for_test([sys.executable, str(script_path)])

            async def sampler(request):
                seen_requests.append(request)
                if len(seen_requests) == 1:
                    return [
                        ResponseItem.function_call(
                            "exec_command",
                            json.dumps({"cmd": command, "tty": True, "yield_time_ms": 1_000}),
                            "call-exec-live",
                        )
                    ]
                if len(seen_requests) == 2:
                    return [
                        ResponseItem.function_call(
                            "write_stdin",
                            json.dumps({"session_id": 1000, "chars": "hello\n", "yield_time_ms": 1_000}),
                            "call-stdin",
                        )
                    ]
                return [ResponseItem.message("assistant", (ContentItem.output_text("done after stdin"),))]

            result = await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("run the interactive command"),),
                client,
                provider,
                model_info,
                sampler,
            )

        self.assertEqual(len(seen_requests), 3)
        self.assertEqual(result.last_agent_message, "done after stdin")
        self.assertEqual(tuple(item.call_id for item in result.tool_response_items), ("call-exec-live", "call-stdin"))
        initial_output = result.tool_response_items[0].output.body.text
        followup_output = result.tool_response_items[1].output.body.text
        self.assertIn("ready", initial_output)
        self.assertIn("Process running with session ID 1000", initial_output)
        self.assertIn("got:hello", followup_output)
        self.assertIn("Process exited with code 0", followup_output)
        self.assertEqual(session.services.unified_exec_manager.process_count(), 0)
        terminal_events = [event for event in session.emitted_events if event.type == "terminal_interaction"]
        self.assertEqual(len(terminal_events), 1)
        self.assertEqual(terminal_events[0].payload.process_id, "1000")
        self.assertEqual(terminal_events[0].payload.stdin, "hello\n")
        self.assertEqual(terminal_events[0].payload.call_id, "call-exec-live")

    async def test_run_user_turn_sampling_dispatches_parallel_tool_calls_concurrently_and_groups_outputs(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = ParallelEchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [
                    ResponseItem.function_call("parallel_echo", "{}", "call-1"),
                    ResponseItem.function_call("parallel_echo", "{}", "call-2"),
                    ResponseItem.function_call("parallel_echo", "{}", "call-3"),
                ]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done after tools"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(handler.started, ["call-1", "call-2", "call-3"])
        self.assertFalse(handler.timed_out_waiting_for_parallel_peer)
        self.assertEqual(tuple(item.call_id for item in result.tool_response_items), ("call-1", "call-2", "call-3"))
        follow_up_input = seen_requests[1].request_plan.request["input"]
        function_call_indexes = [
            index
            for index, item in enumerate(follow_up_input)
            if item.type == "function_call"
        ]
        output_indexes = [
            index
            for index, item in enumerate(follow_up_input)
            if item.type == "function_call_output"
        ]
        self.assertEqual(len(function_call_indexes), 3)
        self.assertEqual(len(output_indexes), 3)
        self.assertLess(max(function_call_indexes), min(output_indexes))
        self.assertEqual(
            tuple(follow_up_input[index].call_id for index in function_call_indexes),
            tuple(follow_up_input[index].call_id for index in output_indexes),
        )

    async def test_run_user_turn_sampling_runs_pre_sampling_auto_compact_before_recording_input(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        compact_calls = []

        async def auto_compact_token_status(_turn_context):
            return {"token_limit_reached": True}

        async def run_auto_compact(turn_context, *, initial_context_injection, reason, phase):
            compact_calls.append(
                (
                    turn_context,
                    initial_context_injection,
                    reason,
                    phase,
                    session.context_recorded,
                    tuple(item.type for item in session.history),
                )
            )

        session.auto_compact_token_status = auto_compact_token_status
        session.run_auto_compact = run_auto_compact

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.response_items[-1].content[0].text, "done")
        self.assertEqual(
            compact_calls,
            [
                (
                    session.turn_context,
                    "do_not_inject",
                    "context_limit",
                    "pre_turn",
                    False,
                    ("message",),
                )
            ],
        )
        self.assertTrue(session.context_recorded)

    async def test_run_user_turn_sampling_pre_sampling_auto_compact_error_completes_before_input_recording(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        sampler_calls = []

        async def auto_compact_token_status(_turn_context):
            return SimpleNamespace(token_limit_reached=True)

        async def run_auto_compact(_turn_context, **_kwargs):
            raise CodexErr.usage_limit_reached(UsageLimitReachedError())

        async def sampler(request):
            sampler_calls.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("unreachable"),))]

        session.auto_compact_token_status = auto_compact_token_status
        session.run_auto_compact = run_auto_compact

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(sampler_calls, [])
        self.assertFalse(session.context_recorded)
        self.assertEqual(tuple(item.type for item in session.history), ("message",))
        self.assertEqual(session.turn_error_lifecycle[0][1].type, "usage_limit_exceeded")
        self.assertIn({"type": "usage_limit_reached", "turn_context": session.turn_context}, session.goal_runtime_events)
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "task_complete"))
        self.assertEqual(result.request_plans, ())

    async def test_run_user_turn_sampling_runs_mid_turn_auto_compact_before_followup(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []
        compact_calls = []
        token_statuses = [
            SimpleNamespace(token_limit_reached=False),
            SimpleNamespace(token_limit_reached=True),
            SimpleNamespace(token_limit_reached=False),
        ]

        async def auto_compact_token_status(_turn_context):
            return token_statuses.pop(0)

        async def run_auto_compact(turn_context, *, initial_context_injection, reason, phase):
            compact_calls.append((turn_context, initial_context_injection, reason, phase))

        session.auto_compact_token_status = auto_compact_token_status
        session.run_auto_compact = run_auto_compact

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [ResponseItem.function_call("echo", "{}", "call-echo")]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done after compact"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(result.response_items[-1].content[0].text, "done after compact")
        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(
            compact_calls,
            [(session.turn_context, "before_last_user_message", "context_limit", "mid_turn")],
        )

    async def test_run_user_turn_sampling_mid_turn_auto_compact_usage_limit_completes_without_error_event(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []

        token_statuses = [{"token_limit_reached": False}, {"token_limit_reached": True}]

        async def auto_compact_token_status(_turn_context):
            return token_statuses.pop(0)

        async def run_auto_compact(_turn_context, **_kwargs):
            raise CodexErr.usage_limit_reached(UsageLimitReachedError())

        session.auto_compact_token_status = auto_compact_token_status
        session.run_auto_compact = run_auto_compact

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.function_call("echo", "{}", "call-echo")]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(len(seen_requests), 1)
        self.assertEqual(session.turn_error_lifecycle[0][1].type, "usage_limit_exceeded")
        self.assertIn({"type": "usage_limit_reached", "turn_context": session.turn_context}, session.goal_runtime_events)
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("task_started", "task_complete"))
        self.assertIsNone(events_of_type(session, "task_complete")[-1].payload.last_agent_message)

    async def test_run_user_turn_sampling_maps_fatal_tool_error_to_codex_err(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        router = ToolRouter.from_parts(ToolRegistry.from_tools([FatalHandler()]), ())

        async def sampler(_request):
            return [ResponseItem.function_call("fatal_tool", "{}", "call-fatal")]

        with self.assertRaises(CodexErr) as caught:
            await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: router,
            )

        self.assertEqual(caught.exception.kind, "fatal")
        self.assertIn("tool exploded", str(caught.exception))
        self.assertEqual(session.history[-1].type, "function_call")

    async def test_run_user_turn_sampling_responds_to_bad_tool_search_arguments(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        router = ToolRouter.from_parts(ToolRegistry.from_tools([]), ())
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [
                    ResponseItem.tool_search_call(
                        {"limit": 3},
                        call_id="search-bad",
                        execution="client",
                    )
                ]
            return [ResponseItem.message("assistant", (ContentItem.output_text("recovered"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(result.response_items[-1].content[0].text, "recovered")
        self.assertEqual(result.tool_response_items[0].type, "function_call_output")
        self.assertEqual(result.tool_response_items[0].call_id, "")
        self.assertIn("failed to parse tool_search arguments", result.tool_response_items[0].output.to_text())
        self.assertEqual(session.recorded[-2], result.tool_response_items)
        followup_input = seen_requests[1].request_plan.request["input"]
        self.assertFalse(any(item.type == "function_call_output" and item.call_id == "" for item in followup_input))
        tool_search_outputs = [item for item in followup_input if item.type == "tool_search_output"]
        self.assertEqual(len(tool_search_outputs), 1)
        self.assertEqual(tool_search_outputs[0].call_id, "search-bad")
        self.assertEqual(tool_search_outputs[0].execution, "client")
        self.assertEqual(tool_search_outputs[0].tools, ())

    async def test_run_user_turn_sampling_records_stream_bad_tool_search_arguments(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        router = ToolRouter.from_parts(ToolRegistry.from_tools([]), ())
        seen_requests = []
        bad_call = ResponseItem.tool_search_call(
            {"limit": 3},
            call_id="search-stream-bad",
            execution="client",
        )
        final = ResponseItem.message("assistant", (ContentItem.output_text("recovered"),), id="msg-2")

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(
                    response_items=(),
                    stream_events=(
                        {"type": "output_item_done", "item": bad_call},
                        {"type": "completed", "response_id": "resp-1", "end_turn": True},
                    ),
                )
            return SimpleNamespace(response_items=(final,), stream_events=())

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(result.response_items, (final,))
        self.assertEqual(len(result.tool_response_items), 1)
        self.assertEqual(result.tool_response_items[0].type, "function_call_output")
        self.assertIn("failed to parse tool_search arguments", result.tool_response_items[0].output.to_text())
        followup_input = seen_requests[1].request_plan.request["input"]
        self.assertIn(bad_call, followup_input)
        tool_search_outputs = [item for item in followup_input if item.type == "tool_search_output"]
        self.assertEqual(len(tool_search_outputs), 1)
        self.assertEqual(tool_search_outputs[0].call_id, "search-stream-bad")
        self.assertEqual(tool_search_outputs[0].execution, "client")
        self.assertEqual(tool_search_outputs[0].tools, ())

    async def test_run_user_turn_sampling_can_limit_tool_followups(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())

        async def sampler(_request):
            return [ResponseItem.function_call("echo", "{}", "call-echo")]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
            max_tool_followups=0,
        )

        self.assertEqual(len(handler.invocations), 1)
        self.assertEqual(len(result.request_plans), 1)
        self.assertEqual(result.response_items[0].type, "function_call")
        self.assertEqual(result.tool_response_items[0].type, "function_call_output")

    async def test_run_user_turn_sampling_default_followups_continue_until_final_answer(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) <= 10:
                return [ResponseItem.function_call("echo", "{}", f"call-echo-{len(seen_requests)}")]
            return [ResponseItem.message("assistant", (ContentItem.output_text("finally done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(seen_requests), 11)
        self.assertEqual(len(handler.invocations), 10)
        self.assertEqual(result.response_items[-1].content[0].text, "finally done")
        self.assertEqual(len(result.tool_response_items), 10)
        self.assertEqual(len(result.request_plans), 11)

    async def test_run_user_turn_sampling_dispatches_stream_only_tool_call(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []
        tool_call = ResponseItem.function_call("echo", "{}", "call-stream")
        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-2")

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(
                    response_items=(),
                    stream_events=(
                        {"type": "output_item_done", "item": tool_call},
                        {"type": "completed", "response_id": "resp-1", "end_turn": True},
                    ),
                )
            return SimpleNamespace(
                response_items=(final,),
                stream_events=(
                    {"type": "completed", "response_id": "resp-2", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(handler.invocations), 1)
        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(result.response_items, (final,))
        self.assertEqual(len(result.tool_response_items), 1)
        self.assertEqual(result.tool_response_items[0].type, "function_call_output")
        self.assertEqual(result.tool_response_items[0].call_id, "call-stream")
        followup_input = seen_requests[1].request_plan.request["input"]
        self.assertIn(tool_call, followup_input)
        self.assertIn(result.tool_response_items[0], followup_input)

    async def test_run_user_turn_sampling_replaces_invalid_tool_output_image_and_retries(self) -> None:
        session = Session()
        tool_output = ResponseItem(
            type="function_call_output",
            call_id="call-image",
            output=FunctionCallOutputPayload.from_content_items(
                (
                    FunctionCallOutputContentItem.input_image(
                        "data:image/png;base64,AAA",
                    ),
                ),
                success=True,
            ),
        )
        session.history.extend(
            (
                ResponseItem.message("user", (ContentItem.input_text("see image"),)),
                ResponseItem.function_call("view_image", "{}", "call-image"),
                tool_output,
            )
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            input_modalities=("text", "image"),
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                raise CodexErr.simple("invalid_image_request")
            return [ResponseItem.message("assistant", (ContentItem.output_text("recovered"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        retry_input = result.request_plans[1].request["input"]
        retry_output = next(item for item in retry_input if item.type == "function_call_output")
        self.assertEqual(retry_output.output.body.content_items[0].type, "input_text")
        self.assertEqual(retry_output.output.body.content_items[0].text, "Invalid image")
        self.assertEqual(session.history[-2].output.body.content_items[0].text, "Invalid image")
        self.assertEqual(result.response_items[-1].content[0].text, "recovered")

    async def test_run_user_turn_sampling_invalid_user_image_emits_bad_request_and_completes(self) -> None:
        session = Session()
        session.history.append(
            ResponseItem.message(
                "user",
                (ContentItem.input_image("data:image/png;base64,AAA"),),
            )
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            input_modalities=("text", "image"),
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(_request):
            raise CodexErr.simple("invalid_image_request")

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertEqual(result.response_items, ())
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(session.history[-1].content[0].type, "input_image")
        error = events_of_type(session, "error")[-1]
        self.assertEqual(error.type, "error")
        self.assertEqual(error.payload.codex_error_info.type, "bad_request")

    async def test_run_user_turn_sampling_followup_invalid_user_image_preserves_accumulated_result(self) -> None:
        session = Session()
        session.history.append(
            ResponseItem.message(
                "user",
                (ContentItem.input_image("data:image/png;base64,AAA"),),
            )
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            input_modalities=("text", "image"),
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        first_response = ResponseItem.message("assistant", (ContentItem.output_text("partial"),))
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(response_items=(first_response,), end_turn=False)
            raise CodexErr.simple("invalid_image_request")

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(result.turn_status, "completed")
        self.assertEqual(result.response_items, (first_response,))
        self.assertEqual(result.last_agent_message, "partial")
        error = events_of_type(session, "error")[-1]
        self.assertEqual(error.type, "error")
        self.assertEqual(error.payload.codex_error_info.type, "bad_request")

    async def test_run_user_turn_sampling_drains_pending_input_before_followup(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                session.input_queue.items.append(UserInput.text_input("steer while running"))
                return [ResponseItem.message("assistant", (ContentItem.output_text("first answer"),))]
            return [ResponseItem.message("assistant", (ContentItem.output_text("final answer"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(len(result.request_plans), 2)
        followup_input = result.request_plans[1].request["input"]
        followup_texts = [
            item.content[0].text
            for item in followup_input
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertIn("steer while running", followup_texts)
        self.assertEqual(result.response_items[-1].content[0].text, "final answer")
        self.assertEqual(session.input_queue.calls, 2)
        self.assertEqual(session.input_queue.active_turns, [session.active_turn, session.active_turn])

    async def test_run_user_turn_sampling_compacts_before_draining_pending_only_followup(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        compact_history_texts = []
        token_statuses = [
            SimpleNamespace(token_limit_reached=False),
            SimpleNamespace(token_limit_reached=True),
            SimpleNamespace(token_limit_reached=False),
        ]

        async def auto_compact_token_status(_turn_context):
            return token_statuses.pop(0)

        async def run_auto_compact(_turn_context, **_kwargs):
            compact_history_texts.append(
                tuple(
                    item.content[0].text
                    for item in session.history
                    if getattr(item, "type", None) == "message" and getattr(item, "content", None)
                )
            )

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                session.input_queue.items.append(UserInput.text_input("pending steer"))
                return [ResponseItem.message("assistant", (ContentItem.output_text("first answer"),))]
            return [ResponseItem.message("assistant", (ContentItem.output_text("final answer"),))]

        session.auto_compact_token_status = auto_compact_token_status
        session.run_auto_compact = run_auto_compact

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(compact_history_texts, [("context", "hello", "first answer")])
        followup_texts = [
            item.content[0].text
            for item in seen_requests[1].request_plan.request["input"]
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertIn("pending steer", followup_texts)
        self.assertEqual(result.response_items[-1].content[0].text, "final answer")

    async def test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                session.input_queue.items.append(UserInput.text_input("pending steer"))
                return [ResponseItem.message("assistant", (ContentItem.output_text("first"),))]
            return [ResponseItem.message("assistant", (ContentItem.output_text("second"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
            max_tool_followups=0,
        )

        self.assertEqual(len(seen_requests), 2)
        followup_input = result.request_plans[1].request["input"]
        followup_texts = [
            item.content[0].text
            for item in followup_input
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertIn("pending steer", followup_texts)
        self.assertEqual(result.response_items[-1].content[0].text, "second")

    async def test_run_user_turn_sampling_empty_input_drains_pending_before_first_request(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        session.input_queue.items.append(UserInput.text_input("queued first"))
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 1)
        self.assertEqual(len(result.request_plans), 1)
        first_request_texts = [
            item.content[0].text
            for item in seen_requests[0].request_plan.request["input"]
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertIn("queued first", first_request_texts)
        self.assertEqual(result.last_agent_message, "done")

    async def test_run_user_turn_sampling_empty_input_pending_hook_blocks_first_request(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        session.input_queue.items.append(UserInput.text_input("blocked first"))
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        def hook(prompt):
            self.assertEqual(prompt, "blocked first")
            return HookRuntimeOutcome(should_stop=True, additional_contexts=("blocked before sampling",))

        async def sampler(_request):
            raise AssertionError("sampler should not run when pre-sampling pending input is blocked")

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.response_items, ())
        history_texts = [
            item.content[0].text
            for item in session.history
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertIn("blocked before sampling", history_texts)
        self.assertNotIn("blocked first", history_texts)

    async def test_run_user_turn_sampling_empty_input_pending_input_uses_active_turn(self) -> None:
        session = Session()
        session.input_queue = StrictActiveTurnInputQueue()
        session.input_queue.items.append(UserInput.text_input("queued first with active turn"))
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(result.request_plans), 1)
        self.assertGreaterEqual(len(session.input_queue.active_turns), 2)
        self.assertTrue(all(value is session.active_turn for value in session.input_queue.active_turns))
        self.assertEqual(result.last_agent_message, "done")

    async def test_run_user_turn_sampling_empty_input_pending_input_uses_active_turn_with_keyword_only_queue(self) -> None:
        session = Session()
        session.input_queue = KeywordOnlyActiveTurnInputQueue()
        session.input_queue.items.append(UserInput.text_input("queued first with keyword-only active turn"))
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        async def sampler(request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(result.request_plans), 1)
        self.assertTrue(session.input_queue.active_turns)
        self.assertTrue(all(value is session.active_turn for value in session.input_queue.active_turns))
        self.assertEqual(result.last_agent_message, "done")

    async def test_run_user_turn_sampling_pending_input_hook_records_context_after_input(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        hook_prompts = []

        def hook(prompt):
            hook_prompts.append(prompt)
            if prompt == "pending steer":
                return HookRuntimeOutcome(additional_contexts=("pending context",))
            return HookRuntimeOutcome()

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                session.input_queue.items.append(UserInput.text_input("pending steer"))
                return [ResponseItem.message("assistant", (ContentItem.output_text("first"),))]
            return [ResponseItem.message("assistant", (ContentItem.output_text("second"),))]

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(hook_prompts, ["hello", "pending steer"])
        self.assertEqual(len(seen_requests), 2)
        followup_texts = [
            item.content[0].text
            for item in seen_requests[1].request_plan.request["input"]
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertLess(followup_texts.index("pending steer"), followup_texts.index("pending context"))
        self.assertEqual(result.response_items[-1].content[0].text, "second")

    async def test_run_user_turn_sampling_pending_input_hook_blocks_followup(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        hook_prompts = []
        first_response = ResponseItem.message("assistant", (ContentItem.output_text("first"),))

        def hook(prompt):
            hook_prompts.append(prompt)
            if prompt == "blocked steer":
                return {"should_stop": True, "additional_contexts": ("pending blocked context",)}
            return HookRuntimeOutcome()

        async def sampler(request):
            seen_requests.append(request)
            session.input_queue.items.append(UserInput.text_input("blocked steer"))
            return [first_response]

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(hook_prompts, ["hello", "blocked steer"])
        self.assertEqual(len(seen_requests), 1)
        self.assertEqual(result.response_items, (first_response,))
        self.assertEqual(result.last_agent_message, "first")
        history_texts = [
            item.content[0].text
            for item in session.history
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertIn("pending blocked context", history_texts)
        self.assertNotIn("blocked steer", history_texts)

    async def test_run_user_turn_sampling_mixed_pending_input_continues_when_later_user_input_accepted(self) -> None:
        session = Session()
        session.input_queue = PendingInputQueue()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        hook_prompts = []
        injected_item = ResponseItem.message("user", (ContentItem.input_text("mailbox context"),))

        def hook(prompt):
            hook_prompts.append(prompt)
            if prompt == "blocked steer":
                return {"should_stop": True, "additional_contexts": ("blocked context",)}
            return HookRuntimeOutcome()

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                session.input_queue.items.extend(
                    (
                        {"type": "user_input", "items": ({"type": "text", "text": "blocked steer"},)},
                        {"type": "response_item", "item": injected_item},
                        {"type": "UserInput", "content": ({"type": "text", "text": "accepted steer"},)},
                    )
                )
                return [ResponseItem.message("assistant", (ContentItem.output_text("first"),))]
            return [ResponseItem.message("assistant", (ContentItem.output_text("second"),))]

        session.run_user_prompt_submit_hook = hook

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(hook_prompts, ["hello", "blocked steer", "accepted steer"])
        self.assertEqual(len(seen_requests), 2)
        followup_texts = [
            item.content[0].text
            for item in seen_requests[1].request_plan.request["input"]
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertIn("blocked context", followup_texts)
        self.assertIn("mailbox context", followup_texts)
        self.assertIn("accepted steer", followup_texts)
        self.assertNotIn("blocked steer", followup_texts)
        self.assertEqual(result.last_agent_message, "second")

    async def test_run_user_turn_sampling_follows_stream_completed_end_turn_false(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-2")

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(
                    response_items=(),
                    stream_events=(
                        {"type": "completed", "response_id": "resp-1", "end_turn": False},
                    ),
                )
            return SimpleNamespace(
                response_items=(final,),
                stream_events=(
                    {"type": "output_item_added", "item": ResponseItem.message("assistant", (), id="msg-2")},
                    {"type": "output_text_delta", "delta": "done"},
                    {"type": "output_item_done", "item": final},
                    {"type": "completed", "response_id": "resp-2", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(len(result.request_plans), 2)
        self.assertEqual(result.response_items, (final,))
        self.assertEqual(result.stream_event_apply_plans[0].completed_event_apply_plan.result_needs_follow_up, True)

    async def test_run_user_turn_sampling_defers_pending_input_behind_model_followup(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        session.input_queue = PendingInputQueue()
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        followup_done = ResponseItem.message("assistant", (ContentItem.output_text("continuation done"),), id="msg-2")
        final = ResponseItem.message("assistant", (ContentItem.output_text("pending handled"),), id="msg-3")

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                session.input_queue.items.append(UserInput.text_input("pending steer"))
                return SimpleNamespace(
                    response_items=(),
                    stream_events=(
                        {"type": "completed", "response_id": "resp-1", "end_turn": False},
                    ),
                )
            if len(seen_requests) == 2:
                return SimpleNamespace(
                    response_items=(followup_done,),
                    stream_events=(
                        {"type": "completed", "response_id": "resp-2", "end_turn": True},
                    ),
                )
            return SimpleNamespace(
                response_items=(final,),
                stream_events=(
                    {"type": "completed", "response_id": "resp-3", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 3)
        second_request_texts = [
            item.content[0].text
            for item in seen_requests[1].request_plan.request["input"]
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        third_request_texts = [
            item.content[0].text
            for item in seen_requests[2].request_plan.request["input"]
            if getattr(item, "type", None) == "message" and getattr(item, "content", None)
        ]
        self.assertNotIn("pending steer", second_request_texts)
        self.assertIn("pending steer", third_request_texts)
        self.assertEqual(result.response_items, (followup_done, final))
        self.assertEqual(result.last_agent_message, "pending handled")

    async def test_run_user_turn_sampling_follows_raw_response_completed_end_turn_false(self) -> None:
        session = Session()
        session.turn_context.turn_id = "turn-1"
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-2")

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(
                    response_items=(),
                    stream_events=(
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp-1",
                                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                                "end_turn": False,
                            },
                        },
                    ),
                )
            return SimpleNamespace(
                response_items=(final,),
                stream_events=(
                    {"type": "completed", "response_id": "resp-2", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(len(result.request_plans), 2)
        self.assertEqual(result.response_items, (final,))
        self.assertEqual(result.stream_event_apply_plans[0].completed_event_apply_plan.result_needs_follow_up, True)
        self.assertEqual(result.stream_event_apply_plans[0].completed_event_apply_plan.completed_response_id_after, "resp-1")

    async def test_run_user_turn_sampling_model_followup_bypasses_tool_followup_limit(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread-1", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []
        final = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-2")

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return SimpleNamespace(
                    response_items=(),
                    stream_events=(
                        {"type": "completed", "response_id": "resp-1", "end_turn": False},
                    ),
                )
            return SimpleNamespace(
                response_items=(final,),
                stream_events=(
                    {"type": "completed", "response_id": "resp-2", "end_turn": True},
                ),
            )

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
            max_tool_followups=0,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(len(result.request_plans), 2)
        self.assertEqual(result.response_items, (final,))

    async def test_run_user_input_op_sampling_records_sampler_response_items(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_input_op_sampling_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),)),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 1)
        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(session.history[-1].content[0].text, "done")

    async def test_run_user_turn_sampling_can_use_model_client_session_sampler(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        model_session = client.new_session()
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        transported = []

        async def transport(prepared):
            transported.append(prepared)
            self.assertEqual(prepared.prepared_request["model"], "gpt-test")
            self.assertEqual(prepared.prepared_request["instructions"], "base")
            self.assertIn("input", prepared.prepared_request)
            return [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}]

        async def sampler(request):
            return await sample_with_model_client_session(request, model_session, transport)

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(transported), 1)
        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(session.history[-1].content[0].text, "done")


if __name__ == "__main__":
    unittest.main()
