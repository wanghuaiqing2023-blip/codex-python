import json

from pycodex.core import (
    ModelClient,
    X_CODEX_PARENT_THREAD_ID_HEADER,
    X_CODEX_TURN_METADATA_HEADER,
    X_CODEX_WINDOW_ID_HEADER,
    X_OPENAI_SUBAGENT_HEADER,
)
from pycodex.protocol import SessionSource, SubAgentSource, ThreadId


def _split_window_id(window_id: str) -> tuple[str, int]:
    thread_id, generation = window_id.rsplit(":", 1)
    return thread_id, int(generation)


def test_responses_api_parent_and_subagent_requests_include_identity_headers():
    # Rust: codex/codex-rs/core/tests/suite/responses_api_proxy_headers.rs
    # Test: responses_api_parent_and_subagent_requests_include_identity_headers.
    parent_thread_id = ThreadId.from_string("22222222-2222-4222-8222-222222222222")
    child_thread_id = ThreadId.from_string("33333333-3333-4333-8333-333333333333")

    parent = ModelClient(
        session_id="parent-session",
        thread_id=parent_thread_id,
        installation_id="install",
        session_source=SessionSource.default(),
    )
    child = ModelClient(
        session_id="child-session",
        thread_id=child_thread_id,
        installation_id="install",
        session_source=SessionSource.subagent(
            SubAgentSource.thread_spawn(parent_thread_id, depth=1)
        ),
    )

    parent_headers = parent.build_responses_identity_headers()
    child_turn_metadata = json.dumps(
        {"forked_from_thread_id": str(parent_thread_id)},
        separators=(",", ":"),
    )
    child_headers = child.build_websocket_headers(
        turn_metadata_header=child_turn_metadata
    )

    parent_window_id = parent_headers[X_CODEX_WINDOW_ID_HEADER]
    child_window_id = child_headers[X_CODEX_WINDOW_ID_HEADER]
    parsed_parent_thread_id, parent_generation = _split_window_id(parent_window_id)
    parsed_child_thread_id, child_generation = _split_window_id(child_window_id)

    assert parent_generation == 0
    assert child_generation == 0
    assert parsed_parent_thread_id == str(parent_thread_id)
    assert parsed_child_thread_id == str(child_thread_id)
    assert parsed_child_thread_id != parsed_parent_thread_id
    assert X_OPENAI_SUBAGENT_HEADER not in parent_headers
    assert child_headers[X_OPENAI_SUBAGENT_HEADER] == "collab_spawn"
    assert child_headers[X_CODEX_PARENT_THREAD_ID_HEADER] == str(parent_thread_id)
    assert json.loads(child_headers[X_CODEX_TURN_METADATA_HEADER])[
        "forked_from_thread_id"
    ] == str(parent_thread_id)
