from __future__ import annotations

from pycodex.tui.app.config_persistence import (
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
