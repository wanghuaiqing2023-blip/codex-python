"""Config service helpers ported from ``app-server/src/config_manager_service.rs``."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pycodex.app_server_protocol import (
    ConfigBatchWriteParams,
    ConfigEdit,
    ConfigLayerMetadata,
    ConfigLayerSource,
    ConfigReadParams,
    ConfigReadResponse,
    ConfigValueWriteParams,
    ConfigWriteErrorCode,
    ConfigWriteResponse,
    MergeStrategy,
    OverriddenMetadata,
    WriteStatus,
)
from pycodex.config import ConfigLayerEntry, ConfigLayerStack, ConfigLayerStackOrdering

JsonValue = Any


class ConfigManagerError(Exception):
    def __init__(self, message: str, *, code: ConfigWriteErrorCode | str | None = None) -> None:
        super().__init__(message)
        self.code = ConfigWriteErrorCode.parse(code) if code is not None else None

    @classmethod
    def write(cls, code: ConfigWriteErrorCode | str, message: str) -> "ConfigManagerError":
        return cls(message, code=code)

    def write_error_code(self) -> ConfigWriteErrorCode | None:
        return self.code


@dataclass(frozen=True)
class ConfigManagerService:
    """Small facade for Rust's service extension methods on ``ConfigManager``."""

    codex_home: Path
    layers: ConfigLayerStack

    async def read(self, params: ConfigReadParams) -> ConfigReadResponse:
        effective = self.layers.effective_config()
        return ConfigReadResponse(
            config=deepcopy(effective),
            origins=_protocol_origins(self.layers.origins()),
            layers=(
                tuple(
                    _protocol_layer(layer)
                    for layer in self.layers.get_layers(
                        ConfigLayerStackOrdering.HIGHEST_PRECEDENCE_FIRST,
                        True,
                    )
                )
                if params.include_layers
                else None
            ),
        )

    async def read_requirements(self) -> Any | None:
        requirements_toml = getattr(self.layers, "requirements_toml", None)
        if _is_empty_requirement(requirements_toml):
            return None
        return requirements_toml

    async def write_value(self, params: ConfigValueWriteParams) -> ConfigWriteResponse:
        return await self.apply_edits(params.file_path, params.expected_version, [(params.key_path, params.value, params.merge_strategy)])

    async def batch_write(self, params: ConfigBatchWriteParams) -> ConfigWriteResponse:
        return await self.apply_edits(
            params.file_path,
            params.expected_version,
            [(edit.key_path, edit.value, edit.merge_strategy) for edit in params.edits],
        )

    async def apply_edits(
        self,
        file_path: str | None,
        expected_version: str | None,
        edits: Sequence[tuple[str, JsonValue, MergeStrategy | str]],
    ) -> ConfigWriteResponse:
        allowed_path = Path(self.codex_home) / "config.toml"
        provided_path = Path(file_path) if file_path is not None else allowed_path
        if not paths_match(allowed_path, provided_path):
            raise ConfigManagerError.write(
                ConfigWriteErrorCode.CONFIG_LAYER_READONLY,
                "Only writes to the user config are allowed",
            )

        user_layer = self.layers.get_active_user_layer() or create_empty_user_layer(allowed_path)
        if expected_version is not None and expected_version != user_layer.version:
            raise ConfigManagerError.write(
                ConfigWriteErrorCode.CONFIG_VERSION_CONFLICT,
                "Configuration was modified since last read. Fetch latest version and retry.",
            )

        user_config = deepcopy(dict(user_layer.config))
        parsed_segments: list[list[str]] = []
        for key_path, value, strategy in edits:
            segments = parse_key_path(key_path)
            _reject_legacy_profile_write(segments, value)
            parsed_value = parse_value(value)
            apply_merge(user_config, segments, parsed_value, MergeStrategy.parse(strategy))
            parsed_segments.append(segments)

        updated_layers = self.layers.with_user_config(provided_path, user_config)
        effective = updated_layers.effective_config()
        overridden = first_overridden_edit(updated_layers, effective, parsed_segments)
        return ConfigWriteResponse(
            status=WriteStatus.OK_OVERRIDDEN if overridden is not None else WriteStatus.OK,
            version=updated_layers.get_active_user_layer().version,  # type: ignore[union-attr]
            file_path=provided_path,
            overridden_metadata=overridden,
        )


