from pycodex.analytics import (
    AnalyticsReducer,
    CodexCompactionEvent,
    CompactionImplementation,
    CompactionPhase,
    CompactionReason,
    CompactionStatus,
    CompactionStrategy,
    CompactionTrigger,
    ThreadMetadataState,
    codex_compaction_event,
)


def sample_app_server_client_metadata(*, rpc_transport: str = "stdio", experimental_api_enabled: bool | None = True) -> dict:
    return {
        "product_client_id": "codex_cli_rs",
        "client_name": "codex-tui",
        "client_version": "1.0.0",
        "rpc_transport": rpc_transport,
        "experimental_api_enabled": experimental_api_enabled,
    }


def sample_runtime_metadata() -> dict:
    return {
        "codex_rs_version": "0.1.0",
        "runtime_os": "macos",
        "runtime_os_version": "15.3.1",
        "runtime_arch": "aarch64",
    }


def test_compaction_implementation_serializes_remote_v2() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/facts.rs
    # Rust test: analytics_client_tests::compaction_implementation_serializes_remote_v2
    # Contract: ResponsesCompactionV2 serializes as responses_compaction_v2.
    assert CompactionImplementation.RESPONSES_COMPACTION_V2.value == "responses_compaction_v2"


def test_compaction_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::compaction_event_serializes_expected_shape
    # Contract: codex_compaction_event_params projects Rust compaction fact plus thread/client/runtime metadata.
    payload = codex_compaction_event(
        CodexCompactionEvent(
            thread_id="thread-1",
            turn_id="turn-1",
            trigger=CompactionTrigger.AUTO,
            reason=CompactionReason.CONTEXT_LIMIT,
            implementation=CompactionImplementation.RESPONSES_COMPACT,
            phase=CompactionPhase.MID_TURN,
            strategy=CompactionStrategy.MEMENTO,
            status=CompactionStatus.COMPLETED,
            error=None,
            active_context_tokens_before=120_000,
            active_context_tokens_after=18_000,
            started_at=100,
            completed_at=106,
            duration_ms=6543,
        ),
        session_id="session-thread-1",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_source="user",
        subagent_source=None,
        parent_thread_id=None,
    )

    assert payload == {
        "event_type": "codex_compaction_event",
        "event_params": {
            "thread_id": "thread-1",
            "session_id": "session-thread-1",
            "turn_id": "turn-1",
            "app_server_client": sample_app_server_client_metadata(),
            "runtime": sample_runtime_metadata(),
            "thread_source": "user",
            "subagent_source": None,
            "parent_thread_id": None,
            "trigger": "auto",
            "reason": "context_limit",
            "implementation": "responses_compact",
            "phase": "mid_turn",
            "strategy": "memento",
            "status": "completed",
            "error": None,
            "active_context_tokens_before": 120_000,
            "active_context_tokens_after": 18_000,
            "started_at": 100,
            "completed_at": 106,
            "duration_ms": 6543,
        },
    }


def test_compaction_event_ingests_custom_fact_with_thread_metadata() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::compaction_event_ingests_custom_fact
    # Contract: reducer compaction ingestion combines fact fields with connection and thread metadata.
    events = AnalyticsReducer().ingest_compaction(
        CodexCompactionEvent(
            thread_id="thread-1",
            turn_id="turn-compact",
            trigger=CompactionTrigger.MANUAL,
            reason=CompactionReason.USER_REQUESTED,
            implementation=CompactionImplementation.RESPONSES,
            phase=CompactionPhase.STANDALONE_TURN,
            strategy=CompactionStrategy.MEMENTO,
            status=CompactionStatus.FAILED,
            error="context limit exceeded",
            active_context_tokens_before=131_000,
            active_context_tokens_after=131_000,
            started_at=100,
            completed_at=101,
            duration_ms=1200,
        ),
        app_server_client=sample_app_server_client_metadata(rpc_transport="websocket", experimental_api_enabled=False),
        runtime=sample_runtime_metadata(),
        thread_metadata=ThreadMetadataState(
            session_id="session-thread-1",
            thread_source="subagent",
            subagent_source="thread_spawn",
            parent_thread_id="22222222-2222-2222-2222-222222222222",
        ),
    )

    assert len(events) == 1
    payload = events[0]
    assert payload["event_type"] == "codex_compaction_event"
    assert payload["event_params"]["session_id"] == "session-thread-1"
    assert payload["event_params"]["thread_id"] == "thread-1"
    assert payload["event_params"]["turn_id"] == "turn-compact"
    assert payload["event_params"]["app_server_client"]["product_client_id"] == "codex_cli_rs"
    assert payload["event_params"]["app_server_client"]["client_name"] == "codex-tui"
    assert payload["event_params"]["app_server_client"]["rpc_transport"] == "websocket"
    assert payload["event_params"]["runtime"]["codex_rs_version"] == "0.1.0"
    assert payload["event_params"]["thread_source"] == "subagent"
    assert payload["event_params"]["subagent_source"] == "thread_spawn"
    assert payload["event_params"]["parent_thread_id"] == "22222222-2222-2222-2222-222222222222"
    assert payload["event_params"]["trigger"] == "manual"
    assert payload["event_params"]["reason"] == "user_requested"
    assert payload["event_params"]["implementation"] == "responses"
    assert payload["event_params"]["phase"] == "standalone_turn"
    assert payload["event_params"]["strategy"] == "memento"
    assert payload["event_params"]["status"] == "failed"
