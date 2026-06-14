import pytest
from dataclasses import dataclass

from pycodex.tui.config_update import (
    ConfigBatchWriteParams,
    ConfigEdit,
    FEATURE_DEFAULTS,
    ConfigReadParams,
    MergeStrategy,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    SkillsConfigWriteParams,
    app_scoped_key_path,
    build_feature_enabled_edit,
    build_memory_settings_edits,
    build_model_selection_edits,
    build_oss_provider_edit,
    build_service_tier_selection_edits,
    build_windows_sandbox_mode_edits,
    clear_config_value,
    read_effective_config,
    replace_config_value,
    trusted_project_edit,
    write_config_batch,
    write_skill_enabled,
    write_trusted_project,
)


def test_replace_and_clear_config_value_match_rust_edit_shape():
    assert replace_config_value("model", "gpt-5") == ConfigEdit(
        key_path="model",
        value="gpt-5",
        merge_strategy=MergeStrategy.REPLACE,
    )
    assert clear_config_value("service_tier") == ConfigEdit(
        key_path="service_tier",
        value=None,
        merge_strategy=MergeStrategy.REPLACE,
    )


def test_app_scoped_key_path_quotes_dotted_app_ids():
    # Rust: codex-tui, config_update.rs, app_scoped_key_path_quotes_dotted_app_ids.
    assert app_scoped_key_path("plugin.linear", "enabled") == 'apps."plugin.linear".enabled'


def test_trusted_project_edit_targets_project_trust_level():
    # Rust: codex-tui, config_update.rs, trusted_project_edit_targets_project_trust_level.
    assert trusted_project_edit("/workspace/team.project") == ConfigEdit(
        key_path='projects."/workspace/team.project".trust_level',
        value="trusted",
        merge_strategy=MergeStrategy.REPLACE,
    )


def test_trusted_project_edit_escapes_backslashes_and_quotes():
    assert trusted_project_edit(r'C:\work\"quoted"') == ConfigEdit(
        key_path='projects."C:\\\\work\\\\\\"quoted\\"".trust_level',
        value="trusted",
        merge_strategy=MergeStrategy.REPLACE,
    )


def test_build_model_selection_edits_clears_or_replaces_effort():
    assert build_model_selection_edits("gpt-5", None) == [
        replace_config_value("model", "gpt-5"),
        clear_config_value("model_reasoning_effort"),
    ]
    assert build_model_selection_edits("gpt-5", "high") == [
        replace_config_value("model", "gpt-5"),
        replace_config_value("model_reasoning_effort", "high"),
    ]


def test_build_service_tier_selection_edits_normalizes_known_tiers():
    assert build_service_tier_selection_edits(None) == [clear_config_value("service_tier")]
    assert build_service_tier_selection_edits(SERVICE_TIER_DEFAULT_REQUEST_VALUE) == [
        replace_config_value("service_tier", "default")
    ]
    assert build_service_tier_selection_edits("priority") == [replace_config_value("service_tier", "fast")]
    assert build_service_tier_selection_edits("fast") == [replace_config_value("service_tier", "fast")]
    assert build_service_tier_selection_edits("flex") == [replace_config_value("service_tier", "flex")]
    assert build_service_tier_selection_edits("custom") == [replace_config_value("service_tier", "custom")]


def test_build_windows_sandbox_mode_edits_writes_new_key_and_clears_legacy_flags():
    assert build_windows_sandbox_mode_edits(True) == [
        replace_config_value("windows.sandbox", "elevated"),
        clear_config_value("features.experimental_windows_sandbox"),
        clear_config_value("features.elevated_windows_sandbox"),
        clear_config_value("features.enable_experimental_windows_sandbox"),
    ]
    assert build_windows_sandbox_mode_edits(False)[0] == replace_config_value("windows.sandbox", "unelevated")


def test_build_feature_enabled_edit_clears_default_false_disabled_features():
    feature_defaults = {"new_feature": False, "stable_feature": True}

    assert build_feature_enabled_edit("new_feature", False, feature_defaults=feature_defaults) == clear_config_value(
        "features.new_feature"
    )
    assert build_feature_enabled_edit("new_feature", True, feature_defaults=feature_defaults) == replace_config_value(
        "features.new_feature", True
    )
    assert build_feature_enabled_edit("stable_feature", False, feature_defaults=feature_defaults) == replace_config_value(
        "features.stable_feature", False
    )


def test_build_feature_enabled_edit_uses_rust_feature_defaults_without_injection():
    assert FEATURE_DEFAULTS["memories"] is False
    assert FEATURE_DEFAULTS["guardian_approval"] is True

    assert build_feature_enabled_edit("memories", False) == clear_config_value("features.memories")
    assert build_feature_enabled_edit("guardian_approval", False) == replace_config_value(
        "features.guardian_approval", False
    )


def test_build_feature_enabled_edit_accepts_rust_feature_spec_shape():
    @dataclass(frozen=True)
    class FeatureSpec:
        key: str
        default_enabled: bool

    feature_defaults = [FeatureSpec("experimental_model", False)]

    assert build_feature_enabled_edit(
        "experimental_model",
        False,
        feature_defaults=feature_defaults,
    ) == clear_config_value("features.experimental_model")


def test_build_memory_and_oss_provider_edits():
    assert build_memory_settings_edits(True, False) == [
        replace_config_value("memories.use_memories", True),
        replace_config_value("memories.generate_memories", False),
    ]
    assert build_oss_provider_edit("ollama") == replace_config_value("oss_provider", "ollama")


class FakeRequestHandle:
    def __init__(self, response="ok"):
        self.response = response
        self.requests = []

    async def request_typed(self, request):
        self.requests.append(request)
        return self.response


@pytest.mark.asyncio
async def test_write_config_batch_sends_config_batch_write_request():
    handle = FakeRequestHandle()
    edit = replace_config_value("model", "gpt-5")

    assert await write_config_batch(handle, [edit]) == "ok"

    request = handle.requests[0]
    assert request.kind == "ConfigBatchWrite"
    assert request.id.startswith("tui-config-write-")
    assert request.params == ConfigBatchWriteParams(edits=[edit])


@pytest.mark.asyncio
async def test_write_trusted_project_uses_trusted_project_edit():
    handle = FakeRequestHandle()

    await write_trusted_project(handle, "/workspace/team.project")

    assert handle.requests[0].params.edits == [trusted_project_edit("/workspace/team.project")]


@pytest.mark.asyncio
async def test_read_effective_config_sends_config_read_request():
    handle = FakeRequestHandle(response={"model": "gpt-5"})

    assert await read_effective_config(handle, "/workspace") == {"model": "gpt-5"}

    request = handle.requests[0]
    assert request.kind == "ConfigRead"
    assert request.id.startswith("tui-config-read-")
    assert request.params == ConfigReadParams(include_layers=False, cwd="/workspace")


@pytest.mark.asyncio
async def test_write_skill_enabled_sends_skills_config_write_request():
    handle = FakeRequestHandle()

    await write_skill_enabled(handle, "/skills/demo", True)

    request = handle.requests[0]
    assert request.kind == "SkillsConfigWrite"
    assert request.id.startswith("tui-skill-config-write-")
    assert request.params == SkillsConfigWriteParams(path="/skills/demo", name=None, enabled=True)