def create_empty_user_layer(config_toml: Path | str) -> ConfigLayerEntry:
    return ConfigLayerEntry.new(_state_user_source(config_toml), {})


def parse_value(value: JsonValue) -> JsonValue | None:
    if value is None:
        return None
    return deepcopy(value)


def parse_key_path(path: str) -> list[str]:
    if not path.strip():
        raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "keyPath must not be empty")

    segments: list[str] = []
    segment = ""
    quoted = False
    index = 0
    while index < len(path):
        ch = path[index]
        if ch == '"' and not quoted and not segment:
            quoted = True
        elif ch == '"' and quoted:
            quoted = False
        elif ch == "\\" and quoted:
            index += 1
            if index >= len(path):
                raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "unterminated escape in keyPath")
            segment += path[index]
        elif ch == "." and not quoted:
            if not segment:
                raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "keyPath segments must not be empty")
            segments.append(segment)
            segment = ""
        elif ch == '"':
            raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "invalid quoted keyPath segment")
        else:
            segment += ch
        index += 1

    if quoted:
        raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "unterminated quoted keyPath segment")
    if not segment:
        raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "keyPath segments must not be empty")
    segments.append(segment)
    return segments


def apply_merge(root: dict[str, JsonValue], segments: Sequence[str], value: JsonValue | None, strategy: MergeStrategy | str) -> bool:
    if value is None:
        return clear_path(root, segments)
    if not segments:
        raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "keyPath must not be empty")

    current: JsonValue = root
    for segment in segments[:-1]:
        if not isinstance(current, dict):
            raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "cannot set value on non-table parent")
        next_value = current.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
            current[segment] = next_value
        current = next_value

    if not isinstance(current, dict):
        raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "cannot set value on non-table parent")

    last = segments[-1]
    old_value = deepcopy(current.get(last))
    parsed_strategy = MergeStrategy.parse(strategy)
    if parsed_strategy is MergeStrategy.UPSERT and isinstance(current.get(last), dict) and isinstance(value, Mapping):
        merged = deepcopy(current[last])
        merge_toml_values(merged, dict(value))
        current[last] = merged
    else:
        current[last] = deepcopy(value)
    return old_value != current.get(last)


def clear_path(root: dict[str, JsonValue], segments: Sequence[str]) -> bool:
    if not segments:
        raise ConfigManagerError.write(ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR, "keyPath must not be empty")
    current: JsonValue = root
    for segment in segments[:-1]:
        if not isinstance(current, dict) or segment not in current:
            return False
        current = current[segment]
    if not isinstance(current, dict):
        return False
    return current.pop(segments[-1], None) is not None


def merge_toml_values(base: dict[str, JsonValue], overlay: Mapping[str, JsonValue]) -> None:
    for key, value in overlay.items():
        if isinstance(base.get(key), dict) and isinstance(value, Mapping):
            merge_toml_values(base[key], value)  # type: ignore[arg-type]
        else:
            base[key] = deepcopy(value)


def value_at_path(root: JsonValue, segments: Sequence[str]) -> JsonValue | None:
    current = root
    for segment in segments:
        if isinstance(current, Mapping):
            if segment not in current:
                return None
            current = current[segment]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def override_message(layer: Any) -> str:
    source_type = getattr(layer, "type", None) or getattr(layer, "variant", None)
    if source_type == "mdm":
        return f"Overridden by managed policy (MDM): {getattr(layer, 'domain')}"
    if source_type == "system":
        return f"Overridden by managed config (system): {getattr(layer, 'file')}"
    if source_type == "project":
        return f"Overridden by project config: {getattr(layer, 'dot_codex_folder')}/config.toml"
    if source_type == "session_flags":
        return "Overridden by session flags"
    if source_type == "user":
        return f"Overridden by user config: {getattr(layer, 'file')}"
    if source_type == "legacy_managed_config_toml_from_file":
        return f"Overridden by legacy managed_config.toml: {getattr(layer, 'file')}"
    if source_type == "legacy_managed_config_toml_from_mdm":
        return "Overridden by legacy managed configuration from MDM"
    return f"Overridden by {source_type}"


