from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.tui.app.startup_prompts import (
    Config,
    ConfigOverrides,
    EventSender,
    HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG,
    MODEL_AVAILABILITY_NUX_MAX_SHOW_COUNT,
    ModelAvailabilityNux,
    ModelAvailabilityNuxConfig,
    ModelPreset,
    ModelUpgrade,
    Notices,
    StartupTooltipOverride,
    emit_project_config_warnings,
    emit_skill_load_warnings,
    emit_system_bwrap_warning,
    handle_model_migration_prompt_if_needed,
    prepare_startup_tooltip_override,
    apply_accepted_model_migration,
    migration_prompt_hidden,
    normalize_harness_overrides_for_cwd,
    select_model_availability_nux,
    should_show_model_migration_prompt,
    target_preset_for_upgrade,
)


def test_should_show_model_migration_prompt_matches_rust_conditions() -> None:
    models = [
        ModelPreset("old", upgrade=ModelUpgrade("new")),
        ModelPreset("new", show_in_picker=True),
        ModelPreset("hidden", show_in_picker=False),
    ]

    assert should_show_model_migration_prompt("old", "new", {}, models)
    assert not should_show_model_migration_prompt("new", "new", {}, models)
    assert not should_show_model_migration_prompt("old", "new", {"old": "new"}, models)
    assert not should_show_model_migration_prompt("old", "hidden", {}, models)
    assert should_show_model_migration_prompt("other", "new", {}, models)


def test_migration_prompt_hidden_and_target_preset_for_upgrade() -> None:
    config = Config(notices=Notices(hide_gpt5_1_migration_prompt=True))
    models = [ModelPreset("target", show_in_picker=True), ModelPreset("hidden", show_in_picker=False)]

    assert migration_prompt_hidden(config, HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG)
    assert not migration_prompt_hidden(config, "unknown")
    assert target_preset_for_upgrade(models, "target") == models[0]
    assert target_preset_for_upgrade(models, "hidden") is None


def test_apply_accepted_model_migration_updates_config_and_emits_events_in_order() -> None:
    config = Config(model="old")
    tx = EventSender()

    apply_accepted_model_migration(config, tx, "old", "new", "high")

    assert config.model == "new"
    assert config.model_reasoning_effort == "high"
    assert [event["type"] for event in tx.events] == [
        "PersistModelMigrationPromptAcknowledged",
        "UpdateModel",
        "UpdateReasoningEffort",
        "PersistModelSelection",
    ]


def test_select_model_availability_nux_respects_show_limit_and_first_match() -> None:
    models = [
        ModelPreset("a", availability_nux=ModelAvailabilityNux("A is available")),
        ModelPreset("b", availability_nux=ModelAvailabilityNux("B is available")),
    ]
    config = ModelAvailabilityNuxConfig(shown_count={"a": MODEL_AVAILABILITY_NUX_MAX_SHOW_COUNT, "b": 3})

    assert select_model_availability_nux(models, config) == StartupTooltipOverride("b", "B is available")
    assert select_model_availability_nux(models, ModelAvailabilityNuxConfig()) == StartupTooltipOverride("a", "A is available")


def test_normalize_harness_overrides_resolves_relative_add_dirs(tmp_path: Path) -> None:
    base_cwd = tmp_path / "base"
    base_cwd.mkdir()
    overrides = ConfigOverrides(additional_writable_roots=[Path("rel")])

    normalized = normalize_harness_overrides_for_cwd(overrides, base_cwd)

    assert normalized.additional_writable_roots == [base_cwd / "rel"]


def test_warning_emitters_match_rust_event_order() -> None:
    tx = EventSender()
    emit_skill_load_warnings(tx, [{"path": "bad/SKILL.md", "message": "invalid"}])
    assert [event["cell"]["message"] for event in tx.events] == [
        "Skipped loading 1 skill(s) due to invalid SKILL.md files.",
        "bad/SKILL.md: invalid",
    ]

    tx = EventSender()
    layer = {"name": {"kind": "Project", "dot_codex_folder": ".codex"}, "disabled_reason": "not trusted"}
    emit_project_config_warnings(tx, {"config_layers": [layer]})
    assert "Project-local config" in tx.events[0]["cell"]["message"]
    assert ".codex" in tx.events[0]["cell"]["message"]

    tx = EventSender()
    emit_system_bwrap_warning(tx, {"permission_profile": "profile"}, lambda profile: "warn " + profile)
    assert tx.events[0]["cell"]["message"] == "warn profile"


def test_prepare_startup_tooltip_override_updates_count() -> None:
    config = Config(model_availability_nux=ModelAvailabilityNuxConfig(shown_count={"a": 1}))
    models = [ModelPreset("a", availability_nux=ModelAvailabilityNux("A is available"))]

    message = asyncio.run(prepare_startup_tooltip_override(config, models, False))

    assert message == "A is available"
    assert config.model_availability_nux.shown_count == {"a": 2}


def test_handle_model_migration_prompt_accept_reject_and_exit() -> None:
    models = [
        ModelPreset("old", upgrade=ModelUpgrade("new", migration_config_key=HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG)),
        ModelPreset("new", show_in_picker=True, display_name="New", default_reasoning_effort="high"),
    ]

    config = Config(model="old")
    tx = EventSender()
    result = asyncio.run(handle_model_migration_prompt_if_needed(lambda _copy: "accepted", config, "old", tx, models))
    assert result is None
    assert config.model == "new"
    assert [event["type"] for event in tx.events] == [
        "PersistModelMigrationPromptAcknowledged",
        "UpdateModel",
        "UpdateReasoningEffort",
        "PersistModelSelection",
    ]

    config = Config(model="old")
    tx = EventSender()
    result = asyncio.run(handle_model_migration_prompt_if_needed(lambda _copy: "rejected", config, "old", tx, models))
    assert result is None
    assert [event["type"] for event in tx.events] == ["PersistModelMigrationPromptAcknowledged"]

    config = Config(model="old")
    tx = EventSender()
    result = asyncio.run(handle_model_migration_prompt_if_needed(lambda _copy: "exit", config, "old", tx, models))
    assert result is not None
    assert result.exit_reason == "UserRequested"
