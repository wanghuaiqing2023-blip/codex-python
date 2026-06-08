import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.tools.handlers.utils import apply_granted_turn_permissions, record_granted_request_permissions
from pycodex.core.http_transport import run_user_turn_http_sampling_from_session
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.core.context_manager.history import (
    estimate_item_token_count,
    estimate_response_item_model_visible_bytes,
)
from pycodex.core.codex_thread import SessionSettingsUpdate
from pycodex.features import Feature
from pycodex.core.tools.context import FunctionToolOutput
from pycodex.core.tools.orchestrator import build_tool_orchestrator_plan_for_session, OrchestratorApprovalKind
from pycodex.core.tools.registry import ToolRegistry
from pycodex.core.tools.router import ToolRouter
from pycodex.core.tools.sandboxing import ExecApprovalRequirement
from pycodex.core.session.turn.runtime import run_user_turn_sampling_from_session
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AccountPlanType,
    ApprovalsReviewer,
    AskForApproval,
    CodexErr,
    CollaborationMode,
    ContentItem,
    CreditsSnapshot,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSandboxKind,
    ManagedFileSystemPermissions,
    FileSystemSpecialPath,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    GranularApprovalConfig,
    NetworkSandboxPolicy,
    NetworkPermissions,
    PermissionGrantScope,
    PermissionProfile,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
    ResponseItem,
    RateLimitSnapshot,
    RateLimitWindow,
    ReasoningEffort,
    ReasoningSummary,
    SandboxPermissions,
    SandboxPolicy,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    SessionSource,
    ServiceTier,
    ByteRange,
    ModeKind,
    Settings,
    SubAgentSource,
    TextElement,
    TokenUsage,
    TurnItem,
    ThreadSettingsOverrides,
    ToolName,
    TruncationPolicyConfig,
    TurnEnvironmentSelection,
    TurnContextNetworkItem,
    UserInput,
    UsageLimitReachedError,
)


class FakeResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return []


class EchoHandler:
    def __init__(self) -> None:
        self.invocations = []

    def tool_name(self) -> ToolName:
        return ToolName.plain("echo")

    def handle(self, invocation):
        self.invocations.append(invocation)
        return FunctionToolOutput.from_text("tool ok", True)


class ModelMessages:
    def __init__(self, messages):
        self._messages = messages

    def get_personality_message(self, personality):
        return self._messages.get(personality)


class FeatureSet:
    def __init__(self, *features) -> None:
        self.features = set(features)

    def enabled(self, feature) -> bool:
        return feature in self.features


def non_lifecycle_events(session: InMemoryCodexSession):
    return tuple(event for event in session.emitted_events if event.type not in {"task_started", "task_complete"})


def events_of_type(session: InMemoryCodexSession, event_type: str):
    return tuple(event for event in session.emitted_events if event.type == event_type)


class SessionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _collect_permissions_prompt_texts(prompt_input: tuple[ResponseItem, ...] | list[ResponseItem]) -> list[str]:
        assert_prompt_items = [item for item in prompt_input if item.role == "developer" and item.content]
        if not assert_prompt_items:
            raise AssertionError("expected developer prompt item for permissions instructions")
        prompt_texts = [item.content[0].text or "" for item in assert_prompt_items if item.content]
        return prompt_texts

    @staticmethod
    def _assert_prompt_input_contains_permissions_instructions(prompt_input: tuple[ResponseItem, ...] | list[ResponseItem]) -> list[str]:
        texts = SessionRuntimeTests._collect_permissions_prompt_texts(prompt_input)
        if not any("<permissions instructions>" in text for text in texts):
            raise AssertionError("expected permissions instructions marker in developer prompt")
        if not any("Network access is enabled" in text for text in texts):
            raise AssertionError("expected permissions prompt to include enabled network access text")
        return texts

    async def test_in_memory_session_runs_user_turn_http_sampling(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            user_instructions="project instructions",
            base_instructions="base",
            history=[ResponseItem.message("developer", (ContentItem.input_text("context"),))],
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = {"base_url": "https://api.example.test/v1"}

        result = await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(session.context_updates_recorded, 1)
        self.assertEqual(len(session.recorded_batches), 3)
        self.assertEqual(session.history[-1], result.response_items[0])
        self.assertEqual(session.history[-1].content[0].text, "done")
        self.assertEqual(seen["body"]["instructions"], "base")
        self.assertEqual(seen["body"]["input"][0]["role"], "developer")
        self.assertEqual(seen["body"]["input"][1]["role"], "developer")
        self.assertIn("<permissions instructions>", seen["body"]["input"][1]["content"][0]["text"])
        input_texts = [item["content"][0]["text"] for item in seen["body"]["input"] if item.get("content")]
        self.assertTrue(any("project instructions" in text for text in input_texts))
        self.assertEqual(input_texts[-1], "hello")
        self.assertGreaterEqual(len(result.request_plans), 1)
        http_prompt_texts = self._assert_prompt_input_contains_permissions_instructions(
            result.request_plans[0].prompt.get_formatted_input()
        )

    async def test_in_memory_session_emits_turn_lifecycle_events(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "context_window": 128000,
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            turn_id="turn-1",
            model_info=model_info,
            server_reasoning_included=True,
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            SimpleNamespace(is_azure_responses_endpoint=lambda: False),
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(
            tuple(event.type for event in session.emitted_events),
            (
                "task_started",
                "item_started",
                "item_completed",
                "item_started",
                "item_completed",
                "task_complete",
            ),
        )
        self.assertEqual(session.emitted_events[0].payload.turn_id, "turn-1")
        self.assertEqual(session.emitted_events[0].payload.model_context_window, 128000)
        self.assertEqual(session.emitted_events[2].payload.item.type, "UserMessage")
        self.assertEqual(session.emitted_events[2].payload.item.item.message(), "hello")
        self.assertEqual(session.emitted_events[4].payload.item.type, "AgentMessage")
        self.assertEqual(session.emitted_events[4].payload.item.item.content[0].text, "done")
        self.assertEqual(session.emitted_events[5].payload.turn_id, "turn-1")
        self.assertEqual(session.emitted_events[5].payload.last_agent_message, "done")
        self.assertFalse(session.server_reasoning_included)
        self.assertEqual(session.flush_rollout_count, 1)
        self.assertEqual(result.session_events, tuple(session.emitted_events))

    async def test_in_memory_session_records_context_update_items_from_reference_context(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            current_date="2026-05-30",
            timezone="Asia/Shanghai",
        )

        first_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(first_turn)
        session.cwd = Path("C:/work/other")
        second_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(second_turn)

        self.assertEqual(session.context_updates_recorded, 2)
        self.assertEqual(len(session.recorded_batches), 2)
        self.assertEqual(session.recorded_batches[0][0].role, "developer")
        self.assertIn("<permissions instructions>", session.recorded_batches[0][0].content[0].text)
        self.assertEqual(session.recorded_batches[0][1].role, "user")
        self.assertIn("<environment_context>", session.recorded_batches[0][1].content[0].text)
        item = session.recorded_batches[1][0]
        self.assertEqual(item.role, "user")
        self.assertIn("<environment_context>", item.content[0].text)
        self.assertIn(f"<cwd>{Path('C:/work/other')}</cwd>", item.content[0].text)
        self.assertEqual(session.history[-1], item)

    async def test_in_memory_session_replace_last_turn_images_rewrites_tool_output_images(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            history=[
                ResponseItem.message("user", (ContentItem.input_text("look"),)),
                ResponseItem.function_call("view_image", "{}", "call-image"),
                ResponseItem(
                    type="function_call_output",
                    call_id="call-image",
                    output=FunctionCallOutputPayload.from_content_items(
                        (
                            FunctionCallOutputContentItem.input_text("before"),
                            FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA"),
                        ),
                        success=True,
                    ),
                ),
            ],
        )

        replaced = await session.replace_last_turn_images("Invalid image")

        self.assertTrue(replaced)
        output = session.history[-1].output
        self.assertEqual(output.body.content_items[0].text, "before")
        self.assertEqual(output.body.content_items[1].type, "input_text")
        self.assertEqual(output.body.content_items[1].text, "Invalid image")
        self.assertTrue(output.success)

    async def test_in_memory_session_replace_last_turn_images_does_not_touch_user_images(self) -> None:
        user_image = ResponseItem.message(
            "user",
            (ContentItem.input_image("data:image/png;base64,AAA"),),
        )
        session = InMemoryCodexSession(cwd="C:/work/project", history=[user_image])

        replaced = await session.replace_last_turn_images("Invalid image")

        self.assertFalse(replaced)
        self.assertEqual(session.history, [user_image])

    async def test_in_memory_session_record_conversation_items_truncates_function_output_history(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-test", truncation_policy=TruncationPolicyConfig.bytes(10)),
        )
        turn = await session.new_default_turn()
        item = ResponseItem(
            type="function_call_output",
            call_id="call-long",
            output=FunctionCallOutputPayload.from_text("abcdefghijklmnopqrstuvwxyz", success=True),
        )

        await session.record_conversation_items(turn, (item,))

        self.assertEqual(session.recorded_batches[-1], (item,))
        history_output = session.history[-1].output
        self.assertTrue(history_output.success)
        self.assertNotEqual(history_output.to_text(), item.output.to_text())
        self.assertIn("chars truncated", history_output.to_text())

    async def test_in_memory_session_record_conversation_items_truncates_custom_tool_output_history(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        turn = SimpleNamespace(truncation_policy=TruncationPolicyConfig.bytes(8), model_info=None)
        image = FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA")
        item = ResponseItem(
            type="custom_tool_call_output",
            call_id="call-custom",
            name="custom",
            output=FunctionCallOutputPayload.from_content_items(
                (
                    FunctionCallOutputContentItem.input_text("abcdefghijklmnopqrstuvwxyz"),
                    image,
                ),
                success=False,
            ),
        )

        await session.record_conversation_items(turn, (item,))

        self.assertEqual(session.recorded_batches[-1], (item,))
        history_output = session.history[-1].output
        self.assertFalse(history_output.success)
        self.assertEqual(history_output.body.content_items[-1], image)
        self.assertIn("chars truncated", history_output.body.content_items[0].text)

    async def test_in_memory_session_new_default_turn_carries_session_source(self) -> None:
        source = SessionSource.subagent(SubAgentSource.other_source("guardian"))
        session = InMemoryCodexSession(cwd="C:/work/project", session_source=source)

        turn = await session.new_default_turn()

        self.assertEqual(turn.session_source, source)

    async def test_in_memory_session_input_queue_drains_pending_items_for_active_turn(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        await session.inject_if_running(
            (
                {"type": "text", "text": "queued steer"},
                ResponseItem.message("user", (ContentItem.input_text("queued item"),)),
            )
        )

        self.assertTrue(await session.input_queue.has_pending_input(session.active_turn))
        pending = await session.input_queue.get_pending_input(session.active_turn)

        self.assertEqual(pending[0], UserInput.text_input("queued steer"))
        self.assertEqual(pending[1].content[0].text, "queued item")
        self.assertFalse(await session.input_queue.has_pending_input(session.active_turn))

    async def test_in_memory_session_inject_if_running_returns_items_without_active_turn(self) -> None:
        # Rust source: codex-core/src/session/inject.rs inject_if_running None branch.
        session = InMemoryCodexSession(cwd="C:/work/project", active_turn=None)
        item = ResponseItem.message("user", (ContentItem.input_text("outside turn"),))

        result = await session.inject_if_running([item])

        self.assertEqual(result, (item,))
        self.assertFalse(await session.input_queue.has_pending_input(None))

    async def test_in_memory_session_inject_no_new_turn_queues_when_active_turn_exists(self) -> None:
        # Rust source: codex-core/src/session/inject.rs inject_no_new_turn first tries active injection.
        session = InMemoryCodexSession(cwd="C:/work/project")
        item = ResponseItem.message("user", (ContentItem.input_text("active turn"),))

        await session.inject_no_new_turn([item], None)

        self.assertEqual(session.recorded_batches, [])
        pending = await session.input_queue.get_pending_input(session.active_turn)
        self.assertEqual(pending, (item,))

    async def test_in_memory_session_record_user_prompt_emits_turn_item_events(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", thread_id="thread-1", turn_id="turn-1")
        turn = await session.new_default_turn()
        text_element = TextElement(
            ByteRange(0, len("hello".encode("utf-8"))),
            "user-name",
        )
        user_input = UserInput.text_input("hello", text_elements=(text_element,))

        await session.record_user_prompt_and_emit_turn_item(turn, (user_input,))

        self.assertEqual(session.history[-1].role, "user")
        self.assertEqual(session.history[-1].content[0].text, "hello")
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("item_started", "item_completed"))
        started = session.emitted_events[0].payload
        completed = session.emitted_events[1].payload
        self.assertEqual(started.thread_id, "thread-1")
        self.assertEqual(started.turn_id, "turn-1")
        self.assertEqual(completed.thread_id, "thread-1")
        self.assertEqual(completed.turn_id, "turn-1")
        self.assertEqual(completed.item.type, "UserMessage")
        self.assertEqual(completed.item.item.content, (user_input,))
        legacy = completed.as_legacy_events()[0]
        self.assertEqual(legacy.type, "user_message")
        self.assertEqual(legacy.payload.message, "hello")
        self.assertEqual(legacy.payload.text_elements, (text_element,))

    async def test_in_memory_session_record_response_item_emits_turn_item_events(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", thread_id="thread-1", turn_id="turn-1")
        turn = await session.new_default_turn()
        response_item = ResponseItem.message("assistant", (ContentItem.output_text("done"),), id="msg-1")

        await session.record_response_item_and_emit_turn_item(turn, response_item)

        self.assertEqual(session.history[-1], response_item)
        self.assertEqual(tuple(event.type for event in session.emitted_events), ("item_started", "item_completed"))
        started = session.emitted_events[0].payload
        completed = session.emitted_events[1].payload
        self.assertEqual(started.thread_id, "thread-1")
        self.assertEqual(started.turn_id, "turn-1")
        self.assertEqual(started.item.type, "AgentMessage")
        self.assertEqual(completed.thread_id, "thread-1")
        self.assertEqual(completed.turn_id, "turn-1")
        self.assertEqual(completed.item.type, "AgentMessage")
        self.assertEqual(completed.item.item.content[0].text, "done")

    async def test_in_memory_session_http_sampling_uses_pending_input_followup(self) -> None:
        bodies = []
        session = InMemoryCodexSession(cwd="C:/work/project")

        class Response:
            def __init__(self, text):
                self.text = text

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": self.text}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            body = json.loads(request.data.decode("utf-8"))
            bodies.append(body)
            if len(bodies) == 1:
                session.input_queue.items.append(UserInput.text_input("steer while running"))
                return Response("first")
            return Response("final")

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        result = await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(bodies), 2)
        second_input_texts = [
            item["content"][0]["text"]
            for item in bodies[1]["input"]
            if item.get("type") == "message" and item.get("content")
        ]
        self.assertIn("steer while running", second_input_texts)
        self.assertEqual(result.response_items[-1].content[0].text, "final")

    async def test_in_memory_session_records_stream_loop_tail_side_effects(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            features=FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
            unified_diff="diff --git a/file b/file",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        usage = {
            "input_tokens": 3,
            "output_tokens": 4,
            "total_tokens": 7,
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
            SimpleNamespace(is_azure_responses_endpoint=lambda: False),
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.response_items[-1].content[0].text, "done")
        self.assertEqual(session.response_processed_ids, ["resp-1"])
        self.assertEqual(session.drain_in_flight_count, 1)
        self.assertEqual(session.token_usage_info.total_token_usage.total_tokens, 7)
        self.assertEqual(
            [call[0] for call in session.loop_tail_calls],
            ["response_processed", "drain_in_flight", "token_count", "turn_diff"],
        )
        self.assertEqual(
            session.loop_tail_calls[0],
            ("response_processed", "resp-1"),
        )
        self.assertEqual(
            session.loop_tail_calls[-1],
            ("turn_diff", "diff --git a/file b/file"),
        )
        non_lifecycle = non_lifecycle_events(session)
        self.assertEqual(non_lifecycle[-2].type, "token_count")
        self.assertEqual(non_lifecycle[-1].type, "turn_diff")
        self.assertEqual(
            non_lifecycle[-1].payload.unified_diff,
            "diff --git a/file b/file",
        )

    async def test_in_memory_session_tool_dispatch_increments_active_turn_tool_calls(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [ResponseItem.function_call("echo", "{}", "call-echo")]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            SimpleNamespace(is_azure_responses_endpoint=lambda: False),
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(session.active_turn.turn_state.tool_calls, 1)
        self.assertEqual(len(handler.invocations), 1)
        self.assertIs(handler.invocations[0].session, session)
        self.assertEqual(result.tool_response_items[0].output.to_text(), "tool ok")
        self.assertEqual(result.response_items[-1].content[0].text, "done")

    async def test_in_memory_session_records_terminal_error_lifecycle(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
                "context_window": 100,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        async def sampler(_request):
            raise CodexErr.simple("context_window_exceeded")

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            SimpleNamespace(is_azure_responses_endpoint=lambda: False),
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(session.turn_error_lifecycle[0][1].type, "context_window_exceeded")
        self.assertEqual(session.token_usage_info.model_context_window, 95)
        self.assertEqual(session.token_usage_info.total_token_usage.total_tokens, 95)
        self.assertEqual([event.type for event in non_lifecycle_events(session)], ["token_count", "error"])
        self.assertEqual(events_of_type(session, "error")[-1].payload.codex_error_info.type, "context_window_exceeded")
        self.assertIsNone(events_of_type(session, "task_complete")[-1].payload.last_agent_message)

    async def test_in_memory_session_records_usage_limit_error_lifecycle(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        rate_limits = RateLimitSnapshot(
            limit_id="codex",
            primary=RateLimitWindow(used_percent=100.0, window_minutes=60),
        )
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        async def sampler(_request):
            raise CodexErr.usage_limit_reached(UsageLimitReachedError(rate_limits=rate_limits))

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            SimpleNamespace(is_azure_responses_endpoint=lambda: False),
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(session.turn_error_lifecycle[0][1].type, "usage_limit_exceeded")
        self.assertIs(session.latest_rate_limits, rate_limits)
        self.assertEqual([event.type for event in non_lifecycle_events(session)], ["token_count", "error"])
        self.assertEqual(events_of_type(session, "error")[-1].payload.codex_error_info.type, "usage_limit_exceeded")
        self.assertIsNone(events_of_type(session, "task_complete")[-1].payload.last_agent_message)

    async def test_in_memory_session_invalid_user_image_records_bad_request_lifecycle(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "input_modalities": ("text", "image"),
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            history=[ResponseItem.message("user", (ContentItem.input_image("data:image/png;base64,AAA"),))],
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        async def sampler(_request):
            raise CodexErr.simple("invalid_image_request")

        result = await run_user_turn_sampling_from_session(
            session,
            (),
            client,
            SimpleNamespace(is_azure_responses_endpoint=lambda: False),
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertEqual(result.response_items, ())
        self.assertIsNone(result.last_agent_message)
        self.assertEqual(session.turn_error_lifecycle[0][1].type, "bad_request")
        error = events_of_type(session, "error")[-1]
        self.assertEqual(error.type, "error")
        self.assertEqual(error.payload.codex_error_info.type, "bad_request")

    async def test_in_memory_session_reasoning_settings_feed_http_sampling_request(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": True,
                "support_verbosity": False,
                "default_reasoning_level": "medium",
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            reasoning_effort="high",
            reasoning_summary="concise",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["reasoning"], {"effort": "high", "summary": "concise"})

    async def test_in_memory_session_service_tier_feeds_http_sampling_request(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            service_tier="priority",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["service_tier"], "priority")

    async def test_in_memory_session_service_tier_enum_feeds_http_sampling_request(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier if tier == "priority" else None,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            service_tier=ServiceTier.FAST,
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["service_tier"], "priority")

    async def test_in_memory_session_turn_config_inherits_service_tier(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", service_tier="priority")

        turn = await session.new_default_turn()

        self.assertEqual(turn.config.service_tier, "priority")

    async def test_in_memory_session_turn_config_inherits_allow_login_shell(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", allow_login_shell=True)

        turn = await session.new_default_turn()

        self.assertTrue(turn.config.permissions.allow_login_shell)

    async def test_in_memory_session_update_settings_applies_turn_local_environments_once(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(TurnEnvironmentSelection("sticky", Path("C:/work/project")),),
        )
        environments = (TurnEnvironmentSelection("env-1", Path("C:/work/project")),)

        await session.update_settings(SessionSettingsUpdate(environments=environments))
        override_turn = await session.new_default_turn()
        sticky_turn = await session.new_default_turn()

        self.assertEqual(session.environments, (TurnEnvironmentSelection("sticky", Path("C:/work/project")),))
        self.assertEqual(override_turn.environments, environments)
        self.assertEqual(sticky_turn.environments, session.environments)

    async def test_in_memory_session_default_turn_overlays_cwd_onto_sticky_primary_environment(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(TurnEnvironmentSelection("sticky", Path("C:/work/selected")),),
        )

        turn = await session.new_default_turn()

        self.assertEqual(session.environments, (TurnEnvironmentSelection("sticky", Path("C:/work/selected")),))
        self.assertEqual(turn.environments, (TurnEnvironmentSelection("sticky", Path("C:/work/project")),))
        self.assertEqual(turn.cwd, Path("C:/work/project"))
        self.assertEqual(turn.config.cwd, Path("C:/work/project"))

    async def test_in_memory_session_turn_local_environment_preserves_selected_cwd(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(TurnEnvironmentSelection("sticky", Path("C:/work/selected")),),
        )
        environments = (TurnEnvironmentSelection("env-1", Path("C:/work/explicit")),)

        await session.update_settings(SessionSettingsUpdate(environments=environments))
        turn = await session.new_default_turn()

        self.assertEqual(turn.environments, environments)
        self.assertEqual(turn.cwd, Path("C:/work/explicit"))
        self.assertEqual(turn.config.cwd, Path("C:/work/explicit"))

    async def test_in_memory_session_environment_context_renders_multiple_turn_environments(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(
                TurnEnvironmentSelection("local", Path("C:/work/local")),
                TurnEnvironmentSelection("remote", Path("C:/work/remote")),
            ),
            current_date="2026-05-30",
            timezone="Asia/Shanghai",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        context_item = session.recorded_batches[0][1]
        context_text = context_item.content[0].text
        self.assertIn("<environments>", context_text)
        self.assertIn('<environment id="local">', context_text)
        self.assertIn(f"<cwd>{Path('C:/work/project')}</cwd>", context_text)
        self.assertIn('<environment id="remote">', context_text)
        self.assertIn(f"<cwd>{Path('C:/work/remote')}</cwd>", context_text)
        self.assertIn("<current_date>2026-05-30</current_date>", context_text)

    async def test_in_memory_session_default_turn_supplies_local_time_context(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        self.assertRegex(turn.current_date, r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsInstance(turn.timezone, str)
        self.assertTrue(turn.timezone)
        context_text = session.recorded_batches[0][1].content[0].text
        self.assertIn("<current_date>", context_text)
        self.assertIn("<timezone>", context_text)

    async def test_in_memory_session_update_settings_applies_final_output_json_schema(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

        await session.update_settings(SessionSettingsUpdate(final_output_json_schema=schema))
        turn_with_schema = await session.new_default_turn()
        await session.update_settings(SessionSettingsUpdate(final_output_json_schema=None))
        turn_without_schema = await session.new_default_turn()

        self.assertEqual(turn_with_schema.final_output_json_schema, schema)
        self.assertIsNone(turn_without_schema.final_output_json_schema)

    async def test_in_memory_session_turn_config_inherits_reasoning_settings(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_effort="high",
            reasoning_summary="concise",
        )

        turn = await session.new_default_turn()

        self.assertEqual(turn.config.model_reasoning_effort, "high")
        self.assertEqual(turn.config.model_reasoning_summary, "concise")

    async def test_in_memory_session_turn_inherits_collaboration_reasoning_effort(self) -> None:
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-5.2-codex", reasoning_effort=ReasoningEffort.HIGH),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            collaboration_mode=collaboration_mode,
        )

        turn = await session.new_default_turn()

        self.assertEqual(turn.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(turn.config.model_reasoning_effort, ReasoningEffort.HIGH)

    async def test_in_memory_session_turn_inherits_collaboration_model(self) -> None:
        base_model_info = SimpleNamespace(
            slug="gpt-old",
            input_modalities=("text",),
            supports_reasoning_summaries=True,
        )
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-5.2-codex"),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=base_model_info,
            collaboration_mode=collaboration_mode,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()

        self.assertEqual(turn.model_info.slug, "gpt-5.2-codex")
        self.assertEqual(turn.model_info.input_modalities, ("text",))
        self.assertEqual(turn.config.model, "gpt-5.2-codex")
        self.assertIsNotNone(reference)
        self.assertEqual(reference.model, "gpt-5.2-codex")

    async def test_in_memory_session_preview_and_update_settings(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
        )
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-next", reasoning_effort=ReasoningEffort.HIGH),
        )
        updates = SessionSettingsUpdate(
            collaboration_mode=collaboration_mode,
            reasoning_summary=ReasoningSummary.CONCISE,
            service_tier="priority",
        )

        preview = await session.preview_settings(updates)
        self.assertEqual(preview.model, "gpt-next")
        self.assertEqual(preview.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(preview.reasoning_summary, ReasoningSummary.CONCISE)
        self.assertEqual(preview.service_tier, "priority")
        self.assertIsNone(session.collaboration_mode)

        applied = await session.update_settings(updates)
        self.assertEqual(applied.model, "gpt-next")
        self.assertIs(session.collaboration_mode, collaboration_mode)
        self.assertEqual(session.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(session.reasoning_summary, ReasoningSummary.CONCISE)
        self.assertEqual(session.service_tier, "priority")

    async def test_in_memory_session_settings_normalize_service_tier_values(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")

        preview = await session.preview_settings(SessionSettingsUpdate(service_tier=ServiceTier.FAST))
        self.assertEqual(preview.service_tier, "priority")

        applied = await session.update_settings(SessionSettingsUpdate(service_tier="fast"))
        self.assertEqual(applied.service_tier, "priority")
        self.assertEqual(session.service_tier, "priority")

        defaulted = await session.update_settings(SessionSettingsUpdate(service_tier=None))
        self.assertEqual(defaulted.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)
        self.assertEqual(session.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)

        unchanged = await session.update_settings(SessionSettingsUpdate())
        self.assertEqual(unchanged.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)
        self.assertEqual(session.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)

    async def test_in_memory_session_update_settings_projects_sandbox_policy_to_permission_profile(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")

        applied = await session.update_settings(
            SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only())
        )

        self.assertEqual(session.sandbox_policy, SandboxPolicy.read_only())
        self.assertIsNotNone(session.permission_profile)
        self.assertEqual(session.permission_profile.type, "managed")
        self.assertEqual(
            session.permission_profile.file_system_sandbox_policy().kind,
            FileSystemSandboxKind.RESTRICTED,
        )
        self.assertEqual(
            session.file_system_sandbox_policy,
            session.permission_profile.file_system_sandbox_policy(),
        )
        self.assertEqual(applied.permission_profile, session.permission_profile)
        self.assertEqual(applied.file_system_sandbox_policy, session.file_system_sandbox_policy)

    async def test_in_memory_session_update_settings_preserves_deny_entries_when_projecting_sandbox_policy(self) -> None:
        deny_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path("C:/denied/path"),
            FileSystemAccessMode.DENY,
        )
        base_file_system = FileSystemSandboxPolicy.restricted((deny_entry,))
        base_profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.from_sandbox_policy(base_file_system),
            NetworkSandboxPolicy.RESTRICTED,
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            permission_profile=base_profile,
            file_system_sandbox_policy=base_file_system,
        )

        await session.update_settings(SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only()))

        projected = session.permission_profile.file_system_sandbox_policy()
        self.assertIn(deny_entry, projected.entries)
        self.assertEqual(session.file_system_sandbox_policy, projected)

    async def test_in_memory_session_preview_settings_projects_sandbox_policy_to_permission_profile(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")

        preview = await session.preview_settings(
            SessionSettingsUpdate(sandbox_policy=SandboxPolicy.workspace_write((), False, False))
        )

        self.assertEqual(preview.sandbox_policy(), SandboxPolicy.workspace_write((), False, False))
        self.assertIsNotNone(preview.permission_profile)
        self.assertEqual(preview.permission_profile.type, "managed")
        self.assertEqual(
            preview.permission_profile.file_system_sandbox_policy().kind,
            FileSystemSandboxKind.RESTRICTED,
        )
        self.assertEqual(preview.file_system_sandbox_policy.kind, FileSystemSandboxKind.RESTRICTED)
        self.assertEqual(session.sandbox_policy, SandboxPolicy.danger_full_access())
        self.assertEqual(session.permission_profile, PermissionProfile.disabled())

    async def test_in_memory_session_preview_settings_preserves_deny_entries_when_projecting_sandbox_policy(self) -> None:
        deny_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path("C:/denied/path"),
            FileSystemAccessMode.DENY,
        )
        base_file_system = FileSystemSandboxPolicy.restricted((deny_entry,))
        base_profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.from_sandbox_policy(base_file_system),
            NetworkSandboxPolicy.RESTRICTED,
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            permission_profile=base_profile,
            file_system_sandbox_policy=base_file_system,
        )

        preview = await session.preview_settings(SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only()))

        projected = preview.permission_profile.file_system_sandbox_policy()
        self.assertIn(deny_entry, projected.entries)
        self.assertEqual(preview.file_system_sandbox_policy, projected)

    async def test_in_memory_session_applies_protocol_thread_settings_overrides(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
            collaboration_mode=CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings(
                    model="gpt-current",
                    reasoning_effort=ReasoningEffort.HIGH,
                    developer_instructions="keep this",
                ),
            ),
            service_tier="priority",
        )
        preview = await session.preview_thread_settings_overrides(ThreadSettingsOverrides.default())

        self.assertEqual(preview.model, "gpt-current")
        self.assertEqual(preview.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(preview.service_tier, "priority")

        applied = await session.apply_thread_settings_overrides(
            ThreadSettingsOverrides(
                model="gpt-next",
                effort=None,
                service_tier=None,
            )
        )

        self.assertEqual(applied.model, "gpt-next")
        self.assertIsNone(applied.reasoning_effort)
        self.assertEqual(applied.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)
        self.assertEqual(session.collaboration_mode.settings.model, "gpt-next")
        self.assertIsNone(session.collaboration_mode.settings.reasoning_effort)
        self.assertEqual(session.collaboration_mode.settings.developer_instructions, "keep this")
        self.assertEqual(session.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)

    async def test_in_memory_session_thread_config_snapshot_reflects_current_settings(self) -> None:
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-current", reasoning_effort=ReasoningEffort.HIGH),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
            model_provider_id="openai",
            collaboration_mode=collaboration_mode,
            reasoning_summary=ReasoningSummary.CONCISE,
            service_tier="priority",
        )

        snapshot = await session.thread_config_snapshot()

        self.assertEqual(snapshot.model, "gpt-current")
        self.assertEqual(snapshot.model_provider_id, "openai")
        self.assertEqual(snapshot.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(snapshot.reasoning_summary, ReasoningSummary.CONCISE)
        self.assertEqual(snapshot.service_tier, "priority")
        self.assertIs(snapshot.collaboration_mode, collaboration_mode)

    async def test_in_memory_session_thread_config_snapshot_reflects_sandbox_projection(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        updates = SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only())

        applied = await session.update_settings(updates)
        prior_sandbox = session.sandbox_policy
        prior_permission_profile = session.permission_profile
        prior_fs_policy = session.file_system_sandbox_policy

        snapshot = await session.thread_config_snapshot()

        self.assertEqual(snapshot.permission_profile, prior_permission_profile)
        self.assertIs(snapshot.permission_profile, applied.permission_profile)
        self.assertEqual(snapshot.sandbox_policy(), prior_sandbox)
        self.assertEqual(snapshot.permission_profile.file_system_sandbox_policy(), prior_fs_policy)
        self.assertEqual(session.sandbox_policy, prior_sandbox)
        self.assertEqual(session.permission_profile, prior_permission_profile)
        self.assertEqual(session.file_system_sandbox_policy, prior_fs_policy)

    async def test_in_memory_session_thread_config_snapshot_preserves_deny_entries_when_projecting_sandbox_policy(self) -> None:
        deny_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path("C:/denied/path"),
            FileSystemAccessMode.DENY,
        )
        base_file_system = FileSystemSandboxPolicy.restricted((deny_entry,))
        base_profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.from_sandbox_policy(base_file_system),
            NetworkSandboxPolicy.RESTRICTED,
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            permission_profile=base_profile,
            file_system_sandbox_policy=base_file_system,
        )

        await session.update_settings(SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only()))
        snapshot = await session.thread_config_snapshot()

        projected = snapshot.permission_profile.file_system_sandbox_policy()
        self.assertIn(deny_entry, projected.entries)
        self.assertEqual(snapshot.permission_profile, session.permission_profile)
        self.assertEqual(snapshot.sandbox_policy(), session.sandbox_policy)

    async def test_in_memory_session_settings_snapshot_tracks_workspace_roots(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
            workspace_roots=("C:/work/project", "C:/work/shared"),
            profile_workspace_roots=("C:/profile/root",),
            active_permission_profile="active-profile",
        )

        preview = await session.preview_settings(SessionSettingsUpdate(cwd="D:/next/project"))
        self.assertEqual(preview.cwd, Path("D:/next/project"))
        self.assertEqual(preview.workspace_roots, (Path("D:/next/project"), Path("C:/work/shared")))
        self.assertEqual(preview.profile_workspace_roots, (Path("C:/profile/root"),))
        self.assertEqual(preview.active_permission_profile, "active-profile")
        self.assertEqual(session.cwd, Path("C:/work/project"))

        applied = await session.update_settings(
            SessionSettingsUpdate(
                cwd="D:/next/project",
                workspace_roots=("D:/explicit/root",),
                profile_workspace_roots=("D:/profile/root",),
                active_permission_profile="next-profile",
            )
        )

        self.assertEqual(applied.workspace_roots, (Path("D:/explicit/root"),))
        self.assertEqual(session.cwd, Path("D:/next/project"))
        self.assertEqual(session.workspace_roots, (Path("D:/explicit/root"),))
        self.assertEqual(session.profile_workspace_roots, (Path("D:/profile/root"),))
        self.assertEqual(session.active_permission_profile, "next-profile")

    async def test_in_memory_session_turn_inherits_session_features(self) -> None:
        features = object()
        session = InMemoryCodexSession(cwd="C:/work/project", features=features)

        turn = await session.new_default_turn()

        self.assertIs(turn.features, features)

    async def test_in_memory_session_turn_inherits_approvals_reviewer(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW,
        )

        turn = await session.new_default_turn()

        self.assertEqual(turn.config.approvals_reviewer, ApprovalsReviewer.AUTO_REVIEW)

    async def test_in_memory_session_reference_context_preserves_turn_id(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", turn_id="turn-123")

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.turn_id, "turn-123")

    async def test_in_memory_session_reference_context_preserves_reasoning_effort_and_auto_summary(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_effort="high",
            reasoning_summary="concise",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.effort, "high")
        self.assertEqual(reference.summary, "auto")

    async def test_in_memory_session_reference_context_writes_auto_summary_compat_field(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_summary=ReasoningSummary.CONCISE,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.summary, "auto")

    async def test_in_memory_session_new_default_turn_reflects_sandbox_projection(self) -> None:
        deny_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path("C:/denied/path"),
            FileSystemAccessMode.DENY,
        )
        base_file_system = FileSystemSandboxPolicy.restricted((deny_entry,))
        base_profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.from_sandbox_policy(base_file_system),
            NetworkSandboxPolicy.RESTRICTED,
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            permission_profile=base_profile,
            file_system_sandbox_policy=base_file_system,
        )

        await session.update_settings(SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only()))
        snapshot = await session.thread_config_snapshot()
        turn = await session.new_default_turn()

        self.assertIs(turn.permission_profile, snapshot.permission_profile)
        self.assertEqual(turn.sandbox_policy, session.sandbox_policy)
        self.assertEqual(turn.file_system_sandbox_policy, session.file_system_sandbox_policy)
        self.assertEqual(snapshot.permission_profile.file_system_sandbox_policy(), turn.file_system_sandbox_policy)
        self.assertIn(deny_entry, turn.file_system_sandbox_policy.entries)

    async def test_in_memory_session_reference_context_serializes_reasoning_effort_enum(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_effort=ReasoningEffort.HIGH,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.effort, "high")

    async def test_in_memory_session_reference_context_preserves_sandbox_policies(self) -> None:
        sandbox_policy = SandboxPolicy.read_only()
        file_system_policy = FileSystemSandboxPolicy.default()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            sandbox_policy=sandbox_policy,
            file_system_sandbox_policy=file_system_policy,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.sandbox_policy, sandbox_policy)
        self.assertEqual(reference.file_system_sandbox_policy, file_system_policy)

    async def test_in_memory_session_reference_context_normalizes_network_item(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            network=SimpleNamespace(
                allowed_domains=("api.example.com",),
                denied_domains=("bad.example.com",),
            ),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(
            reference.network,
            TurnContextNetworkItem(
                allowed_domains=("api.example.com",),
                denied_domains=("bad.example.com",),
            ),
        )

    async def test_in_memory_session_initial_context_prepends_model_switch_message(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-new",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "get_model_instructions": lambda _self, _personality: "Use the new model policy.",
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        await session.set_previous_turn_settings(SimpleNamespace(model="gpt-old", realtime_active=False))

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        self.assertEqual(session.recorded_batches[0][0].role, "developer")
        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<model_switch>", developer_sections[0])
        self.assertIn("Use the new model policy.", developer_sections[0])
        self.assertIn("<permissions instructions>", developer_sections[1])
        self.assertEqual((await session.previous_turn_settings()).model, "gpt-new")

    async def test_in_memory_session_initial_context_includes_collaboration_mode_after_permissions(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            collaboration_mode=SimpleNamespace(
                settings=SimpleNamespace(developer_instructions="Plan before editing.")
            ),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertEqual(developer_sections[1], "<collaboration_mode>Plan before editing.</collaboration_mode>")

    async def test_in_memory_session_initial_context_supports_granular_approval_policy(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=False,
            request_permissions=False,
            mcp_elicitations=True,
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            approval_policy=granular,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("Approval policy is `granular`", developer_sections[0])
        self.assertIn("`sandbox_approval`", developer_sections[0])
        self.assertIn("`rules`", developer_sections[0])
        self.assertNotIn("# request_permissions Tool", developer_sections[0])
        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.approval_policy, granular)

    async def test_in_memory_session_reference_context_jsonifies_collaboration_mode(self) -> None:
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(developer_instructions="Plan before editing."),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            collaboration_mode=collaboration_mode,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(
            reference.collaboration_mode,
            {
                "mode": "default",
                "settings": {"developer_instructions": "Plan before editing."},
            },
        )

    async def test_in_memory_session_reference_context_defaults_collaboration_mode(self) -> None:
        model_info = type("ModelInfo", (), {"slug": "gpt-5.2-codex"})()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(
            reference.collaboration_mode,
            {"mode": "default", "settings": {"model": "gpt-5.2-codex"}},
        )

    async def test_in_memory_session_initial_context_includes_developer_instructions_after_permissions(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            developer_instructions="Follow the project policy.",
            collaboration_mode=SimpleNamespace(
                settings=SimpleNamespace(developer_instructions="Plan before editing.")
            ),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertEqual(developer_sections[1], "Follow the project policy.")
        self.assertEqual(developer_sections[2], "<collaboration_mode>Plan before editing.</collaboration_mode>")

    async def test_in_memory_session_guardian_source_separates_developer_instructions(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            developer_instructions="Review shell approvals carefully.",
            session_source=SessionSource.subagent(SubAgentSource.other_source("guardian")),
            collaboration_mode=SimpleNamespace(
                settings=SimpleNamespace(developer_instructions="Plan before editing.")
            ),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        self.assertEqual(session.recorded_batches[0][0].role, "developer")
        self.assertEqual(session.recorded_batches[0][1].role, "user")
        self.assertEqual(session.recorded_batches[0][2].role, "developer")
        first_sections = [content.text for content in session.recorded_batches[0][0].content]
        final_sections = [content.text for content in session.recorded_batches[0][2].content]
        self.assertIn("<permissions instructions>", first_sections[0])
        self.assertEqual(first_sections[1], "<collaboration_mode>Plan before editing.</collaboration_mode>")
        self.assertIn("<environment_context>", session.recorded_batches[0][1].content[0].text)
        self.assertEqual(final_sections, ["Review shell approvals carefully."])

    async def test_in_memory_session_initial_context_includes_realtime_start(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            realtime_active=True,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<realtime_conversation>", developer_sections[1])
        self.assertIn("Realtime conversation started.", developer_sections[1])

    async def test_in_memory_session_initial_context_includes_custom_realtime_start(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            realtime_active=True,
            experimental_realtime_start_instructions="Use short spoken replies.",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<realtime_conversation>", developer_sections[1])
        self.assertIn("Use short spoken replies.", developer_sections[1])

    async def test_in_memory_session_initial_context_uses_previous_turn_settings_for_realtime_end(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        await session.set_previous_turn_settings(SimpleNamespace(model="gpt-test", realtime_active=True))

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<realtime_conversation>", developer_sections[1])
        self.assertIn("Realtime conversation ended.", developer_sections[1])

    async def test_in_memory_session_next_turn_is_first_is_consumed_like_session_state(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")

        self.assertTrue(await session.take_next_turn_is_first())
        self.assertFalse(await session.take_next_turn_is_first())

        await session.set_next_turn_is_first(True)
        self.assertTrue(await session.take_next_turn_is_first())
        self.assertFalse(await session.take_next_turn_is_first())

        await session.set_next_turn_is_first(False)
        self.assertFalse(await session.take_next_turn_is_first())

    async def test_in_memory_session_initial_context_includes_personality_spec(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "model_messages": ModelMessages({"friendly": "Be warm."}),
                "supports_personality": lambda _self: False,
                "get_model_instructions": lambda _self, _personality: "base",
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            personality="friendly",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<personality_spec>", developer_sections[1])
        self.assertIn("Be warm.", developer_sections[1])

    async def test_in_memory_session_initial_context_skips_baked_personality_spec(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "model_messages": ModelMessages({"friendly": "Be warm."}),
                "supports_personality": lambda _self: True,
                "get_model_instructions": lambda _self, _personality: "base",
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            personality="friendly",
            base_instructions="base",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertEqual(len(developer_sections), 1)
        self.assertIn("<permissions instructions>", developer_sections[0])

    async def test_in_memory_session_records_personality_update_from_reference_context(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "model_messages": ModelMessages(
                    {
                        "friendly": "Be warm.",
                        "terse": "Be concise.",
                    }
                ),
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            personality="friendly",
        )

        first_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(first_turn)
        session.personality = "terse"
        second_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(second_turn)

        self.assertEqual(len(session.recorded_batches), 2)
        item = session.recorded_batches[1][0]
        self.assertEqual(item.role, "developer")
        self.assertIn("<personality_spec>", item.content[0].text)
        self.assertIn("Be concise.", item.content[0].text)

    async def test_in_memory_session_exposes_reference_context_item(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)

        self.assertIsNone(await session.reference_context_item())
        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()

        self.assertIsNotNone(reference)
        self.assertEqual(reference.cwd, Path("C:/work/project"))
        self.assertEqual(reference.model, "gpt-test")

    async def test_in_memory_session_can_set_and_replace_reference_context_item(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()
        replacement = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "compacted"}],
        }

        await session.set_reference_context_item(None)
        self.assertIsNone(await session.reference_context_item())
        await session.replace_history([replacement], reference)

        self.assertEqual(await session.reference_context_item(), reference)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(session.history[0].role, "assistant")
        self.assertEqual(session.history[0].content[0].text, "compacted")

    async def test_in_memory_session_replace_compacted_history_records_compacted_item(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()
        replacement = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "summarized"}],
        }
        compacted_item = {
            "message": "summary",
            "replacement_history": [replacement],
        }

        await session.replace_compacted_history([replacement], reference, compacted_item)

        self.assertEqual(await session.reference_context_item(), reference)
        self.assertEqual(session.history[0].content[0].text, "summarized")
        self.assertEqual(len(session.compacted_items), 1)
        self.assertEqual(session.compacted_items[0].message, "summary")
        self.assertEqual(session.compacted_items[0].replacement_history, (replacement,))

    async def test_in_memory_session_inject_no_new_turn_records_items_and_flushes(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", active_turn=None)
        item = {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "outside turn"}],
        }

        await session.inject_no_new_turn([item], None)
        await session.flush_rollout()

        self.assertEqual(len(session.recorded_batches), 1)
        self.assertEqual(session.recorded_batches[0][0].role, "user")
        self.assertEqual(session.history[-1].content[0].text, "outside turn")
        self.assertEqual(session.flush_rollout_count, 1)

    async def test_in_memory_session_records_session_and_turn_permission_grants(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        session_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )
        turn_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        await record_granted_request_permissions(session_response, session=session)
        await record_granted_request_permissions(turn_response, turn_state=session)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(await session.granted_session_permissions(), expected)
        self.assertEqual(await session.granted_turn_permissions(), expected)
        self.assertTrue(session.strict_auto_review_enabled)
        self.assertTrue(await session.strict_auto_review())

    async def test_in_memory_session_new_turn_clears_turn_grants_but_keeps_session_grants(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        session_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )
        turn_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        await record_granted_request_permissions(session_response, session=session)
        await record_granted_request_permissions(turn_response, turn_state=session)
        await session.new_default_turn()

        self.assertEqual(
            await session.granted_session_permissions(),
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)
        self.assertFalse(await session.strict_auto_review())

    async def test_in_memory_session_request_permissions_normalizes_and_records_response(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(
                    network=NetworkPermissions(enabled=True),
                    file_system=FileSystemPermissions.from_read_write_roots(None, (cwd,)),
                ),
                scope=PermissionGrantScope.SESSION,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        requested_child = session.cwd / "child"
        args = RequestPermissionsArgs(
            RequestPermissionProfile(
                network=NetworkPermissions(enabled=True),
                file_system=FileSystemPermissions.from_read_write_roots(None, (requested_child,)),
            )
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(response.permissions.to_additional_permission_profile(), expected)
        self.assertEqual(await session.granted_session_permissions(), expected)
        self.assertIsNone(await session.granted_turn_permissions())

    async def test_in_memory_session_request_permissions_passes_session_cwd_when_cwd_missing(self) -> None:
        seen = {}

        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            seen["cwd"] = cwd
            return RequestPermissionsResponse(
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                scope=PermissionGrantScope.TURN,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, None, None)

        self.assertEqual(seen["cwd"], session.cwd)
        self.assertEqual(
            response.permissions.to_additional_permission_profile(),
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

    async def test_in_memory_session_request_permissions_records_turn_scope_and_strict_auto_review(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(response.permissions.to_additional_permission_profile(), expected)
        self.assertIsNone(await session.granted_session_permissions())
        self.assertEqual(await session.granted_turn_permissions(), expected)
        self.assertTrue(session.strict_auto_review_enabled)

    async def test_in_memory_session_empty_strict_turn_response_records_no_strict_state(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(),
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(
            response,
            RequestPermissionsResponse(
                RequestPermissionProfile(),
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            ),
        )
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_auto_denies_when_approval_never(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            raise AssertionError("approval never should not request permissions from the client")

        session = InMemoryCodexSession(
            cwd="C:/work/project",
            approval_policy=AskForApproval.NEVER,
            request_permissions_callback=callback,
        )
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(
            response,
            RequestPermissionsResponse(
                RequestPermissionProfile(),
                scope=PermissionGrantScope.TURN,
                strict_auto_review=False,
            ),
        )
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_auto_denies_when_granular_disallows_tool(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            raise AssertionError("granular policy should not request permissions from the client")

        session = InMemoryCodexSession(
            cwd="C:/work/project",
            approval_policy=GranularApprovalConfig(
                sandbox_approval=True,
                rules=True,
                mcp_elicitations=True,
                request_permissions=False,
            ),
            request_permissions_callback=callback,
        )
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(response, RequestPermissionsResponse(RequestPermissionProfile()))
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_strict_turn_grant_feeds_orchestrator_plan(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        await record_granted_request_permissions(response, turn_state=session)
        plan = await build_tool_orchestrator_plan_for_session(
            session,
            explicit_requirement=ExecApprovalRequirement.skip(),
            approval_policy=AskForApproval.NEVER,
            file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            managed_network_active=False,
        )

        self.assertEqual(plan.approval.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertTrue(plan.approval.strict_auto_review)
        self.assertTrue(plan.approval.guardian_review_id_required)

    async def test_in_memory_session_request_permissions_rejects_strict_auto_review_session_scope(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                scope=PermissionGrantScope.SESSION,
                strict_auto_review=True,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(response, RequestPermissionsResponse(RequestPermissionProfile()))
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_accepts_async_mapping_response(self) -> None:
        async def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
                "strict_auto_review": True,
            }

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(response.permissions.to_additional_permission_profile(), expected)
        self.assertEqual(await session.granted_turn_permissions(), expected)
        self.assertTrue(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_without_callback_records_no_grants(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(response, RequestPermissionsResponse(RequestPermissionProfile()))
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_none_callback_response_records_no_grants(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return None

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(response, RequestPermissionsResponse(RequestPermissionProfile()))
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_grants_feed_later_permission_application(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(
            effective.additional_permissions,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

    async def test_in_memory_session_turn_grants_feed_later_permission_application(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
        )

        await record_granted_request_permissions(response, turn_state=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(
            effective.additional_permissions,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )
        self.assertIsNone(await session.granted_session_permissions())

    async def test_in_memory_session_recorded_grant_preapproves_matching_inline_permissions(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        granted = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        response = RequestPermissionsResponse(
            RequestPermissionProfile.from_additional_permission_profile(granted),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            granted,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(effective.additional_permissions, granted)
        self.assertTrue(effective.permissions_preapproved)

    async def test_in_memory_session_recorded_grant_does_not_preapprove_broader_inline_permissions(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        granted = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(None, (session.cwd / "child",))
        )
        requested = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(None, (session.cwd,))
        )
        response = RequestPermissionsResponse(
            RequestPermissionProfile.from_additional_permission_profile(granted),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            requested,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(effective.additional_permissions, requested)
        self.assertFalse(effective.permissions_preapproved)

    async def test_in_memory_session_relative_deny_glob_grant_preapproves_matching_inline_permissions(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        requested = AdditionalPermissionProfile(
            file_system=FileSystemPermissions(
                entries=(
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                        FileSystemAccessMode.WRITE,
                    ),
                    FileSystemSandboxEntry(
                        FileSystemPath.glob_pattern("**/*.env"),
                        FileSystemAccessMode.DENY,
                    ),
                )
            )
        )
        response = RequestPermissionsResponse(
            RequestPermissionProfile.from_additional_permission_profile(requested),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            requested,
        )

        self.assertTrue(effective.permissions_preapproved)

    async def test_in_memory_session_new_turn_stops_turn_grant_application(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
        )

        await record_granted_request_permissions(response, turn_state=session)
        await session.new_default_turn()
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.USE_DEFAULT)
        self.assertIsNone(effective.additional_permissions)

    async def test_in_memory_session_session_grant_applies_after_new_turn(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        await session.new_default_turn()
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(
            effective.additional_permissions,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

    async def test_in_memory_session_set_total_tokens_full_emits_token_count(self) -> None:
        model_info = SimpleNamespace(
            slug="gpt-test",
            context_window=2000,
            max_context_window=None,
            effective_context_window_percent=80,
        )
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        turn_context = await session.new_default_turn()

        await session.set_total_tokens_full(turn_context)

        self.assertEqual(session.token_usage_info.total_token_usage.total_tokens, 1600)
        self.assertEqual(session.token_usage_info.last_token_usage.total_tokens, 1600)
        self.assertEqual(session.token_usage_info.model_context_window, 1600)
        self.assertEqual(len(session.emitted_events), 1)
        event = session.emitted_events[0]
        self.assertEqual(event.type, "token_count")
        self.assertEqual(event.payload.info, session.token_usage_info)
        self.assertIsNone(event.payload.rate_limits)

    async def test_in_memory_session_total_token_usage_delegates_to_state_history_tail_accounting(self) -> None:
        model_info = SimpleNamespace(slug="gpt-test")
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        turn_context = await session.new_default_turn()
        counted = ResponseItem.message("assistant", (ContentItem.output_text("already counted by API"),))
        added_user = ResponseItem.message("user", (ContentItem.input_text("new user message"),))
        added_tool_output = ResponseItem(
            type="custom_tool_call_output",
            call_id="tool-tail",
            output=FunctionCallOutputPayload.from_text("new tool output"),
        )

        await session.record_conversation_items(turn_context, (counted,))
        await session.record_token_usage_info(turn_context, TokenUsage(total_tokens=100))
        await session.record_conversation_items(turn_context, (added_user, added_tool_output))

        self.assertEqual(
            await session.get_total_token_usage(),
            100 + estimate_item_token_count(added_user) + estimate_item_token_count(added_tool_output),
        )
        total_usage = await session.total_token_usage()
        self.assertIsNotNone(total_usage)
        self.assertEqual(total_usage.total_tokens, 100)

    async def test_in_memory_session_total_token_usage_breakdown_delegates_to_state_history(self) -> None:
        model_info = SimpleNamespace(slug="gpt-test")
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        turn_context = await session.new_default_turn()
        counted = ResponseItem.message("assistant", (ContentItem.output_text("already counted by API"),))
        added_user = ResponseItem.message("user", (ContentItem.input_text("new user message"),))
        added_tool_output = ResponseItem(
            type="custom_tool_call_output",
            call_id="tool-tail",
            output=FunctionCallOutputPayload.from_text("new tool output"),
        )

        await session.record_conversation_items(turn_context, (counted,))
        await session.record_token_usage_info(turn_context, TokenUsage(total_tokens=100))
        await session.record_conversation_items(turn_context, (added_user, added_tool_output))

        breakdown = await session.get_total_token_usage_breakdown()

        self.assertEqual(breakdown.last_api_response_total_tokens, 100)
        self.assertEqual(
            breakdown.all_history_items_model_visible_bytes,
            sum(estimate_response_item_model_visible_bytes(item) for item in (counted, added_user, added_tool_output)),
        )
        self.assertEqual(
            breakdown.estimated_tokens_of_items_added_since_last_successful_api_response,
            estimate_item_token_count(added_user) + estimate_item_token_count(added_tool_output),
        )
        self.assertEqual(
            breakdown.estimated_bytes_of_items_added_since_last_successful_api_response,
            estimate_response_item_model_visible_bytes(added_user)
            + estimate_response_item_model_visible_bytes(added_tool_output),
        )

    async def test_in_memory_session_update_rate_limits_merges_and_emits_token_count(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        turn_context = await session.new_default_turn()
        previous = RateLimitSnapshot(
            limit_id="codex",
            credits=CreditsSnapshot(has_credits=True, unlimited=False, balance="10"),
            plan_type=AccountPlanType.PRO,
        )
        await session.record_rate_limits_info(previous)
        update = RateLimitSnapshot(
            primary=RateLimitWindow(used_percent=100.0, window_minutes=60),
        )

        await session.update_rate_limits(turn_context, update)

        self.assertEqual(session.latest_rate_limits.limit_id, "codex")
        self.assertEqual(session.latest_rate_limits.primary.used_percent, 100.0)
        self.assertEqual(session.latest_rate_limits.credits.balance, "10")
        self.assertEqual(session.latest_rate_limits.plan_type, AccountPlanType.PRO)
        self.assertEqual(len(session.emitted_events), 1)
        event = session.emitted_events[0]
        self.assertEqual(event.type, "token_count")
        self.assertIsNone(event.payload.info)
        self.assertEqual(event.payload.rate_limits, session.latest_rate_limits)

    async def test_in_memory_session_run_user_turn_sampling_tracks_resolved_config_from_settings_projection(self) -> None:
        captured = []
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            thread_id="thread-900",
            user_instructions="project instructions",
            base_instructions="base",
            history=[ResponseItem.message("developer", (ContentItem.input_text("context"),))],
        )

        await session.update_settings(SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only(network_access=True)))
        thread_snapshot = await session.thread_config_snapshot()
        expected_permission_profile = thread_snapshot.permission_profile.to_mapping()

        class FakeAnalytics:
            def track_turn_resolved_config(self, context, payload):
                captured.append((context, payload))

        session.services = SimpleNamespace(analytics_events_client=FakeAnalytics())
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        async def sampler(_request):
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            SimpleNamespace(is_azure_responses_endpoint=lambda: False),
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.last_agent_message, "done")
        self.assertEqual(len(captured), 1)
        _analytics_context, payload = captured[0]
        self.assertEqual(payload["permission_profile"], expected_permission_profile)
        self.assertTrue(payload["sandbox_network_access"])

        self.assertGreaterEqual(len(result.request_plans), 1)
        sampling_prompt_texts = self._assert_prompt_input_contains_permissions_instructions(
            result.request_plans[0].prompt.get_formatted_input()
        )
        self.assertGreaterEqual(len(sampling_prompt_texts), 1)
        self.assertTrue(any("<permissions instructions>" in text for text in sampling_prompt_texts))

    async def test_in_memory_session_prompt_instructions_injection_consistent_between_sampling_variants(self) -> None:
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        provider = {"base_url": "https://api.example.test/v1"}
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        auth = "sk-test"

        async def build_http_result() -> list[str]:
            seen = {}

            def opener(request):
                seen["body"] = json.loads(request.data.decode("utf-8"))
                return FakeResponse()

            session = InMemoryCodexSession(
                cwd="C:/work/project",
                model_info=model_info,
                user_instructions="project instructions",
                base_instructions="base",
                history=[ResponseItem.message("developer", (ContentItem.input_text("context"),))],
            )
            session.services = SimpleNamespace(analytics_events_client=None)
            await session.update_settings(SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only(network_access=True)))
            return self._collect_permissions_prompt_texts(
                (
                    await run_user_turn_http_sampling_from_session(
                        session,
                        (UserInput.text_input("hello"),),
                        client,
                        provider,
                        model_info,
                        auth=auth,
                        opener=opener,
                        built_tools=lambda _sess, _turn: Router(),
                    )
                ).request_plans[0].prompt.get_formatted_input()
            )

        async def build_sampling_result() -> list[str]:
            session = InMemoryCodexSession(
                cwd="C:/work/project",
                model_info=model_info,
                thread_id="thread-900",
                user_instructions="project instructions",
                base_instructions="base",
                history=[ResponseItem.message("developer", (ContentItem.input_text("context"),))],
            )
            session.services = SimpleNamespace(analytics_events_client=None)
            await session.update_settings(SessionSettingsUpdate(sandbox_policy=SandboxPolicy.read_only(network_access=True)))

            async def sampler(_request):
                return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

            return self._collect_permissions_prompt_texts(
                (
                    await run_user_turn_sampling_from_session(
                        session,
                        (UserInput.text_input("hello"),),
                        client,
                        SimpleNamespace(is_azure_responses_endpoint=lambda: False),
                        model_info,
                        sampler,
                        built_tools=lambda _sess, _turn: Router(),
                    )
                ).request_plans[0].prompt.get_formatted_input()
            )

        http_texts = await build_http_result()
        sampling_texts = await build_sampling_result()

        self.assertGreaterEqual(len(http_texts), 1)
        self.assertGreaterEqual(len(sampling_texts), 1)
        self.assertEqual(
            len([text for text in http_texts if "<permissions instructions>" in text]),
            len([text for text in sampling_texts if "<permissions instructions>" in text]),
        )

    async def test_in_memory_session_rate_limits_default_missing_limit_id_to_codex_after_other_bucket(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        await session.record_rate_limits_info(
            RateLimitSnapshot(
                limit_id="codex_other",
                limit_name="codex_other",
                primary=RateLimitWindow(used_percent=20.0, window_minutes=60, resets_at=200),
            )
        )

        await session.record_rate_limits_info(
            RateLimitSnapshot(
                primary=RateLimitWindow(used_percent=30.0, window_minutes=60, resets_at=300),
            )
        )

        self.assertEqual(session.latest_rate_limits.limit_id, "codex")
        self.assertIsNone(session.latest_rate_limits.limit_name)
        self.assertEqual(session.latest_rate_limits.primary.used_percent, 30.0)

    async def test_in_memory_session_rate_limits_carry_credits_and_plan_type_across_buckets(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        await session.record_rate_limits_info(
            RateLimitSnapshot(
                limit_id="codex",
                limit_name="codex",
                primary=RateLimitWindow(used_percent=10.0, window_minutes=60, resets_at=100),
                credits=CreditsSnapshot(has_credits=True, unlimited=False, balance="50"),
                plan_type=AccountPlanType.PLUS,
            )
        )

        await session.record_rate_limits_info(
            RateLimitSnapshot(
                limit_id="codex_other",
                primary=RateLimitWindow(used_percent=30.0, window_minutes=120, resets_at=200),
            )
        )

        self.assertEqual(session.latest_rate_limits.limit_id, "codex_other")
        self.assertIsNone(session.latest_rate_limits.limit_name)
        self.assertEqual(session.latest_rate_limits.primary.used_percent, 30.0)
        self.assertEqual(session.latest_rate_limits.primary.window_minutes, 120)
        self.assertEqual(session.latest_rate_limits.credits, CreditsSnapshot(True, False, "50"))
        self.assertEqual(session.latest_rate_limits.plan_type, AccountPlanType.PLUS)


if __name__ == "__main__":
    unittest.main()


