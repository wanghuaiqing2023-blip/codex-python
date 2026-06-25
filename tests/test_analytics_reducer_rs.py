import hashlib
from pathlib import Path

from pycodex.analytics import (
    AnalyticsEventsQueue,
    AnalyticsReducer,
    AppInvocation,
    AppMentionedInput,
    AppUsedInput,
    HookEventName,
    HookRunFact,
    HookRunInput,
    HookRunStatus,
    HookSource,
    InvocationType,
    PluginCapabilitySummary,
    PluginId,
    PluginState,
    PluginStateChangedInput,
    PluginTelemetryMetadata,
    PluginUsedInput,
    SkillInvocation,
    SkillInvokedInput,
    SkillScope,
    ThreadInitializationMode,
    ThreadMetadataState,
    TrackEventsContext,
    skill_id_for_local_skill,
)


def sample_plugin_metadata(**updates) -> PluginTelemetryMetadata:
    plugin = PluginTelemetryMetadata(
        plugin_id=PluginId(plugin_name="sample", marketplace_name="test"),
        capability_summary=PluginCapabilitySummary(
            has_skills=True,
            mcp_server_names=("mcp-a", "mcp-b"),
            app_connector_ids=("calendar", "drive"),
        ),
    )
    for key, value in updates.items():
        setattr(plugin, key, value)
    return plugin


def tracking(turn_id: str = "turn-1") -> TrackEventsContext:
    return TrackEventsContext(model_slug="gpt-5", thread_id="thread-1", turn_id=turn_id)


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


def sample_thread_metadata() -> ThreadMetadataState:
    return ThreadMetadataState(
        session_id="session-thread-2",
        thread_source="user",
        initialization_mode=ThreadInitializationMode.NEW,
    )


def test_plugin_used_dedupe_is_keyed_by_turn_and_plugin() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/client.rs
    # Rust test: analytics_client_tests::plugin_used_dedupe_is_keyed_by_turn_and_plugin
    # Contract: plugin-used dedupe key is (turn_id, plugin_id.as_key()).
    queue = AnalyticsEventsQueue()
    plugin = sample_plugin_metadata()

    assert queue.should_enqueue_plugin_used(tracking("turn-1"), plugin) is True
    assert queue.should_enqueue_plugin_used(tracking("turn-1"), plugin) is False
    assert queue.should_enqueue_plugin_used(tracking("turn-2"), plugin) is True


def test_app_used_dedupe_is_keyed_by_turn_and_connector() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/client.rs
    # Rust test: analytics_client_tests::app_used_dedupe_is_keyed_by_turn_and_connector
    # Contract: app-used dedupe key is (turn_id, connector_id); missing connector_id is never deduped.
    queue = AnalyticsEventsQueue()
    app = AppInvocation("calendar", "Calendar", InvocationType.IMPLICIT)

    assert queue.should_enqueue_app_used(tracking("turn-1"), app) is True
    assert queue.should_enqueue_app_used(tracking("turn-1"), app) is False
    assert queue.should_enqueue_app_used(tracking("turn-2"), app) is True
    assert queue.should_enqueue_app_used(tracking("turn-1"), AppInvocation(None, "No Connector")) is True
    assert queue.should_enqueue_app_used(tracking("turn-1"), AppInvocation(None, "No Connector")) is True


def test_reducer_ingests_skill_invoked_fact() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::reducer_ingests_skill_invoked_fact
    # Contract: skill invocation facts emit one skill_invocation event per invocation.
    reducer = AnalyticsReducer()
    skill_path = Path("/Users/abc/.codex/skills/doc/SKILL.md")
    expected_skill_id = hashlib.sha1(b"personal_/Users/abc/.codex/skills/doc/SKILL.md_doc").hexdigest()

    payload = reducer.ingest_skill_invoked(
        SkillInvokedInput(
            tracking=tracking(),
            invocations=[
                SkillInvocation(
                    skill_name="doc",
                    skill_scope=SkillScope.USER,
                    skill_path=skill_path,
                    plugin_id=None,
                    invocation_type=InvocationType.EXPLICIT,
                )
            ],
        )
    )

    assert payload == [
        {
            "event_type": "skill_invocation",
            "skill_id": expected_skill_id,
            "skill_name": "doc",
            "event_params": {
                "product_client_id": "codex_cli_rs",
                "skill_scope": "user",
                "plugin_id": None,
                "repo_url": None,
                "thread_id": "thread-1",
                "turn_id": "turn-1",
                "invoke_type": "explicit",
                "model_slug": "gpt-5",
            },
        }
    ]
    assert skill_id_for_local_skill(None, None, skill_path, "doc") == expected_skill_id


