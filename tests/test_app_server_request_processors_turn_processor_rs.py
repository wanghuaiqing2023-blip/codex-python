from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pycodex.app_server.request_processors_turn_processor import (
    CoreAdditionalContextEntry,
    TurnRequestProcessor,
    TurnRequestProcessorError,
    map_additional_context,
    parse_thread_id_for_request,
    resolve_runtime_workspace_roots,
    xcode_26_4_mcp_elicitations_auto_deny,
)
from pycodex.app_server_protocol import (
    AdditionalContextEntry,
    ThreadRealtimeListVoicesResponse,
    TurnInterruptParams,
    TurnInterruptResponse,
    TurnStartParams,
    TurnStartResponse,
)
from pycodex.app_server_protocol.thread_data import Turn
from pycodex.app_server_protocol.turn import UserInput


THREAD_ID = "11111111-1111-4111-8111-111111111111"


def _run(coro):
    return asyncio.run(coro)


def test_resolve_runtime_workspace_roots_resolves_against_base_and_dedupes() -> None:
    # Rust source: resolve_runtime_workspace_roots in request_processors/turn_processor.rs.
    base = Path("C:/workspace/project")

    roots = resolve_runtime_workspace_roots(("src", "src", base / "abs"), base)

    assert roots == (
        str(base / "src"),
        str(base / "abs"),
    )


def test_map_additional_context_sorts_keys_and_projects_core_kind() -> None:
    # Rust source: map_additional_context maps Option<HashMap<..>> into BTreeMap.
    mapped = map_additional_context(
        {
            "zeta": {"value": "outside prompt", "kind": "untrusted"},
            "alpha": AdditionalContextEntry(value="app note", kind="application"),
        }
    )

    assert list(mapped) == ["alpha", "zeta"]
    assert mapped["alpha"] == CoreAdditionalContextEntry(value="app note", kind="Application")
    assert mapped["zeta"] == CoreAdditionalContextEntry(value="outside prompt", kind="Untrusted")
    assert map_additional_context(None) == {}


def test_parse_thread_id_for_request_matches_invalid_request_error_shape() -> None:
    # Rust source: load_thread parses ThreadId and returns invalid_request on parse failure.
    assert parse_thread_id_for_request(THREAD_ID) == THREAD_ID

    try:
        parse_thread_id_for_request("not-a-uuid")
    except TurnRequestProcessorError as exc:
        assert exc.error.code == -32600
        assert exc.error.message.startswith("invalid thread id:")
    else:
        raise AssertionError("expected invalid_request")


def test_load_thread_returns_thread_or_thread_not_found_error() -> None:
    _run(_load_thread_returns_thread_or_thread_not_found_error())


async def _load_thread_returns_thread_or_thread_not_found_error() -> None:
    # Rust source: TurnRequestProcessor::load_thread.
    thread = object()
    processor = _processor(thread_manager=FakeThreadManager({THREAD_ID: thread}))

    assert await processor.load_thread(THREAD_ID) == (THREAD_ID, thread)

    missing = _processor(thread_manager=FakeThreadManager({}))
    try:
        await missing.load_thread(THREAD_ID)
    except TurnRequestProcessorError as exc:
        assert exc.error.code == -32600
        assert exc.error.message == f"thread not found: {THREAD_ID}"
    else:
        raise AssertionError("expected invalid_request")


def test_turn_start_wrapper_parses_params_and_delegates_to_inner_override() -> None:
    _run(_turn_start_wrapper_parses_params_and_delegates_to_inner_override())


async def _turn_start_wrapper_parses_params_and_delegates_to_inner_override() -> None:
    # Rust source: turn_start wrapper maps params to TurnStartParams and returns Some(response.into()).
    response = TurnStartResponse(turn=Turn(id="turn-1", items=(), status="inProgress"))
    processor = _processor()
    calls = []

    async def override(request_id, connection_id, params):
        calls.append((request_id, connection_id, params))
        return response

    processor.turn_start_inner_override = override
    result = await processor.turn_start(
        "req-1",
        "conn-1",
        TurnStartParams(thread_id=THREAD_ID, input=(UserInput.text("hello"),)),
    )

    assert result is response
    assert calls == [("req-1", "conn-1", TurnStartParams(thread_id=THREAD_ID, input=(UserInput.text("hello"),)))]


def test_turn_interrupt_wrapper_allows_none_or_empty_response() -> None:
    _run(_turn_interrupt_wrapper_allows_none_or_empty_response())


async def _turn_interrupt_wrapper_allows_none_or_empty_response() -> None:
    # Rust source: turn_interrupt wrapper preserves optional inner response.
    processor = _processor()
    params = TurnInterruptParams(thread_id=THREAD_ID, turn_id="turn-1")

    async def no_response(request_id, parsed):
        assert request_id == "req-1"
        assert parsed == params
        return None

    processor.turn_interrupt_inner_override = no_response
    assert await processor.turn_interrupt("req-1", params) is None

    async def empty_response(request_id, parsed):
        return TurnInterruptResponse()

    processor.turn_interrupt_inner_override = empty_response
    assert isinstance(await processor.turn_interrupt("req-2", params), TurnInterruptResponse)


def test_thread_realtime_list_voices_uses_builtin_voice_list() -> None:
    _run(_thread_realtime_list_voices_uses_builtin_voice_list())


async def _thread_realtime_list_voices_uses_builtin_voice_list() -> None:
    # Rust source: thread_realtime_list_voices returns RealtimeVoicesList::builtin().
    processor = _processor()

    response = await processor.thread_realtime_list_voices()

    assert isinstance(response, ThreadRealtimeListVoicesResponse)
    assert response.voices.default_v1.value == "cove"
    assert response.voices.default_v2.value == "marin"


def test_xcode_26_4_mcp_elicitations_auto_deny_matches_client_line() -> None:
    # Rust source: xcode_26_4_mcp_elicitations_auto_deny.
    assert xcode_26_4_mcp_elicitations_auto_deny("Xcode", "26.4") is True
    assert xcode_26_4_mcp_elicitations_auto_deny("Xcode", "26.4.1") is True
    assert xcode_26_4_mcp_elicitations_auto_deny("Xcode", "26.5") is False
    assert xcode_26_4_mcp_elicitations_auto_deny("Other", "26.4") is False
    assert xcode_26_4_mcp_elicitations_auto_deny("Xcode", None) is False


def test_track_error_response_forwards_to_analytics_client() -> None:
    processor = _processor(analytics_events_client=FakeAnalytics())
    error = SimpleNamespace(message="bad")

    processor.track_error_response("req-1", error)

    assert processor.analytics_events_client.calls == [("req-1", error)]


class FakeThreadManager:
    def __init__(self, threads=None):
        self.threads = threads or {}

    async def get_thread(self, thread_id):
        return self.threads.get(thread_id)


class FakeAnalytics:
    def __init__(self):
        self.calls = []

    def track_error_response(self, request_id, error):
        self.calls.append((request_id, error))


def _processor(**overrides):
    values = {
        "auth_manager": object(),
        "thread_manager": FakeThreadManager(),
        "outgoing": object(),
        "analytics_events_client": object(),
        "arg0_paths": object(),
        "config": SimpleNamespace(model_provider_id="openai", codex_home="codex-home"),
        "config_manager": object(),
        "pending_thread_unloads": set(),
        "thread_state_manager": object(),
        "thread_watch_manager": object(),
        "thread_list_state_permit": object(),
        "skills_watcher": object(),
    }
    values.update(overrides)
    return TurnRequestProcessor.new(**values)
