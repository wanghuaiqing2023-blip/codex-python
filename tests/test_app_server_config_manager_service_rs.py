"""Parity tests for Rust ``app-server/src/config_manager_service.rs`` helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pycodex.app_server.config_manager_service import (
    ConfigManagerError,
    ConfigManagerService,
    apply_merge,
    clear_path,
    parse_key_path,
    value_at_path,
)
from pycodex.app_server_protocol import (
    ConfigBatchWriteParams,
    ConfigEdit,
    ConfigReadParams,
    ConfigValueWriteParams,
    ConfigWriteErrorCode,
    MergeStrategy,
    WriteStatus,
)
from pycodex.config import ConfigLayerEntry, ConfigLayerSource, ConfigLayerStack
from pycodex.core.config.edit import read_toml_mapping


def _stack(codex_home: Path, *layers: ConfigLayerEntry) -> ConfigLayerStack:
    if not layers:
        layers = (ConfigLayerEntry.new(ConfigLayerSource.user(codex_home / "config.toml"), {}),)
    return ConfigLayerStack.new(layers)


def test_parse_key_path_supports_bare_quoted_and_escaped_segments() -> None:
    # Rust crate/module/test: codex-app-server/src/config_manager_service.rs
    # parse_key_path; covers dotted, quoted, and escaped keyPath segments.
    assert parse_key_path("model_provider.openai.wire_api") == ["model_provider", "openai", "wire_api"]
    assert parse_key_path('"model.provider"."openai.api"') == ["model.provider", "openai.api"]
    assert parse_key_path('"quoted\\"name".value') == ['quoted"name', "value"]
    assert parse_key_path('"slash\\\\name".value') == ["slash\\name", "value"]


@pytest.mark.parametrize(
    ("key_path", "message"),
    [
        ("", "keyPath must not be empty"),
        ("model..provider", "keyPath segments must not be empty"),
        ('"model.provider', "unterminated quoted keyPath segment"),
        ('model"provider"', "invalid quoted keyPath segment"),
        ('"model.provider\\', "unterminated escape in keyPath"),
    ],
)
def test_parse_key_path_rejects_empty_and_malformed_segments(key_path: str, message: str) -> None:
    # Rust crate/module/test: codex-app-server/src/config_manager_service.rs
    # parse_key_path; mirrors Rust validation error branches.
    with pytest.raises(ConfigManagerError) as excinfo:
        parse_key_path(key_path)
    assert excinfo.value.write_error_code() is ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR
    assert str(excinfo.value) == message


def test_apply_merge_upsert_merges_tables_replace_overwrites() -> None:
    # Rust test: upsert_merges_tables_replace_overwrites.
    config = {"tools": {"web_search": {"enabled": True, "limit": 3}}}
    changed = apply_merge(
        config,
        ["tools", "web_search"],
        {"limit": 5, "allowed": True},
        MergeStrategy.UPSERT,
    )
    assert changed is True
    assert config["tools"]["web_search"] == {"enabled": True, "limit": 5, "allowed": True}

    changed = apply_merge(
        config,
        ["tools", "web_search"],
        {"enabled": False},
        MergeStrategy.REPLACE,
    )
    assert changed is True
    assert config["tools"]["web_search"] == {"enabled": False}


def test_clear_missing_nested_config_is_noop() -> None:
    # Rust test: clear_missing_nested_config_is_noop.
    config = {"model_provider": {"openai": {"wire_api": "responses"}}}
    assert clear_path(config, ["model_provider", "missing", "wire_api"]) is False
    assert clear_path(config, ["model_provider", "openai", "missing"]) is False
    assert config == {"model_provider": {"openai": {"wire_api": "responses"}}}


def test_value_at_path_reads_mapping_and_array_segments() -> None:
    # Rust helper: value_at_path; array traversal is used by override detection.
    config = {"tools": {"servers": [{"name": "alpha"}, {"name": "beta"}]}}
    assert value_at_path(config, ["tools", "servers", "1", "name"]) == "beta"
    assert value_at_path(config, ["tools", "servers", "bogus"]) is None
    assert value_at_path(config, ["tools", "servers", "9"]) is None


def test_write_value_rejects_legacy_profile_selector(tmp_path: Path) -> None:
    # Rust tests: write_value_rejects_legacy_profile_selector and
    # write_value_rejects_legacy_profile_table.
    service = ConfigManagerService(tmp_path, _stack(tmp_path))

    with pytest.raises(ConfigManagerError) as excinfo:
        asyncio.run(
            service.write_value(
                ConfigValueWriteParams(
                    key_path="profile",
                    value="dev",
                    merge_strategy=MergeStrategy.REPLACE,
                )
            )
        )
    assert excinfo.value.write_error_code() is ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR
    assert "`profile` is a legacy config selector" in str(excinfo.value)

    with pytest.raises(ConfigManagerError) as excinfo:
        asyncio.run(
            service.write_value(
                ConfigValueWriteParams(
                    key_path="profiles.dev.model",
                    value="gpt-5",
                    merge_strategy=MergeStrategy.REPLACE,
                )
            )
        )
    assert excinfo.value.write_error_code() is ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR
    assert "`profiles` contains legacy config profile tables" in str(excinfo.value)


def test_batch_write_rejects_legacy_profile_selector(tmp_path: Path) -> None:
    # Rust test: batch_write_rejects_legacy_profile_selector.
    service = ConfigManagerService(tmp_path, _stack(tmp_path))

    with pytest.raises(ConfigManagerError) as excinfo:
        asyncio.run(
            service.batch_write(
                ConfigBatchWriteParams(
                    edits=(
                        ConfigEdit(
                            key_path="profile",
                            value="dev",
                            merge_strategy=MergeStrategy.REPLACE,
                        ),
                    )
                )
            )
        )
    assert excinfo.value.write_error_code() is ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR


def test_version_conflict_rejected(tmp_path: Path) -> None:
    # Rust test: version_conflict_rejected.
    service = ConfigManagerService(tmp_path, _stack(tmp_path))

    with pytest.raises(ConfigManagerError) as excinfo:
        asyncio.run(
            service.write_value(
                ConfigValueWriteParams(
                    key_path="model",
                    value="gpt-5",
                    merge_strategy=MergeStrategy.REPLACE,
                    expected_version="stale",
                )
            )
        )
    assert excinfo.value.write_error_code() is ConfigWriteErrorCode.CONFIG_VERSION_CONFLICT


def test_write_value_defaults_to_user_config_path(tmp_path: Path) -> None:
    # Rust tests: write_value_defaults_to_user_config_path and
    # write_value_defaults_to_selected_user_config_path.
    user_layer = ConfigLayerEntry.new(ConfigLayerSource.user(tmp_path / "config.toml"), {"model": "old"})
    service = ConfigManagerService(tmp_path, _stack(tmp_path, user_layer))

    response = asyncio.run(
        service.write_value(
            ConfigValueWriteParams(
                key_path="model",
                value="gpt-5",
                merge_strategy=MergeStrategy.REPLACE,
            )
        )
    )

    assert response.status is WriteStatus.OK
    assert response.file_path == tmp_path / "config.toml"
    assert response.overridden_metadata is None


def test_batch_write_reloads_latest_user_config_and_persists_to_disk(tmp_path: Path) -> None:
    # Rust owner/test contract:
    # - ConfigManagerService::apply_edits reloads thread-agnostic layers for
    #   every write, then persists changed ConfigEdit values atomically.
    # - This prevents a long-lived TUI service from replacing unrelated config
    #   values written after its startup snapshot was created.
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'model = "external-model"\n\n[desktop]\nnotifications = true\n',
        encoding="utf-8",
    )
    stale_layer = ConfigLayerEntry.new(
        ConfigLayerSource.user(config_path),
        {"model": "startup-model"},
    )
    service = ConfigManagerService(tmp_path, _stack(tmp_path, stale_layer))

    response = asyncio.run(
        service.batch_write(
            ConfigBatchWriteParams(
                edits=(
                    ConfigEdit("model", "gpt-persisted", MergeStrategy.REPLACE),
                    ConfigEdit("model_reasoning_effort", "medium", MergeStrategy.REPLACE),
                )
            )
        )
    )

    persisted = read_toml_mapping(config_path)
    assert persisted["model"] == "gpt-persisted"
    assert persisted["model_reasoning_effort"] == "medium"
    assert persisted["desktop"] == {"notifications": True}
    assert response.file_path == config_path


def test_write_value_reports_override(tmp_path: Path) -> None:
    # Rust tests: write_value_reports_override and write_value_reports_managed_override.
    user_layer = ConfigLayerEntry.new(ConfigLayerSource.user(tmp_path / "config.toml"), {"model": "user"})
    project_layer = ConfigLayerEntry.new(ConfigLayerSource.project(tmp_path / ".codex"), {"model": "project"})
    service = ConfigManagerService(tmp_path, _stack(tmp_path, user_layer, project_layer))

    response = asyncio.run(
        service.write_value(
            ConfigValueWriteParams(
                key_path="model",
                value="new-user",
                merge_strategy=MergeStrategy.REPLACE,
            )
        )
    )

    assert response.status is WriteStatus.OK_OVERRIDDEN
    assert response.overridden_metadata is not None
    assert response.overridden_metadata.effective_value == "project"
    assert response.overridden_metadata.message == f"Overridden by project config: {tmp_path / '.codex'}/config.toml"


def test_read_honors_include_layers_and_reports_origins(tmp_path: Path) -> None:
    # Rust test: read_includes_origins_and_layers.
    user_layer = ConfigLayerEntry.new(ConfigLayerSource.user(tmp_path / "config.toml"), {"model": "user"})
    project_layer = ConfigLayerEntry.new(
        ConfigLayerSource.project(tmp_path / ".codex"),
        {"model": "project", "desktop": {"notifications": True}},
    )
    service = ConfigManagerService(tmp_path, _stack(tmp_path, user_layer, project_layer))

    without_layers = asyncio.run(service.read(ConfigReadParams(include_layers=False)))
    with_layers = asyncio.run(service.read(ConfigReadParams(include_layers=True)))

    assert without_layers.layers is None
    assert with_layers.layers is not None
    assert [layer.name.type for layer in with_layers.layers] == ["project", "user"]
    assert without_layers.config.to_mapping()["model"] == "project"
    assert without_layers.origins["model"].name.type == "project"