def compute_override_metadata(
    layers: ConfigLayerStack,
    effective: Mapping[str, JsonValue],
    segments: Sequence[str],
) -> OverriddenMetadata | None:
    user_layer = layers.get_active_user_layer()
    if user_layer is None:
        return None
    user_value = value_at_path(user_layer.config, segments)
    effective_value = value_at_path(effective, segments)
    if user_value is not None and user_value == effective_value:
        return None
    if user_value is None and effective_value is None:
        return None
    overriding_layer = find_effective_layer(layers, segments)
    if overriding_layer is None:
        return None
    protocol_layer = _protocol_metadata(overriding_layer.metadata())
    return OverriddenMetadata(
        message=override_message(overriding_layer.name),
        overriding_layer=protocol_layer,
        effective_value=deepcopy(effective_value),
    )


def first_overridden_edit(
    layers: ConfigLayerStack,
    effective: Mapping[str, JsonValue],
    edits: Sequence[Sequence[str]],
) -> OverriddenMetadata | None:
    for segments in edits:
        metadata = compute_override_metadata(layers, effective, segments)
        if metadata is not None:
            return metadata
    return None


def find_effective_layer(layers: ConfigLayerStack, segments: Sequence[str]) -> ConfigLayerEntry | None:
    for layer in layers.layers_high_to_low():
        if value_at_path(layer.config, segments) is not None:
            return layer
    return None


def paths_match(expected: Path | str, provided: Path | str) -> bool:
    return Path(expected).resolve() == Path(provided).resolve()


def _reject_legacy_profile_write(segments: Sequence[str], value: JsonValue) -> None:
    if value is None:
        return
    if list(segments) == ["profile"]:
        raise ConfigManagerError.write(
            ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR,
            "`profile` is a legacy config selector and can no longer be written; use `--profile <name>` with `<name>.config.toml` instead",
        )
    if segments and segments[0] == "profiles":
        raise ConfigManagerError.write(
            ConfigWriteErrorCode.CONFIG_VALIDATION_ERROR,
            "`profiles` contains legacy config profile tables and can no longer be written; use `--profile <name>` with `<name>.config.toml` instead",
        )


def _protocol_origins(origins: Mapping[str, Any]) -> dict[str, ConfigLayerMetadata]:
    return {key: _protocol_metadata(value) for key, value in origins.items()}


def _protocol_metadata(metadata: Any) -> ConfigLayerMetadata:
    return ConfigLayerMetadata(name=_protocol_source(metadata.name), version=metadata.version)


def _protocol_layer(layer: ConfigLayerEntry) -> Any:
    return {
        "name": _protocol_source(layer.name).to_mapping(),
        "version": layer.version,
        "config": deepcopy(dict(layer.config)),
    }


def _protocol_source(source: Any) -> ConfigLayerSource:
    source_type = getattr(source, "type", None)
    if source_type == "user":
        return ConfigLayerSource.user(getattr(source, "file"), getattr(source, "profile", None))
    if source_type == "system":
        return ConfigLayerSource.system(getattr(source, "file"))
    if source_type == "project":
        return ConfigLayerSource.project(getattr(source, "dot_codex_folder"))
    if source_type == "session_flags":
        return ConfigLayerSource.session_flags()
    if source_type == "legacy_managed_config_toml_from_file":
        return ConfigLayerSource.legacy_managed_config_toml_from_file(getattr(source, "file"))
    if source_type == "legacy_managed_config_toml_from_mdm":
        return ConfigLayerSource.legacy_managed_config_toml_from_mdm()
    if source_type == "mdm":
        return ConfigLayerSource.mdm(getattr(source, "domain"), getattr(source, "key"))
    return ConfigLayerSource.system(Path.cwd() / "<unknown>")


def _state_user_source(config_toml: Path | str) -> Any:
    from pycodex.network_proxy import ConfigLayerSource as StateConfigLayerSource

    return StateConfigLayerSource.user(Path(config_toml), None)


def _is_empty_requirement(value: Any) -> bool:
    return value is None or value == {} or value == ()


__all__ = [
    "ConfigManagerError",
    "ConfigManagerService",
    "apply_merge",
    "clear_path",
    "compute_override_metadata",
    "create_empty_user_layer",
    "find_effective_layer",
    "first_overridden_edit",
    "merge_toml_values",
    "override_message",
    "parse_key_path",
    "parse_value",
    "paths_match",
    "value_at_path",
]
