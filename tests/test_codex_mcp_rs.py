from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.codex_mcp import (
    CODEX_APPS_MCP_SERVER_NAME,
    MCP_SANDBOX_STATE_META_CAPABILITY,
    MCP_TOOL_CODEX_APPS_META_KEY,
    CodexAppsConnectorAuthFailure,
    EffectiveMcpServer,
    McpConfig,
    McpConnectionManager,
    McpOAuthScopesSource,
    McpPermissionPromptAutoApproveContext,
    McpRuntimeContext,
    ToolInfo,
    auth_elicitation_completed_result,
    auth_elicitation_id,
    build_auth_elicitation,
    configured_mcp_servers,
    declared_openai_file_input_param_names,
    effective_mcp_servers,
    mcp_permission_prompt_is_auto_approved,
    qualified_mcp_tool_name_prefix,
    resolve_oauth_scopes,
)
from pycodex.codex_mcp.rmcp_client import ManagedClient
from pycodex.codex_mcp.server import McpServerMetadata
from pycodex.config.mcp_types import AppToolApproval, McpServerConfig
from pycodex.protocol import Tool
from pycodex.protocol.config_types import AskForApproval
from pycodex.protocol.models import PermissionProfile
from pycodex.protocol.tool_name import ToolName
from pycodex.rmcp_client import ListToolsWithConnectorIdResult, ToolWithConnectorId


def _stdio_server(**overrides: object) -> McpServerConfig:
    values: dict[str, object] = {"command": "server"}
    values.update(overrides)
    return McpServerConfig.from_mapping(values)


def test_codex_mcp_lib_reexports_fixed_rust_constants() -> None:
    # Rust: codex-mcp/src/lib.rs, mcp/mod.rs and rmcp_client.rs.
    assert CODEX_APPS_MCP_SERVER_NAME == "codex_apps"
    assert MCP_TOOL_CODEX_APPS_META_KEY == "_codex_apps"
    assert MCP_SANDBOX_STATE_META_CAPABILITY == "codex/sandbox-state-meta"


def test_mcp_auth_scope_resolution_matches_rust_precedence() -> None:
    explicit = resolve_oauth_scopes(["explicit"], ["configured"], ["discovered"])
    configured = resolve_oauth_scopes(None, [], ["discovered"])
    discovered = resolve_oauth_scopes(None, None, ["discovered"])
    empty = resolve_oauth_scopes(None, None, [])

    assert (explicit.scopes, explicit.source) == (
        ("explicit",),
        McpOAuthScopesSource.EXPLICIT,
    )
    assert (configured.scopes, configured.source) == (
        (),
        McpOAuthScopesSource.CONFIGURED,
    )
    assert (discovered.scopes, discovered.source) == (
        ("discovered",),
        McpOAuthScopesSource.DISCOVERED,
    )
    assert (empty.scopes, empty.source) == ((), McpOAuthScopesSource.EMPTY)


def test_effective_servers_preserve_configured_and_add_host_apps(tmp_path: Path) -> None:
    config = McpConfig(
        chatgpt_base_url="https://chatgpt.com",
        codex_home=tmp_path,
        apps_enabled=True,
        configured_mcp_servers={"docs": _stdio_server()},
    )
    auth = SimpleNamespace(uses_codex_backend=lambda: True)

    assert configured_mcp_servers(config) == {"docs": _stdio_server()}
    effective = effective_mcp_servers(config, auth)

    assert set(effective) == {"docs", CODEX_APPS_MCP_SERVER_NAME}
    assert isinstance(effective["docs"], EffectiveMcpServer)
    apps = effective[CODEX_APPS_MCP_SERVER_NAME].configured_config()
    assert apps is not None
    assert apps.transport.url == "https://chatgpt.com/backend-api/wham/apps"


def test_effective_servers_do_not_add_host_apps_without_backend_auth(
    tmp_path: Path,
) -> None:
    config = McpConfig(
        codex_home=tmp_path,
        apps_enabled=True,
        configured_mcp_servers={"docs": _stdio_server()},
    )
    api_key_auth = SimpleNamespace(uses_codex_backend=lambda: False)

    assert set(effective_mcp_servers(config, api_key_auth)) == {"docs"}


def test_connection_manager_reports_complete_names_and_codex_apps_auth(
    tmp_path: Path,
) -> None:
    backend_auth = SimpleNamespace(uses_codex_backend=lambda: True)
    effective = effective_mcp_servers(
        McpConfig(
            codex_home=tmp_path,
            apps_enabled=True,
            configured_mcp_servers={"node_repl": _stdio_server()},
        ),
        backend_auth,
    )
    manager = McpConnectionManager(
        {
            name: server.configured_config()
            for name, server in effective.items()
        },
        auth=backend_auth,
    )

    assert manager.server_names() == ("codex_apps", "node_repl")
    assert manager.enabled_server_names() == ("codex_apps", "node_repl")
    statuses = asyncio.run(manager.auth_statuses())
    assert str(statuses["codex_apps"]).lower().replace("_", " ") == "bearer token"


