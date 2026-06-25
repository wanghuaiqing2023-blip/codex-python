from pathlib import Path

from pycodex.analytics import (
    AppInvocation,
    HookEventName,
    HookRunFact,
    HookRunStatus,
    HookSource,
    InvocationType,
    PluginCapabilitySummary,
    PluginId,
    PluginState,
    PluginTelemetryMetadata,
    TrackEventsContext,
    app_mentioned_event,
    app_used_event,
    codex_hook_run_metadata,
    hook_run_event,
    normalize_path_for_skill_id,
    plugin_management_event,
    plugin_state_event_type,
    plugin_used_event,
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


def test_normalize_path_for_skill_id_repo_scoped_uses_relative_path() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::normalize_path_for_skill_id_repo_scoped_uses_relative_path
    # Contract: repo-scoped skill ids use skill paths relative to the repo root.
    assert (
        normalize_path_for_skill_id(
            "https://example.com/repo.git",
            Path("/repo/root"),
            Path("/repo/root/.codex/skills/doc/SKILL.md"),
        )
        == ".codex/skills/doc/SKILL.md"
    )


def test_normalize_path_for_skill_id_user_scoped_uses_absolute_path() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::normalize_path_for_skill_id_user_scoped_uses_absolute_path
    # Contract: user-scoped skill ids use the canonical-or-original absolute path with `/` separators.
    assert normalize_path_for_skill_id(None, None, Path("/Users/abc/.codex/skills/doc/SKILL.md")) == (
        "/Users/abc/.codex/skills/doc/SKILL.md"
    )


def test_normalize_path_for_skill_id_admin_scoped_uses_absolute_path() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::normalize_path_for_skill_id_admin_scoped_uses_absolute_path
    # Contract: admin/system paths are not repo-relative without repo scope.
    assert normalize_path_for_skill_id(None, None, Path("/etc/codex/skills/doc/SKILL.md")) == (
        "/etc/codex/skills/doc/SKILL.md"
    )


def test_normalize_path_for_skill_id_repo_root_not_in_skill_path_uses_absolute_path() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::normalize_path_for_skill_id_repo_root_not_in_skill_path_uses_absolute_path
    # Contract: repo-scoped skill paths outside the repo root fall back to canonical-or-original absolute path.
    assert (
        normalize_path_for_skill_id(
            "https://example.com/repo.git",
            Path("/repo/root"),
            Path("/other/path/.codex/skills/doc/SKILL.md"),
        )
        == "/other/path/.codex/skills/doc/SKILL.md"
    )


def test_app_mentioned_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::app_mentioned_event_serializes_expected_shape
    # Contract: app-mentioned metadata shape includes tracking, app fields, originator, and invocation type.
    tracking = TrackEventsContext(model_slug="gpt-5", thread_id="thread-1", turn_id="turn-1")

    assert app_mentioned_event(
        tracking,
        AppInvocation("calendar", "Calendar", InvocationType.EXPLICIT),
    ) == {
        "event_type": "codex_app_mentioned",
        "event_params": {
            "connector_id": "calendar",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "app_name": "Calendar",
            "product_client_id": "codex_cli_rs",
            "invoke_type": "explicit",
            "model_slug": "gpt-5",
        },
    }


def test_app_used_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::app_used_event_serializes_expected_shape
    # Contract: app-used metadata uses the same app metadata projection.
    tracking = TrackEventsContext(model_slug="gpt-5", thread_id="thread-2", turn_id="turn-2")

    assert app_used_event(
        tracking,
        AppInvocation("drive", "Google Drive", InvocationType.IMPLICIT),
    )["event_params"] == {
        "connector_id": "drive",
        "thread_id": "thread-2",
        "turn_id": "turn-2",
        "app_name": "Google Drive",
        "product_client_id": "codex_cli_rs",
        "invoke_type": "implicit",
        "model_slug": "gpt-5",
    }


def test_plugin_used_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::plugin_used_event_serializes_expected_shape
    # Contract: plugin-used metadata flattens plugin metadata plus tracking fields.
    tracking = TrackEventsContext(model_slug="gpt-5", thread_id="thread-3", turn_id="turn-3")

    assert plugin_used_event(tracking, sample_plugin_metadata()) == {
        "event_type": "codex_plugin_used",
        "event_params": {
            "plugin_id": "sample@test",
            "plugin_name": "sample",
            "marketplace_name": "test",
            "has_skills": True,
            "mcp_server_count": 2,
            "connector_ids": ["calendar", "drive"],
            "product_client_id": "codex_cli_rs",
            "thread_id": "thread-3",
            "turn_id": "turn-3",
            "model_slug": "gpt-5",
        },
    }


def test_plugin_management_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::plugin_management_event_serializes_expected_shape
    # Contract: plugin management events use state-specific event type and plugin metadata.
    assert plugin_management_event(PluginState.INSTALLED, sample_plugin_metadata()) == {
        "event_type": "codex_plugin_installed",
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
    assert plugin_state_event_type(PluginState.UNINSTALLED) == "codex_plugin_uninstalled"
    assert plugin_state_event_type(PluginState.ENABLED) == "codex_plugin_enabled"
    assert plugin_state_event_type(PluginState.DISABLED) == "codex_plugin_disabled"


def test_plugin_management_event_can_use_remote_plugin_id_override() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::plugin_management_event_can_use_remote_plugin_id_override
    # Contract: remote_plugin_id overrides plugin_id while plugin name/marketplace remain local metadata.
    payload = plugin_management_event(
        PluginState.INSTALLED,
        sample_plugin_metadata(remote_plugin_id="plugins~Plugin_remote"),
    )

    assert payload["event_params"]["plugin_id"] == "plugins~Plugin_remote"
    assert payload["event_params"]["plugin_name"] == "sample"
    assert payload["event_params"]["marketplace_name"] == "test"


def test_hook_run_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::hook_run_event_serializes_expected_shape
    # Contract: hook-run event maps hook enum names, source strings, and statuses.
    tracking = TrackEventsContext(model_slug="gpt-5", thread_id="thread-3", turn_id="turn-3")

    assert hook_run_event(
        tracking,
        HookRunFact(HookEventName.PRE_TOOL_USE, HookSource.USER, HookRunStatus.COMPLETED),
    ) == {
        "event_type": "codex_hook_run",
        "event_params": {
            "thread_id": "thread-3",
            "turn_id": "turn-3",
            "model_slug": "gpt-5",
            "hook_name": "PreToolUse",
            "hook_source": "user",
            "status": "completed",
        },
    }


def test_hook_run_metadata_maps_sources_and_statuses() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::hook_run_metadata_maps_sources_and_statuses
    # Contract: hook source/status mappings match Rust analytics labels.
    tracking = TrackEventsContext(model_slug="gpt-5", thread_id="thread-1", turn_id="turn-1")

    system = codex_hook_run_metadata(
        tracking,
        HookRunFact(HookEventName.SESSION_START, HookSource.SYSTEM, HookRunStatus.COMPLETED),
    )
    project = codex_hook_run_metadata(
        tracking,
        HookRunFact(HookEventName.STOP, HookSource.PROJECT, HookRunStatus.BLOCKED),
    )
    cloud_requirements = codex_hook_run_metadata(
        tracking,
        HookRunFact(HookEventName.STOP, HookSource.CLOUD_REQUIREMENTS, HookRunStatus.BLOCKED),
    )
    unknown = codex_hook_run_metadata(
        tracking,
        HookRunFact(HookEventName.USER_PROMPT_SUBMIT, HookSource.UNKNOWN, HookRunStatus.FAILED),
    )

    assert system["hook_source"] == "system"
    assert system["status"] == "completed"
    assert project["hook_source"] == "project"
    assert project["status"] == "blocked"
    assert cloud_requirements["hook_source"] == "cloud_requirements"
    assert cloud_requirements["status"] == "blocked"
    assert unknown["hook_source"] == "unknown"
    assert unknown["status"] == "failed"


def test_hook_run_metadata_maps_stopped_status() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::hook_run_metadata_maps_stopped_status
    # Contract: stopped hook status serializes as "stopped".
    tracking = TrackEventsContext(model_slug="gpt-5", thread_id="thread-1", turn_id="turn-1")

    stopped = codex_hook_run_metadata(
        tracking,
        HookRunFact(HookEventName.STOP, HookSource.USER, HookRunStatus.STOPPED),
    )

    assert stopped["hook_source"] == "user"
    assert stopped["status"] == "stopped"