def test_reducer_includes_plugin_id_for_plugin_skill_invocations() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::reducer_includes_plugin_id_for_plugin_skill_invocations
    # Contract: plugin-backed skill invocations preserve the plugin_id in event_params.
    payload = AnalyticsReducer().ingest_skill_invoked(
        SkillInvokedInput(
            tracking=tracking(),
            invocations=[
                SkillInvocation(
                    skill_name="sample:doc",
                    skill_scope=SkillScope.USER,
                    skill_path=Path("/Users/abc/.codex/plugins/cache/test/sample/skills/doc/SKILL.md"),
                    plugin_id="sample@test",
                    invocation_type=InvocationType.EXPLICIT,
                )
            ],
        )
    )

    assert payload[0]["event_params"]["plugin_id"] == "sample@test"


def test_reducer_ingests_hook_run_fact() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::reducer_ingests_hook_run_fact
    # Contract: hook-run facts become codex_hook_run events through event metadata projection.
    payload = AnalyticsReducer().ingest_hook_run(
        HookRunInput(
            tracking=tracking(),
            hook=HookRunFact(HookEventName.POST_TOOL_USE, HookSource.UNKNOWN, HookRunStatus.FAILED),
        )
    )

    assert len(payload) == 1
    assert payload[0]["event_type"] == "codex_hook_run"
    assert payload[0]["event_params"]["hook_name"] == "PostToolUse"
    assert payload[0]["event_params"]["hook_source"] == "unknown"
    assert payload[0]["event_params"]["status"] == "failed"


def test_reducer_ingests_app_and_plugin_facts() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::reducer_ingests_app_and_plugin_facts
    # Contract: app-mentioned, app-used, and plugin-used facts emit their corresponding event types.
    reducer = AnalyticsReducer()
    events = []
    events.extend(
        reducer.ingest_app_mentioned(
            AppMentionedInput(
                tracking=tracking(),
                mentions=[AppInvocation("calendar", "Calendar", InvocationType.EXPLICIT)],
            )
        )
    )
    events.extend(
        reducer.ingest_app_used(
            AppUsedInput(
                tracking=tracking(),
                app=AppInvocation("drive", "Drive", InvocationType.IMPLICIT),
            )
        )
    )
    events.extend(reducer.ingest_plugin_used(PluginUsedInput(tracking=tracking(), plugin=sample_plugin_metadata())))

    assert [event["event_type"] for event in events] == [
        "codex_app_mentioned",
        "codex_app_used",
        "codex_plugin_used",
    ]


def test_reducer_ingests_plugin_state_changed_fact() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::reducer_ingests_plugin_state_changed_fact
    # Contract: plugin state changes emit state-specific plugin management events.
    payload = AnalyticsReducer().ingest_plugin_state_changed(
        PluginStateChangedInput(plugin=sample_plugin_metadata(), state=PluginState.DISABLED)
    )

    assert payload == [
        {
            "event_type": "codex_plugin_disabled",
            "event_params": {
                "plugin_id": "sample@test",
                "plugin_name": "sample",
                "marketplace_name": "test",
                "has_skills": True,
                "mcp_server_count": 2,
                "connector_ids": ["calendar", "drive"],
                "product_client_id": "codex_cli_rs",
            },
        }
    ]


def test_unrelated_client_requests_are_ignored_by_reducer() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::unrelated_client_requests_are_ignored_by_reducer
    # Contract: unrelated ClientRequest variants do not create pending turn state for later responses.
    reducer = AnalyticsReducer()

    assert reducer.ingest_client_request(
        connection_id=7,
        request_id=3,
        request_kind="ThreadArchive",
        params={"thread_id": "thread-2"},
    ) == []
    events = reducer.ingest_client_response(
        connection_id=7,
        request_id=3,
        response_kind="TurnStart",
        response={"turn": {"id": "turn-2"}},
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert events == []
    assert reducer.requests == {}
    assert "turn-2" not in reducer.turns


def test_unrelated_client_responses_are_ignored_by_reducer() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::unrelated_client_responses_are_ignored_by_reducer
    # Contract: unrelated ClientResponse variants emit no analytics events.
    reducer = AnalyticsReducer()
    assert reducer.ingest_initialize(
        connection_id=7,
        product_client_id="codex_cli_rs",
        client_name="codex-tui",
        client_version="1.0.0",
        rpc_transport="stdio",
        experimental_api_enabled=True,
        runtime=sample_runtime_metadata(),
    ) == []

    assert reducer.ingest_client_response(
        connection_id=7,
        request_id=9,
        response_kind="ThreadArchive",
        response={},
    ) == []
    assert reducer.turns == {}
