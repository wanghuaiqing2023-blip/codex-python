import json
import unittest
import asyncio
import base64
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketMemoryStream, ResponsesWebsocketTextMessage
from pycodex.codex_api.error import ApiError
from pycodex.codex_client import TransportError
from pycodex.core.http_transport import (
    CODEX_EXEC_ORIGINATOR,
    CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR,
    HttpTransportConfig,
    exec_originator_header_value,
    http_sampling_stream_max_retries,
    http_transport_config_from_provider,
    model_client_http_sampler,
    model_client_websocket_preferred_sampler,
    prewarm_model_client_websocket_session,
    response_items_from_responses_payload,
    run_user_turn_http_sampling_from_session,
    send_prepared_http_sampling_request,
)
from pycodex.core.client import ModelClient
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.core.tools.context import FunctionToolOutput
from pycodex.core.tools.registry import ToolRegistry
from pycodex.core.tools.router import ToolRouter
from pycodex.core.session.turn.sampler import PreparedSamplingRequest
from pycodex.core.session.turn.runtime import UserTurnSamplingRequest, run_user_turn_sampling_from_session
from pycodex.protocol import (
    BaseInstructions,
    CodexErr,
    ContentItem,
    ModelVerification,
    ReasoningEffort,
    RateLimitSnapshot,
    ResponseItem,
    SessionSource,
    SubAgentSource,
    ToolName,
    UserInput,
)


def non_lifecycle_events(events):
    return tuple(event for event in events if event.type not in {"task_started", "task_complete"})


class FakeResponse:
    def __init__(self, payload: dict, headers: object = None) -> None:
        self.payload = payload
        self.headers = headers

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class _SseResponse:
    def __init__(self, event: str, payload: dict) -> None:
        self.event = event
        self.payload = payload

    def read(self) -> bytes:
        return f"event: {self.event}\ndata: {json.dumps(self.payload)}\n\n".encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class History:
    def __init__(self, items: list[ResponseItem]) -> None:
        self.items = items

    def for_prompt(self, _modalities: object) -> list[ResponseItem]:
        return list(self.items)


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


class _WebsocketProvider:
    def info(self):
        return SimpleNamespace(supports_websockets=True)

    async def api_provider(self):
        return SimpleNamespace(
            name="OpenAI",
            base_url="https://api.example.test",
            query_params=None,
            headers={},
            stream_idle_timeout_ms=300_000,
        )

    async def api_auth(self):
        return {"Authorization": "Bearer test"}


def _run_sampler(sampler, request):
    return asyncio.run(
        sampler(
            UserTurnSamplingRequest(
                session=None,
                turn_context=None,
                request_plan=SimpleNamespace(request=request),
            )
        )
    )


class Session:
    def __init__(self) -> None:
        self.turn_context = type("TurnContext", (), {"model_info": None, "user_instructions": None, "cwd": "C:/work"})()
        self.history: list[ResponseItem] = []
        self.recorded: list[tuple[ResponseItem, ...]] = []
        self.emitted_events = []

    async def new_default_turn(self):
        return self.turn_context

    async def record_context_updates_and_set_reference_context_item(self, _turn_context) -> None:
        return None

    async def record_conversation_items(self, _turn_context, items: tuple[ResponseItem, ...]) -> None:
        self.recorded.append(items)
        self.history.extend(items)

    async def clone_history(self) -> History:
        return History(self.history)

    async def get_base_instructions(self) -> BaseInstructions:
        return BaseInstructions("base")

    async def send_event(self, _turn_context, event) -> None:
        self.emitted_events.append(event)


