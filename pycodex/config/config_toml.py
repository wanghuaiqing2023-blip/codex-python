"""Schema-heavy config.toml data shapes ported from ``codex-config``.

This module is being ported in focused slices because Rust ``ConfigToml`` owns a
large number of optional configuration surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol import (
    AskForApproval,
    AutoCompactTokenLimitScope,
    ForcedLoginMethod,
    RealtimeConversationVersion,
    RealtimeVoice,
    ReasoningEffort,
    ReasoningSummary,
    SandboxMode,
    Verbosity,
)
from pycodex.protocol.config_types import Personality, TrustLevel, WebSearchMode, WebSearchToolConfig, WindowsSandboxLevel
from pycodex.protocol.models import NetworkSandboxPolicy, PermissionProfile
from pycodex.model_provider_info import (
    AMAZON_BEDROCK_PROVIDER_ID,
    LEGACY_OLLAMA_CHAT_PROVIDER_ID,
    LMSTUDIO_OSS_PROVIDER_ID,
    ModelProviderAwsAuthInfo,
    ModelProviderInfo,
    OLLAMA_CHAT_PROVIDER_REMOVED_ERROR,
    OLLAMA_OSS_PROVIDER_ID,
)

from . import toml_compat as _toml
from .hook_config import HooksToml
from .mcp_types import McpServerConfig
from .permissions_toml import PermissionsToml
from .profile_toml import ConfigProfile
from .skills_config import SkillsConfig
from .types import (
    AnalyticsConfigToml,
    AppsConfigToml,
    ApprovalsReviewer,
    AuthCredentialsStoreMode,
    FeedbackConfigToml,
    History,
    MarketplaceConfig,
    MemoriesToml,
    Notice,
    OAuthCredentialsStoreMode,
    OtelConfigToml,
    PluginConfig,
    SandboxWorkspaceWrite,
    ShellEnvironmentPolicyToml,
    ToolSuggestConfig,
    Tui,
    UriBasedFileOpener,
    WindowsToml,
)

JsonValue = Any

DEFAULT_PROJECT_DOC_MAX_BYTES = 32 * 1024
RESERVED_MODEL_PROVIDER_IDS = {"amazon-bedrock", "openai", "ollama", "lmstudio"}
FORCED_CHATGPT_WORKSPACE_ID_ERROR = (
    "forced_chatgpt_workspace_id must be a single workspace ID string or a TOML list "
    "of strings; comma-separated strings are not supported. Use "
    '`forced_chatgpt_workspace_id = ["123e4567-e89b-42d3-a456-426614174000", '
    '"123e4567-e89b-42d3-a456-426614174001"]` instead.'
)


@dataclass(frozen=True)
class ForcedChatgptWorkspaceIds:
    values: tuple[str, ...]

    @classmethod
    def from_value(cls, value: JsonValue) -> "ForcedChatgptWorkspaceIds":
        if isinstance(value, str):
            if "," in value:
                raise ValueError(FORCED_CHATGPT_WORKSPACE_ID_ERROR)
            return cls((value,))
        if isinstance(value, list):
            if not all(isinstance(item, str) for item in value):
                raise TypeError("forced_chatgpt_workspace_id list values must be strings")
            return cls(tuple(value))
        raise TypeError("forced_chatgpt_workspace_id must be a string or list of strings")

    @classmethod
    def single(cls, value: str) -> "ForcedChatgptWorkspaceIds":
        return cls.from_value(value)

    @classmethod
    def multiple(cls, values: list[str] | tuple[str, ...]) -> "ForcedChatgptWorkspaceIds":
        return cls.from_value(list(values))

    def into_vec(self) -> list[str]:
        return list(self.values)


@dataclass(frozen=True)
class DebugConfigLockToml:
    export_dir: Path | None = None
    load_path: Path | None = None
    allow_codex_version_mismatch: bool | None = None
    save_fields_resolved_from_model_catalog: bool | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "DebugConfigLockToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("debug.config_lockfile must be a mapping")
        return cls(
            export_dir=Path(value["export_dir"]) if value.get("export_dir") is not None else None,
            load_path=Path(value["load_path"]) if value.get("load_path") is not None else None,
            allow_codex_version_mismatch=value.get("allow_codex_version_mismatch"),
            save_fields_resolved_from_model_catalog=value.get("save_fields_resolved_from_model_catalog"),
        )


@dataclass(frozen=True)
class DebugToml:
    config_lockfile: DebugConfigLockToml | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "DebugToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("debug must be a mapping")
        return cls(config_lockfile=DebugConfigLockToml.from_mapping(value.get("config_lockfile")))


@dataclass(frozen=True)
class ThreadStoreToml:
    type: str
    id: str | None = None

    @classmethod
    def local(cls) -> "ThreadStoreToml":
        return cls("local")

    @classmethod
    def in_memory(cls, id: str) -> "ThreadStoreToml":
        return cls("in_memory", str(id))

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "ThreadStoreToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("thread store must be a mapping")
        store_type = value.get("type")
        if store_type == "local":
            return cls.local()
        if store_type == "in_memory":
            if not isinstance(value.get("id"), str):
                raise TypeError("in_memory thread store requires string id")
            return cls.in_memory(value["id"])
        raise ValueError(f"unknown thread store type: {store_type!r}")


@dataclass(frozen=True)
class AutoReviewToml:
    policy: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "AutoReviewToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("auto_review must be a mapping")
        return cls(policy=value.get("policy"))


@dataclass(frozen=True)
class ProjectConfig:
    trust_level: TrustLevel | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "ProjectConfig | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("project config must be a mapping")
        trust_level = value.get("trust_level")
        return cls(trust_level=TrustLevel(trust_level) if trust_level is not None else None)

    def is_trusted(self) -> bool:
        return self.trust_level == TrustLevel.TRUSTED

    def is_untrusted(self) -> bool:
        return self.trust_level == TrustLevel.UNTRUSTED


@dataclass(frozen=True)
class RealtimeAudioConfig:
    microphone: str | None = None
    speaker: str | None = None


class RealtimeWsMode(str, Enum):
    CONVERSATIONAL = "conversational"
    TRANSCRIPTION = "transcription"


class RealtimeTransport(str, Enum):
    WEBRTC = "webrtc"
    WEBSOCKET = "websocket"


@dataclass(frozen=True)
class RealtimeConfig:
    version: RealtimeConversationVersion = RealtimeConversationVersion.default()
    session_type: RealtimeWsMode = RealtimeWsMode.CONVERSATIONAL
    transport: RealtimeTransport = RealtimeTransport.WEBRTC
    voice: RealtimeVoice | None = None


@dataclass(frozen=True)
class RealtimeToml:
    version: RealtimeConversationVersion | None = None
    session_type: RealtimeWsMode | None = None
    transport: RealtimeTransport | None = None
    voice: RealtimeVoice | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "RealtimeToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("realtime must be a mapping")
        session_type = value.get("type", value.get("session_type"))
        return cls(
            version=RealtimeConversationVersion(value["version"]) if value.get("version") is not None else None,
            session_type=RealtimeWsMode(session_type) if session_type is not None else None,
            transport=RealtimeTransport(value["transport"]) if value.get("transport") is not None else None,
            voice=RealtimeVoice(value["voice"]) if value.get("voice") is not None else None,
        )


@dataclass(frozen=True)
class RealtimeAudioToml:
    microphone: str | None = None
    speaker: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "RealtimeAudioToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("realtime audio must be a mapping")
        return cls(microphone=value.get("microphone"), speaker=value.get("speaker"))


@dataclass(frozen=True)
class ToolsToml:
    web_search: WebSearchToolConfig | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "ToolsToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("tools must be a mapping")
        web_search = value.get("web_search")
        if web_search is None or isinstance(web_search, bool):
            return cls(web_search=None)
        if not isinstance(web_search, dict):
            raise TypeError("tools.web_search must be a mapping, bool, or None")
        return cls(
            web_search=WebSearchToolConfig(
                context_size=web_search.get("context_size"),
                allowed_domains=tuple(web_search["allowed_domains"])
                if web_search.get("allowed_domains") is not None
                else None,
                location=web_search.get("location"),
            )
        )


@dataclass(frozen=True)
class AgentRoleToml:
    description: str | None = None
    config_file: Path | None = None
    nickname_candidates: tuple[str, ...] | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AgentRoleToml":
        if not isinstance(value, dict):
            raise TypeError("agent role must be a mapping")
        candidates = value.get("nickname_candidates")
        return cls(
            description=value.get("description"),
            config_file=Path(value["config_file"]) if value.get("config_file") is not None else None,
            nickname_candidates=tuple(candidates) if candidates is not None else None,
        )


@dataclass(frozen=True)
class AgentsToml:
    max_threads: int | None = None
    max_depth: int | None = None
    job_max_runtime_seconds: int | None = None
    interrupt_message: bool | None = None
    roles: dict[str, AgentRoleToml] | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "AgentsToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("agents must be a mapping")
        known = {"max_threads", "max_depth", "job_max_runtime_seconds", "interrupt_message"}
        return cls(
            max_threads=value.get("max_threads"),
            max_depth=value.get("max_depth"),
            job_max_runtime_seconds=value.get("job_max_runtime_seconds"),
            interrupt_message=value.get("interrupt_message"),
            roles={
                str(key): AgentRoleToml.from_mapping(role)
                for key, role in value.items()
                if key not in known
            },
        )


@dataclass(frozen=True)
class GhostSnapshotToml:
    ignore_large_untracked_files: int | None = None
    ignore_large_untracked_dirs: int | None = None
    disable_warnings: bool | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "GhostSnapshotToml | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("ghost_snapshot must be a mapping")
        return cls(
            ignore_large_untracked_files=value.get(
                "ignore_large_untracked_files",
                value.get("ignore_untracked_files_over_bytes"),
            ),
            ignore_large_untracked_dirs=value.get(
                "ignore_large_untracked_dirs",
                value.get("large_untracked_dir_warning_threshold"),
            ),
            disable_warnings=value.get("disable_warnings"),
        )


@dataclass(frozen=True)
class ConfigLockfileToml:
    version: int
    codex_version: str
    config: ConfigToml

    @classmethod
    def from_toml(cls, contents: str) -> "ConfigLockfileToml":
        return cls.from_mapping(_toml.loads(contents))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConfigLockfileToml":
        if not isinstance(value, Mapping):
            raise TypeError("ConfigLockfileToml input must be a mapping")
        _reject_unknown_fields(value, {"version", "codex_version", "config"}, "ConfigLockfileToml")
        version = _required_int(value, "version")
        codex_version = _required_str(value, "codex_version")
        config_value = _required_mapping(value, "config")
        return cls(version=version, codex_version=codex_version, config=ConfigToml.from_mapping(dict(config_value)))


@dataclass(frozen=True)
class ConfigToml:
    model: str | None = None
    review_model: str | None = None
    model_provider: str | None = None
    model_context_window: int | None = None
    model_auto_compact_token_limit: int | None = None
    model_auto_compact_token_limit_scope: AutoCompactTokenLimitScope | None = None
    approval_policy: AskForApproval | None = None
    approvals_reviewer: ApprovalsReviewer | None = None
    shell_environment_policy: ShellEnvironmentPolicyToml = ShellEnvironmentPolicyToml()
    forced_chatgpt_workspace_id: ForcedChatgptWorkspaceIds | None = None
    project_doc_max_bytes: int | None = DEFAULT_PROJECT_DOC_MAX_BYTES
    project_doc_fallback_filenames: tuple[str, ...] | None = ()
    allow_login_shell: bool | None = True
    sandbox_mode: SandboxMode | None = None
    sandbox_workspace_write: SandboxWorkspaceWrite | None = None
    default_permissions: str | None = None
    permissions: PermissionsToml | None = None
    notify: tuple[str, ...] | None = None
    instructions: str | None = None
    developer_instructions: str | None = None
    include_permissions_instructions: bool | None = None
    include_apps_instructions: bool | None = None
    include_collaboration_mode_instructions: bool | None = None
    include_environment_context: bool | None = None
    model_instructions_file: Path | None = None
    compact_prompt: str | None = None
    forced_login_method: ForcedLoginMethod | None = None
    cli_auth_credentials_store: AuthCredentialsStoreMode | None = None
    mcp_servers: dict[str, McpServerConfig] | None = None
    mcp_oauth_credentials_store: OAuthCredentialsStoreMode | None = None
    mcp_oauth_callback_port: int | None = None
    mcp_oauth_callback_url: str | None = None
    model_providers: dict[str, ModelProviderInfo] | None = None
    tool_output_token_limit: int | None = None
    background_terminal_max_timeout: int | None = None
    js_repl_node_path: Path | None = None
    js_repl_node_module_dirs: tuple[Path, ...] | None = None
    profile: str | None = None
    profiles: dict[str, ConfigProfile] | None = None
    history: History | None = History()
    sqlite_home: Path | None = None
    log_dir: Path | None = None
    file_opener: UriBasedFileOpener | None = None
    tui: Tui | None = None
    hide_agent_reasoning: bool | None = False
    show_raw_agent_reasoning: bool | None = None
    model_reasoning_effort: ReasoningEffort | None = None
    plan_mode_reasoning_effort: ReasoningEffort | None = None
    model_reasoning_summary: ReasoningSummary | None = None
    model_verbosity: Verbosity | None = None
    model_supports_reasoning_summaries: bool | None = None
    model_catalog_json: Path | None = None
    personality: Personality | None = None
    service_tier: str | None = None
    chatgpt_base_url: str | None = None
    apps_mcp_product_sku: str | None = None
    openai_base_url: str | None = None
    audio: RealtimeAudioToml | None = None
    experimental_realtime_ws_base_url: str | None = None
    experimental_realtime_ws_model: str | None = None
    experimental_realtime_ws_backend_prompt: str | None = None
    experimental_realtime_ws_startup_context: str | None = None
    experimental_realtime_start_instructions: str | None = None
    experimental_thread_config_endpoint: str | None = None
    experimental_thread_store_endpoint: str | None = None
    auto_review: AutoReviewToml | None = None
    debug: DebugToml | None = None
    experimental_thread_store: ThreadStoreToml | None = None
    projects: dict[str, ProjectConfig] | None = None
    web_search: WebSearchMode | None = None
    realtime: RealtimeToml | None = None
    realtime_audio: RealtimeAudioToml | None = None
    tools: ToolsToml | None = None
    tool_suggest: ToolSuggestConfig | None = None
    agents: AgentsToml | None = None
    memories: MemoriesToml | None = None
    skills: SkillsConfig | None = None
    hooks: HooksToml | None = None
    plugins: dict[str, PluginConfig] | None = None
    marketplaces: dict[str, MarketplaceConfig] | None = None
    features: dict[str, JsonValue] | None = None
    suppress_unstable_features_warning: bool | None = None
    ghost_snapshot: GhostSnapshotToml | None = None
    project_root_markers: tuple[str, ...] | None = None
    check_for_update_on_startup: bool | None = None
    disable_paste_burst: bool | None = None
    analytics: AnalyticsConfigToml | None = None
    feedback: FeedbackConfigToml | None = None
    apps: AppsConfigToml | None = None
    desktop: dict[str, JsonValue] | None = None
    otel: OtelConfigToml | None = None
    windows: WindowsToml | None = None
    notice: Notice | None = None
    experimental_compact_prompt_file: Path | None = None
    experimental_use_unified_exec_tool: bool | None = None
    oss_provider: str | None = None

    @classmethod
    def from_toml(cls, contents: str) -> "ConfigToml":
        return cls.from_mapping(_toml.loads(contents))

    @classmethod
    def from_mapping(cls, value: dict[str, JsonValue] | Any) -> "ConfigToml":
        if not isinstance(value, dict):
            raise TypeError("ConfigToml input must be a mapping")
        _reject_unknown_fields(value, _CONFIG_TOML_FIELDS, "ConfigToml")
        workspace_value = value.get("forced_chatgpt_workspace_id")
        fallback_value = _optional_str_tuple(value, "project_doc_fallback_filenames", default=())
        audio = RealtimeAudioToml.from_mapping(value.get("audio"))
        realtime_audio = RealtimeAudioToml.from_mapping(value.get("realtime_audio")) or audio
        model_providers = _parse_model_providers(_optional_mapping(value, "model_providers"))
        return cls(
            model=_optional_str(value, "model"),
            review_model=_optional_str(value, "review_model"),
            model_provider=_optional_str(value, "model_provider"),
            model_context_window=_optional_int(value, "model_context_window"),
            model_auto_compact_token_limit=_optional_int(value, "model_auto_compact_token_limit"),
            model_auto_compact_token_limit_scope=_optional_enum(
                value,
                "model_auto_compact_token_limit_scope",
                AutoCompactTokenLimitScope,
            ),
            approval_policy=_optional_enum(value, "approval_policy", AskForApproval),
            approvals_reviewer=_optional_enum(value, "approvals_reviewer", ApprovalsReviewer),
            shell_environment_policy=ShellEnvironmentPolicyToml.from_mapping(
                _optional_mapping(value, "shell_environment_policy")
            ),
            forced_chatgpt_workspace_id=(
                ForcedChatgptWorkspaceIds.from_value(workspace_value)
                if workspace_value is not None
                else None
            ),
            project_doc_max_bytes=value.get("project_doc_max_bytes", DEFAULT_PROJECT_DOC_MAX_BYTES),
            project_doc_fallback_filenames=fallback_value,
            allow_login_shell=_optional_bool(value, "allow_login_shell", default=True),
            sandbox_mode=_optional_enum(value, "sandbox_mode", SandboxMode),
            sandbox_workspace_write=SandboxWorkspaceWrite.from_mapping(_optional_mapping(value, "sandbox_workspace_write")) if "sandbox_workspace_write" in value else None,
            default_permissions=_optional_str(value, "default_permissions"),
            permissions=PermissionsToml.from_mapping(_optional_mapping(value, "permissions")) if "permissions" in value else None,
            notify=_optional_str_tuple(value, "notify"),
            instructions=_optional_str(value, "instructions"),
            developer_instructions=_optional_str(value, "developer_instructions"),
            include_permissions_instructions=_optional_bool(value, "include_permissions_instructions"),
            include_apps_instructions=_optional_bool(value, "include_apps_instructions"),
            include_collaboration_mode_instructions=_optional_bool(value, "include_collaboration_mode_instructions"),
            include_environment_context=_optional_bool(value, "include_environment_context"),
            model_instructions_file=_optional_path(value, "model_instructions_file"),
            compact_prompt=_optional_str(value, "compact_prompt"),
            forced_login_method=_optional_enum(value, "forced_login_method", ForcedLoginMethod),
            cli_auth_credentials_store=_optional_enum(value, "cli_auth_credentials_store", AuthCredentialsStoreMode),
            mcp_servers=_parse_mapping_values(value, "mcp_servers", McpServerConfig.from_mapping, default_empty=True),
            mcp_oauth_credentials_store=_optional_enum(value, "mcp_oauth_credentials_store", OAuthCredentialsStoreMode),
            mcp_oauth_callback_port=_optional_port(value, "mcp_oauth_callback_port"),
            mcp_oauth_callback_url=_optional_str(value, "mcp_oauth_callback_url"),
            model_providers=model_providers,
            tool_output_token_limit=_optional_non_negative_int(value, "tool_output_token_limit"),
            background_terminal_max_timeout=_optional_non_negative_int(value, "background_terminal_max_timeout"),
            js_repl_node_path=_optional_path(value, "js_repl_node_path"),
            js_repl_node_module_dirs=_optional_path_tuple(value, "js_repl_node_module_dirs"),
            profile=_optional_str(value, "profile"),
            profiles=_parse_mapping_values(value, "profiles", ConfigProfile.from_mapping, default_empty=True),
            history=History.from_mapping(_optional_mapping(value, "history")) if "history" in value else History(),
            sqlite_home=_optional_path(value, "sqlite_home"),
            log_dir=_optional_path(value, "log_dir"),
            file_opener=_optional_enum(value, "file_opener", UriBasedFileOpener),
            tui=Tui.from_mapping(_optional_mapping(value, "tui")) if "tui" in value else None,
            hide_agent_reasoning=_optional_bool(value, "hide_agent_reasoning", default=False),
            show_raw_agent_reasoning=_optional_bool(value, "show_raw_agent_reasoning"),
            model_reasoning_effort=_optional_enum(value, "model_reasoning_effort", ReasoningEffort),
            plan_mode_reasoning_effort=_optional_enum(value, "plan_mode_reasoning_effort", ReasoningEffort),
            model_reasoning_summary=_optional_enum(value, "model_reasoning_summary", ReasoningSummary),
            model_verbosity=_optional_enum(value, "model_verbosity", Verbosity),
            model_supports_reasoning_summaries=_optional_bool(value, "model_supports_reasoning_summaries"),
            model_catalog_json=_optional_path(value, "model_catalog_json"),
            personality=_optional_enum(value, "personality", Personality),
            service_tier=_optional_str(value, "service_tier"),
            chatgpt_base_url=_optional_str(value, "chatgpt_base_url"),
            apps_mcp_product_sku=_optional_str(value, "apps_mcp_product_sku"),
            openai_base_url=_optional_str(value, "openai_base_url"),
            audio=audio,
            experimental_realtime_ws_base_url=_optional_str(value, "experimental_realtime_ws_base_url"),
            experimental_realtime_ws_model=_optional_str(value, "experimental_realtime_ws_model"),
            experimental_realtime_ws_backend_prompt=_optional_str(value, "experimental_realtime_ws_backend_prompt"),
            experimental_realtime_ws_startup_context=_optional_str(value, "experimental_realtime_ws_startup_context"),
            experimental_realtime_start_instructions=_optional_str(value, "experimental_realtime_start_instructions"),
            experimental_thread_config_endpoint=_optional_str(value, "experimental_thread_config_endpoint"),
            experimental_thread_store_endpoint=_optional_str(value, "experimental_thread_store_endpoint"),
            auto_review=AutoReviewToml.from_mapping(value.get("auto_review")),
            debug=DebugToml.from_mapping(value.get("debug")),
            experimental_thread_store=ThreadStoreToml.from_mapping(value.get("experimental_thread_store")),
            projects=_parse_mapping_values(value, "projects", ProjectConfig.from_mapping),
            web_search=_optional_enum(value, "web_search", WebSearchMode),
            realtime=RealtimeToml.from_mapping(value.get("realtime")),
            realtime_audio=realtime_audio,
            tools=ToolsToml.from_mapping(value.get("tools")),
            tool_suggest=ToolSuggestConfig.from_mapping(_optional_mapping(value, "tool_suggest")) if "tool_suggest" in value else None,
            agents=AgentsToml.from_mapping(value.get("agents")),
            memories=MemoriesToml.from_mapping(_optional_mapping(value, "memories")) if "memories" in value else None,
            skills=SkillsConfig.from_mapping(_optional_mapping(value, "skills")) if "skills" in value else None,
            hooks=HooksToml.from_mapping(_optional_mapping(value, "hooks")) if "hooks" in value else None,
            plugins=_parse_mapping_values(value, "plugins", PluginConfig.from_mapping, default_empty=True),
            marketplaces=_parse_mapping_values(value, "marketplaces", MarketplaceConfig.from_mapping, default_empty=True),
            features=dict(_optional_mapping(value, "features") or {}) if "features" in value else None,
            suppress_unstable_features_warning=_optional_bool(value, "suppress_unstable_features_warning"),
            ghost_snapshot=GhostSnapshotToml.from_mapping(value.get("ghost_snapshot")),
            project_root_markers=_optional_str_tuple(value, "project_root_markers"),
            check_for_update_on_startup=_optional_bool(value, "check_for_update_on_startup"),
            disable_paste_burst=_optional_bool(value, "disable_paste_burst"),
            analytics=AnalyticsConfigToml.from_mapping(_optional_mapping(value, "analytics")) if "analytics" in value else None,
            feedback=FeedbackConfigToml.from_mapping(_optional_mapping(value, "feedback")) if "feedback" in value else None,
            apps=AppsConfigToml.from_mapping(_optional_mapping(value, "apps")) if "apps" in value else None,
            desktop=dict(_optional_mapping(value, "desktop") or {}) if "desktop" in value else None,
            otel=OtelConfigToml.from_mapping(_optional_mapping(value, "otel")) if "otel" in value else None,
            windows=WindowsToml.from_mapping(_optional_mapping(value, "windows")) if "windows" in value else None,
            notice=Notice.from_mapping(_optional_mapping(value, "notice")) if "notice" in value else None,
            experimental_compact_prompt_file=_optional_path(value, "experimental_compact_prompt_file"),
            experimental_use_unified_exec_tool=_optional_bool(value, "experimental_use_unified_exec_tool"),
            oss_provider=_optional_str(value, "oss_provider"),
        )

    def get_active_project(self, resolved_cwd: str | Path, repo_root: str | Path | None = None) -> ProjectConfig | None:
        if not self.projects:
            return None
        for lookup_key in _normalized_project_lookup_keys(Path(resolved_cwd)):
            project = _project_config_for_lookup_key(self.projects, lookup_key)
            if project is not None:
                return project
        if repo_root is not None:
            for lookup_key in _normalized_project_lookup_keys(Path(repo_root)):
                project = _project_config_for_lookup_key(self.projects, lookup_key)
                if project is not None:
                    return project
        return None

    def derive_permission_profile(
        self,
        sandbox_mode_override: SandboxMode | str | None = None,
        profile_sandbox_mode: SandboxMode | str | None = None,
        windows_sandbox_level: WindowsSandboxLevel | str = WindowsSandboxLevel.DISABLED,
        active_project: ProjectConfig | None = None,
        permission_profile_constraint: Any | None = None,
    ) -> PermissionProfile:
        sandbox_mode_override = _coerce_optional_enum_value(sandbox_mode_override, SandboxMode)
        profile_sandbox_mode = _coerce_optional_enum_value(profile_sandbox_mode, SandboxMode)
        windows_sandbox_level = _coerce_enum_value(windows_sandbox_level, WindowsSandboxLevel)
        sandbox_mode_was_explicit = (
            sandbox_mode_override is not None
            or profile_sandbox_mode is not None
            or self.sandbox_mode is not None
        )
        resolved_sandbox_mode = sandbox_mode_override or profile_sandbox_mode or self.sandbox_mode
        if resolved_sandbox_mode is None and not sandbox_mode_was_explicit and active_project is not None:
            if active_project.is_trusted() or active_project.is_untrusted():
                if _is_windows_platform() and windows_sandbox_level is WindowsSandboxLevel.DISABLED:
                    resolved_sandbox_mode = SandboxMode.READ_ONLY
                else:
                    resolved_sandbox_mode = SandboxMode.WORKSPACE_WRITE
        if resolved_sandbox_mode is None:
            resolved_sandbox_mode = SandboxMode.default()

        effective_sandbox_mode = resolved_sandbox_mode
        if (
            _is_windows_platform()
            and windows_sandbox_level is WindowsSandboxLevel.DISABLED
            and resolved_sandbox_mode is SandboxMode.WORKSPACE_WRITE
        ):
            effective_sandbox_mode = SandboxMode.READ_ONLY

        if effective_sandbox_mode is SandboxMode.READ_ONLY:
            permission_profile = PermissionProfile.read_only()
        elif effective_sandbox_mode is SandboxMode.WORKSPACE_WRITE:
            if self.sandbox_workspace_write is None:
                permission_profile = PermissionProfile.workspace_write()
            else:
                permission_profile = PermissionProfile.workspace_write(
                    self.sandbox_workspace_write.writable_roots,
                    (
                        NetworkSandboxPolicy.ENABLED
                        if self.sandbox_workspace_write.network_access
                        else NetworkSandboxPolicy.RESTRICTED
                    ),
                    self.sandbox_workspace_write.exclude_tmpdir_env_var,
                    self.sandbox_workspace_write.exclude_slash_tmp,
                )
        elif effective_sandbox_mode is SandboxMode.DANGER_FULL_ACCESS:
            permission_profile = PermissionProfile.disabled()
        else:
            raise ValueError(f"unknown sandbox mode: {effective_sandbox_mode}")

        if not sandbox_mode_was_explicit and permission_profile_constraint is not None:
            can_set = getattr(permission_profile_constraint, "can_set", None)
            if callable(can_set):
                try:
                    can_set(permission_profile)
                except Exception:
                    return PermissionProfile.read_only()
        return permission_profile


_CONFIG_TOML_FIELDS = {
    "model",
    "review_model",
    "model_provider",
    "model_context_window",
    "model_auto_compact_token_limit",
    "model_auto_compact_token_limit_scope",
    "approval_policy",
    "approvals_reviewer",
    "auto_review",
    "shell_environment_policy",
    "allow_login_shell",
    "sandbox_mode",
    "sandbox_workspace_write",
    "default_permissions",
    "permissions",
    "notify",
    "instructions",
    "developer_instructions",
    "include_permissions_instructions",
    "include_apps_instructions",
    "include_collaboration_mode_instructions",
    "include_environment_context",
    "model_instructions_file",
    "compact_prompt",
    "forced_chatgpt_workspace_id",
    "forced_login_method",
    "cli_auth_credentials_store",
    "mcp_servers",
    "mcp_oauth_credentials_store",
    "mcp_oauth_callback_port",
    "mcp_oauth_callback_url",
    "model_providers",
    "project_doc_max_bytes",
    "project_doc_fallback_filenames",
    "tool_output_token_limit",
    "background_terminal_max_timeout",
    "js_repl_node_path",
    "js_repl_node_module_dirs",
    "profile",
    "profiles",
    "history",
    "sqlite_home",
    "log_dir",
    "debug",
    "file_opener",
    "tui",
    "hide_agent_reasoning",
    "show_raw_agent_reasoning",
    "model_reasoning_effort",
    "plan_mode_reasoning_effort",
    "model_reasoning_summary",
    "model_verbosity",
    "model_supports_reasoning_summaries",
    "model_catalog_json",
    "personality",
    "service_tier",
    "chatgpt_base_url",
    "apps_mcp_product_sku",
    "openai_base_url",
    "audio",
    "realtime_audio",
    "experimental_realtime_ws_base_url",
    "experimental_realtime_ws_model",
    "experimental_realtime_ws_backend_prompt",
    "experimental_realtime_ws_startup_context",
    "experimental_realtime_start_instructions",
    "experimental_thread_config_endpoint",
    "experimental_thread_store_endpoint",
    "experimental_thread_store",
    "projects",
    "web_search",
    "tools",
    "tool_suggest",
    "agents",
    "memories",
    "skills",
    "hooks",
    "plugins",
    "marketplaces",
    "features",
    "suppress_unstable_features_warning",
    "ghost_snapshot",
    "project_root_markers",
    "check_for_update_on_startup",
    "disable_paste_burst",
    "analytics",
    "feedback",
    "apps",
    "desktop",
    "otel",
    "windows",
    "notice",
    "experimental_compact_prompt_file",
    "experimental_use_unified_exec_tool",
    "oss_provider",
    "realtime",
}


def validate_reserved_model_provider_ids(model_providers: Mapping[str, JsonValue]) -> None:
    conflicts = sorted(
        f"`{key}`"
        for key in model_providers
        if key != AMAZON_BEDROCK_PROVIDER_ID and key in RESERVED_MODEL_PROVIDER_IDS
    )
    if conflicts:
        raise ValueError(
            "model_providers contains reserved built-in provider IDs: "
            f"{', '.join(conflicts)}. Built-in providers cannot be overridden. "
            "Rename your custom provider (for example, `openai-custom`)."
        )


def validate_model_providers(model_providers: Mapping[str, ModelProviderInfo]) -> None:
    validate_reserved_model_provider_ids(model_providers)
    for key, provider in model_providers.items():
        if key == AMAZON_BEDROCK_PROVIDER_ID:
            continue
        if provider.aws is not None:
            raise ValueError(
                f"model_providers.{key}: provider aws is only supported for `{AMAZON_BEDROCK_PROVIDER_ID}`"
            )
        if not provider.name.strip():
            raise ValueError(f"model_providers.{key}: provider name must not be empty")
        try:
            provider.validate()
        except ValueError as exc:
            raise ValueError(f"model_providers.{key}: {exc}") from exc


def validate_oss_provider(provider: str) -> None:
    if provider in {LMSTUDIO_OSS_PROVIDER_ID, OLLAMA_OSS_PROVIDER_ID}:
        return
    if provider == LEGACY_OLLAMA_CHAT_PROVIDER_ID:
        raise ValueError(OLLAMA_CHAT_PROVIDER_REMOVED_ERROR)
    raise ValueError(
        f"Invalid OSS provider '{provider}'. Must be one of: {LMSTUDIO_OSS_PROVIDER_ID}, {OLLAMA_OSS_PROVIDER_ID}"
    )


def _parse_model_providers(value: Mapping[str, JsonValue] | None) -> dict[str, ModelProviderInfo]:
    if value is None:
        return {}
    providers = {str(key): _model_provider_from_mapping(item) for key, item in value.items()}
    validate_model_providers(providers)
    return providers


def _model_provider_from_mapping(value: JsonValue) -> ModelProviderInfo:
    data = _required_mapping({"model_provider": value}, "model_provider")
    _reject_unknown_fields(
        data,
        {
            "name",
            "base_url",
            "env_key",
            "env_key_instructions",
            "experimental_bearer_token",
            "auth",
            "aws",
            "wire_api",
            "query_params",
            "http_headers",
            "env_http_headers",
            "request_max_retries",
            "stream_max_retries",
            "stream_idle_timeout_ms",
            "websocket_connect_timeout_ms",
            "requires_openai_auth",
            "supports_websockets",
        },
        "ModelProviderInfo",
    )
    aws = None
    if data.get("aws") is not None:
        aws_data = _required_mapping(data, "aws")
        _reject_unknown_fields(aws_data, {"profile", "region"}, "ModelProviderAwsAuthInfo")
        aws = ModelProviderAwsAuthInfo(profile=_optional_str(aws_data, "profile"), region=_optional_str(aws_data, "region"))
    return ModelProviderInfo(
        name=_optional_str(data, "name") or "",
        base_url=_optional_str(data, "base_url"),
        env_key=_optional_str(data, "env_key"),
        env_key_instructions=_optional_str(data, "env_key_instructions"),
        experimental_bearer_token=_optional_str(data, "experimental_bearer_token"),
        auth=dict(_required_mapping(data, "auth")) if data.get("auth") is not None else None,
        aws=aws,
        wire_api=_optional_str(data, "wire_api") or "responses",
        query_params=dict(_required_mapping(data, "query_params")) if data.get("query_params") is not None else None,
        http_headers=dict(_required_mapping(data, "http_headers")) if data.get("http_headers") is not None else None,
        env_http_headers=dict(_required_mapping(data, "env_http_headers")) if data.get("env_http_headers") is not None else None,
        request_max_retries_value=_optional_non_negative_int(data, "request_max_retries"),
        stream_max_retries_value=_optional_non_negative_int(data, "stream_max_retries"),
        stream_idle_timeout_ms=_optional_non_negative_int(data, "stream_idle_timeout_ms"),
        websocket_connect_timeout_ms=_optional_non_negative_int(data, "websocket_connect_timeout_ms"),
        requires_openai_auth=_optional_bool(data, "requires_openai_auth", default=False) or False,
        supports_websockets=_optional_bool(data, "supports_websockets", default=False) or False,
    )


def _normalized_project_lookup_keys(path: Path) -> tuple[str, ...]:
    raw = _normalize_project_lookup_key(str(path))
    try:
        canonical = _normalize_project_lookup_key(str(path.resolve(strict=False)))
    except OSError:
        canonical = raw
    if raw == canonical:
        return (canonical,)
    return (canonical, raw)


def _normalize_project_lookup_key(key: str) -> str:
    return key.lower() if _is_windows_path_runtime() else key


def _project_config_for_lookup_key(projects: Mapping[str, ProjectConfig], lookup_key: str) -> ProjectConfig | None:
    direct = projects.get(lookup_key)
    if direct is not None:
        return direct
    matches = [
        (key, project)
        for key, project in projects.items()
        if _normalize_project_lookup_key(str(key)) == lookup_key
    ]
    matches.sort(key=lambda item: item[0])
    return matches[0][1] if matches else None


def _is_windows_path_runtime() -> bool:
    import os

    return os.name == "nt"


def _is_windows_platform() -> bool:
    import sys

    return sys.platform == "win32"


def _reject_unknown_fields(value: Mapping[str, Any], allowed: set[str], type_name: str) -> None:
    unknown = [str(key) for key in value if key not in allowed]
    if unknown:
        raise ValueError(f"unknown fields for {type_name}: {', '.join(unknown)}")


def _optional_mapping(value: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise TypeError(f"{key} must be a table or None")
    return item


def _parse_mapping_values(
    value: Mapping[str, JsonValue],
    key: str,
    parser: Any,
    *,
    default_empty: bool = False,
) -> dict[str, Any] | None:
    mapping = _optional_mapping(value, key)
    if mapping is None:
        return {} if default_empty else None
    return {str(name): parser(item) for name, item in mapping.items()}


def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string or None")
    return item


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    item = _optional_str(value, key)
    if item is None:
        raise ValueError(f"{key} is required")
    return item


def _optional_bool(value: Mapping[str, JsonValue], key: str, *, default: bool | None = None) -> bool | None:
    item = value.get(key, default)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise TypeError(f"{key} must be a bool or None")
    return item


def _optional_int(value: Mapping[str, JsonValue], key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int):
        raise TypeError(f"{key} must be an integer or None")
    return item


def _required_int(value: Mapping[str, JsonValue], key: str) -> int:
    item = _optional_int(value, key)
    if item is None:
        raise ValueError(f"{key} is required")
    return item


def _optional_non_negative_int(value: Mapping[str, JsonValue], key: str) -> int | None:
    item = _optional_int(value, key)
    if item is not None and item < 0:
        raise ValueError(f"{key} must be non-negative")
    return item


def _optional_port(value: Mapping[str, JsonValue], key: str) -> int | None:
    item = _optional_non_negative_int(value, key)
    if item is not None and item > 65535:
        raise ValueError(f"{key} must fit in u16")
    return item


def _required_mapping(value: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    item = _optional_mapping(value, key)
    if item is None:
        raise ValueError(f"{key} is required")
    return item


def _optional_path(value: Mapping[str, JsonValue], key: str) -> Path | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str | Path):
        raise TypeError(f"{key} must be a path string or None")
    return Path(item)


def _optional_path_tuple(value: Mapping[str, JsonValue], key: str) -> tuple[Path, ...] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, list | tuple):
        raise TypeError(f"{key} must be an array or None")
    return tuple(Path(entry) for entry in item)


def _optional_str_tuple(
    value: Mapping[str, JsonValue],
    key: str,
    *,
    default: tuple[str, ...] | None = None,
) -> tuple[str, ...] | None:
    item = value.get(key, default)
    if item is None:
        return None
    if not isinstance(item, list | tuple):
        raise TypeError(f"{key} must be an array or None")
    if not all(isinstance(entry, str) for entry in item):
        raise TypeError(f"{key} entries must be strings")
    return tuple(item)


def _optional_enum(value: Mapping[str, JsonValue], key: str, enum_type: Any) -> Any | None:
    item = value.get(key)
    if item is None:
        return None
    if isinstance(item, enum_type):
        return item
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string or None")
    parse = getattr(enum_type, "parse", None)
    if callable(parse):
        return parse(item)
    return enum_type(item)


def _coerce_enum_value(value: Any, enum_type: Any) -> Any:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{enum_type.__name__} value must be a string or enum")
    parse = getattr(enum_type, "parse", None)
    if callable(parse):
        return parse(value)
    return enum_type(value)


def _coerce_optional_enum_value(value: Any, enum_type: Any) -> Any | None:
    if value is None:
        return None
    return _coerce_enum_value(value, enum_type)


__all__ = [
    "AgentRoleToml",
    "AgentsToml",
    "AutoReviewToml",
    "ConfigLockfileToml",
    "DebugConfigLockToml",
    "DebugToml",
    "ConfigToml",
    "DEFAULT_PROJECT_DOC_MAX_BYTES",
    "FORCED_CHATGPT_WORKSPACE_ID_ERROR",
    "ForcedChatgptWorkspaceIds",
    "GhostSnapshotToml",
    "ProjectConfig",
    "RealtimeAudioConfig",
    "RealtimeAudioToml",
    "RealtimeConfig",
    "RealtimeToml",
    "RealtimeTransport",
    "RealtimeWsMode",
    "ThreadStoreToml",
    "ToolsToml",
    "validate_model_providers",
    "validate_oss_provider",
    "validate_reserved_model_provider_ids",
]
