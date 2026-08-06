"""MCP configuration and orchestration from ``codex-mcp/src/mcp/mod.rs``."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from pycodex.config.mcp_types import (
    AppToolApproval,
    McpServerConfig,
    McpServerTransportConfig,
)
from pycodex.config.types import OAuthCredentialsStoreMode
from pycodex.protocol.config_types import AskForApproval
from pycodex.protocol.models import PermissionProfile

from ..runtime import McpRuntimeContext
from ..server import EffectiveMcpServer
from .auth import (
    McpAuthStatusEntry,
    McpOAuthLoginConfig,
    McpOAuthLoginSupport,
    McpOAuthScopesSource,
    ResolvedMcpOAuthScopes,
    compute_auth_statuses,
    discover_supported_scopes,
    oauth_login_support,
    resolve_oauth_scopes,
    should_retry_without_scopes,
)


CODEX_APPS_MCP_SERVER_NAME = "codex_apps"
CODEX_CONNECTORS_TOKEN_ENV_VAR = "CODEX_CONNECTORS_TOKEN"


class McpSnapshotDetail(str, Enum):
    FULL = "full"
    TOOLS_AND_AUTH_ONLY = "tools_and_auth_only"

    def include_resources(self) -> bool:
        return self is McpSnapshotDetail.FULL


@dataclass(frozen=True)
class McpPermissionPromptAutoApproveContext:
    approvals_reviewer: Any | None = None
    tool_approval_mode: AppToolApproval | None = None


@dataclass
class McpConfig:
    chatgpt_base_url: str = "https://chatgpt.com"
    apps_mcp_path_override: str | None = None
    apps_mcp_product_sku: str | None = None
    codex_home: Path = field(default_factory=lambda: Path.home() / ".codex")
    mcp_oauth_credentials_store_mode: OAuthCredentialsStoreMode = (
        OAuthCredentialsStoreMode.AUTO
    )
    mcp_oauth_callback_port: int | None = None
    mcp_oauth_callback_url: str | None = None
    skill_mcp_dependency_install_enabled: bool = False
    approval_policy: Any = AskForApproval.ON_REQUEST
    codex_linux_sandbox_exe: Path | None = None
    use_legacy_landlock: bool = False
    apps_enabled: bool = False
    prefix_mcp_tool_names: bool = True
    client_elicitation_capability: Any = None
    configured_mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)
    plugin_ids_by_mcp_server_name: dict[str, str] = field(default_factory=dict)
    plugin_capability_summaries: tuple[Any, ...] = ()


@dataclass(frozen=True)
class ToolPluginProvenance:
    plugin_display_names_by_connector_id: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    plugin_display_names_by_mcp_server_name: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    plugin_ids_by_mcp_server_name: Mapping[str, str] = field(default_factory=dict)

    def plugin_display_names_for_connector_id(self, connector_id: str) -> tuple[str, ...]:
        return tuple(self.plugin_display_names_by_connector_id.get(connector_id, ()))

    def plugin_display_names_for_mcp_server_name(
        self,
        server_name: str,
    ) -> tuple[str, ...]:
        return tuple(self.plugin_display_names_by_mcp_server_name.get(server_name, ()))

    def plugin_id_for_mcp_server_name(self, server_name: str) -> str | None:
        return self.plugin_ids_by_mcp_server_name.get(server_name)


@dataclass(frozen=True)
class McpServerStatusSnapshot:
    tools_by_server: Mapping[str, Mapping[str, Any]]
    resources: Mapping[str, tuple[Any, ...]]
    resource_templates: Mapping[str, tuple[Any, ...]]
    auth_statuses: Mapping[str, Any]
    server_names: tuple[str, ...]


def qualified_mcp_tool_name_prefix(server_name: str) -> str:
    return sanitize_responses_api_tool_name(f"mcp__{server_name}__")


def sanitize_responses_api_tool_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return sanitized or "_"


def mcp_permission_prompt_is_auto_approved(
    approval_policy: AskForApproval | str,
    permission_profile: PermissionProfile,
    context: McpPermissionPromptAutoApproveContext,
) -> bool:
    if context.tool_approval_mode is AppToolApproval.APPROVE:
        return True
    approval_value = getattr(approval_policy, "value", approval_policy)
    if approval_value != AskForApproval.NEVER.value:
        return False
    if permission_profile.type in {"disabled", "external"}:
        return True
    return bool(
        permission_profile.file_system_sandbox_policy().has_full_disk_write_access()
    )


def with_codex_apps_mcp(
    servers: Mapping[str, EffectiveMcpServer],
    auth: Any | None,
    config: McpConfig,
) -> dict[str, EffectiveMcpServer]:
    result = dict(servers)
    if host_owned_codex_apps_enabled(config, auth):
        result[CODEX_APPS_MCP_SERVER_NAME] = EffectiveMcpServer.configured(
            _codex_apps_mcp_server_config(config)
        )
    else:
        result.pop(CODEX_APPS_MCP_SERVER_NAME, None)
    return result


def host_owned_codex_apps_enabled(config: McpConfig, auth: Any | None) -> bool:
    return config.apps_enabled and _uses_codex_backend(auth)


def configured_mcp_servers(config: McpConfig) -> dict[str, McpServerConfig]:
    return dict(config.configured_mcp_servers)


def effective_mcp_servers(
    config: McpConfig,
    auth: Any | None = None,
) -> dict[str, EffectiveMcpServer]:
    return effective_mcp_servers_from_configured(
        configured_mcp_servers(config),
        config,
        auth,
    )


def effective_mcp_servers_from_configured(
    configured_servers: Mapping[str, McpServerConfig],
    config: McpConfig,
    auth: Any | None = None,
) -> dict[str, EffectiveMcpServer]:
    servers = {
        name: EffectiveMcpServer.configured(server)
        for name, server in configured_servers.items()
    }
    return with_codex_apps_mcp(servers, auth, config)


def tool_plugin_provenance(config: McpConfig) -> ToolPluginProvenance:
    connectors: dict[str, set[str]] = {}
    servers: dict[str, set[str]] = {}
    for plugin in config.plugin_capability_summaries:
        display_name = str(_field(plugin, "display_name", "displayName") or "")
        for connector_id in _sequence(
            _field(plugin, "app_connector_ids", "appConnectorIds")
        ):
            key = str(_field(connector_id, "0") or connector_id)
            connectors.setdefault(key, set()).add(display_name)
        for server_name in _sequence(
            _field(plugin, "mcp_server_names", "mcpServerNames")
        ):
            servers.setdefault(str(server_name), set()).add(display_name)
    return ToolPluginProvenance(
        {key: tuple(sorted(values)) for key, values in connectors.items()},
        {key: tuple(sorted(values)) for key, values in servers.items()},
        dict(config.plugin_ids_by_mcp_server_name),
    )


async def read_mcp_resource(
    config: McpConfig,
    auth: Any | None,
    runtime_context: McpRuntimeContext,
    server: str,
    uri: str,
) -> Any:
    from ..connection_manager import McpConnectionManager

    selected = {
        name: value
        for name, value in effective_mcp_servers(config, auth).items()
        if name == server
    }
    manager = await McpConnectionManager.from_effective_servers(
        selected,
        runtime_context=runtime_context,
        auth=auth,
        auth_provider=_auth_provider(auth),
        auth_store_mode=config.mcp_oauth_credentials_store_mode,
    )
    try:
        return await _maybe_await(manager.read_resource(server, uri))
    finally:
        await manager.close()


async def collect_mcp_server_status_snapshot_with_detail(
    config: McpConfig,
    auth: Any | None,
    submit_id: str,
    runtime_context: McpRuntimeContext,
    detail: McpSnapshotDetail = McpSnapshotDetail.FULL,
) -> McpServerStatusSnapshot:
    del submit_id
    from ..connection_manager import McpConnectionManager

    servers = effective_mcp_servers(config, auth)
    if not servers:
        return McpServerStatusSnapshot({}, {}, {}, {}, ())
    entries = await compute_auth_statuses(
        servers.items(),
        config.mcp_oauth_credentials_store_mode,
        auth,
    )
    manager = await McpConnectionManager.from_effective_servers(
        servers,
        runtime_context=runtime_context,
        auth=auth,
        auth_provider=_auth_provider(auth),
        auth_store_mode=config.mcp_oauth_credentials_store_mode,
    )
    try:
        tools = await _maybe_await(manager.list_all_tools())
        tools_by_server: dict[str, dict[str, Any]] = {}
        for info in tools:
            tools_by_server.setdefault(info.server_name, {})[
                _tool_name(info.tool)
            ] = info.tool
        resources = (
            await _maybe_await(manager.list_all_resources())
            if detail.include_resources()
            else {}
        )
        templates = (
            await _maybe_await(manager.list_all_resource_templates())
            if detail.include_resources()
            else {}
        )
        return McpServerStatusSnapshot(
            tools_by_server,
            {name: tuple(values) for name, values in resources.items()},
            {name: tuple(values) for name, values in templates.items()},
            {name: entry.auth_status for name, entry in entries.items()},
            tuple(servers),
        )
    finally:
        await manager.close()


def codex_apps_mcp_url(config: McpConfig) -> str:
    return _codex_apps_mcp_url_for_base_url(
        config.chatgpt_base_url,
        config.apps_mcp_path_override,
    )


def _codex_apps_mcp_url_for_base_url(
    base_url: str,
    apps_mcp_path_override: str | None,
) -> str:
    base_url = base_url.rstrip("/")
    if (
        base_url.startswith("https://chatgpt.com")
        or base_url.startswith("https://chat.openai.com")
    ) and "/backend-api" not in base_url:
        base_url = f"{base_url}/backend-api"
    if "/backend-api" in base_url:
        default_path = "wham/apps"
    elif "/api/codex" in base_url:
        default_path = "apps"
    else:
        base_url = f"{base_url}/api/codex"
        default_path = "apps"
    path = (apps_mcp_path_override or default_path).lstrip("/")
    return f"{base_url}/{path}"


def _codex_apps_mcp_server_config(config: McpConfig) -> McpServerConfig:
    token_env = os.environ.get(CODEX_CONNECTORS_TOKEN_ENV_VAR)
    bearer_token_env_var = (
        CODEX_CONNECTORS_TOKEN_ENV_VAR if token_env is not None else None
    )
    headers = (
        {"X-OpenAI-Product-Sku": config.apps_mcp_product_sku}
        if config.apps_mcp_product_sku is not None
        else None
    )
    return McpServerConfig(
        transport=McpServerTransportConfig.streamable_http(
            url=codex_apps_mcp_url(config),
            bearer_token_env_var=bearer_token_env_var,
            http_headers=headers,
        ),
        startup_timeout_sec=30.0,
    )


def _uses_codex_backend(auth: Any | None) -> bool:
    if auth is None:
        return False
    value = getattr(auth, "uses_codex_backend", False)
    return bool(value() if callable(value) else value)


def _auth_provider(auth: Any | None) -> Any | None:
    if auth is None:
        return None
    from pycodex.model_provider.auth import auth_provider_from_auth

    return auth_provider_from_auth(auth)


def _field(value: Any, *names: str) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None or isinstance(value, (str, bytes)):
        return ()
    try:
        return tuple(value)
    except TypeError:
        return ()


def _tool_name(tool: Any) -> str:
    if isinstance(tool, Mapping):
        return str(tool.get("name", ""))
    return str(getattr(tool, "name", ""))


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "CODEX_APPS_MCP_SERVER_NAME",
    "McpAuthStatusEntry",
    "McpConfig",
    "McpOAuthLoginConfig",
    "McpOAuthLoginSupport",
    "McpOAuthScopesSource",
    "McpPermissionPromptAutoApproveContext",
    "McpServerStatusSnapshot",
    "McpSnapshotDetail",
    "ResolvedMcpOAuthScopes",
    "ToolPluginProvenance",
    "collect_mcp_server_status_snapshot_with_detail",
    "compute_auth_statuses",
    "configured_mcp_servers",
    "discover_supported_scopes",
    "effective_mcp_servers",
    "effective_mcp_servers_from_configured",
    "host_owned_codex_apps_enabled",
    "mcp_permission_prompt_is_auto_approved",
    "oauth_login_support",
    "qualified_mcp_tool_name_prefix",
    "read_mcp_resource",
    "resolve_oauth_scopes",
    "should_retry_without_scopes",
    "tool_plugin_provenance",
    "with_codex_apps_mcp",
]