class HttpTransportTests(unittest.TestCase):
    def test_websocket_preferred_sampler_uses_websocket_when_provider_supports_it(self) -> None:
        # Rust crate/module: codex-core/src/client.rs::ModelClientSession::stream
        # Contract: Responses wire API prefers stream_responses_websocket when
        # the provider supports websockets instead of preparing HTTP first.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        seen: dict[str, object] = {}

        def connector(url, headers, turn_state):
            seen["url"] = url
            seen["headers"] = dict(headers)
            seen["turn_state"] = turn_state
            return (
                ResponsesWebsocketMemoryStream(
                    [
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.output_item.done",
                                    "item": {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [{"type": "output_text", "text": "from websocket"}],
                                    },
                                }
                            )
                        ),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.completed",
                                    "response": {"id": "resp-ws-1", "end_turn": True, "usage": {}},
                                }
                            )
                        ),
                    ]
                ),
                101,
                False,
                None,
                "gpt-ws",
            )

        def opener(_request):
            raise AssertionError("HTTP fallback should not be used")

        sampler = model_client_websocket_preferred_sampler(
            session,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            opener=opener,
            websocket_connector=connector,
        )
        result = _run_sampler(
            sampler,
            {
                "model": "gpt-test",
                "input": [],
                "stream": True,
                "store": False,
            },
        )

        self.assertEqual(result.mode, "responses_websocket")
        self.assertEqual(result.response_items[0].content[0].text, "from websocket")
        self.assertEqual(seen["url"], "wss://api.example.test/responses")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer test")
        self.assertEqual(session.websocket_session.last_response.response_id, "resp-ws-1")

    def test_websocket_prewarm_sends_generate_false_but_records_logical_request(self) -> None:
        # Rust crate/module: codex-core/src/client.rs::prewarm_websocket.
        # Contract: warmup sets `generate=false` only on the websocket payload;
        # websocket_session.last_request records the logical request so the
        # first real turn can reuse the warmup response id.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        memory_stream = ResponsesWebsocketMemoryStream(
            [
                ResponsesWebsocketTextMessage(
                    json.dumps(
                        {
                            "type": "response.completed",
                            "response": {"id": "resp-warm", "end_turn": True, "usage": {}},
                        }
                    )
                )
            ]
        )

        def connector(_url, _headers, _turn_state):
            return (memory_stream, 101, False, None, "gpt-ws")

        request = {
            "model": "gpt-test",
            "instructions": "You are Codex.",
            "input": [],
            "tools": [],
            "stream": True,
            "store": False,
        }
        result = asyncio.run(
            prewarm_model_client_websocket_session(
                session,
                HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
                request=request,
                connector=connector,
            )
        )

        sent = json.loads(memory_stream.sent_payloads[0])
        self.assertIsNotNone(result)
        self.assertIs(sent["generate"], False)
        self.assertNotIn("generate", session.websocket_session.last_request)
        self.assertEqual(session.websocket_session.last_request, request)
        self.assertEqual(session.websocket_session.last_response.response_id, "resp-warm")
        self.assertIs(session.websocket_session.last_response_from_untraced_warmup, True)

    def test_websocket_preferred_sampler_passes_provider_connect_timeout(self) -> None:
        # Rust crate/module: codex-core/src/client.rs::ModelClient::connect_websocket.
        # Contract: websocket connection setup is wrapped in
        # provider.info().websocket_connect_timeout().
        class Provider(_WebsocketProvider):
            def info(self):
                return SimpleNamespace(
                    supports_websockets=True,
                    websocket_connect_timeout=lambda: 12_345,
                )

        provider = Provider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        seen: dict[str, float | None] = {}

        def connector(_url, _headers, _turn_state, *, timeout=None):
            seen["timeout"] = timeout
            return (
                ResponsesWebsocketMemoryStream(
                    [
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.completed",
                                    "response": {"id": "resp-ws-timeout", "end_turn": True, "usage": {}},
                                }
                            )
                        )
                    ]
                ),
                101,
                False,
                None,
                "gpt-ws",
            )

        sampler = model_client_websocket_preferred_sampler(
            session,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            websocket_connector=connector,
        )

        _run_sampler(
            sampler,
            {
                "model": "gpt-test",
                "input": [],
                "stream": True,
                "store": False,
            },
        )

        self.assertEqual(seen["timeout"], 12.345)

    def test_websocket_preferred_sampler_falls_back_to_http_on_upgrade_required(self) -> None:
        # Rust crate/module: codex-core/src/client.rs::stream_responses_websocket
        # Contract: HTTP 426 Upgrade Required during websocket connection
        # returns FallbackToHttp and retries the same sampling request over HTTP.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        calls = {"websocket": 0, "http": 0}

        def connector(_url, _headers, _turn_state):
            calls["websocket"] += 1
            raise ApiError.transport_error(TransportError.http(426, body="upgrade required"))

        def opener(_request):
            calls["http"] += 1
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "from http"}],
                        }
                    ]
                }
            )

        sampler = model_client_websocket_preferred_sampler(
            session,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            opener=opener,
            websocket_connector=connector,
        )
        result = _run_sampler(
            sampler,
            {
                "model": "gpt-test",
                "input": [],
                "stream": True,
                "store": False,
            },
        )

        self.assertEqual(calls, {"websocket": 1, "http": 1})
        self.assertEqual(result.mode, "http")
        self.assertEqual(result.response_items[0].content[0].text, "from http")
        self.assertFalse(client.responses_websocket_enabled())

    def test_websocket_preferred_sampler_refreshes_auth_after_401(self) -> None:
        # Rust crate/module: codex-core/src/client.rs::stream_responses_websocket
        # Contract: websocket 401 runs handle_unauthorized, rebuilds auth, and
        # retries the websocket path before surfacing a terminal turn failure.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        token = {"value": "first-token"}
        seen_authorization: list[str] = []

        class Recovery:
            def __init__(self) -> None:
                self.calls = 0

            def has_next(self) -> bool:
                return self.calls == 0

            async def next(self):
                self.calls += 1
                token["value"] = "second-token"
                return object()

        class AuthManager:
            def __init__(self) -> None:
                self.recovery = Recovery()

            def unauthorized_recovery(self) -> Recovery:
                return self.recovery

        def transport_config() -> HttpTransportConfig:
            return HttpTransportConfig(
                "https://api.example.test/responses",
                headers={"Authorization": f"Bearer {token['value']}"},
            )

        def connector(_url, headers, _turn_state):
            seen_authorization.append(headers["Authorization"])
            if headers["Authorization"] == "Bearer first-token":
                raise ApiError.transport_error(TransportError.http(401, body='{"detail":"Unauthorized"}'))
            return (
                ResponsesWebsocketMemoryStream(
                    [
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.output_item.done",
                                    "item": {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [{"type": "output_text", "text": "after refresh"}],
                                    },
                                }
                            )
                        ),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.completed",
                                    "response": {"id": "resp-ws-refresh", "end_turn": True, "usage": {}},
                                }
                            )
                        ),
                    ]
                ),
                101,
                False,
                None,
                "gpt-ws",
            )

        sampler = model_client_websocket_preferred_sampler(
            session,
            transport_config(),
            websocket_connector=connector,
            auth_manager=AuthManager(),
            config_factory=transport_config,
        )
        result = _run_sampler(
            sampler,
            {
                "model": "gpt-test",
                "input": [],
                "stream": True,
                "store": False,
            },
        )

        self.assertEqual(seen_authorization, ["Bearer first-token", "Bearer second-token"])
        self.assertEqual(result.mode, "responses_websocket")
        self.assertEqual(result.response_items[0].content[0].text, "after refresh")

    def test_websocket_preferred_sampler_converts_rate_limit_events_to_protocol_snapshots(self) -> None:
        # Rust crate/modules:
        # - codex-api/src/endpoint/responses_websocket.rs streams
        #   codex.rate_limits via parse_rate_limit_event.
        # - codex-api/src/rate_limits.rs defines event window/credits shape.
        # Contract: core websocket sampling exposes protocol RateLimitSnapshot
        # values to the session runtime instead of codex-api-local dataclasses.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()

        def connector(_url, _headers, _turn_state):
            return (
                ResponsesWebsocketMemoryStream(
                    [
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "codex.rate_limits",
                                    "rate_limits": {
                                        "primary": {
                                            "used_percent": 47,
                                            "window_minutes": 300,
                                            "reset_at": 123456,
                                        }
                                    },
                                    "credits": {
                                        "has_credits": True,
                                        "unlimited": False,
                                        "balance": "12",
                                    },
                                    "plan_type": "pro",
                                    "metered_limit_name": "codex_primary",
                                }
                            )
                        ),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.output_item.done",
                                    "item": {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [{"type": "output_text", "text": "with rate limit"}],
                                    },
                                }
                            )
                        ),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.completed",
                                    "response": {"id": "resp-ws-rate", "end_turn": True, "usage": {}},
                                }
                            )
                        ),
                    ]
                ),
                101,
                False,
                None,
                "gpt-ws",
            )

        sampler = model_client_websocket_preferred_sampler(
            session,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            websocket_connector=connector,
        )
        result = _run_sampler(
            sampler,
            {
                "model": "gpt-test",
                "input": [],
                "stream": True,
                "store": False,
            },
        )

        self.assertIsInstance(result.rate_limits[0], RateLimitSnapshot)
        self.assertEqual(result.rate_limits[0].limit_id, "codex_primary")
        self.assertEqual(result.rate_limits[0].primary.used_percent, 47.0)
        self.assertEqual(result.rate_limits[0].primary.window_minutes, 300)
        self.assertEqual(result.rate_limits[0].primary.resets_at, 123456)
        self.assertEqual(result.rate_limits[0].credits.balance, "12")
        self.assertEqual(result.rate_limits[0].plan_type.value, "pro")
        rate_limit_event = next(event for event in result.stream_events if event.get("type") == "rate_limits")
        self.assertIsInstance(rate_limit_event["rate_limits"], RateLimitSnapshot)

    def test_websocket_preferred_sampler_observes_live_item_and_text_events_before_completed_result(self) -> None:
        # Rust crate/modules:
        # - codex-api/src/endpoint/responses_websocket.rs yields response
        #   events as websocket frames arrive.
        # - codex-core/src/client.rs::stream_responses_websocket forwards the
        #   stream rather than waiting for response.completed before the UI can
        #   observe deltas.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        observed: list[dict[str, object]] = []

        def connector(_url, _headers, _turn_state):
            return (
                ResponsesWebsocketMemoryStream(
                    [
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.output_item.done",
                                    "item": {
                                        "type": "function_call",
                                        "name": "exec_command",
                                        "arguments": "{\"cmd\":\"dir\"}",
                                        "call_id": "call-1",
                                    },
                                }
                            )
                        ),
                        ResponsesWebsocketTextMessage(json.dumps({"type": "response.output_text.delta", "delta": "live "})),
                        ResponsesWebsocketTextMessage(
                            json.dumps({"type": "response.output_text.delta", "delta": "delta"})
                        ),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.output_item.done",
                                    "item": {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [{"type": "output_text", "text": "live delta"}],
                                    },
                                }
                            )
                        ),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.completed",
                                    "response": {"id": "resp-ws-live", "end_turn": True, "usage": {}},
                                }
                            )
                        ),
                    ]
                ),
                101,
                False,
                None,
                "gpt-ws",
            )

        sampler = model_client_websocket_preferred_sampler(
            session,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            websocket_connector=connector,
            stream_event_observer=observed.append,
        )
        internal_observed = []

        async def internal_stream_observer(event):
            internal_observed.append((event.get("type"), event.get("delta")))

        result = asyncio.run(
            sampler(
                UserTurnSamplingRequest(
                    session=None,
                    turn_context=None,
                    request_plan=SimpleNamespace(
                        request={
                            "model": "gpt-test",
                            "input": [],
                            "stream": True,
                            "store": False,
                        }
                    ),
                    stream_event_observer=internal_stream_observer,
                )
            )
        )

        self.assertEqual(
            [event for event in observed if event.get("type") == "output_text_delta"],
            [{"type": "output_text_delta", "delta": "live "}, {"type": "output_text_delta", "delta": "delta"}],
        )
        self.assertIn(("output_text_delta", "live "), internal_observed)
        self.assertIn(("output_text_delta", "delta"), internal_observed)
        self.assertTrue(result.live_stream_events_emitted)
        observed_item_events = [event for event in observed if event.get("type") == "output_item_done"]
        self.assertEqual(observed_item_events[0]["item"].type, "function_call")
        self.assertEqual(observed_item_events[0]["item"].name, "exec_command")
        self.assertEqual(result.response_items[-1].content[0].text, "live delta")

    def test_websocket_stream_marks_live_events_when_only_external_observer_is_present(self) -> None:
        # Rust crate/module: codex-core/src/client.rs + session/turn.rs.
        # Contract: the websocket stream is a single transport source. If a
        # caller observes those raw stream events live, the prepared result must
        # record that fact so the core turn runtime does not replay them as if
        # no live events were emitted.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        observed = []
        def connector(_url, _headers, _turn_state):
            return (
                ResponsesWebsocketMemoryStream(
                    [
                        ResponsesWebsocketTextMessage(json.dumps({"type": "response.output_text.delta", "delta": "live"})),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.output_item.done",
                                    "item": {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [{"type": "output_text", "text": "live"}],
                                    },
                                }
                            )
                        ),
                        ResponsesWebsocketTextMessage(
                            json.dumps(
                                {
                                    "type": "response.completed",
                                    "response": {"id": "resp-ws-external", "end_turn": True, "usage": {}},
                                }
                            )
                        ),
                    ]
                ),
                101,
                False,
                None,
                "gpt-ws",
            )
        sampler = model_client_websocket_preferred_sampler(
            session,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            websocket_connector=connector,
            stream_event_observer=observed.append,
        )

        result = asyncio.run(
            sampler(
                UserTurnSamplingRequest(
                    session=None,
                    turn_context=None,
                    request_plan=SimpleNamespace(
                        request={"model": "gpt-test", "input": [], "stream": True, "store": False}
                    ),
                    stream_event_observer=None,
                )
            )
        )

        self.assertEqual(
            [event for event in observed if event.get("type") == "output_text_delta"],
            [{"type": "output_text_delta", "delta": "live"}],
        )
        self.assertTrue(result.live_stream_events_emitted)

    def test_websocket_stream_disconnect_falls_back_to_http_like_rust(self) -> None:
        # Rust crate/modules:
        # - codex-core/src/session/turn.rs calls
        #   handle_retryable_response_stream_error for retryable stream errors.
        # - codex-core/src/responses_retry.rs falls back from WebSockets to
        #   HTTPS transport once retries are exhausted and websocket fallback is
        #   available.
        # Contract: a websocket stream that closes before response.completed
        # must not strand the TUI turn; it switches the ModelClientSession to
        # HTTP and completes through the Responses SSE path.
        provider = _WebsocketProvider()
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        session = client.new_session()
        websocket_calls = 0
        http_calls = 0
        decisions = []

        def connector(_url, _headers, _turn_state):
            nonlocal websocket_calls
            websocket_calls += 1
            return ResponsesWebsocketMemoryStream([]), 101, False, None, "gpt-ws"

        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {\"type\":\"response.output_item.done\",\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"http fallback\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp-http-fallback\",\"end_turn\":true,\"usage\":{\"input_tokens\":1,\"output_tokens\":2,\"total_tokens\":3}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(_request):
            nonlocal http_calls
            http_calls += 1
            return SseResponse()

        sampler = model_client_websocket_preferred_sampler(
            session,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            opener=opener,
            websocket_connector=connector,
            max_retries=0,
            sleep=lambda _seconds: None,
            on_retry_decision=decisions.append,
        )

        result = _run_sampler(
            sampler,
            {
                "model": "gpt-test",
                "input": [],
                "stream": True,
                "store": False,
            },
        )

        self.assertEqual(websocket_calls, 1)
        self.assertEqual(http_calls, 1)
        self.assertFalse(session.client.responses_websocket_enabled())
        self.assertEqual(result.mode, "http")
        self.assertEqual(result.response_items[0].content[0].text, "http fallback")
        self.assertTrue(decisions)
        self.assertIn("Falling back from WebSockets to HTTPS transport.", decisions[-1].warning_message)

    def test_http_sampling_stream_max_retries_uses_rust_defaults_and_cap(self) -> None:
        self.assertEqual(http_sampling_stream_max_retries({}), 5)
        self.assertEqual(http_sampling_stream_max_retries({"stream_max_retries": 7}), 7)
        self.assertEqual(http_sampling_stream_max_retries({"stream_max_retries": 101}), 100)
        self.assertEqual(
            http_sampling_stream_max_retries({"info": {"stream_max_retries": 3}, "stream_max_retries": 9}),
            3,
        )

    def test_response_items_from_responses_payload_reads_output_items(self) -> None:
        items = response_items_from_responses_payload(
            {"output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}]}
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].role, "assistant")
        self.assertEqual(items[0].content[0].text, "done")

    def test_send_prepared_http_sampling_request_posts_json_and_returns_items(self) -> None:
        seen = {}

        def opener(request):
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["headers"] = {key.lower(): value for key, value in request.header_items()}
            seen["content_type"] = request.headers["Content-type"]
            seen["authorization"] = request.headers["Authorization"]
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                }
            )

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            opener=opener,
        )

        self.assertEqual(seen["url"], "https://api.example.test/responses")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["body"], {"model": "gpt-test", "input": []})
        self.assertEqual(seen["content_type"], "application/json")
        self.assertEqual(seen["authorization"], "Bearer test")
        self.assertEqual(result.response_items[0].content[0].text, "done")

    def test_send_prepared_http_sampling_request_serializes_enum_values(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["headers"] = {key.lower(): value for key, value in request.header_items()}
            return FakeResponse({"output": []})

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"reasoning": {"effort": ReasoningEffort.HIGH}},
        )

        send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=opener,
        )

        self.assertEqual(seen["body"], {"reasoning": {"effort": "high"}})

    def test_send_prepared_http_sampling_request_parses_responses_sse_stream(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {\"type\":\"response.output_item.done\",\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"done\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp-1\",\"usage\":{\"input_tokens\":3,\"output_tokens\":2,\"total_tokens\":5}}}\n"
                    "\n"
                    "data: [DONE]\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(result.raw_result["id"], "resp-1")
        self.assertEqual(result.raw_result["usage"]["input_tokens"], 3)
        self.assertEqual(result.raw_result["output"][0]["type"], "message")

    def test_send_prepared_http_sampling_request_uses_sse_event_name_when_data_lacks_type(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"from event name\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-2\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(result.response_items[0].content[0].text, "from event name")
        self.assertEqual(result.raw_result["id"], "resp-2")
        self.assertEqual(result.raw_result["type"], "response.completed")

    def test_send_prepared_http_sampling_request_accumulates_sse_output_text_delta(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.added\n"
                    "data: {\"item\":{\"id\":\"msg-1\",\"type\":\"message\",\"role\":\"assistant\",\"content\":[]}}\n"
                    "\n"
                    "event: response.output_text.delta\n"
                    "data: {\"delta\":\"hel\"}\n"
                    "\n"
                    "event: response.output_text.delta\n"
                    "data: {\"delta\":\"lo\"}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-delta\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(result.response_items[0].id, "msg-1")
        self.assertEqual(result.response_items[0].content[0].text, "hello")
        self.assertEqual(result.raw_result["output"][0]["content"][0]["text"], "hello")
        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            ("output_item_added", "output_text_delta", "output_text_delta", "completed"),
        )
        self.assertEqual(result.stream_events[1]["delta"], "hel")
        self.assertEqual(result.stream_events[-1]["response_id"], "resp-delta")

    def test_model_client_http_sampler_observes_sse_delta_live_like_rust(self) -> None:
        # Rust source: codex-core/src/client.rs::stream_responses_api maps SSE
        # events as the stream is read. Contract: HTTP fallback must deliver
        # response.output_text.delta to the core live observer before the full
        # response is complete.
        observed: list[dict[str, object]] = []

        class LineSseResponse:
            def __init__(self) -> None:
                self.lines = iter(
                    [
                        b"event: response.output_item.added\n",
                        b'data: {"item":{"id":"msg-live","type":"message","role":"assistant","content":[]}}\n',
                        b"\n",
                        b"event: response.output_text.delta\n",
                        b'data: {"delta":"live "}\n',
                        b"\n",
                        b"event: response.output_text.delta\n",
                        b'data: {"delta":"http"}\n',
                        b"\n",
                        b"event: response.completed\n",
                        b'data: {"response":{"id":"resp-http-live","end_turn":true,"usage":{"input_tokens":1,"output_tokens":2,"total_tokens":3}}}\n',
                        b"\n",
                    ]
                )

            def readline(self) -> bytes:
                return next(self.lines, b"")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        sampler = model_client_http_sampler(
            client.new_session(),
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            opener=lambda _request: LineSseResponse(),
        )

        async def run():
            return await sampler(
                UserTurnSamplingRequest(
                    session=None,
                    turn_context=None,
                    request_plan=SimpleNamespace(
                        request={"model": "gpt-test", "input": [], "stream": True, "store": False}
                    ),
                    stream_event_observer=observed.append,
                )
            )

        result = asyncio.run(run())

        self.assertEqual(
            [event for event in observed if event.get("type") == "output_text_delta"],
            [{"type": "output_text_delta", "delta": "live "}, {"type": "output_text_delta", "delta": "http"}],
        )
        self.assertTrue(result.live_stream_events_emitted)
        self.assertEqual(result.response_items[0].content[0].text, "live http")

    def test_send_prepared_http_sampling_request_records_rust_style_sse_stream_events(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.added\n"
                    "data: {\"item\":{\"id\":\"custom-1\",\"type\":\"custom_tool_call\",\"call_id\":\"call-1\",\"name\":\"apply_patch\",\"input\":\"\"}}\n"
                    "\n"
                    "event: response.custom_tool_call_input.delta\n"
                    "data: {\"item_id\":\"custom-1\",\"call_id\":\"call-1\",\"delta\":\"*** Begin Patch\"}\n"
                    "\n"
                    "event: response.reasoning_summary_text.delta\n"
                    "data: {\"delta\":\"summary\",\"summary_index\":0}\n"
                    "\n"
                    "event: response.reasoning_text.delta\n"
                    "data: {\"delta\":\"raw\",\"content_index\":1}\n"
                    "\n"
                    "event: response.reasoning_summary_part.added\n"
                    "data: {\"summary_index\":2}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"id\":\"custom-1\",\"type\":\"custom_tool_call\",\"call_id\":\"call-1\",\"name\":\"apply_patch\",\"input\":\"*** Begin Patch\"}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-events\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5},\"end_turn\":false}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            (
                "output_item_added",
                "tool_call_input_delta",
                "reasoning_summary_delta",
                "reasoning_content_delta",
                "reasoning_summary_part_added",
                "output_item_done",
                "completed",
            ),
        )
        self.assertEqual(result.stream_events[0]["item"].type, "custom_tool_call")
        self.assertEqual(
            result.stream_events[1],
            {
                "type": "tool_call_input_delta",
                "item_id": "custom-1",
                "delta": "*** Begin Patch",
                "call_id": "call-1",
            },
        )
        self.assertEqual(result.stream_events[2]["summary_index"], 0)
        self.assertEqual(result.stream_events[3]["content_index"], 1)
        self.assertEqual(result.stream_events[4]["summary_index"], 2)
        self.assertEqual(result.stream_events[-1]["response_id"], "resp-events")
        self.assertEqual(result.stream_events[-1]["end_turn"], False)

    def test_send_prepared_http_sampling_request_accumulates_function_call_argument_deltas(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.added\n"
                    "data: {\"item\":{\"id\":\"fc-1\",\"type\":\"function_call\",\"call_id\":\"call-1\",\"name\":\"exec_command\",\"arguments\":\"\"}}\n"
                    "\n"
                    "event: response.function_call_arguments.delta\n"
                    "data: {\"item_id\":\"fc-1\",\"delta\":\"{\\\"cmd\\\":\\\"\"}\n"
                    "\n"
                    "event: response.function_call_arguments.delta\n"
                    "data: {\"item_id\":\"fc-1\",\"delta\":\"echo hi\\\"}\"}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-function-delta\"}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            ("output_item_added", "tool_call_input_delta", "tool_call_input_delta", "completed"),
        )
        self.assertEqual(result.stream_events[1]["item_id"], "fc-1")
        self.assertEqual(result.stream_events[-1]["response_id"], "resp-function-delta")
        self.assertEqual(result.response_items[0].type, "function_call")
        self.assertEqual(result.response_items[0].name, "exec_command")
        self.assertEqual(result.response_items[0].call_id, "call-1")
        self.assertEqual(result.response_items[0].arguments, "{\"cmd\":\"echo hi\"}")
        self.assertEqual(result.raw_result["output"][0]["arguments"], "{\"cmd\":\"echo hi\"}")

    def test_send_prepared_http_sampling_request_accumulates_custom_tool_input_deltas(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.added\n"
                    "data: {\"item\":{\"id\":\"custom-1\",\"type\":\"custom_tool_call\",\"call_id\":\"patch-1\",\"name\":\"apply_patch\",\"input\":\"\"}}\n"
                    "\n"
                    "event: response.custom_tool_call_input.delta\n"
                    "data: {\"item_id\":\"custom-1\",\"call_id\":\"patch-1\",\"delta\":\"*** Begin Patch\\n\"}\n"
                    "\n"
                    "event: response.custom_tool_call_input.delta\n"
                    "data: {\"item_id\":\"custom-1\",\"call_id\":\"patch-1\",\"delta\":\"*** End Patch\\n\"}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-custom-delta\"}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            ("output_item_added", "tool_call_input_delta", "tool_call_input_delta", "completed"),
        )
        self.assertEqual(result.stream_events[1]["item_id"], "custom-1")
        self.assertEqual(result.stream_events[1]["call_id"], "patch-1")
        self.assertEqual(result.stream_events[-1]["response_id"], "resp-custom-delta")
        self.assertEqual(result.response_items[0].type, "custom_tool_call")
        self.assertEqual(result.response_items[0].name, "apply_patch")
        self.assertEqual(result.response_items[0].call_id, "patch-1")
        self.assertEqual(result.response_items[0].input, "*** Begin Patch\n*** End Patch\n")
        self.assertEqual(result.raw_result["output"][0]["input"], "*** Begin Patch\n*** End Patch\n")

    def test_send_prepared_http_sampling_request_replaces_streamed_item_on_matching_done(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.added\n"
                    "data: {\"item\":{\"id\":\"msg-1\",\"type\":\"message\",\"role\":\"assistant\",\"content\":[]}}\n"
                    "\n"
                    "event: response.output_text.delta\n"
                    "data: {\"delta\":\"partial\"}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"id\":\"msg-1\",\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"final\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-done\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(len(result.response_items), 1)
        self.assertEqual(result.response_items[0].content[0].text, "final")
        self.assertEqual(len(result.raw_result["output"]), 1)
        self.assertEqual(result.raw_result["output"][0]["content"][0]["text"], "final")

    def test_send_prepared_http_sampling_request_replaces_streamed_item_without_id_on_done(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.added\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[]}}\n"
                    "\n"
                    "event: response.output_text.delta\n"
                    "data: {\"delta\":\"partial\"}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"final\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-no-id\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(len(result.response_items), 1)
        self.assertEqual(result.response_items[0].content[0].text, "final")
        self.assertEqual(len(result.raw_result["output"]), 1)
        self.assertEqual(result.raw_result["output"][0]["content"][0]["text"], "final")

    def test_send_prepared_http_sampling_request_stops_processing_after_sse_completed_like_rust(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"done\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-complete\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                    "event: response.failed\n"
                    "data: {\"response\":{\"status\":\"failed\",\"error\":{\"message\":\"late failure\"}}}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"late\"}]}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(result.raw_result["id"], "resp-complete")
        self.assertEqual([item.content[0].text for item in result.response_items], ["done"])
        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            ("output_item_done", "completed"),
        )

    def test_send_prepared_http_sampling_request_defers_sse_failed_until_close_like_rust(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.failed\n"
                    "data: {\"response\":{\"status\":\"failed\",\"error\":{\"code\":\"unknown\",\"message\":\"early failure\"}}}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"recovered\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-recovered\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(result.raw_result["id"], "resp-recovered")
        self.assertEqual(result.response_items[0].content[0].text, "recovered")
        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            ("output_item_done", "completed"),
        )

    def test_send_prepared_http_sampling_request_raises_pending_sse_failed_when_stream_closes(self) -> None:
        message = "early failure"

        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.failed\n"
                    f"data: {{\"response\":{{\"status\":\"failed\",\"error\":{{\"code\":\"unknown\",\"message\":{json.dumps(message)}}}}}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: SseResponse(),
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, message)
        self.assertTrue(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_backfills_empty_sse_completed_output(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"function_call\",\"name\":\"echo\",\"arguments\":\"{}\",\"call_id\":\"call-1\"}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-empty-output\",\"output\":[],\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(result.response_items[0].type, "function_call")
        self.assertEqual(result.response_items[0].call_id, "call-1")
        self.assertEqual(len(result.raw_result["output"]), 1)
        self.assertEqual(result.raw_result["output"][0]["type"], "function_call")
        self.assertEqual(result.raw_result["output"][0]["call_id"], "call-1")

    def test_send_prepared_http_sampling_request_rejects_malformed_sse_completed_response(self) -> None:
        class MalformedCompletedSseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.completed\n"
                    "data: {\"response\":{\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: MalformedCompletedSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertIn("failed to parse ResponseCompleted", str(caught.exception))

    def test_send_prepared_http_sampling_request_skips_malformed_sse_output_item_events(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.added\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\"}}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\"}}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"ok\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-skip-malformed\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(len(result.response_items), 1)
        self.assertEqual(result.response_items[0].content[0].text, "ok")
        self.assertEqual(len(result.raw_result["output"]), 1)
        self.assertEqual(result.raw_result["output"][0]["content"][0]["text"], "ok")

    def test_send_prepared_http_sampling_request_skips_malformed_sse_data_events(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {not-json}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: [\"not\", \"an\", \"object\"]\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"type\":\"response.output_item.done\",\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"ok\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp-skip-bad-data\",\"usage\":{\"input_tokens\":4,\"output_tokens\":1,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses"),
            opener=lambda _request: SseResponse(),
        )

        self.assertEqual(len(result.response_items), 1)
        self.assertEqual(result.response_items[0].content[0].text, "ok")
        self.assertEqual(result.raw_result["id"], "resp-skip-bad-data")

    def test_send_prepared_http_sampling_request_reports_closed_before_completed_when_all_sse_data_is_bad(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {not-json}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: [\"not\", \"an\", \"object\"]\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: SseResponse(),
            )

        self.assertEqual(caught.exception.kind, "response_stream_failed")
        self.assertIn("stream closed before response.completed", str(caught.exception))

    def test_send_prepared_http_sampling_request_ignores_completed_without_response_until_stream_closes(self) -> None:
        class MissingResponseCompletedSseResponse:
            def read(self) -> bytes:
                return b"event: response.completed\ndata: {}\n\n"

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: MissingResponseCompletedSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "response_stream_failed")
        self.assertIn("stream closed before response.completed", str(caught.exception))

    def test_send_prepared_http_sampling_request_errors_when_sse_closes_before_completed(self) -> None:
        class DroppedSseResponse:
            def read(self) -> bytes:
                return (
                    "data: {\"type\":\"response.output_item.done\",\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"partial\"}]}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: DroppedSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "response_stream_failed")
        self.assertIn("stream closed before response.completed", str(caught.exception))

    def test_send_prepared_http_sampling_request_maps_sse_rate_limit_failed_to_stream_retry(self) -> None:
        message = (
            "Rate limit reached for gpt-test on tokens per min (TPM): Limit 30000, Used 22999, "
            "Requested 12528. Please try again in 11.054s."
        )

        class RateLimitSseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.failed\n"
                    f"data: {{\"response\":{{\"status\":\"failed\",\"error\":{{\"code\":\"rate_limit_exceeded\",\"message\":{json.dumps(message)}}}}}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: RateLimitSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, message)
        self.assertEqual(caught.exception.payload, 11.054)
        self.assertTrue(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_maps_terminal_sse_failed_errors(self) -> None:
        cases = (
            ("context_length_exceeded", "too much context", "context_window_exceeded"),
            ("insufficient_quota", "quota exceeded", "quota_exceeded"),
            ("usage_not_included", "usage not included", "usage_not_included"),
            ("cyber_policy", "cyber policy", "cyber_policy"),
            ("invalid_prompt", "invalid prompt", "invalid_request"),
            ("server_is_overloaded", "overloaded", "server_overloaded"),
            ("slow_down", "slow down", "server_overloaded"),
        )
        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        for code, message, kind in cases:
            with self.subTest(code=code):
                with self.assertRaises(CodexErr) as caught:
                    send_prepared_http_sampling_request(
                        prepared,
                        HttpTransportConfig("https://api.example.test/responses"),
                        opener=lambda _request, code=code, message=message: _SseResponse(
                            "response.failed",
                            {"response": {"status": "failed", "error": {"code": code, "message": message}}},
                        ),
                    )

                self.assertEqual(caught.exception.kind, kind)
                self.assertFalse(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_uses_cyber_policy_fallback_for_empty_sse_message(self) -> None:
        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: _SseResponse(
                    "response.failed",
                    {"response": {"status": "failed", "error": {"code": "cyber_policy", "message": "   "}}},
                ),
            )

        self.assertEqual(caught.exception.kind, "cyber_policy")
        self.assertEqual(str(caught.exception), "This request has been flagged for possible cybersecurity risk.")

    def test_send_prepared_http_sampling_request_maps_sse_rate_limit_milliseconds_retry(self) -> None:
        message = (
            "Rate limit reached for gpt-test on tokens per min (TPM): Limit 1, Used 1, "
            "Requested 19304. Please try again in 28ms."
        )

        class RateLimitSseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.failed\n"
                    f"data: {{\"response\":{{\"status\":\"failed\",\"error\":{{\"code\":\"rate_limit_exceeded\",\"message\":{json.dumps(message)}}}}}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: RateLimitSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, message)
        self.assertEqual(caught.exception.payload, 0.028)
        self.assertTrue(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_maps_unknown_sse_failed_to_stream(self) -> None:
        message = "temporary provider failure"

        class FailedSseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.failed\n"
                    f"data: {{\"response\":{{\"status\":\"failed\",\"error\":{{\"code\":\"unknown\",\"message\":{json.dumps(message)}}}}}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: FailedSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, message)
        self.assertTrue(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_maps_sse_failed_without_response_to_stream(self) -> None:
        class FailedSseResponse:
            def read(self) -> bytes:
                return b"event: response.failed\ndata: {}\n\n"

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: FailedSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, "response.failed event received")
        self.assertTrue(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_maps_sse_incomplete_reason_to_stream(self) -> None:
        class IncompleteSseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.incomplete\n"
                    "data: {\"response\":{\"status\":\"incomplete\",\"incomplete_details\":{\"reason\":\"max_output_tokens\"}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": [], "stream": True},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=lambda _request: IncompleteSseResponse(),
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, "Incomplete response returned, reason: max_output_tokens")
        self.assertTrue(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_maps_429_to_retry_limit(self) -> None:
        headers = Message()
        headers["x-request-id"] = "req-123"

        def opener(_request):
            raise HTTPError(
                "https://api.example.test/responses",
                429,
                "Too Many Requests",
                headers,
                BytesIO(b'{"error":{"message":"too fast"}}'),
            )

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )

        self.assertEqual(caught.exception.kind, "retry_limit")
        self.assertFalse(caught.exception.is_retryable())
        self.assertEqual(caught.exception.http_status_code_value(), 429)
        self.assertIn("req-123", str(caught.exception))

    def test_send_prepared_http_sampling_request_maps_usage_limit_error(self) -> None:
        headers = Message()
        headers["x-codex-active-limit"] = "codex_other"
        headers["x-codex-other-limit-name"] = "codex_other"
        headers["x-codex-other-primary-used-percent"] = "100"
        headers["x-codex-other-primary-window-minutes"] = "60"
        headers["x-codex-promo-message"] = "Upgrade for more usage"
        headers["x-codex-rate-limit-reached-type"] = "workspace_owner_usage_limit_reached"

        def opener(_request):
            raise HTTPError(
                "https://api.example.test/responses",
                429,
                "Too Many Requests",
                headers,
                BytesIO(b'{"error":{"type":"usage_limit_reached","plan_type":"pro","resets_at":1704069000}}'),
            )

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )

        self.assertEqual(caught.exception.kind, "usage_limit_reached")
        self.assertFalse(caught.exception.is_retryable())
        usage_limit = caught.exception.payload
        self.assertEqual(usage_limit.plan_type.known.value, "pro")
        self.assertEqual(usage_limit.rate_limits.limit_name, "codex_other")
        self.assertEqual(usage_limit.rate_limits.primary.used_percent, 100.0)
        self.assertEqual(usage_limit.promo_message, "Upgrade for more usage")
        self.assertEqual(usage_limit.rate_limit_reached_type.value, "workspace_owner_usage_limit_reached")

    def test_send_prepared_http_sampling_request_maps_response_failed_context_window(self) -> None:
        def opener(_request):
            return FakeResponse(
                {
                    "status": "failed",
                    "error": {
                        "code": "context_length_exceeded",
                        "message": "Your input exceeds the context window of this model.",
                    },
                }
            )

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )

        self.assertEqual(caught.exception.kind, "context_window_exceeded")
        self.assertFalse(caught.exception.is_retryable())

    def test_send_prepared_http_sampling_request_maps_400_to_invalid_request(self) -> None:
        body = b'{"error":{"message":"bad schema","code":"some_other_policy"}}'

        def opener(_request):
            raise HTTPError(
                "https://api.example.test/responses",
                400,
                "Bad Request",
                {},
                BytesIO(body),
            )

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )

        self.assertEqual(caught.exception.kind, "invalid_request")
        self.assertFalse(caught.exception.is_retryable())
        self.assertEqual(caught.exception.message, body.decode("utf-8"))

    def test_send_prepared_http_sampling_request_maps_url_error_to_connection_failed(self) -> None:
        def opener(_request):
            raise URLError("temporary dns failure")

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )

        self.assertEqual(caught.exception.kind, "connection_failed")
        self.assertTrue(caught.exception.is_retryable())
        self.assertIn("temporary dns failure", str(caught.exception))

    def test_send_prepared_http_sampling_request_maps_timeouts_to_request_timeout(self) -> None:
        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        for error in (TimeoutError("timed out"), URLError(TimeoutError("timed out"))):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(CodexErr) as caught:
                    send_prepared_http_sampling_request(
                        prepared,
                        HttpTransportConfig("https://api.example.test/responses"),
                        opener=lambda _request, error=error: (_ for _ in ()).throw(error),
                    )

                self.assertEqual(caught.exception.kind, "request_timeout")
                self.assertTrue(caught.exception.is_retryable())
                self.assertEqual(str(caught.exception), "request timed out")

    def test_send_prepared_http_sampling_request_preserves_identity_error_headers_case_insensitively(self) -> None:
        encoded_error = base64.b64encode(b'{"error":{"code":"token_expired"}}').decode("ascii")
        headers = {
            "X-Request-Id": "req-401",
            "Cf-Ray": "ray-401",
            "X-OpenAI-Authorization-Error": "missing_authorization_header",
            "X-Error-Json": encoded_error,
        }

        def opener(_request):
            raise HTTPError(
                "https://chatgpt.com/backend-api/codex/models",
                401,
                "Unauthorized",
                headers,
                BytesIO(b'{"detail":"Unauthorized"}'),
            )

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        with self.assertRaises(CodexErr) as caught:
            send_prepared_http_sampling_request(
                prepared,
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )

        self.assertEqual(caught.exception.kind, "unexpected_status")
        unexpected = caught.exception.payload
        self.assertEqual(unexpected.request_id, "req-401")
        self.assertEqual(unexpected.cf_ray, "ray-401")
        self.assertEqual(unexpected.identity_authorization_error, "missing_authorization_header")
        self.assertEqual(unexpected.identity_error_code, "token_expired")
        self.assertIn("auth error: missing_authorization_header", str(caught.exception))

    def test_http_transport_config_from_provider_combines_endpoint_auth_and_client_headers(self) -> None:
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            beta_features_header="feature-a",
            include_timing_metrics=True,
        )
        provider = {"base_url": "https://api.example.test/v1"}

        with patch.dict("os.environ", {}, clear=True):
            config = http_transport_config_from_provider(
                client,
                provider,
                auth={"api_key": "sk-test"},
                turn_metadata_header="turn-meta",
            )

        self.assertEqual(config.endpoint, "https://api.example.test/v1/responses")
        self.assertEqual(config.headers["Authorization"], "Bearer sk-test")
        self.assertEqual(config.headers["x-codex-beta-features"], "feature-a")
        self.assertEqual(config.headers["x-codex-turn-metadata"], "turn-meta")
        self.assertEqual(config.headers["x-codex-installation-id"], "install")
        self.assertNotIn("x-client-request-id", config.headers)
        self.assertEqual(config.headers["session-id"], "session")
        self.assertEqual(config.headers["thread-id"], "thread")
        self.assertEqual(config.headers["x-codex-window-id"], "thread:0")
        self.assertEqual(config.headers["x-responsesapi-include-timing-metrics"], "true")
        self.assertEqual(config.headers["Originator"], CODEX_EXEC_ORIGINATOR)

    def test_http_transport_records_and_replays_turn_state_header(self) -> None:
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        model_session = client.new_session()
        config = http_transport_config_from_provider(
            client,
            {"base_url": "https://api.example.test/v1"},
            auth={"api_key": "sk-test"},
        )
        config = HttpTransportConfig(
            config.endpoint,
            headers=config.headers,
            timeout=config.timeout,
            turn_state=model_session.turn_state,
        )
        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )
        seen_headers = []
        response_headers = Message()
        response_headers["x-codex-turn-state"] = "sticky"
        replacement_headers = Message()
        replacement_headers["x-codex-turn-state"] = "replacement"

        def opener(request):
            seen_headers.append({key.lower(): value for key, value in request.header_items()})
            headers = response_headers if len(seen_headers) == 1 else replacement_headers
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                },
                headers=headers,
            )

        first = send_prepared_http_sampling_request(prepared, config, opener=opener)
        second = send_prepared_http_sampling_request(prepared, config, opener=opener)

        self.assertEqual(first.response_items[0].content[0].text, "done")
        self.assertEqual(second.response_items[0].content[0].text, "done")
        self.assertNotIn("x-codex-turn-state", seen_headers[0])
        self.assertEqual(model_session.turn_state.get(), "sticky")
        self.assertEqual(seen_headers[1]["x-codex-turn-state"], "sticky")
        self.assertEqual(model_session.turn_state.get(), "sticky")


    def test_http_transport_config_skips_invalid_identity_header_values(self) -> None:
        client = ModelClient(
            session_id="session",
            thread_id="bad\nthread",
            installation_id="bad\rinstall",
        )
        provider = {"base_url": "https://api.example.test/v1"}

        config = http_transport_config_from_provider(client, provider)

        self.assertNotIn("x-codex-installation-id", config.headers)
        self.assertNotIn("x-client-request-id", config.headers)
        self.assertEqual(config.headers["session-id"], "session")
        self.assertNotIn("thread-id", config.headers)

    def test_http_transport_config_sets_exec_originator_and_supports_override(self) -> None:
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = {"base_url": "https://api.example.test/v1"}

        self.assertEqual(exec_originator_header_value({}), "codex_exec")
        self.assertEqual(
            exec_originator_header_value({CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR: "codex_exec_override"}),
            "codex_exec_override",
        )

        with patch.dict("os.environ", {CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR: "codex_exec_override"}):
            config = http_transport_config_from_provider(client, provider)

        self.assertEqual(config.headers["Originator"], "codex_exec_override")

    def test_model_client_http_sampler_can_run_user_turn_runtime(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["headers"] = {key.lower(): value for key, value in request.header_items()}
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            sampler = model_client_http_sampler(
                client.new_session(),
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )
            provider = type("Provider", (), {"is_azure_responses_endpoint": lambda _self: False})()
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
            return await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(seen["body"]["model"], "gpt-test")
        self.assertEqual(seen["body"]["instructions"], "base")
        self.assertEqual(result.response_items[0].content[0].text, "done")

    def test_model_client_http_sampler_can_retry_retryable_transport_errors(self) -> None:
        attempts = 0
        sleeps = []
        decisions = []

        def opener(_request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise URLError("temporary disconnect")
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done after retry"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            sampler = model_client_http_sampler(
                client.new_session(),
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
                max_retries=1,
                sleep=lambda seconds: sleeps.append(seconds),
                on_retry_decision=lambda decision: decisions.append(decision),
            )
            provider = type("Provider", (), {"is_azure_responses_endpoint": lambda _self: False})()
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
            return await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(attempts, 2)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(result.response_items[0].content[0].text, "done after retry")

    def test_model_client_http_sampler_emits_stream_retry_event_by_default(self) -> None:
        attempts = 0

        def opener(_request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise URLError("temporary disconnect")
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done after retry"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            sampler = model_client_http_sampler(
                client.new_session(),
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
                max_retries=1,
                sleep=lambda _seconds: None,
            )
            provider = type("Provider", (), {"is_azure_responses_endpoint": lambda _self: False})()
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
            result = await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )
            return session, result

        import asyncio

        session, result = asyncio.run(run())

        self.assertEqual(attempts, 2)
        self.assertEqual(result.response_items[0].content[0].text, "done after retry")
        non_lifecycle = non_lifecycle_events(session.emitted_events)
        self.assertEqual(tuple(event.type for event in non_lifecycle), ("stream_error",))
        stream_error = non_lifecycle[0].payload
        self.assertEqual(stream_error.message, "Reconnecting... 1/1")
        self.assertEqual(stream_error.codex_error_info.type, "response_stream_disconnected")
        self.assertIn("temporary disconnect", stream_error.additional_details)

    def test_model_client_http_sampler_refreshes_auth_after_401_like_rust_client(self) -> None:
        # Rust source: codex-core src/client.rs::stream_responses_api catches
        # 401 before generic stream retries and calls handle_unauthorized.
        # Rust test: core/tests/suite/client.rs::provider_auth_command_refreshes_after_401.
        token = {"value": "first-token"}
        seen_authorization: list[str] = []

        class Recovery:
            def __init__(self) -> None:
                self.calls = 0

            def has_next(self) -> bool:
                return self.calls == 0

            async def next(self):
                self.calls += 1
                token["value"] = "second-token"
                return object()

        class AuthManager:
            def __init__(self) -> None:
                self.recovery = Recovery()

            def unauthorized_recovery(self) -> Recovery:
                return self.recovery

        def transport_config() -> HttpTransportConfig:
            return HttpTransportConfig(
                "https://api.example.test/responses",
                headers={"Authorization": f"Bearer {token['value']}"},
            )

        def opener(request):
            seen_authorization.append(request.headers["Authorization"])
            if request.headers["Authorization"] == "Bearer first-token":
                raise HTTPError(
                    request.full_url,
                    401,
                    "Unauthorized",
                    {"X-Request-Id": "req-401"},
                    BytesIO(b'{"detail":"Unauthorized"}'),
                )
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done after auth refresh"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            sampler = model_client_http_sampler(
                client.new_session(),
                transport_config(),
                opener=opener,
                max_retries=0,
                sleep=lambda _seconds: None,
                auth_manager=AuthManager(),
                config_factory=transport_config,
            )
            provider = type("Provider", (), {"is_azure_responses_endpoint": lambda _self: False})()
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
            return await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(seen_authorization, ["Bearer first-token", "Bearer second-token"])
        self.assertEqual(result.response_items[0].content[0].text, "done after auth refresh")

    def test_run_user_turn_http_sampling_from_session_wraps_full_http_path(self) -> None:
        seen = {}

        def opener(request):
            seen["url"] = request.full_url
            seen["authorization"] = request.headers["Authorization"]
            seen["window"] = request.headers["X-codex-window-id"]
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["headers"] = {key.lower(): value for key, value in request.header_items()}
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
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
            return await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(seen["url"], "https://api.example.test/v1/responses")
        self.assertEqual(seen["authorization"], "Bearer sk-test")
        self.assertEqual(seen["window"], "thread:0")
        self.assertEqual(seen["body"]["model"], "gpt-test")
        self.assertEqual(result.response_items[0].content[0].text, "done")

    def test_run_user_turn_http_sampling_infers_guardian_output_schema_non_strict(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "reviewed"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
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
                "C:/work",
                model_info=model_info,
                session_source=SessionSource.subagent(SubAgentSource.other_source("guardian")),
            )
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
            return await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("assess"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
                output_schema={"type": "object"},
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(result.response_items[0].content[0].text, "reviewed")
        self.assertEqual(seen["body"]["text"]["format"]["strict"], False)

    def test_run_user_turn_http_sampling_uses_provider_stream_retry_default(self) -> None:
        attempts = 0

        def opener(_request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise URLError("temporary disconnect")
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done after retry"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            provider = {
                "base_url": "https://api.example.test/v1",
                "stream_max_retries": 1,
                "is_azure_responses_endpoint": lambda: False,
            }
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
            result = await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
                retry_sleep=lambda _seconds: None,
            )
            return session, result

        import asyncio

        session, result = asyncio.run(run())

        self.assertEqual(attempts, 2)
        self.assertEqual(result.response_items[0].content[0].text, "done after retry")
        self.assertEqual(tuple(event.type for event in non_lifecycle_events(session.emitted_events)), ("stream_error",))

    def test_run_user_turn_http_sampling_records_success_rate_limit_headers_with_usage(self) -> None:
        headers = Message()
        headers["x-codex-primary-used-percent"] = "12.5"
        headers["x-codex-primary-window-minutes"] = "60"
        headers["x-codex-secondary-primary-used-percent"] = "80"

        def opener(_request):
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ],
                    "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                },
                headers=headers,
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = InMemoryCodexSession("C:/work")
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
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
            return result, session

        import asyncio

        result, session = asyncio.run(run())

        self.assertEqual(result.response_items[0].content[0].text, "done")
        token_count = next(event for event in reversed(result.session_events) if event.type == "token_count")
        rate_limits = token_count.payload.rate_limits
        self.assertEqual(rate_limits.limit_id, "codex_secondary")
        self.assertEqual(rate_limits.primary.used_percent, 80.0)
        self.assertIsNone(rate_limits.secondary)
        self.assertEqual(session.latest_rate_limits, rate_limits)

    def test_run_user_turn_http_sampling_records_response_header_metadata(self) -> None:
        headers = Message()
        headers["openai-model"] = "gpt-5.2"
        headers["x-reasoning-included"] = ""
        headers["x-models-etag"] = "etag-1"

        def opener(_request):
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ],
                    "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                },
                headers=headers,
            )

        async def run():
            model_info = type(
                "ModelInfo",
                (),
                {
                    "slug": "gpt-5.3-codex",
                    "supports_reasoning_summaries": False,
                    "support_verbosity": False,
                    "service_tier_for_request": lambda _self, tier: tier,
                },
            )()
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = InMemoryCodexSession("C:/work", model_info=model_info)
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
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
            return result, session

        import asyncio

        result, session = asyncio.run(run())

        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertTrue(session.server_reasoning_included)
        self.assertEqual(session.models_etag, "etag-1")
        non_lifecycle = non_lifecycle_events(result.session_events)
        self.assertEqual([event.type for event in non_lifecycle[:2]], ["model_reroute", "warning"])
        reroute = non_lifecycle[0].payload
        self.assertEqual(reroute.from_model, "gpt-5.3-codex")
        self.assertEqual(reroute.to_model, "gpt-5.2")
        self.assertIn("high-risk cyber activity", non_lifecycle[1].payload.message)
        self.assertEqual(non_lifecycle[-1].type, "token_count")

    def test_run_user_turn_http_sampling_projects_sse_header_metadata_stream_events(self) -> None:
        headers = Message()
        headers["openai-model"] = "gpt-5.2"
        headers["x-codex-primary-used-percent"] = "47"
        headers["x-models-etag"] = "etag-sse"
        headers["x-reasoning-included"] = ""

        class SseResponse:
            def __init__(self) -> None:
                self.headers = headers

            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"done\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-1\",\"usage\":{\"input_tokens\":3,\"output_tokens\":2,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        async def run():
            model_info = type(
                "ModelInfo",
                (),
                {
                    "slug": "gpt-5.3-codex",
                    "supports_reasoning_summaries": False,
                    "support_verbosity": False,
                    "service_tier_for_request": lambda _self, tier: tier,
                },
            )()
            client = ModelClient(
                session_id="session",
                thread_id="00000000-0000-0000-0000-000000000123",
                installation_id="install",
            )
            session = InMemoryCodexSession("C:/work", model_info=model_info)
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
            result = await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=lambda _request: SseResponse(),
                built_tools=lambda _sess, _turn: Router(),
            )
            return result, session

        import asyncio

        result, session = asyncio.run(run())

        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            (
                "server_model",
                "rate_limits",
                "models_etag",
                "server_reasoning_included",
                "output_item_done",
                "completed",
            ),
        )
        self.assertEqual(result.stream_events[0]["server_model"], "gpt-5.2")
        self.assertEqual(result.stream_events[1]["rate_limits"].primary.used_percent, 47.0)
        self.assertEqual(result.stream_events[2]["models_etag"], "etag-sse")
        self.assertTrue(result.stream_events[3]["server_reasoning_included"])
        self.assertTrue(session.server_reasoning_included)
        self.assertEqual(session.models_etag, "etag-sse")
        self.assertEqual(session.latest_rate_limits.primary.used_percent, 47.0)
        non_lifecycle = non_lifecycle_events(result.session_events)
        self.assertEqual([event.type for event in non_lifecycle[:2]], ["model_reroute", "warning"])
        self.assertEqual(non_lifecycle[-1].type, "token_count")

    def test_run_user_turn_http_sampling_records_sse_metadata_model_verification_once(self) -> None:
        class SseResponse:
            def read(self) -> bytes:
                return (
                    "event: response.metadata\n"
                    "data: {\"metadata\":{\"openai_verification_recommendation\":[\"trusted_access_for_cyber\",\"trusted_access_for_cyber\",\"unknown\"]},\"headers\":{\"OpenAI-Model\":[\"gpt-5.2\"]}}\n"
                    "\n"
                    "event: response.metadata\n"
                    "data: {\"metadata\":{\"openai_verification_recommendation\":[\"trusted_access_for_cyber\"]}}\n"
                    "\n"
                    "event: response.output_item.done\n"
                    "data: {\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"done\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"response\":{\"id\":\"resp-1\",\"usage\":{\"input_tokens\":3,\"output_tokens\":2,\"total_tokens\":5}}}\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        async def run():
            model_info = type(
                "ModelInfo",
                (),
                {
                    "slug": "gpt-5.3-codex",
                    "supports_reasoning_summaries": False,
                    "support_verbosity": False,
                    "service_tier_for_request": lambda _self, tier: tier,
                },
            )()
            client = ModelClient(
                session_id="session",
                thread_id="00000000-0000-0000-0000-000000000124",
                installation_id="install",
            )
            session = InMemoryCodexSession("C:/work", model_info=model_info)
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
            result = await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=lambda _request: SseResponse(),
                built_tools=lambda _sess, _turn: Router(),
            )
            return result

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(
            tuple(event["type"] for event in result.stream_events),
            ("server_model", "model_verifications", "output_item_done", "completed"),
        )
        self.assertEqual(result.stream_events[0]["server_model"], "gpt-5.2")
        self.assertEqual(
            result.stream_events[1]["model_verifications"],
            (ModelVerification.TRUSTED_ACCESS_FOR_CYBER,),
        )
        self.assertEqual(
            [event.type for event in non_lifecycle_events(result.session_events)[:3]],
            ["model_reroute", "warning", "model_verification"],
        )
        self.assertEqual(
            non_lifecycle_events(result.session_events)[2].payload.verifications,
            (ModelVerification.TRUSTED_ACCESS_FOR_CYBER,),
        )
        self.assertEqual(non_lifecycle_events(result.session_events)[-1].type, "token_count")

    def test_run_user_turn_http_sampling_from_session_default_followups_continue_until_final_answer(self) -> None:
        calls = []

        def opener(request):
            calls.append(request)
            if len(calls) <= 10:
                return FakeResponse(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "echo",
                                "arguments": "{}",
                                "call_id": f"call-echo-{len(calls)}",
                            }
                        ]
                    }
                )
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "finally done"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
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
            handler = EchoHandler()
            router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
            result = await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: router,
            )
            return result, handler

        import asyncio

        result, handler = asyncio.run(run())

        self.assertEqual(len(calls), 11)
        self.assertEqual(len(handler.invocations), 10)
        self.assertEqual(result.response_items[-1].content[0].text, "finally done")
        self.assertEqual(len(result.tool_response_items), 10)

    def test_run_user_turn_http_sampling_follows_completed_end_turn_false_without_tools(self) -> None:
        calls = []

        def opener(request):
            calls.append(request)
            if len(calls) == 1:
                return FakeResponse(
                    {
                        "id": "resp-continue",
                        "end_turn": False,
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "continuing"}],
                            }
                        ],
                    }
                )
            return FakeResponse(
                {
                    "id": "resp-final",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ],
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
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
            return await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(len(calls), 2)
        self.assertEqual([item.content[0].text for item in result.response_items], ["continuing", "done"])
        self.assertEqual(result.raw_results[0].end_turn, False)
        self.assertIsNone(result.raw_results[1].end_turn)


if __name__ == "__main__":
    unittest.main()

