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
from pycodex.config.mcp_types import AppToolApproval, McpServerConfig
from pycodex.protocol.config_types import AskForApproval
from pycodex.protocol.models import PermissionProfile
from pycodex.protocol.tool_name import ToolName


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
