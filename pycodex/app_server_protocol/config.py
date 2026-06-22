"""Config protocol types ported from ``protocol/v2/config.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    AutoCompactTokenLimitScope,
    ReasoningEffort,
    ReasoningSummary,
    Verbosity,
    WebSearchMode,
    WebSearchToolConfig,
)

from .shared import ApprovalsReviewer
from .shared import AskForApproval
from .shared import SandboxMode

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


@dataclass(frozen=True)
class ConfigLayerSource:
    type: str
    domain: str | None = None
    key: str | None = None
    file: Path | None = None
    profile: str | None = None
    dot_codex_folder: Path | None = None

    def __post_init__(self) -> None:
        if self.type not in {
            "mdm",
            "system",
            "user",
            "project",
            "sessionFlags",
            "legacyManagedConfigTomlFromFile",
            "legacyManagedConfigTomlFromMdm",
        }:
            raise ValueError(f"unknown config layer source type: {self.type}")
        object.__setattr__(self, "domain", _optional_str(self.domain, "domain"))
        object.__setattr__(self, "key", _optional_str(self.key, "key"))
        object.__setattr__(self, "file", _optional_absolute_path(self.file, "file"))
        object.__setattr__(self, "profile", _optional_str(self.profile, "profile"))
        object.__setattr__(
            self,
            "dot_codex_folder",
            _optional_absolute_path(self.dot_codex_folder, "dot_codex_folder"),
        )
        if self.type == "mdm":
            _require(self.domain, "domain")
            _require(self.key, "key")
        elif self.type in {"system", "legacyManagedConfigTomlFromFile"}:
            _require(self.file, "file")
        elif self.type == "user":
            _require(self.file, "file")
        elif self.type == "project":
            _require(self.dot_codex_folder, "dot_codex_folder")

    @classmethod
    def mdm(cls, domain: str, key: str) -> "ConfigLayerSource":
        return cls("mdm", domain=domain, key=key)

    @classmethod
    def system(cls, file: Path | str) -> "ConfigLayerSource":
        return cls("system", file=Path(file))

    @classmethod
    def user(cls, file: Path | str, profile: str | None = None) -> "ConfigLayerSource":
        return cls("user", file=Path(file), profile=profile)

    @classmethod
    def project(cls, dot_codex_folder: Path | str) -> "ConfigLayerSource":
        return cls("project", dot_codex_folder=Path(dot_codex_folder))

    @classmethod
    def session_flags(cls) -> "ConfigLayerSource":
        return cls("sessionFlags")

    @classmethod
    def legacy_managed_config_toml_from_file(cls, file: Path | str) -> "ConfigLayerSource":
        return cls("legacyManagedConfigTomlFromFile", file=Path(file))

    @classmethod
    def legacy_managed_config_toml_from_mdm(cls) -> "ConfigLayerSource":
        return cls("legacyManagedConfigTomlFromMdm")

    def precedence(self) -> int:
        if self.type == "mdm":
            return 0
        if self.type == "system":
            return 10
        if self.type == "user":
            return 21 if self.profile is not None else 20
        if self.type == "project":
            return 25
        if self.type == "sessionFlags":
            return 30
        if self.type == "legacyManagedConfigTomlFromFile":
            return 40
        return 50

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigLayerSource":
        data = _mapping(value, "ConfigLayerSource")
        source_type = _ensure_str(data["type"], "type")
        if source_type == "mdm":
            return cls.mdm(_ensure_str(data["domain"], "domain"), _ensure_str(data["key"], "key"))
        if source_type == "system":
            return cls.system(_ensure_str(data["file"], "file"))
        if source_type == "user":
            return cls.user(_ensure_str(data["file"], "file"), _optional_str(data.get("profile"), "profile"))
        if source_type == "project":
            folder = _pick(data, "dot_codex_folder", "dotCodexFolder")
            return cls.project(_ensure_str(folder, "dot_codex_folder"))
        if source_type == "sessionFlags":
            return cls.session_flags()
        if source_type == "legacyManagedConfigTomlFromFile":
            return cls.legacy_managed_config_toml_from_file(_ensure_str(data["file"], "file"))
        if source_type == "legacyManagedConfigTomlFromMdm":
            return cls.legacy_managed_config_toml_from_mdm()
        raise ValueError(f"unknown config layer source type: {source_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.domain is not None:
            result["domain"] = self.domain
        if self.key is not None:
            result["key"] = self.key
        if self.file is not None:
            result["file"] = str(self.file)
        if self.profile is not None:
            result["profile"] = self.profile
        if self.dot_codex_folder is not None:
            result["dot_codex_folder"] = str(self.dot_codex_folder)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = self.to_mapping()
        if "dot_codex_folder" in result:
            result["dotCodexFolder"] = result.pop("dot_codex_folder")
        return result


@dataclass(frozen=True)
class SandboxWorkspaceWrite:
    writable_roots: tuple[Path, ...] = ()
    network_access: bool = False
    exclude_tmpdir_env_var: bool = False
    exclude_slash_tmp: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "writable_roots", _path_tuple(self.writable_roots, "writable_roots"))
        object.__setattr__(self, "network_access", _ensure_bool(self.network_access, "network_access"))
        object.__setattr__(self, "exclude_tmpdir_env_var", _ensure_bool(self.exclude_tmpdir_env_var, "exclude_tmpdir_env_var"))
        object.__setattr__(self, "exclude_slash_tmp", _ensure_bool(self.exclude_slash_tmp, "exclude_slash_tmp"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "SandboxWorkspaceWrite":
        data = {} if value is None else _mapping(value, "SandboxWorkspaceWrite")
        return cls(
            writable_roots=_path_tuple(data.get("writable_roots", ()), "writable_roots"),
            network_access=_ensure_bool(data.get("network_access", False), "network_access"),
            exclude_tmpdir_env_var=_ensure_bool(data.get("exclude_tmpdir_env_var", False), "exclude_tmpdir_env_var"),
            exclude_slash_tmp=_ensure_bool(data.get("exclude_slash_tmp", False), "exclude_slash_tmp"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)


@dataclass(frozen=True)
class ToolsV2:
    web_search: JsonValue | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ToolsV2":
        data = _mapping(value, "ToolsV2")
        return cls(web_search=data.get("web_search"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"web_search": _serialize(self.web_search)}


@dataclass(frozen=True)
class AnalyticsConfig:
    enabled: bool | None = None
    additional: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _optional_bool(self.enabled, "enabled"))
        object.__setattr__(self, "additional", dict(self.additional or {}))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AnalyticsConfig":
        data = dict(_mapping(value, "AnalyticsConfig"))
        enabled = data.pop("enabled", None)
        return cls(enabled=_optional_bool(enabled, "enabled"), additional=data)

    def to_mapping(self) -> dict[str, JsonValue]:
        result = dict(self.additional or {})
        if self.enabled is not None:
            result["enabled"] = self.enabled
        return result


class AppToolApproval(_StringEnum):
    AUTO = "auto"
    PROMPT = "prompt"
    APPROVE = "approve"


@dataclass(frozen=True)
class AppsDefaultConfig:
    enabled: bool = True
    destructive_enabled: bool = True
    open_world_enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _ensure_bool(self.enabled, "enabled"))
        object.__setattr__(self, "destructive_enabled", _ensure_bool(self.destructive_enabled, "destructive_enabled"))
        object.__setattr__(self, "open_world_enabled", _ensure_bool(self.open_world_enabled, "open_world_enabled"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "AppsDefaultConfig":
        data = {} if value is None else _mapping(value, "AppsDefaultConfig")
        return cls(
            enabled=_ensure_bool(data.get("enabled", True), "enabled"),
            destructive_enabled=_ensure_bool(data.get("destructive_enabled", True), "destructive_enabled"),
            open_world_enabled=_ensure_bool(data.get("open_world_enabled", True), "open_world_enabled"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)


@dataclass(frozen=True)
class AppToolConfig:
    enabled: bool | None = None
    approval_mode: AppToolApproval | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _optional_bool(self.enabled, "enabled"))
        object.__setattr__(
            self,
            "approval_mode",
            AppToolApproval.parse(self.approval_mode) if self.approval_mode is not None else None,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "AppToolConfig":
        data = {} if value is None else _mapping(value, "AppToolConfig")
        return cls(enabled=data.get("enabled"), approval_mode=data.get("approval_mode"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)


@dataclass(frozen=True)
class AppToolsConfig:
    tools: dict[str, AppToolConfig] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tools",
            {str(name): _app_tool_config(value) for name, value in (self.tools or {}).items()},
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "AppToolsConfig":
        data = {} if value is None else _mapping(value, "AppToolsConfig")
        return cls(tools={str(name): _app_tool_config(config) for name, config in data.items()})

    def to_mapping(self) -> dict[str, JsonValue]:
        return {name: config.to_mapping() for name, config in (self.tools or {}).items()}


@dataclass(frozen=True)
class AppConfig:
    enabled: bool = True
    destructive_enabled: bool | None = None
    open_world_enabled: bool | None = None
    default_tools_approval_mode: AppToolApproval | str | None = None
    default_tools_enabled: bool | None = None
    tools: AppToolsConfig | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _ensure_bool(self.enabled, "enabled"))
        object.__setattr__(self, "destructive_enabled", _optional_bool(self.destructive_enabled, "destructive_enabled"))
        object.__setattr__(self, "open_world_enabled", _optional_bool(self.open_world_enabled, "open_world_enabled"))
        object.__setattr__(
            self,
            "default_tools_approval_mode",
            AppToolApproval.parse(self.default_tools_approval_mode)
            if self.default_tools_approval_mode is not None
            else None,
        )
        object.__setattr__(self, "default_tools_enabled", _optional_bool(self.default_tools_enabled, "default_tools_enabled"))
        object.__setattr__(self, "tools", _app_tools_config(self.tools) if self.tools is not None else None)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "AppConfig":
        data = {} if value is None else _mapping(value, "AppConfig")
        return cls(
            enabled=data.get("enabled", True),
            destructive_enabled=data.get("destructive_enabled"),
            open_world_enabled=data.get("open_world_enabled"),
            default_tools_approval_mode=data.get("default_tools_approval_mode"),
            default_tools_enabled=data.get("default_tools_enabled"),
            tools=data.get("tools"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)


@dataclass(frozen=True)
class AppsConfig:
    default: AppsDefaultConfig | Mapping[str, JsonValue] | None = None
    apps: dict[str, AppConfig] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "default", _apps_default(self.default) if self.default is not None else None)
        object.__setattr__(
            self,
            "apps",
            {str(name): _app_config(config) for name, config in (self.apps or {}).items()},
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "AppsConfig":
        data = dict({} if value is None else _mapping(value, "AppsConfig"))
        default = data.pop("_default", None)
        return cls(default=default, apps={str(name): _app_config(config) for name, config in data.items()})

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        if self.default is not None:
            result["_default"] = self.default.to_mapping()
        result.update({name: config.to_mapping() for name, config in (self.apps or {}).items()})
        return result


@dataclass(frozen=True)
class ForcedChatgptWorkspaceIds:
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _str_tuple(self.values, "values"))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ForcedChatgptWorkspaceIds":
        if isinstance(value, str):
            return cls((value,))
        return cls(_str_tuple(value, "forced_chatgpt_workspace_id"))

    def into_vec(self) -> list[str]:
        return list(self.values)

    def to_mapping(self) -> JsonValue:
        if len(self.values) == 1:
            return self.values[0]
        return list(self.values)


class ForcedLoginMethod(_StringEnum):
    API_KEY = "api_key"
    CHATGPT = "chatgpt"
    CHATGPT_AUTH_TOKENS = "chatgpt_auth_tokens"
    AGENT_IDENTITY = "agent_identity"


@dataclass(frozen=True)
class Config:
    model: str | None = None
    review_model: str | None = None
    model_context_window: int | None = None
    model_auto_compact_token_limit: int | None = None
    model_auto_compact_token_limit_scope: AutoCompactTokenLimitScope | str | None = None
    model_provider: str | None = None
    approval_policy: AskForApproval | JsonValue | None = None
    approvals_reviewer: ApprovalsReviewer | str | None = None
    sandbox_mode: SandboxMode | str | None = None
    sandbox_workspace_write: SandboxWorkspaceWrite | Mapping[str, JsonValue] | None = None
    forced_chatgpt_workspace_id: ForcedChatgptWorkspaceIds | str | Iterable[str] | None = None
    forced_login_method: ForcedLoginMethod | str | None = None
    web_search: WebSearchMode | str | None = None
    tools: ToolsV2 | Mapping[str, JsonValue] | None = None
    instructions: str | None = None
    developer_instructions: str | None = None
    compact_prompt: str | None = None
    model_reasoning_effort: ReasoningEffort | str | None = None
    model_reasoning_summary: ReasoningSummary | str | None = None
    model_verbosity: Verbosity | str | None = None
    service_tier: str | None = None
    analytics: AnalyticsConfig | Mapping[str, JsonValue] | None = None
    apps: AppsConfig | Mapping[str, JsonValue] | None = None
    desktop: dict[str, JsonValue] | None = None
    additional: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_auto_compact_token_limit_scope", _optional_enum(self.model_auto_compact_token_limit_scope, AutoCompactTokenLimitScope, "model_auto_compact_token_limit_scope"))
        object.__setattr__(self, "approval_policy", AskForApproval.from_mapping(self.approval_policy) if self.approval_policy is not None else None)
        object.__setattr__(self, "approvals_reviewer", ApprovalsReviewer.parse(self.approvals_reviewer) if self.approvals_reviewer is not None else None)
        object.__setattr__(self, "sandbox_mode", SandboxMode.parse(self.sandbox_mode) if self.sandbox_mode is not None else None)
        object.__setattr__(self, "sandbox_workspace_write", SandboxWorkspaceWrite.from_mapping(self.sandbox_workspace_write) if isinstance(self.sandbox_workspace_write, Mapping) else self.sandbox_workspace_write)
        object.__setattr__(self, "forced_chatgpt_workspace_id", ForcedChatgptWorkspaceIds.from_mapping(self.forced_chatgpt_workspace_id) if self.forced_chatgpt_workspace_id is not None and not isinstance(self.forced_chatgpt_workspace_id, ForcedChatgptWorkspaceIds) else self.forced_chatgpt_workspace_id)
        object.__setattr__(self, "forced_login_method", ForcedLoginMethod.parse(self.forced_login_method) if self.forced_login_method is not None else None)
        object.__setattr__(self, "web_search", _optional_enum(self.web_search, WebSearchMode, "web_search"))
        object.__setattr__(self, "tools", ToolsV2.from_mapping(self.tools) if isinstance(self.tools, Mapping) else self.tools)
        object.__setattr__(self, "model_reasoning_effort", _optional_enum(self.model_reasoning_effort, ReasoningEffort, "model_reasoning_effort"))
        object.__setattr__(self, "model_reasoning_summary", _optional_enum(self.model_reasoning_summary, ReasoningSummary, "model_reasoning_summary"))
        object.__setattr__(self, "model_verbosity", _optional_enum(self.model_verbosity, Verbosity, "model_verbosity"))
        object.__setattr__(self, "analytics", AnalyticsConfig.from_mapping(self.analytics) if isinstance(self.analytics, Mapping) else self.analytics)
        object.__setattr__(self, "apps", AppsConfig.from_mapping(self.apps) if isinstance(self.apps, Mapping) else self.apps)
        object.__setattr__(self, "desktop", dict(self.desktop or {}) if self.desktop is not None else None)
        object.__setattr__(self, "additional", dict(self.additional or {}))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Config":
        data = dict(_mapping(value, "Config"))
        known = {field.name for field in fields(cls)} - {"additional"}
        kwargs = {name: data.pop(name) for name in list(data) if name in known}
        kwargs["additional"] = data
        return cls(**kwargs)

    def to_mapping(self) -> dict[str, JsonValue]:
        result = dict(self.additional or {})
        result.update(_to_mapping(self, skip={"additional"}))
        return {key: value for key, value in result.items() if value is not None}


@dataclass(frozen=True)
class ConfigLayerMetadata:
    name: ConfigLayerSource | Mapping[str, JsonValue]
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _layer_source(self.name))
        object.__setattr__(self, "version", _ensure_str(self.version, "version"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigLayerMetadata":
        data = _mapping(value, "ConfigLayerMetadata")
        return cls(name=ConfigLayerSource.from_mapping(data["name"]), version=_ensure_str(data["version"], "version"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"name": self.name.to_mapping(), "version": self.version}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"name": self.name.to_camel_mapping(), "version": self.version}


@dataclass(frozen=True)
class ConfigLayer:
    name: ConfigLayerSource | Mapping[str, JsonValue]
    version: str
    config: JsonValue
    disabled_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _layer_source(self.name))
        object.__setattr__(self, "version", _ensure_str(self.version, "version"))
        object.__setattr__(self, "disabled_reason", _optional_str(self.disabled_reason, "disabled_reason"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigLayer":
        data = _mapping(value, "ConfigLayer")
        return cls(
            name=ConfigLayerSource.from_mapping(data["name"]),
            version=_ensure_str(data["version"], "version"),
            config=data["config"],
            disabled_reason=_optional_str(_pick(data, "disabled_reason", "disabledReason"), "disabled_reason"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"name": self.name.to_mapping(), "version": self.version, "config": self.config}
        if self.disabled_reason is not None:
            result["disabled_reason"] = self.disabled_reason
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"name": self.name.to_camel_mapping(), "version": self.version, "config": self.config}
        if self.disabled_reason is not None:
            result["disabledReason"] = self.disabled_reason
        return result


class MergeStrategy(_StringEnum):
    REPLACE = "replace"
    UPSERT = "upsert"


class WriteStatus(_StringEnum):
    OK = "ok"
    OK_OVERRIDDEN = "okOverridden"


@dataclass(frozen=True)
class OverriddenMetadata:
    message: str
    overriding_layer: ConfigLayerMetadata | Mapping[str, JsonValue]
    effective_value: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))
        object.__setattr__(self, "overriding_layer", _layer_metadata(self.overriding_layer))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "OverriddenMetadata":
        data = _mapping(value, "OverriddenMetadata")
        return cls(
            message=_ensure_str(data["message"], "message"),
            overriding_layer=ConfigLayerMetadata.from_mapping(_pick(data, "overriding_layer", "overridingLayer")),
            effective_value=_pick(data, "effective_value", "effectiveValue"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "message": self.message,
            "overriding_layer": self.overriding_layer.to_mapping(),
            "effective_value": self.effective_value,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "message": self.message,
            "overridingLayer": self.overriding_layer.to_camel_mapping(),
            "effectiveValue": self.effective_value,
        }


@dataclass(frozen=True)
class ConfigWriteResponse:
    status: WriteStatus | str
    version: str
    file_path: Path | str
    overridden_metadata: OverriddenMetadata | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", WriteStatus.parse(self.status))
        object.__setattr__(self, "version", _ensure_str(self.version, "version"))
        object.__setattr__(self, "file_path", _absolute_path(self.file_path, "file_path"))
        object.__setattr__(self, "overridden_metadata", _overridden(self.overridden_metadata) if self.overridden_metadata is not None else None)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigWriteResponse":
        data = _mapping(value, "ConfigWriteResponse")
        return cls(
            status=WriteStatus.parse(data["status"]),
            version=_ensure_str(data["version"], "version"),
            file_path=_ensure_str(_pick(data, "file_path", "filePath"), "file_path"),
            overridden_metadata=_overridden(_pick(data, "overridden_metadata", "overriddenMetadata")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


class ConfigWriteErrorCode(_StringEnum):
    CONFIG_LAYER_READONLY = "configLayerReadonly"
    CONFIG_VERSION_CONFLICT = "configVersionConflict"
    CONFIG_VALIDATION_ERROR = "configValidationError"
    CONFIG_PATH_NOT_FOUND = "configPathNotFound"
    CONFIG_SCHEMA_UNKNOWN_KEY = "configSchemaUnknownKey"
    USER_LAYER_NOT_FOUND = "userLayerNotFound"


@dataclass(frozen=True)
class ConfigReadParams:
    include_layers: bool = False
    cwd: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "include_layers", _ensure_bool(self.include_layers, "include_layers"))
        object.__setattr__(self, "cwd", _optional_str(self.cwd, "cwd"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ConfigReadParams":
        data = {} if value is None else _mapping(value, "ConfigReadParams")
        return cls(
            include_layers=_ensure_bool(_pick(data, "include_layers", "includeLayers", default=False), "include_layers"),
            cwd=_optional_str(data.get("cwd"), "cwd"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"cwd": self.cwd}
        if self.include_layers:
            result["include_layers"] = True
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"cwd": self.cwd}
        if self.include_layers:
            result["includeLayers"] = True
        return result


@dataclass(frozen=True)
class ConfigReadResponse:
    config: Config | Mapping[str, JsonValue]
    origins: dict[str, ConfigLayerMetadata | Mapping[str, JsonValue]]
    layers: tuple[ConfigLayer, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "config", Config.from_mapping(self.config) if isinstance(self.config, Mapping) else self.config)
        object.__setattr__(self, "origins", {str(k): _layer_metadata(v) for k, v in self.origins.items()})
        if self.layers is not None:
            object.__setattr__(self, "layers", tuple(_config_layer(layer) for layer in self.layers))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigReadResponse":
        data = _mapping(value, "ConfigReadResponse")
        return cls(
            config=Config.from_mapping(data["config"]),
            origins={str(k): ConfigLayerMetadata.from_mapping(v) for k, v in _mapping(data["origins"], "origins").items()},
            layers=tuple(ConfigLayer.from_mapping(item) for item in data["layers"]) if data.get("layers") is not None else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"config": self.config.to_mapping(), "origins": {k: v.to_mapping() for k, v in self.origins.items()}}
        if self.layers is not None:
            result["layers"] = [layer.to_mapping() for layer in self.layers]
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"config": self.config.to_mapping(), "origins": {k: v.to_camel_mapping() for k, v in self.origins.items()}}
        if self.layers is not None:
            result["layers"] = [layer.to_camel_mapping() for layer in self.layers]
        return result


@dataclass(frozen=True)
class ComputerUseRequirements:
    allow_locked_computer_use: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ComputerUseRequirements":
        data = _mapping(value, "ComputerUseRequirements")
        return cls(allow_locked_computer_use=_optional_bool(_pick(data, "allow_locked_computer_use", "allowLockedComputerUse"), "allow_locked_computer_use"))


@dataclass(frozen=True)
class ConfiguredHookHandler:
    type: str
    command: str | None = None
    command_windows: str | None = None
    timeout_sec: int | None = None
    async_: bool = False
    status_message: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfiguredHookHandler":
        data = _mapping(value, "ConfiguredHookHandler")
        return cls(
            type=_ensure_str(data["type"], "type"),
            command=_optional_str(data.get("command"), "command"),
            command_windows=_optional_str(_pick(data, "command_windows", "commandWindows"), "command_windows"),
            timeout_sec=_optional_u64(_pick(data, "timeout_sec", "timeoutSec"), "timeout_sec"),
            async_=_ensure_bool(_pick(data, "async", "async_", default=False), "async"),
            status_message=_optional_str(_pick(data, "status_message", "statusMessage"), "status_message"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {
            "type": self.type,
            "command": self.command,
            "command_windows": self.command_windows,
            "timeout_sec": self.timeout_sec,
            "async": self.async_,
            "status_message": self.status_message,
        }
        return {k: v for k, v in result.items() if v is not None}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {
            "type": self.type,
            "command": self.command,
            "commandWindows": self.command_windows,
            "timeoutSec": self.timeout_sec,
            "async": self.async_,
            "statusMessage": self.status_message,
        }
        return {k: v for k, v in result.items() if v is not None}


@dataclass(frozen=True)
class ConfiguredHookMatcherGroup:
    matcher: str | None
    hooks: tuple[ConfiguredHookHandler, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfiguredHookMatcherGroup":
        data = _mapping(value, "ConfiguredHookMatcherGroup")
        return cls(
            matcher=_optional_str(data.get("matcher"), "matcher"),
            hooks=tuple(ConfiguredHookHandler.from_mapping(item) for item in _list(data.get("hooks", ()), "hooks")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"matcher": self.matcher, "hooks": [hook.to_mapping() for hook in self.hooks]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"matcher": self.matcher, "hooks": [hook.to_camel_mapping() for hook in self.hooks]}


@dataclass(frozen=True)
class ManagedHooksRequirements:
    managed_dir: Path | None = None
    windows_managed_dir: Path | None = None
    pre_tool_use: tuple[ConfiguredHookMatcherGroup, ...] = ()
    permission_request: tuple[ConfiguredHookMatcherGroup, ...] = ()
    post_tool_use: tuple[ConfiguredHookMatcherGroup, ...] = ()
    pre_compact: tuple[ConfiguredHookMatcherGroup, ...] = ()
    post_compact: tuple[ConfiguredHookMatcherGroup, ...] = ()
    session_start: tuple[ConfiguredHookMatcherGroup, ...] = ()
    user_prompt_submit: tuple[ConfiguredHookMatcherGroup, ...] = ()
    subagent_start: tuple[ConfiguredHookMatcherGroup, ...] = ()
    subagent_stop: tuple[ConfiguredHookMatcherGroup, ...] = ()
    stop: tuple[ConfiguredHookMatcherGroup, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ManagedHooksRequirements":
        data = _mapping(value, "ManagedHooksRequirements")
        return cls(
            managed_dir=_optional_path(_pick(data, "managed_dir", "managedDir"), "managed_dir"),
            windows_managed_dir=_optional_path(_pick(data, "windows_managed_dir", "windowsManagedDir"), "windows_managed_dir"),
            pre_tool_use=_hook_groups(_pick(data, "pre_tool_use", "PreToolUse", default=())),
            permission_request=_hook_groups(_pick(data, "permission_request", "PermissionRequest", default=())),
            post_tool_use=_hook_groups(_pick(data, "post_tool_use", "PostToolUse", default=())),
            pre_compact=_hook_groups(_pick(data, "pre_compact", "PreCompact", default=())),
            post_compact=_hook_groups(_pick(data, "post_compact", "PostCompact", default=())),
            session_start=_hook_groups(_pick(data, "session_start", "SessionStart", default=())),
            user_prompt_submit=_hook_groups(_pick(data, "user_prompt_submit", "UserPromptSubmit", default=())),
            subagent_start=_hook_groups(_pick(data, "subagent_start", "SubagentStart", default=())),
            subagent_stop=_hook_groups(_pick(data, "subagent_stop", "SubagentStop", default=())),
            stop=_hook_groups(_pick(data, "stop", "Stop", default=())),
        )


class NetworkDomainPermission(_StringEnum):
    ALLOW = "allow"
    DENY = "deny"


class NetworkUnixSocketPermission(_StringEnum):
    ALLOW = "allow"
    NONE = "none"


class ResidencyRequirement(_StringEnum):
    US = "us"


@dataclass(frozen=True)
class NetworkRequirements:
    enabled: bool | None = None
    http_port: int | None = None
    socks_port: int | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    domains: dict[str, NetworkDomainPermission] | None = None
    managed_allowed_domains_only: bool | None = None
    allowed_domains: tuple[str, ...] | None = None
    denied_domains: tuple[str, ...] | None = None
    unix_sockets: dict[str, NetworkUnixSocketPermission] | None = None
    allow_unix_sockets: tuple[str, ...] | None = None
    allow_local_binding: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "NetworkRequirements":
        data = _mapping(value, "NetworkRequirements")
        domains = _pick(data, "domains")
        sockets = _pick(data, "unix_sockets", "unixSockets")
        return cls(
            enabled=_optional_bool(data.get("enabled"), "enabled"),
            http_port=_optional_u16(_pick(data, "http_port", "httpPort"), "http_port"),
            socks_port=_optional_u16(_pick(data, "socks_port", "socksPort"), "socks_port"),
            allow_upstream_proxy=_optional_bool(_pick(data, "allow_upstream_proxy", "allowUpstreamProxy"), "allow_upstream_proxy"),
            dangerously_allow_non_loopback_proxy=_optional_bool(_pick(data, "dangerously_allow_non_loopback_proxy", "dangerouslyAllowNonLoopbackProxy"), "dangerously_allow_non_loopback_proxy"),
            dangerously_allow_all_unix_sockets=_optional_bool(_pick(data, "dangerously_allow_all_unix_sockets", "dangerouslyAllowAllUnixSockets"), "dangerously_allow_all_unix_sockets"),
            domains={str(k): NetworkDomainPermission.parse(v) for k, v in _mapping(domains, "domains").items()} if domains is not None else None,
            managed_allowed_domains_only=_optional_bool(_pick(data, "managed_allowed_domains_only", "managedAllowedDomainsOnly"), "managed_allowed_domains_only"),
            allowed_domains=_optional_str_tuple(_pick(data, "allowed_domains", "allowedDomains"), "allowed_domains"),
            denied_domains=_optional_str_tuple(_pick(data, "denied_domains", "deniedDomains"), "denied_domains"),
            unix_sockets={str(k): NetworkUnixSocketPermission.parse(v) for k, v in _mapping(sockets, "unix_sockets").items()} if sockets is not None else None,
            allow_unix_sockets=_optional_str_tuple(_pick(data, "allow_unix_sockets", "allowUnixSockets"), "allow_unix_sockets"),
            allow_local_binding=_optional_bool(_pick(data, "allow_local_binding", "allowLocalBinding"), "allow_local_binding"),
        )


@dataclass(frozen=True)
class ConfigRequirements:
    allowed_approval_policies: tuple[AskForApproval, ...] | None = None
    allowed_approvals_reviewers: tuple[ApprovalsReviewer, ...] | None = None
    allowed_sandbox_modes: tuple[SandboxMode, ...] | None = None
    allowed_permissions: tuple[str, ...] | None = None
    allowed_web_search_modes: tuple[WebSearchMode, ...] | None = None
    allow_managed_hooks_only: bool | None = None
    allow_appshots: bool | None = None
    computer_use: ComputerUseRequirements | Mapping[str, JsonValue] | None = None
    feature_requirements: dict[str, bool] | None = None
    hooks: ManagedHooksRequirements | Mapping[str, JsonValue] | None = None
    enforce_residency: ResidencyRequirement | str | None = None
    network: NetworkRequirements | Mapping[str, JsonValue] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigRequirements":
        data = _mapping(value, "ConfigRequirements")
        return cls(
            allowed_approval_policies=tuple(AskForApproval.from_mapping(item) for item in _list_or_none(_pick(data, "allowed_approval_policies", "allowedApprovalPolicies")) or ()) or None,
            allowed_approvals_reviewers=tuple(ApprovalsReviewer.parse(item) for item in _list_or_none(_pick(data, "allowed_approvals_reviewers", "allowedApprovalsReviewers")) or ()) or None,
            allowed_sandbox_modes=tuple(SandboxMode.parse(item) for item in _list_or_none(_pick(data, "allowed_sandbox_modes", "allowedSandboxModes")) or ()) or None,
            allowed_permissions=_optional_str_tuple(_pick(data, "allowed_permissions", "allowedPermissions"), "allowed_permissions"),
            allowed_web_search_modes=tuple(WebSearchMode.parse(item) for item in _list_or_none(_pick(data, "allowed_web_search_modes", "allowedWebSearchModes")) or ()) or None,
            allow_managed_hooks_only=_optional_bool(_pick(data, "allow_managed_hooks_only", "allowManagedHooksOnly"), "allow_managed_hooks_only"),
            allow_appshots=_optional_bool(_pick(data, "allow_appshots", "allowAppshots"), "allow_appshots"),
            computer_use=ComputerUseRequirements.from_mapping(_pick(data, "computer_use", "computerUse")) if _pick(data, "computer_use", "computerUse") is not None else None,
            feature_requirements={str(k): _ensure_bool(v, k) for k, v in _mapping(_pick(data, "feature_requirements", "featureRequirements") or {}, "feature_requirements").items()} or None,
            hooks=ManagedHooksRequirements.from_mapping(data["hooks"]) if data.get("hooks") is not None else None,
            enforce_residency=ResidencyRequirement.parse(_pick(data, "enforce_residency", "enforceResidency")) if _pick(data, "enforce_residency", "enforceResidency") is not None else None,
            network=NetworkRequirements.from_mapping(data["network"]) if data.get("network") is not None else None,
        )


@dataclass(frozen=True)
class ConfigRequirementsReadResponse:
    requirements: ConfigRequirements | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", ConfigRequirements.from_mapping(self.requirements) if isinstance(self.requirements, Mapping) else self.requirements)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigRequirementsReadResponse":
        data = _mapping(value, "ConfigRequirementsReadResponse")
        return cls(requirements=ConfigRequirements.from_mapping(data["requirements"]) if data.get("requirements") is not None else None)


class ExternalAgentConfigMigrationItemType(_StringEnum):
    AGENTS_MD = "AGENTS_MD"
    CONFIG = "CONFIG"
    SKILLS = "SKILLS"
    PLUGINS = "PLUGINS"
    MCP_SERVER_CONFIG = "MCP_SERVER_CONFIG"
    SUBAGENTS = "SUBAGENTS"
    HOOKS = "HOOKS"
    COMMANDS = "COMMANDS"
    SESSIONS = "SESSIONS"


@dataclass(frozen=True)
class PluginsMigration:
    marketplace_name: str
    plugin_names: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PluginsMigration":
        data = _mapping(value, "PluginsMigration")
        return cls(
            marketplace_name=_ensure_str(_pick(data, "marketplace_name", "marketplaceName"), "marketplace_name"),
            plugin_names=_str_tuple(_pick(data, "plugin_names", "pluginNames"), "plugin_names"),
        )


@dataclass(frozen=True)
class SessionMigration:
    path: Path
    cwd: Path
    title: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "SessionMigration":
        data = _mapping(value, "SessionMigration")
        return cls(path=_path(data["path"], "path"), cwd=_path(data["cwd"], "cwd"), title=_optional_str(data.get("title"), "title"))


@dataclass(frozen=True)
class _NamedMigration:
    name: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]):
        return cls(name=_ensure_str(_mapping(value, cls.__name__)["name"], "name"))


class McpServerMigration(_NamedMigration):
    pass


class HookMigration(_NamedMigration):
    pass


class SubagentMigration(_NamedMigration):
    pass


class CommandMigration(_NamedMigration):
    pass


@dataclass(frozen=True)
class MigrationDetails:
    plugins: tuple[PluginsMigration, ...] = ()
    sessions: tuple[SessionMigration, ...] = ()
    mcp_servers: tuple[McpServerMigration, ...] = ()
    hooks: tuple[HookMigration, ...] = ()
    subagents: tuple[SubagentMigration, ...] = ()
    commands: tuple[CommandMigration, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "MigrationDetails":
        data = {} if value is None else _mapping(value, "MigrationDetails")
        return cls(
            plugins=tuple(PluginsMigration.from_mapping(item) for item in _list(data.get("plugins", ()), "plugins")),
            sessions=tuple(SessionMigration.from_mapping(item) for item in _list(data.get("sessions", ()), "sessions")),
            mcp_servers=tuple(McpServerMigration.from_mapping(item) for item in _list(_pick(data, "mcp_servers", "mcpServers", default=()), "mcp_servers")),
            hooks=tuple(HookMigration.from_mapping(item) for item in _list(data.get("hooks", ()), "hooks")),
            subagents=tuple(SubagentMigration.from_mapping(item) for item in _list(data.get("subagents", ()), "subagents")),
            commands=tuple(CommandMigration.from_mapping(item) for item in _list(data.get("commands", ()), "commands")),
        )


@dataclass(frozen=True)
class ExternalAgentConfigMigrationItem:
    item_type: ExternalAgentConfigMigrationItemType | str
    description: str
    cwd: Path | None = None
    details: MigrationDetails | Mapping[str, JsonValue] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ExternalAgentConfigMigrationItem":
        data = _mapping(value, "ExternalAgentConfigMigrationItem")
        return cls(
            item_type=ExternalAgentConfigMigrationItemType.parse(_pick(data, "item_type", "itemType")),
            description=_ensure_str(data["description"], "description"),
            cwd=_optional_path(data.get("cwd"), "cwd"),
            details=MigrationDetails.from_mapping(data["details"]) if data.get("details") is not None else None,
        )


@dataclass(frozen=True)
class ExternalAgentConfigDetectResponse:
    items: tuple[ExternalAgentConfigMigrationItem, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ExternalAgentConfigDetectResponse":
        data = _mapping(value, "ExternalAgentConfigDetectResponse")
        return cls(items=tuple(ExternalAgentConfigMigrationItem.from_mapping(item) for item in _list(data["items"], "items")))


@dataclass(frozen=True)
class ExternalAgentConfigDetectParams:
    include_home: bool = False
    cwds: tuple[Path, ...] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ExternalAgentConfigDetectParams":
        data = {} if value is None else _mapping(value, "ExternalAgentConfigDetectParams")
        return cls(
            include_home=_ensure_bool(_pick(data, "include_home", "includeHome", default=False), "include_home"),
            cwds=tuple(_path(item, "cwds") for item in _list(_pick(data, "cwds"), "cwds")) if _pick(data, "cwds") is not None else None,
        )


@dataclass(frozen=True)
class ExternalAgentConfigImportParams:
    migration_items: tuple[ExternalAgentConfigMigrationItem, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ExternalAgentConfigImportParams":
        data = _mapping(value, "ExternalAgentConfigImportParams")
        return cls(migration_items=tuple(ExternalAgentConfigMigrationItem.from_mapping(item) for item in _list(_pick(data, "migration_items", "migrationItems"), "migration_items")))


@dataclass(frozen=True)
class ExternalAgentConfigImportResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ExternalAgentConfigImportResponse":
        if value is not None:
            _mapping(value, "ExternalAgentConfigImportResponse")
        return cls()


class ExternalAgentConfigImportCompletedNotification(ExternalAgentConfigImportResponse):
    pass


@dataclass(frozen=True)
class ConfigEdit:
    key_path: str
    value: JsonValue
    merge_strategy: MergeStrategy | str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigEdit":
        data = _mapping(value, "ConfigEdit")
        return cls(
            key_path=_ensure_str(_pick(data, "key_path", "keyPath"), "key_path"),
            value=data["value"],
            merge_strategy=MergeStrategy.parse(_pick(data, "merge_strategy", "mergeStrategy")),
        )


@dataclass(frozen=True)
class ConfigValueWriteParams(ConfigEdit):
    file_path: str | None = None
    expected_version: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigValueWriteParams":
        data = _mapping(value, "ConfigValueWriteParams")
        return cls(
            key_path=_ensure_str(_pick(data, "key_path", "keyPath"), "key_path"),
            value=data["value"],
            merge_strategy=MergeStrategy.parse(_pick(data, "merge_strategy", "mergeStrategy")),
            file_path=_optional_str(_pick(data, "file_path", "filePath"), "file_path"),
            expected_version=_optional_str(_pick(data, "expected_version", "expectedVersion"), "expected_version"),
        )


@dataclass(frozen=True)
class ConfigBatchWriteParams:
    edits: tuple[ConfigEdit, ...]
    file_path: str | None = None
    expected_version: str | None = None
    reload_user_config: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigBatchWriteParams":
        data = _mapping(value, "ConfigBatchWriteParams")
        return cls(
            edits=tuple(ConfigEdit.from_mapping(item) for item in _list(data["edits"], "edits")),
            file_path=_optional_str(_pick(data, "file_path", "filePath"), "file_path"),
            expected_version=_optional_str(_pick(data, "expected_version", "expectedVersion"), "expected_version"),
            reload_user_config=_ensure_bool(_pick(data, "reload_user_config", "reloadUserConfig", default=False), "reload_user_config"),
        )


@dataclass(frozen=True)
class TextPosition:
    line: int
    column: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "line", _positive_usize(self.line, "line"))
        object.__setattr__(self, "column", _positive_usize(self.column, "column"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TextPosition":
        data = _mapping(value, "TextPosition")
        return cls(line=_positive_usize(data["line"], "line"), column=_positive_usize(data["column"], "column"))


@dataclass(frozen=True)
class TextRange:
    start: TextPosition | Mapping[str, JsonValue]
    end: TextPosition | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _text_position(self.start))
        object.__setattr__(self, "end", _text_position(self.end))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TextRange":
        data = _mapping(value, "TextRange")
        return cls(start=TextPosition.from_mapping(data["start"]), end=TextPosition.from_mapping(data["end"]))


@dataclass(frozen=True)
class ConfigWarningNotification:
    summary: str
    details: str | None = None
    path: str | None = None
    range: TextRange | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _ensure_str(self.summary, "summary"))
        object.__setattr__(self, "details", _optional_str(self.details, "details"))
        object.__setattr__(self, "path", _optional_str(self.path, "path"))
        object.__setattr__(self, "range", _text_range(self.range) if self.range is not None else None)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigWarningNotification":
        data = _mapping(value, "ConfigWarningNotification")
        return cls(
            summary=_ensure_str(data["summary"], "summary"),
            details=_optional_str(data.get("details"), "details"),
            path=_optional_str(data.get("path"), "path"),
            range=TextRange.from_mapping(data["range"]) if data.get("range") is not None else None,
        )


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _pick(data: Mapping[str, JsonValue], *keys: str, default: JsonValue = None) -> JsonValue:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _require(value: JsonValue, field_name: str) -> None:
    if value is None:
        raise TypeError(f"{field_name} is required")


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_bool(value: JsonValue, field_name: str) -> bool | None:
    if value is None:
        return None
    return _ensure_bool(value, field_name)


def _path(value: JsonValue, field_name: str) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError(f"{field_name} must be a path string")


def _absolute_path(value: JsonValue, field_name: str) -> Path:
    path = _path(value, field_name)
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be absolute")
    return path


def _optional_path(value: JsonValue, field_name: str) -> Path | None:
    if value is None:
        return None
    return _path(value, field_name)


def _optional_absolute_path(value: JsonValue, field_name: str) -> Path | None:
    if value is None:
        return None
    return _absolute_path(value, field_name)


def _path_tuple(value: JsonValue, field_name: str) -> tuple[Path, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be a list of paths")
    return tuple(_path(item, field_name) for item in value)


def _str_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be a list of strings")
    result = tuple(value)
    if not all(isinstance(item, str) for item in result):
        raise TypeError(f"{field_name} must be a list of strings")
    return result


def _optional_str_tuple(value: JsonValue, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _str_tuple(value, field_name)


def _list(value: JsonValue, field_name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _list_or_none(value: JsonValue) -> list[JsonValue] | None:
    if value is None:
        return None
    return _list(value, "list")


def _optional_enum(value: JsonValue, enum_cls, field_name: str):
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    parse = getattr(enum_cls, "parse", None)
    return parse(value) if parse is not None else enum_cls(value)


def _optional_u16(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 2**16 - 1:
        raise TypeError(f"{field_name} must be an unsigned 16-bit integer")
    return value


def _optional_u64(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 2**64 - 1:
        raise TypeError(f"{field_name} must be an unsigned 64-bit integer")
    return value


def _positive_usize(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TypeError(f"{field_name} must be a positive integer")
    return value


def _layer_source(value: ConfigLayerSource | Mapping[str, JsonValue]) -> ConfigLayerSource:
    if isinstance(value, ConfigLayerSource):
        return value
    return ConfigLayerSource.from_mapping(value)


def _layer_metadata(value: ConfigLayerMetadata | Mapping[str, JsonValue]) -> ConfigLayerMetadata:
    if isinstance(value, ConfigLayerMetadata):
        return value
    return ConfigLayerMetadata.from_mapping(value)


def _config_layer(value: ConfigLayer | Mapping[str, JsonValue]) -> ConfigLayer:
    if isinstance(value, ConfigLayer):
        return value
    return ConfigLayer.from_mapping(value)


def _overridden(value: OverriddenMetadata | Mapping[str, JsonValue] | None) -> OverriddenMetadata | None:
    if value is None or isinstance(value, OverriddenMetadata):
        return value
    return OverriddenMetadata.from_mapping(value)


def _app_tool_config(value: AppToolConfig | Mapping[str, JsonValue]) -> AppToolConfig:
    if isinstance(value, AppToolConfig):
        return value
    return AppToolConfig.from_mapping(value)


def _app_tools_config(value: AppToolsConfig | Mapping[str, JsonValue]) -> AppToolsConfig:
    if isinstance(value, AppToolsConfig):
        return value
    return AppToolsConfig.from_mapping(value)


def _app_config(value: AppConfig | Mapping[str, JsonValue]) -> AppConfig:
    if isinstance(value, AppConfig):
        return value
    return AppConfig.from_mapping(value)


def _apps_default(value: AppsDefaultConfig | Mapping[str, JsonValue]) -> AppsDefaultConfig:
    if isinstance(value, AppsDefaultConfig):
        return value
    return AppsDefaultConfig.from_mapping(value)


def _hook_groups(value: JsonValue) -> tuple[ConfiguredHookMatcherGroup, ...]:
    return tuple(ConfiguredHookMatcherGroup.from_mapping(item) for item in _list(value, "hook groups"))


def _text_position(value: TextPosition | Mapping[str, JsonValue]) -> TextPosition:
    if isinstance(value, TextPosition):
        return value
    return TextPosition.from_mapping(value)


def _text_range(value: TextRange | Mapping[str, JsonValue]) -> TextRange:
    if isinstance(value, TextRange):
        return value
    return TextRange.from_mapping(value)


def _serialize(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _to_mapping(value: JsonValue, skip: set[str] | None = None) -> dict[str, JsonValue]:
    skip = skip or set()
    result: dict[str, JsonValue] = {}
    for field in fields(value):
        name = field.name
        if name in skip:
            continue
        serialized = _serialize(getattr(value, name))
        if serialized is not None:
            result[name] = serialized
    return result


def _to_camel_mapping(value: JsonValue) -> dict[str, JsonValue]:
    return {_snake_to_camel(key): item for key, item in _to_mapping(value).items()}


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


__all__ = [
    "AnalyticsConfig",
    "AppConfig",
    "AppToolApproval",
    "AppToolConfig",
    "AppToolsConfig",
    "AppsConfig",
    "AppsDefaultConfig",
    "CommandMigration",
    "ComputerUseRequirements",
    "Config",
    "ConfigBatchWriteParams",
    "ConfigEdit",
    "ConfigLayer",
    "ConfigLayerMetadata",
    "ConfigLayerSource",
    "ConfigReadParams",
    "ConfigReadResponse",
    "ConfigRequirements",
    "ConfigRequirementsReadResponse",
    "ConfigValueWriteParams",
    "ConfigWarningNotification",
    "ConfigWriteErrorCode",
    "ConfigWriteResponse",
    "ConfiguredHookHandler",
    "ConfiguredHookMatcherGroup",
    "ExternalAgentConfigDetectParams",
    "ExternalAgentConfigDetectResponse",
    "ExternalAgentConfigImportCompletedNotification",
    "ExternalAgentConfigImportParams",
    "ExternalAgentConfigImportResponse",
    "ExternalAgentConfigMigrationItem",
    "ExternalAgentConfigMigrationItemType",
    "ForcedChatgptWorkspaceIds",
    "ForcedLoginMethod",
    "HookMigration",
    "ManagedHooksRequirements",
    "McpServerMigration",
    "MergeStrategy",
    "MigrationDetails",
    "NetworkDomainPermission",
    "NetworkRequirements",
    "NetworkUnixSocketPermission",
    "OverriddenMetadata",
    "PluginsMigration",
    "ResidencyRequirement",
    "SandboxWorkspaceWrite",
    "SessionMigration",
    "SubagentMigration",
    "TextPosition",
    "TextRange",
    "ToolsV2",
    "WriteStatus",
]
