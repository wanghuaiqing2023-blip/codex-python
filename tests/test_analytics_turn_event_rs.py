from pathlib import Path

from pycodex.analytics import (
    AnalyticsReducer,
    CompletedTurnState,
    ThreadInitializationMode,
    ThreadMetadataState,
    TokenUsage,
    TurnResolvedConfigFact,
    TurnState,
    TurnStatus,
    TurnToolCounts,
    codex_turn_event,
    sandbox_policy_mode,
)


def sample_app_server_client_metadata() -> dict:
    return {
        "product_client_id": "codex_cli_rs",
        "client_name": "codex-tui",
        "client_version": "1.0.0",
        "rpc_transport": "stdio",
        "experimental_api_enabled": True,
    }


def sample_runtime_metadata() -> dict:
    return {
        "codex_rs_version": "0.1.0",
        "runtime_os": "macos",
        "runtime_os_version": "15.3.1",
        "runtime_arch": "aarch64",
    }


def sample_resolved_config(**updates) -> TurnResolvedConfigFact:
    values = {
        "turn_id": "turn-2",
        "thread_id": "thread-2",
        "num_input_images": 2,
        "submission_type": None,
        "ephemeral": False,
        "session_source": "cli",
        "model": "gpt-5",
        "model_provider": "openai",
        "permission_profile": "read_only",
        "permission_profile_cwd": Path("/repo"),
        "reasoning_effort": "high",
        "reasoning_summary": "detailed",
        "service_tier": "flex",
        "approval_policy": "on-request",
        "approvals_reviewer": "auto_review",
        "sandbox_network_access": True,
        "collaboration_mode": "plan",
        "personality": "pragmatic",
        "is_first_turn": True,
    }
    values.update(updates)
    return TurnResolvedConfigFact(**values)


def sample_thread_metadata() -> ThreadMetadataState:
    return ThreadMetadataState(
        session_id="session-thread-2",
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
    )


def test_managed_full_disk_with_restricted_network_reports_external_sandbox() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: reducer::tests::managed_full_disk_with_restricted_network_reports_external_sandbox
    # Contract: managed full-disk write with restricted network reports external_sandbox, not full_access.
    assert (
        sandbox_policy_mode(
            {
                "kind": "Managed",
                "file_system": {"mode": "unrestricted"},
                "network": {"mode": "restricted"},
            }
        )
        == "external_sandbox"
    )