def test_mcp_permission_auto_approval_matches_rust_policy() -> None:
    approved_tool = McpPermissionPromptAutoApproveContext(
        tool_approval_mode=AppToolApproval.APPROVE
    )
    assert mcp_permission_prompt_is_auto_approved(
        AskForApproval.ON_REQUEST,
        PermissionProfile.read_only(),
        approved_tool,
    )
    assert not mcp_permission_prompt_is_auto_approved(
        AskForApproval.NEVER,
        PermissionProfile.read_only(),
        McpPermissionPromptAutoApproveContext(),
    )
    assert mcp_permission_prompt_is_auto_approved(
        AskForApproval.NEVER,
        PermissionProfile.disabled(),
        McpPermissionPromptAutoApproveContext(),
    )


def test_tool_metadata_and_names_match_rust_contract() -> None:
    assert qualified_mcp_tool_name_prefix("my server!") == "mcp__my_server___"
    assert declared_openai_file_input_param_names(
        {"openai/fileParams": ["path", "", 7, "other"]}
    ) == ("path", "other")

    tool = ToolInfo(
        server_name="docs",
        callable_name="search",
        callable_namespace="docs",
        tool={"name": "search", "inputSchema": {"type": "object"}},
    )
    assert tool.canonical_tool_name() == ToolName.namespaced("docs", "search")


@pytest.mark.asyncio
async def test_managed_client_normalizes_codex_apps_connector_namespace_and_name() -> None:
    # Rust: codex-mcp::rmcp_client::list_tools_for_client_uncached applies the
    # codex_apps callable namespace/name normalization before model exposure.
    class Client:
        async def list_tools_with_connector_ids(self, *, timeout):
            assert timeout == 5
            return ListToolsWithConnectorIdResult(
                tools=(
                    ToolWithConnectorId(
                        tool=Tool(
                            name="github_get_user_login",
                            title="GitHub_Get User Login",
                            input_schema={"type": "object"},
                        ),
                        connector_id="connector_github",
                        connector_name="GitHub",
                        connector_description="Read GitHub account metadata.",
                    ),
                )
            )

    managed = ManagedClient(
        server_name=CODEX_APPS_MCP_SERVER_NAME,
        client=Client(),
        metadata=McpServerMetadata(
            pollutes_memory=True,
            origin="https://chatgpt.com",
            supports_parallel_tool_calls=False,
        ),
        tool_timeout=5,
    )

    (tool,) = await managed.list_tools()

    assert tool.callable_namespace == "codex_apps__github"
    assert tool.callable_name == "_get_user_login"
    assert tool.canonical_tool_name() == ToolName.namespaced(
        "codex_apps__github",
        "_get_user_login",
    )
    assert tool.tool.name == "github_get_user_login"
    assert tool.tool.title == "Get User Login"
    assert tool.connector_id == "connector_github"
    assert tool.namespace_description == "Read GitHub account metadata."


def test_auth_elicitation_payload_and_completion_match_rust() -> None:
    failure = CodexAppsConnectorAuthFailure(
        connector_id="calendar",
        connector_name="Calendar",
        install_url="https://chatgpt.com/apps/calendar",
        auth_reason="missing_link",
    )
    elicitation = build_auth_elicitation("call-7", failure)
    assert elicitation.elicitation_id == "codex_apps_auth_call-7"
    assert elicitation.url == failure.install_url
    assert elicitation.message == "Sign in to Calendar on ChatGPT to use it in Codex."
    assert auth_elicitation_id("call-7") == elicitation.elicitation_id

    result = auth_elicitation_completed_result(failure, {"request": "meta"})
    assert result["isError"] is True
    assert result["_meta"] == {"request": "meta"}
    assert "Retry this tool call now." in result["content"][0]["text"]


def test_runtime_context_rejects_missing_local_stdio_environment(tmp_path: Path) -> None:
    context = McpRuntimeContext(
        environment_manager=SimpleNamespace(get_environment=lambda _name: None),
        local_stdio_fallback_cwd=tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="local stdio MCP server `docs` requires a local environment",
    ):
        context.resolve_server_environment("docs", _stdio_server())


def test_connection_manager_resource_path_is_real_and_validated() -> None:
    manager = McpConnectionManager(
        {"docs": _stdio_server()},
        resources={"docs": ({"uri": "docs://one"},)},
        resource_templates={"docs": ({"uriTemplate": "docs://{id}"},)},
        resource_contents={("docs", "docs://one"): {"contents": ["one"]}},
    )

    assert manager.has_servers()
    assert asyncio.run(manager.list_all_resources()) == {
        "docs": ({"uri": "docs://one"},)
    }
    assert asyncio.run(manager.read_resource("docs", "docs://one")) == {
        "contents": ["one"]
    }
    assert asyncio.run(manager.close()) is None
