"""Config type helpers ported from ``codex-config::types``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .mcp_types import (
    AppToolApproval,
    McpServerConfig,
    McpServerDisabledReason,
    McpServerEnvVar,
    McpServerOAuthConfig,
    McpServerToolConfig,
    McpServerTransportConfig,
)
from .skills_config import BundledSkillsConfig, SkillConfig, SkillsConfig
from .tui_keymap import (
    KeybindingSpec,
    KeybindingsSpec,
    TuiApprovalKeymap,
    TuiChatKeymap,
    TuiComposerKeymap,
    TuiEditorKeymap,
    TuiGlobalKeymap,
    TuiKeymap,
    TuiListKeymap,
    TuiPagerKeymap,
    TuiVimNormalKeymap,
    TuiVimOperatorKeymap,
    TuiVimTextObjectKeymap,
    normalize_key_name,
    normalize_keybinding_spec,
)
from pycodex.protocol.config_types import (
    AltScreenMode,
    ApprovalsReviewer,
    ModeKind,
    Personality,
    ServiceTier,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    WebSearchMode,
)


DEFAULT_OTEL_ENVIRONMENT = "dev"
DEFAULT_MEMORIES_MAX_ROLLOUTS_PER_STARTUP = 2
DEFAULT_MEMORIES_MAX_ROLLOUT_AGE_DAYS = 10
DEFAULT_MEMORIES_MIN_ROLLOUT_IDLE_HOURS = 6
DEFAULT_MEMORIES_MIN_RATE_LIMIT_REMAINING_PERCENT = 25
DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION = 256
DEFAULT_MEMORIES_MAX_UNUSED_DAYS = 30
MIN_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION = 1
MAX_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION = 4096
MIN_MEMORIES_MAX_ROLLOUTS_PER_STARTUP = 1
MAX_MEMORIES_MAX_ROLLOUTS_PER_STARTUP = 128


class SessionPickerViewMode(str, Enum):
    COMFORTABLE = "comfortable"
    DENSE = "dense"

    def __str__(self) -> str:
        return self.value


class AuthCredentialsStoreMode(str, Enum):
    FILE = "file"
    KEYRING = "keyring"
    AUTO = "auto"
    EPHEMERAL = "ephemeral"


class OAuthCredentialsStoreMode(str, Enum):
    AUTO = "auto"
    FILE = "file"
    KEYRING = "keyring"


class WindowsSandboxModeToml(str, Enum):
    ELEVATED = "elevated"
    UNELEVATED = "unelevated"


@dataclass(frozen=True)
class WindowsToml:
    sandbox: WindowsSandboxModeToml | None = None
    sandbox_private_desktop: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "WindowsToml":
        value = _mapping_or_empty(value, "WindowsToml")
        _reject_unknown_fields(value, {"sandbox", "sandbox_private_desktop"}, "WindowsToml")
        sandbox = _optional_enum(value, "sandbox", WindowsSandboxModeToml)
        return cls(
            sandbox=sandbox,
            sandbox_private_desktop=_optional_bool(value, "sandbox_private_desktop"),
        )


class UriBasedFileOpener(str, Enum):
    VSCODE = "vscode"
    VSCODE_INSIDERS = "vscode-insiders"
    WINDSURF = "windsurf"
    CURSOR = "cursor"
    NONE = "none"

    def get_scheme(self) -> str | None:
        return None if self is UriBasedFileOpener.NONE else self.value


class HistoryPersistence(str, Enum):
    SAVE_ALL = "save-all"
    NONE = "none"


@dataclass(frozen=True)
class History:
    persistence: HistoryPersistence = HistoryPersistence.SAVE_ALL
    max_bytes: int | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "History":
        value = _mapping_or_empty(value, "History")
        _reject_unknown_fields(value, {"persistence", "max_bytes"}, "History")
        return cls(
            persistence=_optional_enum(value, "persistence", HistoryPersistence) or HistoryPersistence.SAVE_ALL,
            max_bytes=_optional_int(value, "max_bytes"),
        )


@dataclass(frozen=True)
class AnalyticsConfigToml:
    enabled: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AnalyticsConfigToml":
        value = _mapping_or_empty(value, "AnalyticsConfigToml")
        _reject_unknown_fields(value, {"enabled"}, "AnalyticsConfigToml")
        return cls(enabled=_optional_bool(value, "enabled"))


@dataclass(frozen=True)
class FeedbackConfigToml:
    enabled: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "FeedbackConfigToml":
        value = _mapping_or_empty(value, "FeedbackConfigToml")
        _reject_unknown_fields(value, {"enabled"}, "FeedbackConfigToml")
        return cls(enabled=_optional_bool(value, "enabled"))


class ToolSuggestDiscoverableType(str, Enum):
    CONNECTOR = "connector"
    PLUGIN = "plugin"


@dataclass(frozen=True)
class ToolSuggestDiscoverable:
    kind: ToolSuggestDiscoverableType
    id: str

    @classmethod
    def connector(cls, id: str) -> "ToolSuggestDiscoverable":
        return cls(ToolSuggestDiscoverableType.CONNECTOR, id)

    @classmethod
    def plugin(cls, id: str) -> "ToolSuggestDiscoverable":
        return cls(ToolSuggestDiscoverableType.PLUGIN, id)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ToolSuggestDiscoverable":
        _reject_unknown_fields(value, {"type", "id"}, "ToolSuggestDiscoverable")
        return cls(_required_enum(value, "type", ToolSuggestDiscoverableType), _required_str(value, "id"))

    def to_mapping(self) -> dict[str, str]:
        return {"type": self.kind.value, "id": self.id}


@dataclass(frozen=True)
class ToolSuggestDisabledTool:
    kind: ToolSuggestDiscoverableType
    id: str

    @classmethod
    def connector(cls, id: str) -> "ToolSuggestDisabledTool":
        return cls(ToolSuggestDiscoverableType.CONNECTOR, id)

    @classmethod
    def plugin(cls, id: str) -> "ToolSuggestDisabledTool":
        return cls(ToolSuggestDiscoverableType.PLUGIN, id)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ToolSuggestDisabledTool":
        _reject_unknown_fields(value, {"type", "id"}, "ToolSuggestDisabledTool")
        return cls(_required_enum(value, "type", ToolSuggestDiscoverableType), _required_str(value, "id"))

    def normalized(self) -> "ToolSuggestDisabledTool | None":
        trimmed = self.id.strip()
        if not trimmed:
            return None
        return ToolSuggestDisabledTool(self.kind, trimmed)

    def to_mapping(self) -> dict[str, str]:
        return {"type": self.kind.value, "id": self.id}


@dataclass(frozen=True)
class ToolSuggestConfig:
    discoverables: tuple[ToolSuggestDiscoverable, ...] = ()
    disabled_tools: tuple[ToolSuggestDisabledTool, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ToolSuggestConfig":
        value = _mapping_or_empty(value, "ToolSuggestConfig")
        _reject_unknown_fields(value, {"discoverables", "disabled_tools"}, "ToolSuggestConfig")
        return cls(
            discoverables=tuple(
                ToolSuggestDiscoverable.from_mapping(item)
                for item in _mapping_sequence(value.get("discoverables", ()), "discoverables")
            ),
            disabled_tools=tuple(
                ToolSuggestDisabledTool.from_mapping(item)
                for item in _mapping_sequence(value.get("disabled_tools", ()), "disabled_tools")
            ),
        )


@dataclass(frozen=True)
class AppsDefaultConfig:
    enabled: bool = True
    destructive_enabled: bool = True
    open_world_enabled: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppsDefaultConfig":
        value = _mapping_or_empty(value, "AppsDefaultConfig")
        _reject_unknown_fields(value, {"enabled", "destructive_enabled", "open_world_enabled"}, "AppsDefaultConfig")
        return cls(
            enabled=_optional_bool(value, "enabled") if "enabled" in value else True,
            destructive_enabled=_optional_bool(value, "destructive_enabled") if "destructive_enabled" in value else True,
            open_world_enabled=_optional_bool(value, "open_world_enabled") if "open_world_enabled" in value else True,
        )


@dataclass(frozen=True)
class AppToolConfig:
    enabled: bool | None = None
    approval_mode: AppToolApproval | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppToolConfig":
        value = _mapping_or_empty(value, "AppToolConfig")
        _reject_unknown_fields(value, {"enabled", "approval_mode"}, "AppToolConfig")
        approval = value.get("approval_mode")
        return cls(
            enabled=_optional_bool(value, "enabled"),
            approval_mode=AppToolApproval.from_value(approval) if approval is not None else None,
        )


@dataclass(frozen=True)
class AppToolsConfig:
    tools: dict[str, AppToolConfig] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppToolsConfig":
        value = _mapping_or_empty(value, "AppToolsConfig")
        return cls(tools={str(name): AppToolConfig.from_mapping(config) for name, config in value.items()})


@dataclass(frozen=True)
class AppConfig:
    enabled: bool = True
    destructive_enabled: bool | None = None
    open_world_enabled: bool | None = None
    default_tools_approval_mode: AppToolApproval | None = None
    default_tools_enabled: bool | None = None
    tools: AppToolsConfig | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppConfig":
        value = _mapping_or_empty(value, "AppConfig")
        _reject_unknown_fields(
            value,
            {
                "enabled",
                "destructive_enabled",
                "open_world_enabled",
                "default_tools_approval_mode",
                "default_tools_enabled",
                "tools",
            },
            "AppConfig",
        )
        approval = value.get("default_tools_approval_mode")
        tools_value = value.get("tools")
        if tools_value is not None and not isinstance(tools_value, Mapping):
            raise TypeError("tools must be a table or None")
        return cls(
            enabled=_optional_bool(value, "enabled") if "enabled" in value else True,
            destructive_enabled=_optional_bool(value, "destructive_enabled"),
            open_world_enabled=_optional_bool(value, "open_world_enabled"),
            default_tools_approval_mode=AppToolApproval.from_value(approval) if approval is not None else None,
            default_tools_enabled=_optional_bool(value, "default_tools_enabled"),
            tools=AppToolsConfig.from_mapping(tools_value) if tools_value is not None else None,
        )


@dataclass(frozen=True)
class AppsConfigToml:
    default: AppsDefaultConfig | None = None
    apps: dict[str, AppConfig] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppsConfigToml":
        value = _mapping_or_empty(value, "AppsConfigToml")
        default_value = value.get("_default")
        if default_value is not None and not isinstance(default_value, Mapping):
            raise TypeError("_default must be a table or None")
        apps = {
            str(name): AppConfig.from_mapping(config)
            for name, config in value.items()
            if name != "_default"
        }
        return cls(
            default=AppsDefaultConfig.from_mapping(default_value) if default_value is not None else None,
            apps=apps,
        )


class OtelHttpProtocol(str, Enum):
    BINARY = "binary"
    JSON = "json"


@dataclass(frozen=True)
class OtelTlsConfig:
    ca_certificate: Path | None = None
    client_certificate: Path | None = None
    client_private_key: Path | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "OtelTlsConfig":
        value = _mapping_or_empty(value, "OtelTlsConfig")
        _reject_unknown_fields(value, {"ca_certificate", "client_certificate", "client_private_key"}, "OtelTlsConfig")
        return cls(
            ca_certificate=_optional_path(value, "ca_certificate"),
            client_certificate=_optional_path(value, "client_certificate"),
            client_private_key=_optional_path(value, "client_private_key"),
        )


@dataclass(frozen=True)
class OtelExporterKind:
    kind: str
    endpoint: str | None = None
    headers: dict[str, str] | None = None
    protocol: OtelHttpProtocol | None = None
    tls: OtelTlsConfig | None = None

    @classmethod
    def none(cls) -> "OtelExporterKind":
        return cls("none")

    @classmethod
    def statsig(cls) -> "OtelExporterKind":
        return cls("statsig")

    @classmethod
    def otlp_http(
        cls,
        endpoint: str,
        *,
        headers: Mapping[str, str] | None = None,
        protocol: OtelHttpProtocol | str = OtelHttpProtocol.BINARY,
        tls: OtelTlsConfig | Mapping[str, Any] | None = None,
    ) -> "OtelExporterKind":
        return cls(
            "otlp-http",
            endpoint=endpoint,
            headers=dict(headers or {}),
            protocol=protocol if isinstance(protocol, OtelHttpProtocol) else OtelHttpProtocol(protocol),
            tls=tls if isinstance(tls, OtelTlsConfig) or tls is None else OtelTlsConfig.from_mapping(tls),
        )

    @classmethod
    def otlp_grpc(
        cls,
        endpoint: str,
        *,
        headers: Mapping[str, str] | None = None,
        tls: OtelTlsConfig | Mapping[str, Any] | None = None,
    ) -> "OtelExporterKind":
        return cls(
            "otlp-grpc",
            endpoint=endpoint,
            headers=dict(headers or {}),
            tls=tls if isinstance(tls, OtelTlsConfig) or tls is None else OtelTlsConfig.from_mapping(tls),
        )

    @classmethod
    def from_value(cls, value: Any) -> "OtelExporterKind":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            if value == "none":
                return cls.none()
            if value == "statsig":
                return cls.statsig()
        if not isinstance(value, Mapping):
            raise TypeError("OTEL exporter must be a string or table")
        kind = _required_str(value, "type") if "type" in value else _required_str(value, "kind")
        if kind == "none":
            return cls.none()
        if kind == "statsig":
            return cls.statsig()
        headers = _optional_str_mapping(value, "headers") or {}
        tls_value = value.get("tls")
        tls = OtelTlsConfig.from_mapping(tls_value) if isinstance(tls_value, Mapping) else None
        if kind == "otlp-http":
            return cls.otlp_http(
                _required_str(value, "endpoint"),
                headers=headers,
                protocol=_optional_enum(value, "protocol", OtelHttpProtocol) or OtelHttpProtocol.BINARY,
                tls=tls,
            )
        if kind == "otlp-grpc":
            return cls.otlp_grpc(_required_str(value, "endpoint"), headers=headers, tls=tls)
        raise ValueError(f"unknown OTEL exporter kind: {kind}")


@dataclass(frozen=True)
class OtelConfigToml:
    log_user_prompt: bool | None = None
    environment: str | None = None
    exporter: OtelExporterKind | None = None
    trace_exporter: OtelExporterKind | None = None
    metrics_exporter: OtelExporterKind | None = None
    span_attributes: dict[str, str] | None = None
    tracestate: dict[str, dict[str, str]] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "OtelConfigToml":
        value = _mapping_or_empty(value, "OtelConfigToml")
        _reject_unknown_fields(
            value,
            {"log_user_prompt", "environment", "exporter", "trace_exporter", "metrics_exporter", "span_attributes", "tracestate"},
            "OtelConfigToml",
        )
        return cls(
            log_user_prompt=_optional_bool(value, "log_user_prompt"),
            environment=_optional_str(value, "environment"),
            exporter=OtelExporterKind.from_value(value["exporter"]) if "exporter" in value and value["exporter"] is not None else None,
            trace_exporter=OtelExporterKind.from_value(value["trace_exporter"]) if "trace_exporter" in value and value["trace_exporter"] is not None else None,
            metrics_exporter=OtelExporterKind.from_value(value["metrics_exporter"]) if "metrics_exporter" in value and value["metrics_exporter"] is not None else None,
            span_attributes=_optional_str_mapping(value, "span_attributes"),
            tracestate=_optional_nested_str_mapping(value, "tracestate"),
        )


@dataclass(frozen=True)
class OtelConfig:
    log_user_prompt: bool = False
    environment: str = DEFAULT_OTEL_ENVIRONMENT
    exporter: OtelExporterKind = OtelExporterKind.none()
    trace_exporter: OtelExporterKind = OtelExporterKind.none()
    metrics_exporter: OtelExporterKind = OtelExporterKind.statsig()
    span_attributes: dict[str, str] | None = None
    tracestate: dict[str, dict[str, str]] | None = None

    @classmethod
    def from_toml(cls, value: OtelConfigToml | Mapping[str, Any] | None) -> "OtelConfig":
        toml = value if isinstance(value, OtelConfigToml) else OtelConfigToml.from_mapping(value)
        defaults = cls()
        return cls(
            log_user_prompt=_coalesce(toml.log_user_prompt, defaults.log_user_prompt),
            environment=_coalesce(toml.environment, defaults.environment),
            exporter=_coalesce(toml.exporter, defaults.exporter),
            trace_exporter=_coalesce(toml.trace_exporter, defaults.trace_exporter),
            metrics_exporter=_coalesce(toml.metrics_exporter, defaults.metrics_exporter),
            span_attributes=dict(toml.span_attributes or {}),
            tracestate={key: dict(inner) for key, inner in (toml.tracestate or {}).items()},
        )


@dataclass(frozen=True)
class Notifications:
    value: bool | tuple[str, ...] = True

    @classmethod
    def from_value(cls, value: Any) -> "Notifications":
        if isinstance(value, cls):
            return value
        if isinstance(value, bool):
            return cls(value)
        if isinstance(value, list | tuple):
            if not all(isinstance(item, str) for item in value):
                raise TypeError("notifications command entries must be strings")
            return cls(tuple(value))
        raise TypeError("notifications must be a bool or array of strings")

    @property
    def enabled(self) -> bool | None:
        return self.value if isinstance(self.value, bool) else None

    @property
    def custom(self) -> tuple[str, ...] | None:
        return self.value if isinstance(self.value, tuple) else None


class NotificationMethod(str, Enum):
    AUTO = "auto"
    OSC9 = "osc9"
    BEL = "bel"

    def __str__(self) -> str:
        return self.value


class NotificationCondition(str, Enum):
    UNFOCUSED = "unfocused"
    ALWAYS = "always"

    def __str__(self) -> str:
        return self.value


class TuiPetAnchor(str, Enum):
    COMPOSER = "composer"
    SCREEN_BOTTOM = "screen-bottom"


@dataclass(frozen=True)
class TuiNotificationSettings:
    notifications: Notifications = Notifications()
    method: NotificationMethod = NotificationMethod.AUTO
    condition: NotificationCondition = NotificationCondition.UNFOCUSED

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "TuiNotificationSettings":
        value = _mapping_or_empty(value, "TuiNotificationSettings")
        _reject_unknown_fields(value, {"notifications", "notification_method", "notification_condition"}, "TuiNotificationSettings")
        return cls(
            notifications=Notifications.from_value(value.get("notifications", True)),
            method=_optional_enum(value, "notification_method", NotificationMethod) or NotificationMethod.AUTO,
            condition=_optional_enum(value, "notification_condition", NotificationCondition) or NotificationCondition.UNFOCUSED,
        )


@dataclass(frozen=True)
class ModelAvailabilityNuxConfig:
    shown_count: dict[str, int] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ModelAvailabilityNuxConfig":
        value = _mapping_or_empty(value, "ModelAvailabilityNuxConfig")
        result: dict[str, int] = {}
        for key, item in value.items():
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise TypeError("model availability NUX counts must be non-negative integers")
            result[str(key)] = item
        return cls(result)


@dataclass(frozen=True)
class Tui:
    notification_settings: TuiNotificationSettings = TuiNotificationSettings()
    animations: bool = True
    show_tooltips: bool = True
    vim_mode_default: bool = False
    raw_output_mode: bool = False
    alternate_screen: AltScreenMode = AltScreenMode.AUTO
    status_line: tuple[str, ...] | None = None
    status_line_use_colors: bool = True
    terminal_title: tuple[str, ...] | None = None
    theme: str | None = None
    pet: str | None = None
    pet_anchor: TuiPetAnchor = TuiPetAnchor.COMPOSER
    session_picker_view: SessionPickerViewMode | None = None
    keymap: TuiKeymap = field(default_factory=TuiKeymap)
    model_availability_nux: ModelAvailabilityNuxConfig = field(
        default_factory=lambda: ModelAvailabilityNuxConfig.from_mapping(None)
    )
    terminal_resize_reflow_max_rows: int | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "Tui":
        value = _mapping_or_empty(value, "Tui")
        _reject_unknown_fields(
            value,
            {
                "notifications",
                "notification_method",
                "notification_condition",
                "animations",
                "show_tooltips",
                "vim_mode_default",
                "raw_output_mode",
                "alternate_screen",
                "status_line",
                "status_line_use_colors",
                "terminal_title",
                "theme",
                "pet",
                "pet_anchor",
                "session_picker_view",
                "keymap",
                "model_availability_nux",
                "terminal_resize_reflow_max_rows",
            },
            "Tui",
        )
        notification_fields = {
            key: value[key]
            for key in ("notifications", "notification_method", "notification_condition")
            if key in value
        }
        keymap = value.get("keymap")
        if keymap is None:
            keymap_mapping = TuiKeymap()
        elif isinstance(keymap, Mapping):
            keymap_mapping = TuiKeymap.from_mapping(keymap)
        else:
            raise TypeError("keymap must be a table or None")
        terminal_resize_reflow_max_rows = _optional_int(value, "terminal_resize_reflow_max_rows")
        if terminal_resize_reflow_max_rows is not None and terminal_resize_reflow_max_rows < 0:
            raise ValueError("terminal_resize_reflow_max_rows must be non-negative")
        model_availability_nux = value.get("model_availability_nux")
        if model_availability_nux is not None and not isinstance(model_availability_nux, Mapping):
            raise TypeError("model_availability_nux must be a table or None")
        return cls(
            notification_settings=TuiNotificationSettings.from_mapping(notification_fields),
            animations=_coalesce(_optional_bool(value, "animations"), True),
            show_tooltips=_coalesce(_optional_bool(value, "show_tooltips"), True),
            vim_mode_default=_coalesce(_optional_bool(value, "vim_mode_default"), False),
            raw_output_mode=_coalesce(_optional_bool(value, "raw_output_mode"), False),
            alternate_screen=_optional_enum(value, "alternate_screen", AltScreenMode) or AltScreenMode.AUTO,
            status_line=_optional_str_tuple(value, "status_line"),
            status_line_use_colors=_coalesce(_optional_bool(value, "status_line_use_colors"), True),
            terminal_title=_optional_str_tuple(value, "terminal_title"),
            theme=_optional_str(value, "theme"),
            pet=_optional_str(value, "pet"),
            pet_anchor=_optional_enum(value, "pet_anchor", TuiPetAnchor) or TuiPetAnchor.COMPOSER,
            session_picker_view=_optional_enum(value, "session_picker_view", SessionPickerViewMode),
            keymap=keymap_mapping,
            model_availability_nux=ModelAvailabilityNuxConfig.from_mapping(model_availability_nux),
            terminal_resize_reflow_max_rows=terminal_resize_reflow_max_rows,
        )


DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS = 1000


@dataclass(frozen=True)
class ExternalConfigMigrationPrompts:
    home: bool | None = None
    home_last_prompted_at: int | None = None
    projects: dict[str, bool] | None = None
    project_last_prompted_at: dict[str, int] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ExternalConfigMigrationPrompts":
        value = _mapping_or_empty(value, "ExternalConfigMigrationPrompts")
        _reject_unknown_fields(value, {"home", "home_last_prompted_at", "projects", "project_last_prompted_at"}, "ExternalConfigMigrationPrompts")
        return cls(
            home=_optional_bool(value, "home"),
            home_last_prompted_at=_optional_int(value, "home_last_prompted_at"),
            projects=_optional_bool_mapping(value, "projects") or {},
            project_last_prompted_at=_optional_int_mapping(value, "project_last_prompted_at") or {},
        )


@dataclass(frozen=True)
class Notice:
    hide_full_access_warning: bool | None = None
    hide_world_writable_warning: bool | None = None
    fast_default_opt_out: bool | None = None
    hide_rate_limit_model_nudge: bool | None = None
    hide_gpt5_1_migration_prompt: bool | None = None
    hide_gpt_5_1_codex_max_migration_prompt: bool | None = None
    model_migrations: dict[str, str] | None = None
    external_config_migration_prompts: ExternalConfigMigrationPrompts = ExternalConfigMigrationPrompts()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "Notice":
        value = _mapping_or_empty(value, "Notice")
        allowed = {
            "hide_full_access_warning",
            "hide_world_writable_warning",
            "fast_default_opt_out",
            "hide_rate_limit_model_nudge",
            "hide_gpt5_1_migration_prompt",
            "hide_gpt-5.1-codex-max_migration_prompt",
            "model_migrations",
            "external_config_migration_prompts",
        }
        _reject_unknown_fields(value, allowed, "Notice")
        prompts = value.get("external_config_migration_prompts")
        if prompts is not None and not isinstance(prompts, Mapping):
            raise TypeError("external_config_migration_prompts must be a table")
        return cls(
            hide_full_access_warning=_optional_bool(value, "hide_full_access_warning"),
            hide_world_writable_warning=_optional_bool(value, "hide_world_writable_warning"),
            fast_default_opt_out=_optional_bool(value, "fast_default_opt_out"),
            hide_rate_limit_model_nudge=_optional_bool(value, "hide_rate_limit_model_nudge"),
            hide_gpt5_1_migration_prompt=_optional_bool(value, "hide_gpt5_1_migration_prompt"),
            hide_gpt_5_1_codex_max_migration_prompt=_optional_bool(value, "hide_gpt-5.1-codex-max_migration_prompt"),
            model_migrations=_optional_str_mapping(value, "model_migrations") or {},
            external_config_migration_prompts=ExternalConfigMigrationPrompts.from_mapping(prompts),
        )


@dataclass(frozen=True)
class PluginMcpServerConfig:
    enabled: bool = True
    default_tools_approval_mode: AppToolApproval | None = None
    enabled_tools: tuple[str, ...] | None = None
    disabled_tools: tuple[str, ...] | None = None
    tools: dict[str, McpServerToolConfig] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "PluginMcpServerConfig":
        value = _mapping_or_empty(value, "PluginMcpServerConfig")
        _reject_unknown_fields(value, {"enabled", "default_tools_approval_mode", "enabled_tools", "disabled_tools", "tools"}, "PluginMcpServerConfig")
        tools_value = value.get("tools")
        if tools_value is not None and not isinstance(tools_value, Mapping):
            raise TypeError("tools must be a table")
        return cls(
            enabled=_optional_bool(value, "enabled") if "enabled" in value else True,
            default_tools_approval_mode=AppToolApproval.from_value(value["default_tools_approval_mode"]) if value.get("default_tools_approval_mode") is not None else None,
            enabled_tools=_optional_str_tuple(value, "enabled_tools"),
            disabled_tools=_optional_str_tuple(value, "disabled_tools"),
            tools={str(name): McpServerToolConfig.from_mapping(config) for name, config in (tools_value or {}).items()},
        )


@dataclass(frozen=True)
class PluginConfig:
    enabled: bool = True
    mcp_servers: dict[str, PluginMcpServerConfig] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "PluginConfig":
        value = _mapping_or_empty(value, "PluginConfig")
        _reject_unknown_fields(value, {"enabled", "mcp_servers"}, "PluginConfig")
        mcp_servers = value.get("mcp_servers")
        if mcp_servers is not None and not isinstance(mcp_servers, Mapping):
            raise TypeError("mcp_servers must be a table")
        return cls(
            enabled=_optional_bool(value, "enabled") if "enabled" in value else True,
            mcp_servers={str(name): PluginMcpServerConfig.from_mapping(config) for name, config in (mcp_servers or {}).items()},
        )


class MarketplaceSourceType(str, Enum):
    GIT = "git"
    LOCAL = "local"


@dataclass(frozen=True)
class MarketplaceConfig:
    last_updated: str | None = None
    last_revision: str | None = None
    source_type: MarketplaceSourceType | None = None
    source: str | None = None
    ref_name: str | None = None
    sparse_paths: tuple[str, ...] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "MarketplaceConfig":
        value = _mapping_or_empty(value, "MarketplaceConfig")
        _reject_unknown_fields(value, {"last_updated", "last_revision", "source_type", "source", "ref", "sparse_paths"}, "MarketplaceConfig")
        return cls(
            last_updated=_optional_str(value, "last_updated"),
            last_revision=_optional_str(value, "last_revision"),
            source_type=_optional_enum(value, "source_type", MarketplaceSourceType),
            source=_optional_str(value, "source"),
            ref_name=_optional_str(value, "ref"),
            sparse_paths=_optional_str_tuple(value, "sparse_paths"),
        )


@dataclass(frozen=True)
class SandboxWorkspaceWrite:
    writable_roots: tuple[Path, ...] = ()
    network_access: bool = False
    exclude_tmpdir_env_var: bool = False
    exclude_slash_tmp: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "SandboxWorkspaceWrite":
        value = _mapping_or_empty(value, "SandboxWorkspaceWrite")
        _reject_unknown_fields(value, {"writable_roots", "network_access", "exclude_tmpdir_env_var", "exclude_slash_tmp"}, "SandboxWorkspaceWrite")
        roots = tuple(Path(item) for item in _sequence(value.get("writable_roots", ()), "writable_roots"))
        return cls(
            writable_roots=roots,
            network_access=_optional_bool(value, "network_access") if "network_access" in value else False,
            exclude_tmpdir_env_var=_optional_bool(value, "exclude_tmpdir_env_var") if "exclude_tmpdir_env_var" in value else False,
            exclude_slash_tmp=_optional_bool(value, "exclude_slash_tmp") if "exclude_slash_tmp" in value else False,
        )

    def to_sandbox_settings(self) -> dict[str, Any]:
        return {
            "writable_roots": tuple(self.writable_roots),
            "network_access": self.network_access,
            "exclude_tmpdir_env_var": self.exclude_tmpdir_env_var,
            "exclude_slash_tmp": self.exclude_slash_tmp,
        }


@dataclass(frozen=True)
class ShellEnvironmentPolicyToml:
    inherit: str | None = None
    ignore_default_excludes: bool | None = None
    exclude: tuple[str, ...] | None = None
    set: dict[str, str] | None = None
    include_only: tuple[str, ...] | None = None
    experimental_use_profile: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ShellEnvironmentPolicyToml":
        value = _mapping_or_empty(value, "ShellEnvironmentPolicyToml")
        _reject_unknown_fields(value, {"inherit", "ignore_default_excludes", "exclude", "set", "include_only", "experimental_use_profile"}, "ShellEnvironmentPolicyToml")
        return cls(
            inherit=_optional_str(value, "inherit"),
            ignore_default_excludes=_optional_bool(value, "ignore_default_excludes"),
            exclude=_optional_str_tuple(value, "exclude"),
            set=_optional_str_mapping(value, "set"),
            include_only=_optional_str_tuple(value, "include_only"),
            experimental_use_profile=_optional_bool(value, "experimental_use_profile"),
        )

    def to_policy_mapping(self) -> dict[str, Any]:
        return {
            "inherit": self.inherit or "all",
            "ignore_default_excludes": True if self.ignore_default_excludes is None else self.ignore_default_excludes,
            "exclude": tuple(self.exclude or ()),
            "set": dict(self.set or {}),
            "include_only": tuple(self.include_only or ()),
            "use_profile": False if self.experimental_use_profile is None else self.experimental_use_profile,
        }

    def to_policy(self) -> ShellEnvironmentPolicy:
        mapping = self.to_policy_mapping()
        return ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit(mapping["inherit"]),
            ignore_default_excludes=mapping["ignore_default_excludes"],
            exclude=mapping["exclude"],
            set_values=mapping["set"],
            include_only=mapping["include_only"],
            use_profile=mapping["use_profile"],
        )


@dataclass(frozen=True)
class MemoriesToml:
    """Memories settings loaded from ``config.toml``."""

    disable_on_external_context: bool | None = None
    generate_memories: bool | None = None
    use_memories: bool | None = None
    dedicated_tools: bool | None = None
    max_raw_memories_for_consolidation: int | None = None
    max_unused_days: int | None = None
    max_rollout_age_days: int | None = None
    max_rollouts_per_startup: int | None = None
    min_rollout_idle_hours: int | None = None
    min_rate_limit_remaining_percent: int | None = None
    extract_model: str | None = None
    consolidation_model: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "MemoriesToml":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise TypeError("memories toml must be a mapping or None")
        disable = _optional_bool(value, "disable_on_external_context")
        legacy_disable = _optional_bool(value, "no_memories_if_mcp_or_web_search")
        return cls(
            disable_on_external_context=disable if disable is not None else legacy_disable,
            generate_memories=_optional_bool(value, "generate_memories"),
            use_memories=_optional_bool(value, "use_memories"),
            dedicated_tools=_optional_bool(value, "dedicated_tools"),
            max_raw_memories_for_consolidation=_optional_int(
                value, "max_raw_memories_for_consolidation"
            ),
            max_unused_days=_optional_int(value, "max_unused_days"),
            max_rollout_age_days=_optional_int(value, "max_rollout_age_days"),
            max_rollouts_per_startup=_optional_int(value, "max_rollouts_per_startup"),
            min_rollout_idle_hours=_optional_int(value, "min_rollout_idle_hours"),
            min_rate_limit_remaining_percent=_optional_int(
                value, "min_rate_limit_remaining_percent"
            ),
            extract_model=_optional_str(value, "extract_model"),
            consolidation_model=_optional_str(value, "consolidation_model"),
        )


@dataclass(frozen=True)
class MemoriesConfig:
    """Effective memories settings after defaults are applied."""

    disable_on_external_context: bool = False
    generate_memories: bool = True
    use_memories: bool = True
    dedicated_tools: bool = False
    max_raw_memories_for_consolidation: int = (
        DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION
    )
    max_unused_days: int = DEFAULT_MEMORIES_MAX_UNUSED_DAYS
    max_rollout_age_days: int = DEFAULT_MEMORIES_MAX_ROLLOUT_AGE_DAYS
    max_rollouts_per_startup: int = DEFAULT_MEMORIES_MAX_ROLLOUTS_PER_STARTUP
    min_rollout_idle_hours: int = DEFAULT_MEMORIES_MIN_ROLLOUT_IDLE_HOURS
    min_rate_limit_remaining_percent: int = (
        DEFAULT_MEMORIES_MIN_RATE_LIMIT_REMAINING_PERCENT
    )
    extract_model: str | None = None
    consolidation_model: str | None = None

    @classmethod
    def from_toml(
        cls, value: MemoriesToml | Mapping[str, Any] | None
    ) -> "MemoriesConfig":
        toml = value if isinstance(value, MemoriesToml) else MemoriesToml.from_mapping(value)
        defaults = cls()
        return cls(
            disable_on_external_context=_coalesce(
                toml.disable_on_external_context, defaults.disable_on_external_context
            ),
            generate_memories=_coalesce(toml.generate_memories, defaults.generate_memories),
            use_memories=_coalesce(toml.use_memories, defaults.use_memories),
            dedicated_tools=_coalesce(toml.dedicated_tools, defaults.dedicated_tools),
            max_raw_memories_for_consolidation=_clamp(
                _coalesce(
                    toml.max_raw_memories_for_consolidation,
                    defaults.max_raw_memories_for_consolidation,
                ),
                MIN_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION,
                MAX_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION,
            ),
            max_unused_days=_clamp(
                _coalesce(toml.max_unused_days, defaults.max_unused_days), 0, 365
            ),
            max_rollout_age_days=_clamp(
                _coalesce(toml.max_rollout_age_days, defaults.max_rollout_age_days),
                0,
                90,
            ),
            max_rollouts_per_startup=_clamp(
                _coalesce(
                    toml.max_rollouts_per_startup, defaults.max_rollouts_per_startup
                ),
                MIN_MEMORIES_MAX_ROLLOUTS_PER_STARTUP,
                MAX_MEMORIES_MAX_ROLLOUTS_PER_STARTUP,
            ),
            min_rollout_idle_hours=_clamp(
                _coalesce(toml.min_rollout_idle_hours, defaults.min_rollout_idle_hours),
                1,
                48,
            ),
            min_rate_limit_remaining_percent=_clamp(
                _coalesce(
                    toml.min_rate_limit_remaining_percent,
                    defaults.min_rate_limit_remaining_percent,
                ),
                0,
                100,
            ),
            extract_model=toml.extract_model,
            consolidation_model=toml.consolidation_model,
        )


def _optional_bool(value: Mapping[str, Any], key: str) -> bool | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise TypeError(f"{key} must be a bool or None")
    return item


def _optional_int(value: Mapping[str, Any], key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int):
        raise TypeError(f"{key} must be an integer or None")
    return item


def _optional_str(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string or None")
    return item


def _optional_path(value: Mapping[str, Any], key: str) -> Path | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str | Path):
        raise TypeError(f"{key} must be a path string or None")
    return Path(item)


def _optional_enum(value: Mapping[str, Any], key: str, enum_type: type[Enum]) -> Any | None:
    item = value.get(key)
    if item is None:
        return None
    if isinstance(item, enum_type):
        return item
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string or None")
    return enum_type(item)


def _required_enum(value: Mapping[str, Any], key: str, enum_type: type[Enum]) -> Any:
    item = _optional_enum(value, key, enum_type)
    if item is None:
        raise ValueError(f"{key} is required")
    return item


def _required_str(value: Mapping[str, Any], key: str) -> str:
    item = _optional_str(value, key)
    if item is None:
        raise ValueError(f"{key} is required")
    return item


def _optional_str_tuple(value: Mapping[str, Any], key: str) -> tuple[str, ...] | None:
    item = value.get(key)
    if item is None:
        return None
    return tuple(_sequence(item, key))


def _optional_str_mapping(value: Mapping[str, Any], key: str) -> dict[str, str] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise TypeError(f"{key} must be a table or None")
    result: dict[str, str] = {}
    for item_key, item_value in item.items():
        if not isinstance(item_key, str) or not isinstance(item_value, str):
            raise TypeError(f"{key} must map strings to strings")
        result[item_key] = item_value
    return result


def _optional_bool_mapping(value: Mapping[str, Any], key: str) -> dict[str, bool] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise TypeError(f"{key} must be a table or None")
    result: dict[str, bool] = {}
    for item_key, item_value in item.items():
        if not isinstance(item_key, str) or not isinstance(item_value, bool):
            raise TypeError(f"{key} must map strings to bools")
        result[item_key] = item_value
    return result


def _optional_int_mapping(value: Mapping[str, Any], key: str) -> dict[str, int] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise TypeError(f"{key} must be a table or None")
    result: dict[str, int] = {}
    for item_key, item_value in item.items():
        if not isinstance(item_key, str) or isinstance(item_value, bool) or not isinstance(item_value, int):
            raise TypeError(f"{key} must map strings to integers")
        result[item_key] = item_value
    return result


def _optional_nested_str_mapping(value: Mapping[str, Any], key: str) -> dict[str, dict[str, str]] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise TypeError(f"{key} must be a table or None")
    result: dict[str, dict[str, str]] = {}
    for item_key, item_value in item.items():
        if not isinstance(item_key, str) or not isinstance(item_value, Mapping):
            raise TypeError(f"{key} must map strings to tables")
        result[item_key] = _optional_str_mapping({"value": item_value}, "value") or {}
    return result


def _sequence(value: Any, key: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise TypeError(f"{key} must be an array")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} entries must be strings")
    return tuple(value)


def _mapping_sequence(value: Any, key: str) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise TypeError(f"{key} must be an array")
    if not all(isinstance(item, Mapping) for item in value):
        raise TypeError(f"{key} entries must be tables")
    return tuple(value)


def _mapping_or_empty(value: Mapping[str, Any] | None, type_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping or None")
    return value


def _reject_unknown_fields(value: Mapping[str, Any], allowed: set[str], type_name: str) -> None:
    unknown = [str(key) for key in value if key not in allowed]
    if unknown:
        raise ValueError(f"unknown fields for {type_name}: {', '.join(unknown)}")


def _coalesce(value: Any | None, default: Any) -> Any:
    return default if value is None else value


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


__all__ = [
    "AnalyticsConfigToml",
    "AltScreenMode",
    "AppConfig",
    "AppToolApproval",
    "AppToolConfig",
    "AppToolsConfig",
    "AppsConfigToml",
    "AppsDefaultConfig",
    "ApprovalsReviewer",
    "AuthCredentialsStoreMode",
    "BundledSkillsConfig",
    "DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION",
    "DEFAULT_MEMORIES_MAX_ROLLOUTS_PER_STARTUP",
    "DEFAULT_MEMORIES_MAX_ROLLOUT_AGE_DAYS",
    "DEFAULT_MEMORIES_MAX_UNUSED_DAYS",
    "DEFAULT_MEMORIES_MIN_RATE_LIMIT_REMAINING_PERCENT",
    "DEFAULT_MEMORIES_MIN_ROLLOUT_IDLE_HOURS",
    "DEFAULT_OTEL_ENVIRONMENT",
    "DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS",
    "ExternalConfigMigrationPrompts",
    "FeedbackConfigToml",
    "History",
    "HistoryPersistence",
    "KeybindingSpec",
    "KeybindingsSpec",
    "MAX_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION",
    "MAX_MEMORIES_MAX_ROLLOUTS_PER_STARTUP",
    "MIN_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION",
    "MIN_MEMORIES_MAX_ROLLOUTS_PER_STARTUP",
    "MarketplaceConfig",
    "MarketplaceSourceType",
    "MemoriesConfig",
    "MemoriesToml",
    "McpServerConfig",
    "McpServerDisabledReason",
    "McpServerEnvVar",
    "McpServerOAuthConfig",
    "McpServerToolConfig",
    "McpServerTransportConfig",
    "ModelAvailabilityNuxConfig",
    "ModeKind",
    "Notice",
    "NotificationCondition",
    "NotificationMethod",
    "Notifications",
    "OAuthCredentialsStoreMode",
    "OtelConfig",
    "OtelConfigToml",
    "OtelExporterKind",
    "OtelHttpProtocol",
    "OtelTlsConfig",
    "PluginConfig",
    "PluginMcpServerConfig",
    "Personality",
    "SandboxWorkspaceWrite",
    "SessionPickerViewMode",
    "ServiceTier",
    "ShellEnvironmentPolicy",
    "ShellEnvironmentPolicyInherit",
    "ShellEnvironmentPolicyToml",
    "SkillConfig",
    "SkillsConfig",
    "ToolSuggestConfig",
    "ToolSuggestDisabledTool",
    "ToolSuggestDiscoverable",
    "ToolSuggestDiscoverableType",
    "Tui",
    "TuiApprovalKeymap",
    "TuiChatKeymap",
    "TuiComposerKeymap",
    "TuiEditorKeymap",
    "TuiGlobalKeymap",
    "TuiKeymap",
    "TuiListKeymap",
    "TuiNotificationSettings",
    "TuiPagerKeymap",
    "TuiPetAnchor",
    "TuiVimNormalKeymap",
    "TuiVimOperatorKeymap",
    "TuiVimTextObjectKeymap",
    "UriBasedFileOpener",
    "WebSearchMode",
    "WindowsSandboxModeToml",
    "WindowsToml",
    "normalize_key_name",
    "normalize_keybinding_spec",
]
