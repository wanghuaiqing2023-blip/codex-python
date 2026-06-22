"""Feature flag registry ported from Codex's ``codex_features`` crate."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.protocol import Event, EventMsg, WarningEvent


LOGGER = logging.getLogger(__name__)


class StageKind(str, Enum):
    UNDER_DEVELOPMENT = "under_development"
    EXPERIMENTAL = "experimental"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


@dataclass(frozen=True)
class Stage:
    kind: StageKind
    name: str | None = None
    menu_description: str | None = None
    announcement: str | None = None

    @classmethod
    def under_development(cls) -> "Stage":
        return cls(StageKind.UNDER_DEVELOPMENT)

    @classmethod
    def experimental(
        cls,
        name: str,
        menu_description: str,
        announcement: str = "",
    ) -> "Stage":
        return cls(StageKind.EXPERIMENTAL, name, menu_description, announcement)

    @classmethod
    def stable(cls) -> "Stage":
        return cls(StageKind.STABLE)

    @classmethod
    def deprecated(cls) -> "Stage":
        return cls(StageKind.DEPRECATED)

    @classmethod
    def removed(cls) -> "Stage":
        return cls(StageKind.REMOVED)

    def experimental_menu_name(self) -> str | None:
        return self.name if self.kind is StageKind.EXPERIMENTAL else None

    def experimental_menu_description(self) -> str | None:
        return self.menu_description if self.kind is StageKind.EXPERIMENTAL else None

    def experimental_announcement(self) -> str | None:
        if self.kind is not StageKind.EXPERIMENTAL:
            return None
        return self.announcement or None


class Feature(Enum):
    SHELL_TOOL = "ShellTool"
    CODEX_HOOKS = "CodexHooks"
    CODE_MODE = "CodeMode"
    CODE_MODE_ONLY = "CodeModeOnly"
    UNIFIED_EXEC = "UnifiedExec"
    SHELL_ZSH_FORK = "ShellZshFork"
    TERMINAL_RESIZE_REFLOW = "TerminalResizeReflow"
    APPLY_PATCH_STREAMING_EVENTS = "ApplyPatchStreamingEvents"
    EXEC_PERMISSION_APPROVALS = "ExecPermissionApprovals"
    REQUEST_PERMISSIONS_TOOL = "RequestPermissionsTool"
    WEB_SEARCH_REQUEST = "WebSearchRequest"
    WEB_SEARCH_CACHED = "WebSearchCached"
    STANDALONE_WEB_SEARCH = "StandaloneWebSearch"
    USE_LEGACY_LANDLOCK = "UseLegacyLandlock"
    SHELL_SNAPSHOT = "ShellSnapshot"
    RUNTIME_METRICS = "RuntimeMetrics"
    MEMORY_TOOL = "MemoryTool"
    CHRONICLE = "Chronicle"
    CHILD_AGENTS_MD = "ChildAgentsMd"
    ENABLE_REQUEST_COMPRESSION = "EnableRequestCompression"
    NETWORK_PROXY = "NetworkProxy"
    COLLAB = "Collab"
    MULTI_AGENT_V2 = "MultiAgentV2"
    SPAWN_CSV = "SpawnCsv"
    APPS = "Apps"
    ENABLE_MCP_APPS = "EnableMcpApps"
    APPS_MCP_PATH_OVERRIDE = "AppsMcpPathOverride"
    TOOL_SEARCH = "ToolSearch"
    TOOL_SEARCH_ALWAYS_DEFER_MCP_TOOLS = "ToolSearchAlwaysDeferMcpTools"
    NON_PREFIXED_MCP_TOOL_NAMES = "NonPrefixedMcpToolNames"
    TOOL_SUGGEST = "ToolSuggest"
    PLUGINS = "Plugins"
    PLUGIN_HOOKS = "PluginHooks"
    IN_APP_BROWSER = "InAppBrowser"
    BROWSER_USE = "BrowserUse"
    BROWSER_USE_EXTERNAL = "BrowserUseExternal"
    COMPUTER_USE = "ComputerUse"
    REMOTE_PLUGIN = "RemotePlugin"
    PLUGIN_SHARING = "PluginSharing"
    EXTERNAL_MIGRATION = "ExternalMigration"
    IMAGE_GENERATION = "ImageGeneration"
    SKILL_MCP_DEPENDENCY_INSTALL = "SkillMcpDependencyInstall"
    SKILL_ENV_VAR_DEPENDENCY_PROMPT = "SkillEnvVarDependencyPrompt"
    MENTIONS_V2 = "MentionsV2"
    DEFAULT_MODE_REQUEST_USER_INPUT = "DefaultModeRequestUserInput"
    GUARDIAN_APPROVAL = "GuardianApproval"
    GOALS = "Goals"
    TOOL_CALL_MCP_ELICITATION = "ToolCallMcpElicitation"
    AUTH_ELICITATION = "AuthElicitation"
    PERSONALITY = "Personality"
    ARTIFACT = "Artifact"
    FAST_MODE = "FastMode"
    REALTIME_CONVERSATION = "RealtimeConversation"
    PREVENT_IDLE_SLEEP = "PreventIdleSleep"
    RESPONSES_WEBSOCKET_RESPONSE_PROCESSED = "ResponsesWebsocketResponseProcessed"
    REMOTE_COMPACTION_V2 = "RemoteCompactionV2"
    WORKSPACE_DEPENDENCIES = "WorkspaceDependencies"
    GHOST_COMMIT = "GhostCommit"
    JS_REPL = "JsRepl"
    JS_REPL_TOOLS_ONLY = "JsReplToolsOnly"
    SEARCH_TOOL = "SearchTool"
    USE_LINUX_SANDBOX_BWRAP = "UseLinuxSandboxBwrap"
    REQUEST_RULE = "RequestRule"
    WINDOWS_SANDBOX = "WindowsSandbox"
    WINDOWS_SANDBOX_ELEVATED = "WindowsSandboxElevated"
    REMOTE_MODELS = "RemoteModels"
    CODEX_GIT_COMMIT = "CodexGitCommit"
    SQLITE = "Sqlite"
    APPLY_PATCH_FREEFORM = "ApplyPatchFreeform"
    UNAVAILABLE_DUMMY_TOOLS = "UnavailableDummyTools"
    STEER = "Steer"
    COLLABORATION_MODES = "CollaborationModes"
    REMOTE_CONTROL = "RemoteControl"
    IMAGE_DETAIL_ORIGINAL = "ImageDetailOriginal"
    TUI_APP_SERVER = "TuiAppServer"
    WORKSPACE_OWNER_USAGE_NUDGE = "WorkspaceOwnerUsageNudge"
    RESPONSES_WEBSOCKETS = "ResponsesWebsockets"
    RESPONSES_WEBSOCKETS_V2 = "ResponsesWebsocketsV2"

    def key(self) -> str:
        return self.info().key

    def stage(self) -> Stage:
        return self.info().stage

    def default_enabled(self) -> bool:
        return self.info().default_enabled

    def info(self) -> "FeatureSpec":
        try:
            return _FEATURE_SPECS_BY_ID[self]
        except KeyError as exc:
            raise RuntimeError(f"missing FeatureSpec for {self!r}") from exc


@dataclass(frozen=True)
class LegacyFeatureUsage:
    alias: str
    feature: Feature
    summary: str
    details: str | None = None


@dataclass(frozen=True)
class FeatureSpec:
    id: Feature
    key: str
    stage: Stage
    default_enabled: bool


@dataclass
class MultiAgentV2ConfigToml:
    enabled: bool | None = None
    max_concurrent_threads_per_session: int | None = None
    min_wait_timeout_ms: int | None = None
    max_wait_timeout_ms: int | None = None
    default_wait_timeout_ms: int | None = None
    usage_hint_enabled: bool | None = None
    usage_hint_text: str | None = None
    root_agent_usage_hint_text: str | None = None
    subagent_usage_hint_text: str | None = None
    tool_namespace: str | None = None
    hide_spawn_agent_metadata: bool | None = None
    non_code_mode_only: bool | None = None

    def feature_enabled(self) -> bool | None:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


@dataclass
class AppsMcpPathOverrideConfigToml:
    enabled: bool | None = None
    path: str | None = None

    def feature_enabled(self) -> bool | None:
        if self.enabled is not None:
            return self.enabled
        return True if self.path is not None else None

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


class NetworkProxyModeToml(str, Enum):
    LIMITED = "limited"
    FULL = "full"


class NetworkProxyDomainPermissionToml(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class NetworkProxyUnixSocketPermissionToml(str, Enum):
    ALLOW = "allow"
    NONE = "none"


@dataclass
class NetworkProxyConfigToml:
    enabled: bool | None = None
    proxy_url: str | None = None
    enable_socks5: bool | None = None
    socks_url: str | None = None
    enable_socks5_udp: bool | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    mode: NetworkProxyModeToml | None = None
    domains: Mapping[str, NetworkProxyDomainPermissionToml] | None = None
    unix_sockets: Mapping[str, NetworkProxyUnixSocketPermissionToml] | None = None
    allow_local_binding: bool | None = None

    def feature_enabled(self) -> bool | None:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


FeatureConfig = MultiAgentV2ConfigToml | AppsMcpPathOverrideConfigToml | NetworkProxyConfigToml


@dataclass
class FeatureToml:
    value: bool | FeatureConfig

    @classmethod
    def enabled_toggle(cls, enabled: bool) -> "FeatureToml":
        return cls(bool(enabled))

    @classmethod
    def config(cls, config: FeatureConfig) -> "FeatureToml":
        return cls(config)

    @classmethod
    def from_value(cls, value: bool | Mapping[str, Any], config_type: type[FeatureConfig]) -> "FeatureToml":
        if isinstance(value, bool):
            return cls.enabled_toggle(value)
        if isinstance(value, Mapping):
            return cls.config(_config_from_mapping(config_type, value))
        raise TypeError("feature config must be a bool or mapping")

    def enabled(self) -> bool | None:
        if isinstance(self.value, bool):
            return self.value
        return self.value.feature_enabled()

    def set_enabled(self, enabled: bool) -> None:
        if isinstance(self.value, bool):
            self.value = bool(enabled)
        else:
            self.value.set_enabled(bool(enabled))


@dataclass
class FeaturesToml:
    multi_agent_v2: FeatureToml | None = None
    apps_mcp_path_override: FeatureToml | None = None
    network_proxy: FeatureToml | None = None
    _entries: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_entries(cls, entries: Mapping[str, bool]) -> "FeaturesToml":
        return cls(_entries={str(key): bool(value) for key, value in entries.items()})

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "FeaturesToml":
        entries: dict[str, bool] = {}
        multi_agent_v2: FeatureToml | None = None
        apps_mcp_path_override: FeatureToml | None = None
        network_proxy: FeatureToml | None = None

        for key, value in values.items():
            if key == "multi_agent_v2":
                multi_agent_v2 = FeatureToml.from_value(value, MultiAgentV2ConfigToml)
            elif key == "apps_mcp_path_override":
                apps_mcp_path_override = FeatureToml.from_value(value, AppsMcpPathOverrideConfigToml)
            elif key == "network_proxy":
                network_proxy = FeatureToml.from_value(value, NetworkProxyConfigToml)
            elif isinstance(value, bool):
                entries[str(key)] = value
            else:
                raise TypeError(f"feature `{key}` must be a bool or known config table")

        return cls(
            multi_agent_v2=multi_agent_v2,
            apps_mcp_path_override=apps_mcp_path_override,
            network_proxy=network_proxy,
            _entries=entries,
        )

    def entries(self) -> dict[str, bool]:
        entries = dict(self._entries)
        _insert_feature_enabled(entries, Feature.MULTI_AGENT_V2, self.multi_agent_v2)
        _insert_feature_enabled(entries, Feature.APPS_MCP_PATH_OVERRIDE, self.apps_mcp_path_override)
        _insert_feature_enabled(entries, Feature.NETWORK_PROXY, self.network_proxy)
        return entries

    def materialize_resolved_enabled(self, features: "Features") -> None:
        for key in legacy_feature_keys():
            self._entries.pop(key, None)

        for spec in FEATURES:
            enabled = features.enabled(spec.id)
            if spec.id is Feature.MULTI_AGENT_V2:
                self.multi_agent_v2 = _materialize_resolved_feature_enabled(self.multi_agent_v2, enabled)
            elif spec.id is Feature.APPS_MCP_PATH_OVERRIDE:
                self.apps_mcp_path_override = _materialize_resolved_feature_enabled(
                    self.apps_mcp_path_override,
                    enabled,
                )
            elif spec.id is Feature.NETWORK_PROXY:
                self.network_proxy = _materialize_resolved_feature_enabled(self.network_proxy, enabled)
            else:
                self._entries[spec.key] = enabled


@dataclass(frozen=True)
class FeatureOverrides:
    web_search_request: bool | None = None

    def apply(self, features: "Features") -> None:
        if self.web_search_request is None:
            return
        features.set_enabled(Feature.WEB_SEARCH_REQUEST, self.web_search_request)
        features.record_legacy_usage("web_search_request", Feature.WEB_SEARCH_REQUEST)


@dataclass(frozen=True)
class FeatureConfigSource:
    features: FeaturesToml | None = None
    experimental_use_unified_exec_tool: bool | None = None


class Features:
    """Effective enabled feature set with legacy-usage tracking."""

    def __init__(
        self,
        enabled: Sequence[Feature] | set[Feature] | None = None,
        legacy_usages: Sequence[LegacyFeatureUsage] | set[LegacyFeatureUsage] | None = None,
    ) -> None:
        self._enabled: set[Feature] = set(enabled or ())
        self._legacy_usages: set[LegacyFeatureUsage] = set(legacy_usages or ())

    @classmethod
    def with_defaults(cls) -> "Features":
        return cls(spec.id for spec in FEATURES if spec.default_enabled)

    @classmethod
    def from_sources(
        cls,
        base: FeatureConfigSource | None = None,
        profile: FeatureConfigSource | None = None,
        overrides: FeatureOverrides | None = None,
    ) -> "Features":
        features = cls.with_defaults()
        for source in (base or FeatureConfigSource(), profile or FeatureConfigSource()):
            _apply_legacy_feature_toggles(features, source.experimental_use_unified_exec_tool)
            if source.features is not None:
                features.apply_toml(source.features)
        (overrides or FeatureOverrides()).apply(features)
        features.normalize_dependencies()
        return features

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Features)
            and self._enabled == other._enabled
            and self._legacy_usages == other._legacy_usages
        )

    def __repr__(self) -> str:
        enabled = ", ".join(feature.key() for feature in self.enabled_features())
        return f"Features(enabled=[{enabled}])"

    def enabled(self, feature: Feature) -> bool:
        return feature in self._enabled

    def apps_enabled_for_auth(self, has_chatgpt_auth: bool) -> bool:
        return self.enabled(Feature.APPS) and has_chatgpt_auth

    def use_legacy_landlock(self) -> bool:
        return self.enabled(Feature.USE_LEGACY_LANDLOCK)

    def enable(self, feature: Feature) -> "Features":
        self._enabled.add(feature)
        return self

    def disable(self, feature: Feature) -> "Features":
        self._enabled.discard(feature)
        return self

    def set_enabled(self, feature: Feature, enabled: bool) -> "Features":
        return self.enable(feature) if enabled else self.disable(feature)

    def record_legacy_usage_force(self, alias: str, feature: Feature) -> None:
        summary, details = legacy_usage_notice(alias, feature)
        self._legacy_usages.add(LegacyFeatureUsage(alias, feature, summary, details))

    def record_legacy_usage(self, alias: str, feature: Feature) -> None:
        if alias != feature.key():
            self.record_legacy_usage_force(alias, feature)

    def legacy_feature_usages(self) -> tuple[LegacyFeatureUsage, ...]:
        return tuple(
            sorted(
                self._legacy_usages,
                key=lambda usage: (usage.alias, usage.feature.key(), usage.summary, usage.details or ""),
            )
        )

    def apply_map(self, values: Mapping[str, bool]) -> None:
        for key in sorted(values):
            enabled = bool(values[key])
            if key == "web_search_request":
                self.record_legacy_usage_force("features.web_search_request", Feature.WEB_SEARCH_REQUEST)
            elif key == "web_search_cached":
                self.record_legacy_usage_force("features.web_search_cached", Feature.WEB_SEARCH_CACHED)
            elif key in _IGNORED_REMOVED_FEATURE_KEYS:
                continue
            elif key == "use_legacy_landlock":
                self.record_legacy_usage_force("features.use_legacy_landlock", Feature.USE_LEGACY_LANDLOCK)

            feature = feature_for_key(key)
            if feature is None:
                LOGGER.warning("unknown feature key in config: %s", key)
                continue
            if feature is Feature.TUI_APP_SERVER:
                continue
            if key != feature.key():
                self.record_legacy_usage(key, feature)
            self.set_enabled(feature, enabled)

    def apply_toml(self, features: FeaturesToml) -> None:
        self.apply_map(features.entries())

    def enabled_features(self) -> list[Feature]:
        return [feature for feature in Feature if feature in self._enabled]

    def normalize_dependencies(self) -> None:
        if self.enabled(Feature.SPAWN_CSV) and not self.enabled(Feature.COLLAB):
            self.enable(Feature.COLLAB)
        if self.enabled(Feature.CODE_MODE_ONLY) and not self.enabled(Feature.CODE_MODE):
            self.enable(Feature.CODE_MODE)

    def emit_metrics(self, telemetry: Any) -> None:
        counter = getattr(telemetry, "counter", None)
        if not callable(counter):
            return
        for spec in FEATURES:
            if spec.stage.kind is StageKind.REMOVED:
                continue
            enabled = self.enabled(spec.id)
            if enabled != spec.default_enabled:
                counter(
                    "codex.feature.state",
                    1,
                    [("feature", spec.key), ("value", str(enabled).lower())],
                )


def legacy_usage_notice(alias: str, feature: Feature) -> tuple[str, str | None]:
    canonical = feature.key()
    if feature in (Feature.WEB_SEARCH_REQUEST, Feature.WEB_SEARCH_CACHED):
        label = {
            "web_search": "[features].web_search",
            "features.web_search_request": "[features].web_search_request",
            "web_search_request": "[features].web_search_request",
            "features.web_search_cached": "[features].web_search_cached",
            "web_search_cached": "[features].web_search_cached",
        }.get(alias, alias)
        summary = f"`{label}` is deprecated because web search is enabled by default."
        return summary, web_search_details()

    if feature is Feature.USE_LEGACY_LANDLOCK:
        label = {
            "features.use_legacy_landlock": "[features].use_legacy_landlock",
            "use_legacy_landlock": "[features].use_legacy_landlock",
        }.get(alias, alias)
        summary = f"`{label}` is deprecated and will be removed soon."
        details = "Remove this setting to stop opting into the legacy Linux sandbox behavior."
        return summary, details

    label = alias if "." in alias or alias.startswith("[") else f"[features].{alias}"
    summary = f"`{label}` is deprecated. Use `[features].{canonical}` instead."
    details = None
    if alias != canonical:
        details = (
            f"Enable it with `--enable {canonical}` or `[features].{canonical}` in config.toml. "
            "See https://developers.openai.com/codex/config-basic#feature-flags for details."
        )
    return summary, details


def web_search_details() -> str:
    return (
        "Set `web_search` to `\"live\"`, `\"cached\"`, or `\"disabled\"` at the top level "
        "(or under a profile) in config.toml if you want to override it."
    )


def legacy_feature_keys() -> tuple[str, ...]:
    return tuple(_LEGACY_ALIASES)


def feature_for_key(key: str) -> Feature | None:
    spec = _FEATURE_SPECS_BY_KEY.get(key)
    if spec is not None:
        return spec.id
    feature = _LEGACY_ALIASES.get(key)
    if feature is not None:
        _log_alias(key, feature)
    return feature


def canonical_feature_for_key(key: str) -> Feature | None:
    spec = _FEATURE_SPECS_BY_KEY.get(key)
    return None if spec is None else spec.id


def is_known_feature_key(key: str) -> bool:
    return feature_for_key(key) is not None


def unstable_features_warning_event(
    effective_features: Mapping[str, Any] | None,
    suppress_unstable_features_warning: bool,
    features: Features,
    config_path: str,
) -> Event | None:
    if suppress_unstable_features_warning:
        return None

    under_development_feature_keys: list[str] = []
    if effective_features is not None:
        for key, value in effective_features.items():
            if value is not True:
                continue
            spec = _FEATURE_SPECS_BY_KEY.get(key)
            if spec is None:
                continue
            if not features.enabled(spec.id):
                continue
            if spec.stage.kind is StageKind.UNDER_DEVELOPMENT:
                under_development_feature_keys.append(spec.key)

    if not under_development_feature_keys:
        return None

    joined = ", ".join(under_development_feature_keys)
    message = (
        f"Under-development features enabled: {joined}. Under-development features are incomplete "
        "and may behave unpredictably. To suppress this warning, set "
        f"`suppress_unstable_features_warning = true` in {config_path}."
    )
    return Event("", EventMsg.with_payload("warning", WarningEvent(message)))


def _insert_feature_enabled(entries: dict[str, bool], feature: Feature, feature_toml: FeatureToml | None) -> None:
    if feature_toml is None:
        return
    enabled = feature_toml.enabled()
    if enabled is not None:
        entries[feature.key()] = enabled


def _materialize_resolved_feature_enabled(feature_toml: FeatureToml | None, enabled: bool) -> FeatureToml:
    if feature_toml is None:
        return FeatureToml.enabled_toggle(enabled)
    feature_toml.set_enabled(enabled)
    return feature_toml


def _config_from_mapping(config_type: type[FeatureConfig], values: Mapping[str, Any]) -> FeatureConfig:
    allowed = set(config_type.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = set(values) - allowed
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise TypeError(f"unknown fields for {config_type.__name__}: {unknown_list}")

    data = dict(values)
    if config_type is NetworkProxyConfigToml and isinstance(data.get("mode"), str):
        data["mode"] = NetworkProxyModeToml(data["mode"])
    if config_type is NetworkProxyConfigToml and isinstance(data.get("domains"), Mapping):
        data["domains"] = {
            str(key): (value if isinstance(value, NetworkProxyDomainPermissionToml) else NetworkProxyDomainPermissionToml(value))
            for key, value in data["domains"].items()
        }
    if config_type is NetworkProxyConfigToml and isinstance(data.get("unix_sockets"), Mapping):
        data["unix_sockets"] = {
            str(key): (
                value
                if isinstance(value, NetworkProxyUnixSocketPermissionToml)
                else NetworkProxyUnixSocketPermissionToml(value)
            )
            for key, value in data["unix_sockets"].items()
        }
    return config_type(**data)


def _apply_legacy_feature_toggles(
    features: Features,
    experimental_use_unified_exec_tool: bool | None,
) -> None:
    if experimental_use_unified_exec_tool is None:
        return
    features.set_enabled(Feature.UNIFIED_EXEC, experimental_use_unified_exec_tool)
    _log_alias("experimental_use_unified_exec_tool", Feature.UNIFIED_EXEC)
    features.record_legacy_usage("experimental_use_unified_exec_tool", Feature.UNIFIED_EXEC)


def _log_alias(alias: str, feature: Feature) -> None:
    canonical = feature.key()
    if alias == canonical:
        return
    LOGGER.info(
        "legacy feature toggle detected; prefer `[features].%s`",
        canonical,
        extra={"alias": alias, "canonical": canonical},
    )


def _prevent_idle_sleep_stage() -> Stage:
    if sys.platform == "darwin" or sys.platform.startswith("linux") or sys.platform == "win32":
        return Stage.experimental(
            name="Prevent sleep while running",
            menu_description="Keep your computer awake while Codex is running a thread.",
            announcement="NEW: Prevent sleep while running is now available in /experimental.",
        )
    return Stage.under_development()


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec(Feature.GHOST_COMMIT, "undo", Stage.removed(), False),
    FeatureSpec(Feature.SHELL_TOOL, "shell_tool", Stage.stable(), True),
    FeatureSpec(Feature.UNIFIED_EXEC, "unified_exec", Stage.stable(), sys.platform != "win32"),
    FeatureSpec(Feature.SHELL_ZSH_FORK, "shell_zsh_fork", Stage.under_development(), False),
    FeatureSpec(Feature.SHELL_SNAPSHOT, "shell_snapshot", Stage.stable(), True),
    FeatureSpec(Feature.JS_REPL, "js_repl", Stage.removed(), False),
    FeatureSpec(Feature.CODE_MODE, "code_mode", Stage.under_development(), False),
    FeatureSpec(Feature.CODE_MODE_ONLY, "code_mode_only", Stage.under_development(), False),
    FeatureSpec(Feature.JS_REPL_TOOLS_ONLY, "js_repl_tools_only", Stage.removed(), False),
    FeatureSpec(
        Feature.TERMINAL_RESIZE_REFLOW,
        "terminal_resize_reflow",
        Stage.experimental(
            name="Terminal resize reflow",
            menu_description="Rebuild Codex-owned transcript scrollback when the terminal width changes.",
        ),
        True,
    ),
    FeatureSpec(Feature.WEB_SEARCH_REQUEST, "web_search_request", Stage.deprecated(), False),
    FeatureSpec(Feature.WEB_SEARCH_CACHED, "web_search_cached", Stage.deprecated(), False),
    FeatureSpec(Feature.STANDALONE_WEB_SEARCH, "standalone_web_search", Stage.under_development(), False),
    FeatureSpec(Feature.SEARCH_TOOL, "search_tool", Stage.removed(), False),
    FeatureSpec(Feature.CODEX_GIT_COMMIT, "codex_git_commit", Stage.removed(), False),
    FeatureSpec(Feature.RUNTIME_METRICS, "runtime_metrics", Stage.under_development(), False),
    FeatureSpec(Feature.SQLITE, "sqlite", Stage.removed(), True),
    FeatureSpec(
        Feature.MEMORY_TOOL,
        "memories",
        Stage.experimental(
            name="Memories",
            menu_description=(
                "Allow Codex to create new memories from conversations and bring relevant memories "
                "into new conversations."
            ),
            announcement="NEW: Codex can now generate and use memories. Try it now with `/memories`",
        ),
        False,
    ),
    FeatureSpec(Feature.CHRONICLE, "chronicle", Stage.under_development(), False),
    FeatureSpec(Feature.CHILD_AGENTS_MD, "child_agents_md", Stage.under_development(), False),
    FeatureSpec(Feature.APPLY_PATCH_FREEFORM, "apply_patch_freeform", Stage.removed(), False),
    FeatureSpec(Feature.APPLY_PATCH_STREAMING_EVENTS, "apply_patch_streaming_events", Stage.under_development(), False),
    FeatureSpec(Feature.EXEC_PERMISSION_APPROVALS, "exec_permission_approvals", Stage.under_development(), False),
    FeatureSpec(Feature.CODEX_HOOKS, "hooks", Stage.stable(), True),
    FeatureSpec(Feature.REQUEST_PERMISSIONS_TOOL, "request_permissions_tool", Stage.under_development(), False),
    FeatureSpec(Feature.USE_LINUX_SANDBOX_BWRAP, "use_linux_sandbox_bwrap", Stage.removed(), False),
    FeatureSpec(Feature.USE_LEGACY_LANDLOCK, "use_legacy_landlock", Stage.deprecated(), False),
    FeatureSpec(Feature.REQUEST_RULE, "request_rule", Stage.removed(), False),
    FeatureSpec(Feature.WINDOWS_SANDBOX, "experimental_windows_sandbox", Stage.removed(), False),
    FeatureSpec(Feature.WINDOWS_SANDBOX_ELEVATED, "elevated_windows_sandbox", Stage.removed(), False),
    FeatureSpec(Feature.REMOTE_MODELS, "remote_models", Stage.removed(), False),
    FeatureSpec(Feature.ENABLE_REQUEST_COMPRESSION, "enable_request_compression", Stage.stable(), True),
    FeatureSpec(
        Feature.NETWORK_PROXY,
        "network_proxy",
        Stage.experimental(
            name="Network proxy",
            menu_description="Apply network proxy restrictions to sandboxed sessions that already have network access.",
            announcement="NEW: Network proxy can now be enabled from /experimental. Restart Codex after enabling it.",
        ),
        False,
    ),
    FeatureSpec(Feature.COLLAB, "multi_agent", Stage.stable(), True),
    FeatureSpec(Feature.MULTI_AGENT_V2, "multi_agent_v2", Stage.under_development(), False),
    FeatureSpec(Feature.SPAWN_CSV, "enable_fanout", Stage.under_development(), False),
    FeatureSpec(Feature.APPS, "apps", Stage.stable(), True),
    FeatureSpec(Feature.ENABLE_MCP_APPS, "enable_mcp_apps", Stage.under_development(), False),
    FeatureSpec(Feature.APPS_MCP_PATH_OVERRIDE, "apps_mcp_path_override", Stage.under_development(), False),
    FeatureSpec(Feature.TOOL_SEARCH, "tool_search", Stage.removed(), False),
    FeatureSpec(Feature.TOOL_SEARCH_ALWAYS_DEFER_MCP_TOOLS, "tool_search_always_defer_mcp_tools", Stage.under_development(), False),
    FeatureSpec(Feature.NON_PREFIXED_MCP_TOOL_NAMES, "non_prefixed_mcp_tool_names", Stage.under_development(), False),
    FeatureSpec(Feature.UNAVAILABLE_DUMMY_TOOLS, "unavailable_dummy_tools", Stage.removed(), False),
    FeatureSpec(Feature.TOOL_SUGGEST, "tool_suggest", Stage.stable(), True),
    FeatureSpec(Feature.PLUGINS, "plugins", Stage.stable(), True),
    FeatureSpec(Feature.PLUGIN_HOOKS, "plugin_hooks", Stage.removed(), False),
    FeatureSpec(Feature.IN_APP_BROWSER, "in_app_browser", Stage.stable(), True),
    FeatureSpec(Feature.BROWSER_USE, "browser_use", Stage.stable(), True),
    FeatureSpec(Feature.BROWSER_USE_EXTERNAL, "browser_use_external", Stage.stable(), True),
    FeatureSpec(Feature.COMPUTER_USE, "computer_use", Stage.stable(), True),
    FeatureSpec(Feature.REMOTE_PLUGIN, "remote_plugin", Stage.under_development(), False),
    FeatureSpec(Feature.PLUGIN_SHARING, "plugin_sharing", Stage.stable(), True),
    FeatureSpec(
        Feature.EXTERNAL_MIGRATION,
        "external_migration",
        Stage.experimental(
            name="External migration",
            menu_description=(
                "Show a startup prompt when Codex detects migratable external agent config for this "
                "machine or project."
            ),
        ),
        False,
    ),
    FeatureSpec(Feature.IMAGE_GENERATION, "image_generation", Stage.stable(), True),
    FeatureSpec(Feature.SKILL_MCP_DEPENDENCY_INSTALL, "skill_mcp_dependency_install", Stage.stable(), True),
    FeatureSpec(Feature.SKILL_ENV_VAR_DEPENDENCY_PROMPT, "skill_env_var_dependency_prompt", Stage.removed(), False),
    FeatureSpec(
        Feature.MENTIONS_V2,
        "mentions_v2",
        Stage.experimental(
            name="Mentions v2",
            menu_description="Use a unified @ mention popup for files, folders, apps, plugins, and skills.",
        ),
        False,
    ),
    FeatureSpec(Feature.STEER, "steer", Stage.removed(), True),
    FeatureSpec(Feature.DEFAULT_MODE_REQUEST_USER_INPUT, "default_mode_request_user_input", Stage.under_development(), False),
    FeatureSpec(Feature.GUARDIAN_APPROVAL, "guardian_approval", Stage.stable(), True),
    FeatureSpec(Feature.GOALS, "goals", Stage.stable(), True),
    FeatureSpec(Feature.COLLABORATION_MODES, "collaboration_modes", Stage.removed(), True),
    FeatureSpec(Feature.TOOL_CALL_MCP_ELICITATION, "tool_call_mcp_elicitation", Stage.stable(), True),
    FeatureSpec(Feature.AUTH_ELICITATION, "auth_elicitation", Stage.under_development(), False),
    FeatureSpec(Feature.PERSONALITY, "personality", Stage.stable(), True),
    FeatureSpec(Feature.ARTIFACT, "artifact", Stage.under_development(), False),
    FeatureSpec(Feature.FAST_MODE, "fast_mode", Stage.stable(), True),
    FeatureSpec(Feature.REALTIME_CONVERSATION, "realtime_conversation", Stage.under_development(), False),
    FeatureSpec(Feature.REMOTE_CONTROL, "remote_control", Stage.removed(), False),
    FeatureSpec(Feature.IMAGE_DETAIL_ORIGINAL, "image_detail_original", Stage.removed(), False),
    FeatureSpec(Feature.TUI_APP_SERVER, "tui_app_server", Stage.removed(), True),
    FeatureSpec(Feature.PREVENT_IDLE_SLEEP, "prevent_idle_sleep", _prevent_idle_sleep_stage(), False),
    FeatureSpec(Feature.WORKSPACE_OWNER_USAGE_NUDGE, "workspace_owner_usage_nudge", Stage.removed(), False),
    FeatureSpec(Feature.RESPONSES_WEBSOCKETS, "responses_websockets", Stage.removed(), False),
    FeatureSpec(Feature.RESPONSES_WEBSOCKETS_V2, "responses_websockets_v2", Stage.removed(), False),
    FeatureSpec(
        Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED,
        "responses_websocket_response_processed",
        Stage.under_development(),
        False,
    ),
    FeatureSpec(Feature.REMOTE_COMPACTION_V2, "remote_compaction_v2", Stage.under_development(), False),
    FeatureSpec(Feature.WORKSPACE_DEPENDENCIES, "workspace_dependencies", Stage.stable(), True),
)

_FEATURE_SPECS_BY_ID = {spec.id: spec for spec in FEATURES}
_FEATURE_SPECS_BY_KEY = {spec.key: spec for spec in FEATURES}

_LEGACY_ALIASES: dict[str, Feature] = {
    "connectors": Feature.APPS,
    "enable_experimental_windows_sandbox": Feature.WINDOWS_SANDBOX,
    "experimental_use_unified_exec_tool": Feature.UNIFIED_EXEC,
    "request_permissions": Feature.EXEC_PERMISSION_APPROVALS,
    "web_search": Feature.WEB_SEARCH_REQUEST,
    "collab": Feature.COLLAB,
    "memory_tool": Feature.MEMORY_TOOL,
    "telepathy": Feature.CHRONICLE,
    "codex_hooks": Feature.CODEX_HOOKS,
}

_IGNORED_REMOVED_FEATURE_KEYS = {
    "tui_app_server",
    "undo",
    "js_repl",
    "js_repl_tools_only",
    "remote_control",
    "apply_patch_freeform",
    "tool_search",
    "image_detail_original",
    "plugin_hooks",
    "skill_env_var_dependency_prompt",
}


__all__ = [
    "AppsMcpPathOverrideConfigToml",
    "Feature",
    "FeatureConfigSource",
    "FeatureOverrides",
    "FEATURES",
    "FeatureSpec",
    "FeatureToml",
    "Features",
    "FeaturesToml",
    "LegacyFeatureUsage",
    "MultiAgentV2ConfigToml",
    "NetworkProxyConfigToml",
    "NetworkProxyDomainPermissionToml",
    "NetworkProxyModeToml",
    "NetworkProxyUnixSocketPermissionToml",
    "Stage",
    "StageKind",
    "canonical_feature_for_key",
    "feature_for_key",
    "is_known_feature_key",
    "legacy_feature_keys",
    "legacy_usage_notice",
    "unstable_features_warning_event",
    "web_search_details",
]
