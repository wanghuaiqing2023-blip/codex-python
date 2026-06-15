from __future__ import annotations

from pycodex.tui.app.config_persistence import (
    ConfigPersistencePlan,
    DEFAULT_OVERRIDDEN_WRITE_MESSAGE,
    ConfigReadResponse,
    ConfigWriteResponse,
    EffectiveConfigBody,
    FeatureSpec,
    MemoriesToml,
    OverriddenMetadata,
    approval_policy_from_effective_config,
    approvals_reviewer_from_effective_config,
    feature_enabled_from_effective_config,
    features_toml_from_json,
    memories_from_effective_config,
    overridden_write_message,
    sandbox_mode_from_effective_config,
    windows_sandbox_mode_from_effective_config,
    rebuild_config_for_resume_or_fallback_errors_when_cwd_changes,
    rebuild_config_for_resume_or_fallback_uses_current_config_on_same_cwd_error,
    refresh_in_memory_config_from_disk_best_effort_keeps_current_config_on_error,
    refresh_in_memory_config_from_disk_loads_latest_apps_state,
    refresh_in_memory_config_from_disk_updates_resize_reflow_config,
    refresh_in_memory_config_from_disk_uses_active_chat_widget_cwd,
    sync_tui_pet_disabled_updates_chat_widget_config_copy,
    sync_tui_pet_selection_updates_chat_widget_config_copy,
    sync_tui_theme_selection_updates_chat_widget_config_copy,
    update_reasoning_effort_updates_collaboration_mode,
)


def test_overridden_write_message_uses_metadata_or_default() -> None:
    assert overridden_write_message(ConfigWriteResponse()) == DEFAULT_OVERRIDDEN_WRITE_MESSAGE
    assert overridden_write_message(ConfigWriteResponse(OverriddenMetadata("managed by policy"))) == "managed by policy"
    assert overridden_write_message({"overridden_metadata": {"message": "mdm"}}) == "mdm"


def test_feature_enabled_from_effective_config_uses_root_features_or_default() -> None:
    response = ConfigReadResponse(
        EffectiveConfigBody(additional={"features": {"guardian_approval": False, "experimental": True}})
    )

    assert not feature_enabled_from_effective_config(response, FeatureSpec("guardian_approval", True))
    assert feature_enabled_from_effective_config(response, FeatureSpec("experimental", False))
    assert feature_enabled_from_effective_config(response, FeatureSpec("missing", True))
    assert not feature_enabled_from_effective_config(response, FeatureSpec("missing_false", False))
    assert features_toml_from_json(["not", "a", "map"]) is None


def test_effective_config_extractors_return_direct_config_fields() -> None:
    response = ConfigReadResponse(
        EffectiveConfigBody(
            additional={},
            approvals_reviewer="auto_review",
            approval_policy="on-request",
            sandbox_mode="workspace-write",
        )
    )

    assert approvals_reviewer_from_effective_config(response) == "auto_review"
    assert approval_policy_from_effective_config(response) == "on-request"
    assert sandbox_mode_from_effective_config(response) == "workspace-write"


def test_memories_and_windows_sandbox_from_effective_config_additional_maps() -> None:
    response = ConfigReadResponse(
        {
            "additional": {
                "memories": {"use_memories": True, "generate_memories": False},
                "windows": {"sandbox": "read-only"},
            }
        }
    )

    assert memories_from_effective_config(response) == MemoriesToml(use_memories=True, generate_memories=False)
    assert windows_sandbox_mode_from_effective_config(response) == "read-only"
    assert memories_from_effective_config({"config": {"additional": {}}}) is None


def test_runtime_sync_paths_are_semantic_config_persistence_plans() -> None:
    assert update_reasoning_effort_updates_collaboration_mode("high") == ConfigPersistencePlan(
        action="update_reasoning_effort",
        updates=(("chat_widget.reasoning_effort", "high"), ("config.model_reasoning_effort", "high")),
    )

    assert sync_tui_theme_selection_updates_chat_widget_config_copy("dracula") == ConfigPersistencePlan(
        action="sync_tui_theme_selection",
        updates=(("config.tui_theme", "dracula"), ("chat_widget.config.tui_theme", "dracula")),
    )
    assert sync_tui_pet_selection_updates_chat_widget_config_copy("chefito") == ConfigPersistencePlan(
        action="sync_tui_pet_selection",
        updates=(("config.tui_pet", "chefito"), ("chat_widget.config.tui_pet", "chefito")),
    )
    assert sync_tui_pet_disabled_updates_chat_widget_config_copy("none") == ConfigPersistencePlan(
        action="sync_tui_pet_disabled",
        updates=(("config.tui_pet", "none"), ("chat_widget.config.tui_pet", "none")),
    )


def test_resume_and_best_effort_refresh_paths_are_semantic_plans() -> None:
    assert refresh_in_memory_config_from_disk_best_effort_keeps_current_config_on_error("starting", RuntimeError("broken")).use_current_config
    assert rebuild_config_for_resume_or_fallback_uses_current_config_on_same_cwd_error("/repo").use_current_config

    changed = rebuild_config_for_resume_or_fallback_errors_when_cwd_changes("/repo", "/other")
    assert changed.error == "Failed to rebuild config for cwd /other"
    assert changed.use_current_config is False


def test_refresh_in_memory_config_plans_sync_latest_runtime_config() -> None:
    """Rust codex-tui app::config_persistence refresh_in_memory_config_from_disk tests."""

    assert refresh_in_memory_config_from_disk_loads_latest_apps_state("app-a", False) == ConfigPersistencePlan(
        action="refresh_in_memory_config_from_disk",
        updates=(("effective_config.apps.app-a.enabled", False), ("chat_widget.plugin_mentions_config", "sync")),
        refresh_from_disk=True,
    )
    assert refresh_in_memory_config_from_disk_uses_active_chat_widget_cwd("/workspace/next") == ConfigPersistencePlan(
        action="refresh_in_memory_config_from_disk",
        updates=(("config.cwd", "/workspace/next"),),
        refresh_from_disk=True,
    )
    assert refresh_in_memory_config_from_disk_updates_resize_reflow_config(9000) == ConfigPersistencePlan(
        action="refresh_in_memory_config_from_disk",
        updates=(("config.terminal_resize_reflow.max_rows", 9000),),
        refresh_from_disk=True,
    )
