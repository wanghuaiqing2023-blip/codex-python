from types import SimpleNamespace

from pycodex.core import (
    OPENAI_BETA_HEADER,
    RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE,
    X_CODEX_TURN_METADATA_HEADER,
    LastResponse,
    ModelClient,
    SamplingCompletedEventApplyPlan,
    SamplingStreamEventApplyPlan,
    WebsocketStreamOutcome,
)
from pycodex.core.client_common import Prompt
from pycodex.protocol import ContentItem, FunctionCallOutputPayload, ResponseItem, ServiceTier


class FeatureSet:
    def enabled(self, _feature: object) -> bool:
        return False


def _provider() -> SimpleNamespace:
    return SimpleNamespace(
        info=lambda: SimpleNamespace(supports_websockets=True),
        is_azure_responses_endpoint=lambda: False,
    )


def _model_info() -> SimpleNamespace:
    return SimpleNamespace(
        slug="gpt-websocket",
        supports_reasoning_summaries=False,
        support_verbosity=False,
        service_tier_for_request=lambda tier: "priority" if tier in {ServiceTier.FAST, "fast", "priority"} else tier,
    )


def _user(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _assistant(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def _completed_plan(response_id: str) -> SamplingStreamEventApplyPlan:
    return SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id=response_id,
            completed_response_id_after=response_id,
        ),
    )


def test_websocket_test_codex_shell_chain():
    # Rust source: codex/codex-rs/core/tests/suite/agent_websocket.rs
    # Rust test: websocket_test_codex_shell_chain.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=_provider())
    session = client.new_session()
    first = _user("run the echo command")
    tool_output = ResponseItem(
        type="function_call_output",
        call_id="shell-command-call",
        output=FunctionCallOutputPayload.from_text("websocket\n"),
    )
    first_request = {"model": "m", "input": [first]}
    second_request = {"model": "m", "input": [first, tool_output]}

    first_ws, first_from_warmup = session.prepare_websocket_request(first_request, first_request)
    session.websocket_session.last_request = first_request
    session.websocket_session.last_response = LastResponse("resp-1")
    second_ws, second_from_warmup = session.prepare_websocket_request(second_request, second_request)

    assert first_from_warmup is False
    assert second_from_warmup is False
    assert first_ws["type"] == "response.create"
    assert second_ws["type"] == "response.create"
    assert second_ws["previous_response_id"] == "resp-1"
    assert second_ws["input"] == [
        {
            "type": "function_call_output",
            "call_id": "shell-command-call",
            "output": "websocket\n",
        }
    ]


def test_websocket_first_turn_uses_startup_prewarm_and_create():
    # Rust source: codex/codex-rs/core/tests/suite/agent_websocket.rs
    # Rust test: websocket_first_turn_uses_startup_prewarm_and_create.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=_provider())
    session = client.new_session()
    request = {"model": "m", "input": [_user("hello")], "tools": [{"type": "function", "name": "shell_command"}]}
    turn_metadata = '{"request_kind":"prewarm","window_id":"thread:0"}'

    prewarm = session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(_completed_plan("warm-1"),),
        connection=SimpleNamespace(is_closed=False),
        turn_metadata_header=turn_metadata,
        unified_diff=None,
    )
    warmup = prewarm["result"].websocket_request

    assert prewarm["prewarmed"] is True
    assert warmup["type"] == "response.create"
    assert warmup["generate"] is False
    assert warmup["client_metadata"][X_CODEX_TURN_METADATA_HEADER] == turn_metadata
    assert request["tools"]


def test_websocket_first_turn_handles_handshake_delay_with_startup_prewarm():
    # Rust source: codex/codex-rs/core/tests/suite/agent_websocket.rs
    # Rust test: websocket_first_turn_handles_handshake_delay_with_startup_prewarm.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=_provider())
    session = client.new_session()
    connection = SimpleNamespace(is_closed=False, accept_delay_ms=150)

    result = session.preconnect_websocket(connection)

    assert result == {"preconnected": True, "connection_reused": False}
    assert session.websocket_connection_needs_new() is False


def test_websocket_v2_test_codex_shell_chain():
    # Rust source: codex/codex-rs/core/tests/suite/agent_websocket.rs
    # Rust test: websocket_v2_test_codex_shell_chain.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=_provider())
    session = client.new_session()
    first = _user("run the echo command")
    assistant = _assistant("thinking")
    output = ResponseItem(
        type="function_call_output",
        call_id="shell-command-call",
        output=FunctionCallOutputPayload.from_text("websocket\n"),
    )
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-1", (assistant,))

    second_ws, _from_warmup = session.prepare_websocket_request(
        {"model": "m", "input": [first, assistant, output]},
        {"model": "m", "input": [first, assistant, output]},
    )
    headers = client.build_websocket_headers()

    assert second_ws["type"] == "response.create"
    assert second_ws["previous_response_id"] == "resp-1"
    assert second_ws["input"] == [
        {
            "type": "function_call_output",
            "call_id": "shell-command-call",
            "output": "websocket\n",
        }
    ]
    assert headers[OPENAI_BETA_HEADER] == RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE


def test_websocket_v2_first_turn_uses_updated_fast_tier_after_startup_prewarm():
    # Rust source: codex/codex-rs/core/tests/suite/agent_websocket.rs
    # Rust test: websocket_v2_first_turn_uses_updated_fast_tier_after_startup_prewarm.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

    warmup = client.build_responses_request(_provider(), Prompt.default(), _model_info(), service_tier=None)
    turn = client.build_responses_request(_provider(), Prompt.default(), _model_info(), service_tier=ServiceTier.FAST)

    assert warmup["service_tier"] is None
    assert turn["service_tier"] == "priority"


def test_websocket_v2_first_turn_drops_fast_tier_after_startup_prewarm():
    # Rust source: codex/codex-rs/core/tests/suite/agent_websocket.rs
    # Rust test: websocket_v2_first_turn_drops_fast_tier_after_startup_prewarm.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

    warmup = client.build_responses_request(_provider(), Prompt.default(), _model_info(), service_tier="fast")
    turn = client.build_responses_request(_provider(), Prompt.default(), _model_info(), service_tier=None)

    assert warmup["service_tier"] == "priority"
    assert turn["service_tier"] is None


def test_websocket_v2_next_turn_uses_updated_service_tier():
    # Rust source: codex/codex-rs/core/tests/suite/agent_websocket.rs
    # Rust test: websocket_v2_next_turn_uses_updated_service_tier.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

    first_turn = client.build_responses_request(_provider(), Prompt.default(), _model_info(), service_tier=ServiceTier.FAST)
    second_turn = client.build_responses_request(_provider(), Prompt.default(), _model_info(), service_tier=None)

    assert first_turn["service_tier"] == "priority"
    assert second_turn["service_tier"] is None
