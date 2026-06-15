from __future__ import annotations

import pytest

from pycodex.config.mcp_edit import ConfigEditsBuilder, load_global_mcp_servers_blocking
from pycodex.config.mcp_types import (
    AppToolApproval,
    McpServerConfig,
    McpServerEnvVar,
    McpServerOAuthConfig,
    McpServerToolConfig,
    McpServerTransportConfig,
)


def test_load_global_mcp_servers_missing_or_without_table_returns_empty(tmp_path) -> None:
    # Rust: load_global_mcp_servers returns an empty map for missing config or no mcp_servers.
    assert load_global_mcp_servers_blocking(tmp_path) == {}

    (tmp_path / "config.toml").write_text('model = "gpt-5"\n', encoding="utf-8")
    assert load_global_mcp_servers_blocking(tmp_path) == {}


def test_load_global_mcp_servers_rejects_inline_bearer_token(tmp_path) -> None:
    # Rust: ensure_no_inline_bearer_tokens reports a targeted error before type conversion.
    (tmp_path / "config.toml").write_text(
        """
        [mcp_servers.github]
        url = "https://example.com/mcp"
        bearer_token = "secret"
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mcp_servers.github uses unsupported `bearer_token`"):
        load_global_mcp_servers_blocking(tmp_path)


def test_replace_mcp_servers_serializes_per_tool_approval_overrides(tmp_path) -> None:
    # Rust: replace_mcp_servers_serializes_per_tool_approval_overrides.
    servers = {
        "docs": McpServerConfig(
            transport=McpServerTransportConfig.stdio(command="docs-server"),
            supports_parallel_tool_calls=True,
            default_tools_approval_mode=AppToolApproval.AUTO,
            tools={
                "search": McpServerToolConfig(approval_mode=AppToolApproval.APPROVE),
                "read": McpServerToolConfig(approval_mode=AppToolApproval.PROMPT),
            },
        )
    }

    ConfigEditsBuilder.new(tmp_path).replace_mcp_servers(servers).apply_blocking()

    serialized = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert serialized == (
        '[mcp_servers.docs]\n'
        'command = "docs-server"\n'
        "supports_parallel_tool_calls = true\n"
        'default_tools_approval_mode = "auto"\n'
        "\n"
        "[mcp_servers.docs.tools]\n"
        "\n"
        "[mcp_servers.docs.tools.read]\n"
        'approval_mode = "prompt"\n'
        "\n"
        "[mcp_servers.docs.tools.search]\n"
        'approval_mode = "approve"\n'
    )
    assert load_global_mcp_servers_blocking(tmp_path) == servers


def test_replace_mcp_servers_serializes_oauth_client_id(tmp_path) -> None:
    # Rust: replace_mcp_servers_serializes_oauth_client_id.
    servers = {
        "maas_outlook": McpServerConfig(
            transport=McpServerTransportConfig.streamable_http(url="https://example.com/mcp"),
            oauth=McpServerOAuthConfig(client_id="eci-prd-pub-codex-123"),
        )
    }

    ConfigEditsBuilder.new(tmp_path).replace_mcp_servers(servers).apply_blocking()

    serialized = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert serialized == (
        "[mcp_servers.maas_outlook]\n"
        'url = "https://example.com/mcp"\n'
        "\n"
        "[mcp_servers.maas_outlook.oauth]\n"
        'client_id = "eci-prd-pub-codex-123"\n'
    )
    assert load_global_mcp_servers_blocking(tmp_path) == servers


def test_replace_mcp_servers_serializes_stdio_details_and_reads_back(tmp_path) -> None:
    servers = {
        "local": McpServerConfig(
            transport=McpServerTransportConfig.stdio(
                command="server",
                args=("--flag", "value"),
                env={"B": "2", "A": "1"},
                env_vars=(
                    McpServerEnvVar("LEGACY_TOKEN"),
                    McpServerEnvVar("REMOTE_TOKEN", "remote"),
                ),
                cwd="/tmp",
            ),
            enabled=False,
            required=True,
            startup_timeout_sec=1.25,
            tool_timeout_sec=2.5,
            enabled_tools=("search",),
            disabled_tools=("delete",),
        )
    }

    ConfigEditsBuilder.new(tmp_path).replace_mcp_servers(servers).apply_blocking()

    serialized = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert 'args = ["--flag", "value"]' in serialized
    assert "[mcp_servers.local.env]" in serialized
    assert 'A = "1"' in serialized
    assert 'B = "2"' in serialized
    assert 'env_vars = ["LEGACY_TOKEN", { name = "REMOTE_TOKEN", source = "remote" }]' in serialized
    assert load_global_mcp_servers_blocking(tmp_path) == servers


def test_replace_mcp_servers_empty_removes_table_preserving_other_config(tmp_path) -> None:
    (tmp_path / "config.toml").write_text(
        """
        model = "gpt-5"

        [mcp_servers.docs]
        command = "docs-server"
        """,
        encoding="utf-8",
    )

    ConfigEditsBuilder.new(tmp_path).replace_mcp_servers({}).apply_blocking()

    assert (tmp_path / "config.toml").read_text(encoding="utf-8") == 'model = "gpt-5"\n'
    assert load_global_mcp_servers_blocking(tmp_path) == {}
