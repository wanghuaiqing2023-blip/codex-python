from pycodex.analytics import (
    AnalyticsReducer,
    AnalyticsJsonRpcError,
    CompletedTurnState,
    InputError,
    PendingTurnSteerState,
    ThreadInitializationMode,
    ThreadMetadataState,
    TurnState,
    TurnStatus,
    TurnSteerRequestError,
    TurnSteerResult,
    apply_accepted_turn_steer,
    codex_turn_steer_event,
)


def sample_app_server_client_metadata() -> dict:
    return {
        "product_client_id": "codex-tui",
        "client_name": "codex-tui",
        "client_version": "1.0.0",
        "rpc_transport": "stdio",
        "experimental_api_enabled": None,
    }


def sample_runtime_metadata() -> dict:
    return {
        "codex_rs_version": "0.1.0",
        "runtime_os": "macos",
        "runtime_os_version": "15.3.1",
        "runtime_arch": "aarch64",
    }


def sample_thread_metadata() -> ThreadMetadataState:
    return ThreadMetadataState(
        session_id="session-thread-2",
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
    )


def sample_pending_request() -> PendingTurnSteerState:
    return PendingTurnSteerState(
        thread_id="thread-2",
        expected_turn_id="turn-2",
        num_input_images=1,
        created_at=123456,
    )


def test_accepted_turn_steer_emits_expected_event() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs + src/events.rs
    # Rust test: analytics_client_tests::accepted_turn_steer_emits_expected_event
    # Contract: accepted turn steer emits Rust-shaped codex_turn_steer_event using request metadata.
    payload = codex_turn_steer_event(
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        pending_request=sample_pending_request(),
        thread_metadata=sample_thread_metadata(),
        accepted_turn_id="turn-2",
        result=TurnSteerResult.ACCEPTED,
        rejection_reason=None,
    )

    assert payload == {
        "event_type": "codex_turn_steer_event",
        "event_params": {
            "thread_id": "thread-2",
            "session_id": "session-thread-2",
            "expected_turn_id": "turn-2",
            "accepted_turn_id": "turn-2",
            "app_server_client": sample_app_server_client_metadata(),
            "runtime": sample_runtime_metadata(),
            "thread_source": "user",
            "subagent_source": None,
            "parent_thread_id": None,
            "num_input_images": 1,
            "result": "accepted",
            "rejection_reason": None,
            "created_at": 123456,
        },
    }


def test_rejected_turn_steer_maps_error_types() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust tests: analytics_client_tests::{rejected_turn_steer_uses_request_connection_metadata,
    #             rejected_turn_steer_maps_active_turn_not_steerable_error_type,
    #             rejected_turn_steer_maps_input_too_large_error_type}
    # Contract: rejected turn steer keeps request metadata and maps optional typed JSON-RPC error reasons.
    base = {
        "app_server_client": sample_app_server_client_metadata(),
        "runtime": sample_runtime_metadata(),
        "pending_request": sample_pending_request(),
        "thread_metadata": sample_thread_metadata(),
        "accepted_turn_id": None,
        "result": TurnSteerResult.REJECTED,
    }

    no_active = codex_turn_steer_event(
        **base,
        rejection_reason=AnalyticsJsonRpcError.turn_steer(TurnSteerRequestError.NO_ACTIVE_TURN),
    )
    non_steerable = codex_turn_steer_event(
        **base,
        rejection_reason=AnalyticsJsonRpcError.turn_steer(TurnSteerRequestError.NON_STEERABLE_REVIEW),
    )
    too_large = codex_turn_steer_event(
        **base,
        rejection_reason=AnalyticsJsonRpcError.input(InputError.TOO_LARGE),
    )

    assert no_active["event_params"]["thread_id"] == "thread-2"
    assert no_active["event_params"]["accepted_turn_id"] is None
    assert no_active["event_params"]["result"] == "rejected"
    assert no_active["event_params"]["rejection_reason"] == "no_active_turn"
    assert non_steerable["event_params"]["rejection_reason"] == "non_steerable_review"
    assert too_large["event_params"]["rejection_reason"] == "input_too_large"


def test_accepted_turn_steers_increment_turn_steer_count() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::accepted_steers_increment_turn_steer_count
    # Contract: only accepted turn steer responses increment the accepted turn state's steer_count.
    turns = {
        "turn-2": TurnState(
            thread_id="thread-2",
            num_input_images=1,
            completed=CompletedTurnState(TurnStatus.COMPLETED, None, 456, 1234),
        )
    }

    apply_accepted_turn_steer(turns, "turn-2")
    apply_accepted_turn_steer(turns, "missing-turn")
    apply_accepted_turn_steer(turns, "turn-2")

    assert turns["turn-2"].steer_count == 2


def test_turn_steer_does_not_emit_without_pending_request() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::turn_steer_does_not_emit_without_pending_request
    # Contract: TurnSteer error responses without a matching pending request emit no analytics event.
    reducer = AnalyticsReducer()

    events = reducer.ingest_turn_steer_error_response(
        connection_id=7,
        request_id=4,
        error_type=AnalyticsJsonRpcError.turn_steer(TurnSteerRequestError.NO_ACTIVE_TURN),
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert events == []


def test_accepted_turn_steer_response_removes_pending_request_and_increments_turn() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust tests: analytics_client_tests::accepted_turn_steer_emits_expected_event,
    #             analytics_client_tests::accepted_steers_increment_turn_steer_count
    # Contract: accepted TurnSteer responses consume pending request metadata and increment the accepted turn state.
    reducer = AnalyticsReducer()
    reducer.turns["turn-2"] = TurnState(thread_id="thread-2")
    reducer.track_turn_steer_request(
        connection_id=7,
        request_id=4,
        thread_id="thread-2",
        expected_turn_id="turn-2",
        input_items=[
            {"type": "Text", "text": "more"},
            {"type": "LocalImage", "path": "/tmp/a.png"},
        ],
        created_at=123456,
    )

    events = reducer.ingest_turn_steer_response(
        connection_id=7,
        request_id=4,
        accepted_turn_id="turn-2",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    late = reducer.ingest_turn_steer_response(
        connection_id=7,
        request_id=4,
        accepted_turn_id="turn-2",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert late == []
    assert reducer.turns["turn-2"].steer_count == 1
    assert len(events) == 1
    params = events[0]["event_params"]
    assert params["thread_id"] == "thread-2"
    assert params["expected_turn_id"] == "turn-2"
    assert params["accepted_turn_id"] == "turn-2"
    assert params["num_input_images"] == 1
    assert params["result"] == "accepted"
    assert params["rejection_reason"] is None
    assert params["created_at"] == 123456
