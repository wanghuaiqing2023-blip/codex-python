from pycodex.analytics import (
    AnalyticsReducer,
    CodexCompactionEvent,
    CompactionImplementation,
    CompactionPhase,
    CompactionReason,
    CompactionStatus,
    CompactionStrategy,
    CompactionTrigger,
    SubAgentThreadStartedInput,
    ThreadInitializationMode,
    subagent_thread_started_event,
    thread_initialized_event,
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


def subagent_input(**updates) -> SubAgentThreadStartedInput:
    values = {
        "session_id": "session-root",
        "thread_id": "thread-review",
        "parent_thread_id": None,
        "product_client_id": "codex-tui",
        "client_name": "codex-tui",
        "client_version": "1.0.0",
        "model": "gpt-5",
        "ephemeral": False,
        "subagent_source": "Review",
        "created_at": 123,
    }
    values.update(updates)
    return SubAgentThreadStartedInput(**values)


def test_thread_initialized_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::thread_initialized_event_serializes_expected_shape
    # Contract: ThreadInitializedEvent serializes the Rust field shape.
    payload = thread_initialized_event(
        thread_id="thread-0",
        session_id="session-thread-0",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        model="gpt-5",
        ephemeral=True,
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
        subagent_source=None,
        parent_thread_id=None,
        created_at=1,
    )

    assert payload == {
        "event_type": "codex_thread_initialized",
        "event_params": {
            "thread_id": "thread-0",
            "session_id": "session-thread-0",
            "app_server_client": sample_app_server_client_metadata(),
            "runtime": sample_runtime_metadata(),
            "model": "gpt-5",
            "ephemeral": True,
            "thread_source": "user",
            "initialization_mode": "new",
            "subagent_source": None,
            "parent_thread_id": None,
            "created_at": 1,
        },
    }


def test_subagent_thread_started_review_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::subagent_thread_started_review_serializes_expected_shape
    # Contract: review subagent thread start uses in-process app metadata and subagent source labels.
    payload = subagent_thread_started_event(subagent_input(), runtime=sample_runtime_metadata())

    assert payload["event_type"] == "codex_thread_initialized"
    assert payload["event_params"]["thread_source"] == "subagent"
    assert payload["event_params"]["app_server_client"]["product_client_id"] == "codex-tui"
    assert payload["event_params"]["app_server_client"]["client_name"] == "codex-tui"
    assert payload["event_params"]["app_server_client"]["client_version"] == "1.0.0"
    assert payload["event_params"]["app_server_client"]["rpc_transport"] == "in_process"
    assert payload["event_params"]["app_server_client"]["experimental_api_enabled"] is None
    assert payload["event_params"]["created_at"] == 123
    assert payload["event_params"]["initialization_mode"] == "new"
    assert payload["event_params"]["subagent_source"] == "review"
    assert payload["event_params"]["parent_thread_id"] is None


def test_subagent_thread_started_thread_spawn_serializes_parent_thread_id() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::subagent_thread_started_thread_spawn_serializes_parent_thread_id
    # Contract: ThreadSpawn source supplies parent_thread_id when explicit parent is absent.
    payload = subagent_thread_started_event(
        subagent_input(
            thread_id="thread-spawn",
            ephemeral=True,
            created_at=124,
            subagent_source={
                "kind": "ThreadSpawn",
                "parent_thread_id": "11111111-1111-1111-1111-111111111111",
            },
        ),
        runtime=sample_runtime_metadata(),
    )

    assert payload["event_params"]["thread_id"] == "thread-spawn"
    assert payload["event_params"]["thread_source"] == "subagent"
    assert payload["event_params"]["subagent_source"] == "thread_spawn"
    assert payload["event_params"]["parent_thread_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["event_params"]["session_id"] == "session-root"


def test_subagent_thread_started_memory_consolidation_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::subagent_thread_started_memory_consolidation_serializes_expected_shape
    # Contract: MemoryConsolidation subagent source serializes as memory_consolidation and does not imply a parent.
    payload = subagent_thread_started_event(
        subagent_input(
            thread_id="thread-memory",
            subagent_source="MemoryConsolidation",
            created_at=125,
        ),
        runtime=sample_runtime_metadata(),
    )

    assert payload["event_params"]["thread_id"] == "thread-memory"
    assert payload["event_params"]["subagent_source"] == "memory_consolidation"
    assert payload["event_params"]["parent_thread_id"] is None


def test_subagent_thread_started_other_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::subagent_thread_started_other_serializes_expected_shape
    # Contract: Other subagent source preserves its label and does not imply a parent.
    payload = subagent_thread_started_event(
        subagent_input(
            thread_id="thread-guardian",
            subagent_source="Other:guardian",
            created_at=126,
        ),
        runtime=sample_runtime_metadata(),
    )

    assert payload["event_params"]["thread_id"] == "thread-guardian"
    assert payload["event_params"]["subagent_source"] == "guardian"
    assert payload["event_params"]["parent_thread_id"] is None


def test_subagent_thread_started_other_serializes_explicit_parent_thread_id() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::subagent_thread_started_other_serializes_explicit_parent_thread_id
    # Contract: explicit parent_thread_id overrides source-derived parent for non-spawn sources.
    payload = subagent_thread_started_event(
        subagent_input(
            thread_id="thread-guardian",
            parent_thread_id="parent-thread-guardian",
            subagent_source="Other:guardian",
            created_at=126,
        ),
        runtime=sample_runtime_metadata(),
    )

    assert payload["event_params"]["subagent_source"] == "guardian"
    assert payload["event_params"]["parent_thread_id"] == "parent-thread-guardian"


def test_subagent_thread_started_publishes_without_initialize() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::subagent_thread_started_publishes_without_initialize
    # Contract: custom subagent-thread-started fact emits without prior Initialize state.
    events = AnalyticsReducer().ingest_subagent_thread_started(subagent_input(created_at=127), runtime=sample_runtime_metadata())

    assert len(events) == 1
    assert events[0]["event_type"] == "codex_thread_initialized"
    assert events[0]["event_params"]["app_server_client"]["product_client_id"] == "codex-tui"
    assert events[0]["event_params"]["thread_source"] == "subagent"
    assert events[0]["event_params"]["subagent_source"] == "review"


def test_initialize_caches_client_and_thread_lifecycle_publishes_once_initialized() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::initialize_caches_client_and_thread_lifecycle_publishes_once_initialized
    # Contract: thread lifecycle events require Initialize, then use cached connection/runtime metadata.
    reducer = AnalyticsReducer()

    before_initialize = reducer.ingest_thread_response(
        connection_id=7,
        thread_id="thread-no-client",
        session_id="session-thread-no-client",
        model="gpt-5",
        ephemeral=False,
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
        created_at=1,
    )
    assert before_initialize == []

    initialized = reducer.ingest_initialize(
        connection_id=7,
        product_client_id="codex_cli_rs",
        client_name="codex-tui",
        client_version="1.0.0",
        rpc_transport="websocket",
        experimental_api_enabled=False,
        runtime={
            "codex_rs_version": "0.99.0",
            "runtime_os": "linux",
            "runtime_os_version": "24.04",
            "runtime_arch": "x86_64",
        },
    )
    assert initialized == []

    events = reducer.ingest_thread_response(
        connection_id=7,
        thread_id="thread-1",
        session_id="session-thread-1",
        model="gpt-5",
        ephemeral=True,
        thread_source="user",
        initialization_mode=ThreadInitializationMode.RESUMED,
        created_at=2,
    )

    assert len(events) == 1
    payload = events[0]
    assert payload["event_type"] == "codex_thread_initialized"
    params = payload["event_params"]
    assert params["thread_id"] == "thread-1"
    assert params["session_id"] == "session-thread-1"
    assert params["ephemeral"] is True
    assert params["initialization_mode"] == "resumed"
    assert params["thread_source"] == "user"
    assert params["app_server_client"]["product_client_id"] == "codex_cli_rs"
    assert params["app_server_client"]["client_name"] == "codex-tui"
    assert params["app_server_client"]["client_version"] == "1.0.0"
    assert params["app_server_client"]["rpc_transport"] == "websocket"
    assert params["app_server_client"]["experimental_api_enabled"] is False
    assert params["runtime"]["codex_rs_version"] == "0.99.0"
    assert params["runtime"]["runtime_os"] == "linux"
    assert params["runtime"]["runtime_os_version"] == "24.04"
    assert params["runtime"]["runtime_arch"] == "x86_64"
    assert reducer.threads["thread-1"].connection_id == 7
    assert reducer.threads["thread-1"].metadata is not None


def test_subagent_thread_started_inherits_parent_connection_for_new_thread() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::subagent_thread_started_inherits_parent_connection_for_new_thread
    # Contract: subagent threads inherit parent thread connection metadata for later reducer events.
    reducer = AnalyticsReducer()
    parent_thread_id = "44444444-4444-4444-4444-444444444444"

    assert reducer.ingest_initialize(
        connection_id=7,
        product_client_id="parent-client",
        client_name="parent-client",
        client_version="1.0.0",
        rpc_transport="stdio",
        experimental_api_enabled=None,
        runtime=sample_runtime_metadata(),
    ) == []
    parent_events = reducer.ingest_thread_response(
        connection_id=7,
        thread_id=parent_thread_id,
        session_id="session-parent",
        model="gpt-5",
        ephemeral=False,
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
        created_at=120,
    )
    assert len(parent_events) == 1

    started_events = reducer.ingest_subagent_thread_started(
        subagent_input(
            session_id="session-root",
            thread_id="thread-review",
            product_client_id="parent-client",
            client_name="parent-client",
            client_version="1.0.0",
            subagent_source={
                "kind": "ThreadSpawn",
                "parent_thread_id": parent_thread_id,
            },
            created_at=130,
        ),
        runtime=sample_runtime_metadata(),
    )

    assert len(started_events) == 1
    thread_state = reducer.threads["thread-review"]
    assert thread_state.connection_id == 7
    assert thread_state.metadata is not None
    assert thread_state.metadata.session_id == "session-root"
    assert thread_state.metadata.thread_source == "subagent"
    assert thread_state.metadata.subagent_source == "thread_spawn"
    assert thread_state.metadata.parent_thread_id == parent_thread_id

    compaction_events = reducer.ingest_compaction(
        CodexCompactionEvent(
            thread_id="thread-review",
            turn_id="turn-compact",
            trigger=CompactionTrigger.MANUAL,
            reason=CompactionReason.USER_REQUESTED,
            implementation=CompactionImplementation.RESPONSES,
            phase=CompactionPhase.STANDALONE_TURN,
            strategy=CompactionStrategy.MEMENTO,
            status=CompactionStatus.COMPLETED,
            error=None,
            active_context_tokens_before=131_000,
            active_context_tokens_after=64_000,
            started_at=100,
            completed_at=101,
            duration_ms=1200,
        ),
        app_server_client=reducer.connections[thread_state.connection_id].app_server_client,
        runtime=reducer.connections[thread_state.connection_id].runtime,
        thread_metadata=thread_state.metadata,
    )

    assert len(compaction_events) == 1
    params = compaction_events[0]["event_params"]
    assert params["session_id"] == "session-root"
    assert params["thread_id"] == "thread-review"
    assert params["app_server_client"]["product_client_id"] == "parent-client"
    assert params["parent_thread_id"] == parent_thread_id
