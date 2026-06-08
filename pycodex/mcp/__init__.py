"""Source-verified public interface slice for ``codex-mcp``.

Rust source:
- ``codex/codex-rs/codex-mcp/src/lib.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

CODEX_APPS_MCP_SERVER_NAME = "codex_apps"
MCP_TOOL_CODEX_APPS_META_KEY = "codex/apps"
MCP_SANDBOX_STATE_META_CAPABILITY = "codex/sandbox_state"


class SandboxState(str, Enum):
    DISABLED = "disabled"
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


@dataclass
class McpConfig:
    servers: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolInfo:
    name: str
    description: str | None = None
    input_schema: Any | None = None
    title: str | None = None


@dataclass
class ToolPluginProvenance:
    plugin_id: str | None = None
    connector_id: str | None = None


@dataclass
class EffectiveMcpServer:
    name: str
    config: Any | None = None


@dataclass
class McpRuntimeContext:
    sandbox_state: SandboxState | None = None


@dataclass(frozen=True)
class CodexAppsToolsCacheKey:
    account_id: str | None
    auth_mode: str | None


def codex_apps_tools_cache_key(account_id: str | None = None, auth_mode: str | None = None) -> CodexAppsToolsCacheKey:
    return CodexAppsToolsCacheKey(account_id, auth_mode)


def host_owned_codex_apps_enabled(*_args: Any, **_kwargs: Any) -> bool:
    return False


def with_codex_apps_mcp(servers: dict[str, Any]) -> dict[str, Any]:
    return dict(servers)


def configured_mcp_servers(config: Any) -> dict[str, Any]:
    return getattr(config, "mcp_servers", {}) if config is not None else {}


def effective_mcp_servers(config: Any, *_args: Any, **_kwargs: Any) -> list[EffectiveMcpServer]:
    return effective_mcp_servers_from_configured(configured_mcp_servers(config))


def effective_mcp_servers_from_configured(configured: dict[str, Any]) -> list[EffectiveMcpServer]:
    return [EffectiveMcpServer(name, value) for name, value in configured.items()]


def tool_plugin_provenance(*_args: Any, **_kwargs: Any) -> ToolPluginProvenance | None:
    return None


def qualified_mcp_tool_name_prefix(server_name: str) -> str:
    return f"mcp__{server_name}__"


def declared_openai_file_input_param_names(_tool: Any) -> list[str]:
    return []


@dataclass
class McpPermissionPromptAutoApproveContext:
    fields: dict[str, Any] = field(default_factory=dict)


def mcp_permission_prompt_is_auto_approved(*_args: Any, **_kwargs: Any) -> bool:
    return False


@dataclass
class McpAuthStatusEntry:
    server_name: str
    status: Any


@dataclass
class McpOAuthLoginConfig:
    server_name: str
    scopes: list[str] = field(default_factory=list)


@dataclass
class ResolvedMcpOAuthScopes:
    scopes: list[str]
    source: str | None = None


class McpOAuthScopesSource(str, Enum):
    CONFIG = "config"
    DISCOVERY = "discovery"


@dataclass
class McpOAuthLoginSupport:
    login_config: McpOAuthLoginConfig | None = None


def compute_auth_statuses(*_args: Any, **_kwargs: Any) -> list[McpAuthStatusEntry]:
    return []


def oauth_login_support(*_args: Any, **_kwargs: Any) -> McpOAuthLoginSupport | None:
    return None


def resolve_oauth_scopes(scopes: list[str] | None = None, *_args: Any, **_kwargs: Any) -> ResolvedMcpOAuthScopes:
    return ResolvedMcpOAuthScopes(scopes or [], None)


def should_retry_without_scopes(*_args: Any, **_kwargs: Any) -> bool:
    return False


def discover_supported_scopes(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


class McpConnectionManager:
    pass


class ElicitationReviewer:
    pass


class ElicitationReviewerHandle:
    pass


@dataclass
class ElicitationReviewRequest:
    fields: dict[str, Any] = field(default_factory=dict)


def auth_elicitation_id(*parts: str) -> str:
    return ":".join(parts)


def build_auth_elicitation(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {}


def build_auth_elicitation_plan(*_args: Any, **_kwargs: Any) -> "CodexAppsAuthElicitationPlan":
    return CodexAppsAuthElicitationPlan()


def auth_elicitation_completed_result(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {}


def connector_auth_failure_from_tool_result(*_args: Any, **_kwargs: Any) -> "CodexAppsConnectorAuthFailure | None":
    return None


@dataclass
class CodexAppsAuthElicitation:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodexAppsAuthElicitationPlan:
    elicitations: list[CodexAppsAuthElicitation] = field(default_factory=list)


@dataclass
class CodexAppsConnectorAuthFailure:
    connector_id: str | None = None
    message: str | None = None


McpServerStatusSnapshot = dict[str, Any]
McpSnapshotDetail = dict[str, Any]


def collect_mcp_server_status_snapshot_with_detail(*_args: Any, **_kwargs: Any) -> tuple[McpServerStatusSnapshot, McpSnapshotDetail]:
    return {}, {}


async def read_mcp_resource(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("MCP resource runtime is not ported")


__all__ = [name for name in globals() if not name.startswith("_")]