def sample_reducer_with_turn_prerequisites(*, include_started: bool = True) -> AnalyticsReducer:
    reducer = AnalyticsReducer()
    reducer.ingest_initialize(
        connection_id=7,
        product_client_id="codex_cli_rs",
        client_name="codex-tui",
        client_version="1.0.0",
        rpc_transport="stdio",
        experimental_api_enabled=True,
        runtime=sample_runtime_metadata(),
    )
    reducer.ingest_thread_response(
        connection_id=7,
        thread_id="thread-2",
        session_id="session-thread-2",
        model="gpt-5",
        ephemeral=False,
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
        created_at=1,
    )
    reducer.track_turn_start_request(
        connection_id=7,
        request_id=3,
        thread_id="thread-2",
        num_input_images=1,
    )
    reducer.ingest_turn_start_response(
        connection_id=7,
        request_id=3,
        turn_id="turn-2",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    reducer.ingest_turn_resolved_config(
        sample_resolved_config(num_input_images=1),
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    if include_started:
        reducer.ingest_turn_started(turn_id="turn-2", started_at=455)
    return reducer


def test_turn_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs + src/reducer.rs
    # Rust test: analytics_client_tests::turn_event_serializes_expected_shape
    # Contract: CodexTurnEventRequest serializes the Rust turn event field shape.
    event = codex_turn_event(
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        turn_id="turn-2",
        turn_state=TurnState(
            thread_id="thread-2",
            num_input_images=2,
            resolved_config=sample_resolved_config(),
            started_at=455,
            completed=CompletedTurnState(TurnStatus.COMPLETED, None, completed_at=456, duration_ms=1234),
        ),
        thread_metadata=sample_thread_metadata(),
    )

    assert event == {
        "event_type": "codex_turn_event",
        "event_params": {
            "thread_id": "thread-2",
            "session_id": "session-thread-2",
            "turn_id": "turn-2",
            "submission_type": None,
            "app_server_client": sample_app_server_client_metadata(),
            "runtime": sample_runtime_metadata(),
            "ephemeral": False,
            "thread_source": "user",
            "initialization_mode": "new",
            "subagent_source": None,
            "parent_thread_id": None,
            "model": "gpt-5",
            "model_provider": "openai",
            "sandbox_policy": "read_only",
            "reasoning_effort": "high",
            "reasoning_summary": "detailed",
            "service_tier": "flex",
            "approval_policy": "on-request",
            "approvals_reviewer": "auto_review",
            "sandbox_network_access": True,
            "collaboration_mode": "plan",
            "personality": "pragmatic",
            "num_input_images": 2,
            "is_first_turn": True,
            "status": "completed",
            "turn_error": None,
            "steer_count": 0,
            "total_tool_call_count": 0,
            "shell_command_count": 0,
            "file_change_count": 0,
            "mcp_tool_call_count": 0,
            "dynamic_tool_call_count": 0,
            "subagent_tool_call_count": 0,
            "web_search_count": 0,
            "image_generation_count": 0,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_output_tokens": None,
            "total_tokens": None,
            "duration_ms": 1234,
            "started_at": 455,
            "completed_at": 456,
        },
    }


def test_turn_event_requires_resolved_config_images_thread_and_completion() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::turn_does_not_emit_without_required_prerequisites
    # Contract: turn event emission waits for thread id, image count, resolved config, and completion.
    base = {
        "app_server_client": sample_app_server_client_metadata(),
        "runtime": sample_runtime_metadata(),
        "turn_id": "turn-2",
        "thread_metadata": sample_thread_metadata(),
    }

    assert codex_turn_event(turn_state=TurnState(), **base) is None
    assert codex_turn_event(
        turn_state=TurnState(
            thread_id="thread-2",
            num_input_images=1,
            completed=CompletedTurnState(TurnStatus.COMPLETED, None, completed_at=456, duration_ms=1234),
        ),
        **base,
    ) is None
    assert codex_turn_event(
        turn_state=TurnState(
            thread_id="thread-2",
            num_input_images=1,
            resolved_config=sample_resolved_config(),
        ),
        **base,
    ) is None


def test_turn_event_projects_token_usage_and_tool_counts() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust tests: analytics_client_tests::turn_lifecycle_emits_turn_event,
    #             analytics_client_tests::turn_event_counts_completed_tool_items
    # Contract: completed turns include token usage and completed tool item counts.
    counts = TurnToolCounts()
    for kind in (
        "CommandExecution",
        "FileChange",
        "McpToolCall",
        "DynamicToolCall",
        "CollabAgentToolCall",
        "WebSearch",
        "ImageGeneration",
        "AgentMessage",
    ):
        counts.record(kind)

    event = codex_turn_event(
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        turn_id="turn-2",
        turn_state=TurnState(
            thread_id="thread-2",
            num_input_images=1,
            resolved_config=sample_resolved_config(num_input_images=1),
            started_at=455,
            token_usage=TokenUsage(123, 45, 140, 13, 321),
            completed=CompletedTurnState(TurnStatus.COMPLETED, None, completed_at=456, duration_ms=1234),
            tool_counts=counts,
        ),
        thread_metadata=sample_thread_metadata(),
    )

    params = event["event_params"]  # type: ignore[index]
    assert params["num_input_images"] == 1
    assert params["input_tokens"] == 123
    assert params["cached_input_tokens"] == 45
    assert params["output_tokens"] == 140
    assert params["reasoning_output_tokens"] == 13
    assert params["total_tokens"] == 321
    assert params["total_tool_call_count"] == 7
    assert params["shell_command_count"] == 1
    assert params["file_change_count"] == 1
    assert params["mcp_tool_call_count"] == 1
    assert params["dynamic_tool_call_count"] == 1
    assert params["subagent_tool_call_count"] == 1
    assert params["web_search_count"] == 1
    assert params["image_generation_count"] == 1


def test_turn_start_error_response_discards_pending_start_request() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::turn_start_error_response_discards_pending_start_request
    # Contract: TurnStart error responses remove pending start requests; late responses cannot attach connection metadata.
    reducer = AnalyticsReducer()
    reducer.track_turn_start_request(
        connection_id=7,
        request_id=3,
        thread_id="thread-2",
        input_items=[
            {"type": "Text", "text": "hello"},
            {"type": "Image", "url": "https://example.com/a.png"},
        ],
    )

    assert reducer.ingest_turn_start_error_response(connection_id=7, request_id=3) == []

    late_response = reducer.ingest_turn_start_response(
        connection_id=7,
        request_id=3,
        turn_id="turn-2",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    assert late_response == []
    assert "turn-2" not in reducer.turns

    resolved_config = reducer.ingest_turn_resolved_config(
        sample_resolved_config(),
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    assert resolved_config == []

    completed = reducer.ingest_turn_completed(
        turn_id="turn-2",
        completed=CompletedTurnState(TurnStatus.COMPLETED, None, completed_at=456, duration_ms=1234),
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    assert completed == []
    assert reducer.turns["turn-2"].connection_id is None
    assert reducer.turns["turn-2"].thread_id == "thread-2"
    assert reducer.turns["turn-2"].num_input_images == 2


def test_turn_lifecycle_emits_failed_turn_event() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::turn_lifecycle_emits_failed_turn_event
    # Contract: failed turn completion emits codex_turn_event with failed status and Codex error info.
    reducer = sample_reducer_with_turn_prerequisites()

    events = reducer.ingest_turn_completed_notification(
        turn_id="turn-2",
        status=TurnStatus.FAILED,
        turn_error="badRequest",
        completed_at=456,
        duration_ms=1234,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert len(events) == 1
    params = events[0]["event_params"]
    assert params["status"] == "failed"
    assert params["turn_error"] == "badRequest"
    assert params["started_at"] == 455
    assert params["duration_ms"] == 1234
    assert "turn-2" not in reducer.turns


def test_turn_lifecycle_emits_interrupted_turn_event_without_error() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::turn_lifecycle_emits_interrupted_turn_event_without_error
    # Contract: interrupted turn completion emits interrupted status with null error.
    reducer = sample_reducer_with_turn_prerequisites()

    events = reducer.ingest_turn_completed_notification(
        turn_id="turn-2",
        status=TurnStatus.INTERRUPTED,
        turn_error=None,
        completed_at=456,
        duration_ms=1234,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert len(events) == 1
    params = events[0]["event_params"]
    assert params["status"] == "interrupted"
    assert params["turn_error"] is None


def test_turn_completed_without_started_notification_emits_null_started_at() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::turn_completed_without_started_notification_emits_null_started_at
    # Contract: completion can emit without a prior TurnStarted notification; started_at and token usage stay null.
    reducer = sample_reducer_with_turn_prerequisites(include_started=False)

    events = reducer.ingest_turn_completed_notification(
        turn_id="turn-2",
        status=TurnStatus.COMPLETED,
        turn_error=None,
        completed_at=456,
        duration_ms=1234,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert len(events) == 1
    params = events[0]["event_params"]
    assert params["status"] == "completed"
    assert params["started_at"] is None
    assert params["duration_ms"] == 1234
    assert params["input_tokens"] is None
    assert params["cached_input_tokens"] is None


def test_reducer_emits_accepted_line_fingerprints_once_from_latest_turn_diff_on_completion() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::reducer_emits_accepted_line_fingerprints_once_from_latest_turn_diff_on_completion
    # Contract: TurnDiffUpdated stores the latest diff; completed turn emits one accepted-line event after the turn event.
    reducer = sample_reducer_with_turn_prerequisites()
    for line in ["let old_value = 1;", "let latest_value = 2;"]:
        diff = f"""diff --git a/src/lib.rs b/src/lib.rs
index 1111111..2222222
--- a/src/lib.rs
+++ b/src/lib.rs
@@ -0,0 +1 @@
+{line}
"""
        assert reducer.ingest_turn_diff_updated(thread_id="thread-2", turn_id="turn-2", diff=diff) == []

    events = reducer.ingest_turn_completed_notification(
        turn_id="turn-2",
        status=TurnStatus.COMPLETED,
        turn_error=None,
        completed_at=999,
        duration_ms=544,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert [event["event_type"] for event in events] == [
        "codex_turn_event",
        "codex_accepted_line_fingerprints",
    ]
    accepted = events[1]["event_params"]
    assert accepted["turn_id"] == "turn-2"
    assert accepted["thread_id"] == "thread-2"
    assert accepted["product_surface"] == "codex"
    assert accepted["model_slug"] == "gpt-5"
    assert accepted["accepted_added_lines"] == 1
    assert accepted["accepted_deleted_lines"] == 0
    assert accepted["line_fingerprints"] == []


def test_reducer_emits_large_accepted_line_aggregates_without_fingerprints() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::reducer_emits_large_accepted_line_aggregates_without_fingerprints
    # Contract: large accepted-line diffs emit aggregate counts while upload payload omits computed fingerprints.
    reducer = sample_reducer_with_turn_prerequisites()
    diff = """diff --git a/src/lib.rs b/src/lib.rs
index 1111111..2222222
--- a/src/lib.rs
+++ b/src/lib.rs
@@ -0,0 +1,20000 @@
""" + "".join(f"+let value_{index} = {index};\n" for index in range(20_000))

    assert reducer.ingest_turn_diff_updated(thread_id="thread-2", turn_id="turn-2", diff=diff) == []
    events = reducer.ingest_turn_completed_notification(
        turn_id="turn-2",
        status=TurnStatus.COMPLETED,
        turn_error=None,
        completed_at=999,
        duration_ms=544,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    accepted_events = [event for event in events if event["event_type"] == "codex_accepted_line_fingerprints"]
    assert len(accepted_events) == 1
    params = accepted_events[0]["event_params"]
    assert params["turn_id"] == "turn-2"
    assert params["thread_id"] == "thread-2"
    assert params["accepted_added_lines"] == 20_000
    assert params["accepted_deleted_lines"] == 0
    assert params["line_fingerprints"] == []
