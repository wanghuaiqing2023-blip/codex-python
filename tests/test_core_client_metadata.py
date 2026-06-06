from pycodex.core import (
    ModelClient,
    X_CODEX_INSTALLATION_ID_HEADER,
    X_CODEX_PARENT_THREAD_ID_HEADER,
    X_CODEX_TURN_METADATA_HEADER,
    X_CODEX_WINDOW_ID_HEADER,
    X_OPENAI_SUBAGENT_HEADER,
    stamp_ws_stream_request_start_ms,
)
from pycodex.protocol import InternalSessionSource, SessionSource, SubAgentSource, ThreadId


def test_build_subagent_headers_sets_other_subagent_label():
    # Rust source: codex/codex-rs/core/src/client_tests.rs
    # Rust test: build_subagent_headers_sets_other_subagent_label.
    client = ModelClient(
        session_id="session",
        thread_id=ThreadId.new(),
        installation_id="11111111-1111-4111-8111-111111111111",
        session_source=SessionSource.subagent(
            SubAgentSource.other_source("memory_consolidation")
        ),
    )

    assert client.build_subagent_headers() == {
        X_OPENAI_SUBAGENT_HEADER: "memory_consolidation"
    }


def test_build_subagent_headers_sets_internal_memory_consolidation_label():
    # Rust source: codex/codex-rs/core/src/client_tests.rs
    # Rust test: build_subagent_headers_sets_internal_memory_consolidation_label.
    # Rust source contract: build_subagent_headers also sets x-openai-memgen-request.
    client = ModelClient(
        session_id="session",
        thread_id=ThreadId.new(),
        installation_id="11111111-1111-4111-8111-111111111111",
        session_source=SessionSource.internal(InternalSessionSource.MEMORY_CONSOLIDATION),
    )

    assert client.build_subagent_headers() == {
        X_OPENAI_SUBAGENT_HEADER: "memory_consolidation",
        "x-openai-memgen-request": "true",
    }


def test_build_ws_client_metadata_includes_window_lineage_and_turn_metadata():
    # Rust source: codex/codex-rs/core/src/client_tests.rs
    # Rust test: build_ws_client_metadata_includes_window_lineage_and_turn_metadata.
    parent_thread_id = ThreadId.new()
    client = ModelClient(
        session_id="session",
        thread_id=ThreadId.new(),
        installation_id="11111111-1111-4111-8111-111111111111",
        session_source=SessionSource.subagent(
            SubAgentSource.thread_spawn(
                parent_thread_id=parent_thread_id,
                depth=2,
                agent_path=None,
                agent_nickname=None,
                agent_role=None,
            )
        ),
    )
    client.advance_window_generation()

    metadata = client.build_ws_client_metadata('{"turn_id":"turn-123"}')

    assert metadata == {
        X_CODEX_INSTALLATION_ID_HEADER: "11111111-1111-4111-8111-111111111111",
        X_CODEX_WINDOW_ID_HEADER: client.current_window_id(),
        X_OPENAI_SUBAGENT_HEADER: "collab_spawn",
        X_CODEX_PARENT_THREAD_ID_HEADER: str(parent_thread_id),
        X_CODEX_TURN_METADATA_HEADER: '{"turn_id":"turn-123"}',
    }


def test_build_ws_client_metadata_omits_invalid_turn_metadata():
    # Rust source: codex/codex-rs/core/src/client.rs::parse_turn_metadata_header.
    # Source contract: invalid header values are treated as absent.
    client = ModelClient(
        session_id="session",
        thread_id=ThreadId.new(),
        installation_id="11111111-1111-4111-8111-111111111111",
    )

    metadata = client.build_ws_client_metadata("bad\nmetadata")

    assert X_CODEX_TURN_METADATA_HEADER not in metadata


def test_stamp_ws_stream_request_start_ms_only_stamps_response_create(monkeypatch):
    # Rust source: codex/codex-rs/core/src/client.rs::stamp_ws_stream_request_start_ms.
    # Source contract: only ResponsesWsRequest::ResponseCreate gets client metadata.
    monkeypatch.setattr("pycodex.core.client.time.time", lambda: 123.456)
    request = {"type": "response.create"}
    non_create_request = {"type": "response.cancel"}

    stamp_ws_stream_request_start_ms(request)
    stamp_ws_stream_request_start_ms(non_create_request)

    assert request["client_metadata"]["x-codex-ws-stream-request-start-ms"] == "123456"
    assert "client_metadata" not in non_create_request
