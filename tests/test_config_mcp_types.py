from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.config.mcp_types import (
    DEFAULT_MCP_SERVER_ENVIRONMENT_ID,
    AppToolApproval,
    McpServerConfig,
    McpServerDisabledReason,
    McpServerEnvVar,
    McpServerOAuthConfig,
    McpServerToolConfig,
    McpServerTransportConfig,
)
from pycodex.config.constraint import RequirementSource


def test_deserialize_stdio_command_server_config_with_defaults() -> None:
    # Rust: codex-config/src/mcp_types_tests.rs deserialize_stdio_command_server_config.
    cfg = McpServerConfig.from_toml('command = "echo"')

    assert cfg.transport == McpServerTransportConfig.stdio(command="echo")
    assert cfg.enabled is True
    assert cfg.required is False
    assert cfg.enabled_tools is None
    assert cfg.disabled_tools is None
    assert cfg.environment_id == DEFAULT_MCP_SERVER_ENVIRONMENT_ID
    assert cfg.is_local_environment()


def test_deserialize_stdio_command_server_config_with_args_env_and_cwd() -> None:
    # Rust: deserialize_stdio_command_server_config_with_arg_with_args_and_env / with_cwd.
    cfg = McpServerConfig.from_toml(
        """
        command = "echo"
        args = ["hello", "world"]
        env = { "FOO" = "BAR" }
        cwd = "/tmp"
        """
    )

    assert cfg.transport == McpServerTransportConfig.stdio(
        command="echo",
        args=("hello", "world"),
        env={"FOO": "BAR"},
        cwd="/tmp",
    )


def test_deserialize_stdio_command_server_config_with_env_var_sources() -> None:
    # Rust: deserialize_stdio_command_server_config_with_env_var_sources.
    cfg = McpServerConfig.from_toml(
        """
        command = "echo"
        env_vars = [
            "LEGACY_TOKEN",
            { name = "LOCAL_TOKEN", source = "local" },
            { name = "REMOTE_TOKEN", source = "remote" },
        ]
        """
    )

    assert cfg.transport.env_vars == (
        McpServerEnvVar("LEGACY_TOKEN"),
        McpServerEnvVar("LOCAL_TOKEN", "local"),
        McpServerEnvVar("REMOTE_TOKEN", "remote"),
    )
    assert cfg.transport.env_vars[0].name() == "LEGACY_TOKEN"
    assert cfg.transport.env_vars[1].source() == "local"
    assert cfg.transport.env_vars[2].is_remote_source()


def test_rejects_unknown_env_var_source() -> None:
    # Rust: deserialize_stdio_command_server_config_rejects_unknown_env_var_source.
    with pytest.raises(ValueError, match="unsupported env_vars source `elsewhere`"):
        McpServerConfig.from_toml(
            """
            command = "echo"
            env_vars = [{ name = "TOKEN", source = "elsewhere" }]
            """
        )


def test_remote_stdio_server_requires_absolute_cwd(tmp_path: Path) -> None:
    # Rust: deserialize_remote_stdio_server_requires_absolute_cwd / accepts_absolute_cwd.
    with pytest.raises(ValueError, match="remote stdio MCP servers require an absolute cwd"):
        McpServerConfig.from_toml(
            """
            command = "echo"
            environment_id = "remote"
            """
        )

    with pytest.raises(ValueError, match="got `relative`"):
        McpServerConfig.from_toml(
            """
            command = "echo"
            environment_id = "remote"
            cwd = "relative"
            """
        )

    cfg = McpServerConfig.from_toml(
        f'''
        command = "echo"
        environment_id = "remote"
        cwd = "{tmp_path.as_posix()}"
        '''
    )
    assert cfg.transport.cwd == tmp_path
    assert not cfg.is_local_environment()


def test_disabled_and_required_flags() -> None:
    # Rust: deserialize_disabled_server_config / deserialize_required_server_config.
    disabled = McpServerConfig.from_toml(
        """
        command = "echo"
        enabled = false
        """
    )
    required = McpServerConfig.from_toml(
        """
        command = "echo"
        required = true
        """
    )

    assert disabled.enabled is False
    assert disabled.required is False
    assert required.required is True


def test_deserialize_streamable_http_server_config_with_headers() -> None:
    # Rust: deserialize_streamable_http_server_config / with_env_var / with_headers.
    cfg = McpServerConfig.from_toml(
        """
        url = "https://example.com/mcp"
        bearer_token_env_var = "GITHUB_TOKEN"
        http_headers = { "X-Foo" = "bar" }
        env_http_headers = { "X-Token" = "TOKEN_ENV" }
        """
    )

    assert cfg.transport == McpServerTransportConfig.streamable_http(
        url="https://example.com/mcp",
        bearer_token_env_var="GITHUB_TOKEN",
        http_headers={"X-Foo": "bar"},
        env_http_headers={"X-Token": "TOKEN_ENV"},
    )
    assert cfg.enabled is True


def test_deserialize_streamable_http_server_config_with_oauth() -> None:
    # Rust: deserialize_streamable_http_server_config_with_oauth_resource / oauth_client_id.
    cfg = McpServerConfig.from_toml(
        """
        url = "https://example.com/mcp"
        oauth_resource = "https://api.example.com"

        [oauth]
        client_id = "eci-prd-pub-codex-123"
        """
    )

    assert cfg.oauth_resource == "https://api.example.com"
    assert cfg.oauth == McpServerOAuthConfig(client_id="eci-prd-pub-codex-123")
    assert cfg.oauth_client_id() == "eci-prd-pub-codex-123"


def test_deserialize_tool_filters_parallel_and_approval_modes() -> None:
    # Rust: tool filters, parallel tool calls, default/per-tool approval mode.
    cfg = McpServerConfig.from_toml(
        """
        command = "echo"
        enabled_tools = ["allowed"]
        disabled_tools = ["blocked"]
        supports_parallel_tool_calls = true
        tool_timeout_sec = 2.0
        default_tools_approval_mode = "approve"

        [tools.search]
        approval_mode = "prompt"
        """
    )

    assert cfg.enabled_tools == ("allowed",)
    assert cfg.disabled_tools == ("blocked",)
    assert cfg.supports_parallel_tool_calls is True
    assert cfg.tool_timeout_sec == 2.0
    assert cfg.default_tools_approval_mode == AppToolApproval.APPROVE
    assert cfg.tools["search"] == McpServerToolConfig(approval_mode=AppToolApproval.PROMPT)
    assert cfg.to_mapping()["default_tools_approval_mode"] == "approve"


def test_unknown_server_fields_are_ignored() -> None:
    # Rust: deserialize_ignores_unknown_server_fields.
    cfg = McpServerConfig.from_toml(
        """
        command = "echo"
        trust_level = "trusted"
        """
    )

    assert cfg == McpServerConfig(transport=McpServerTransportConfig.stdio(command="echo"))


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (
            """
            command = "echo"
            url = "https://example.com"
            """,
            "url is not supported for stdio",
        ),
        (
            """
            url = "https://example.com"
            env = { "FOO" = "BAR" }
            """,
            "env is not supported for streamable_http",
        ),
        (
            """
            command = "echo"
            http_headers = { "X-Foo" = "bar" }
            """,
            "http_headers is not supported for stdio",
        ),
        (
            """
            command = "echo"
            oauth = { client_id = "eci-prd-pub-codex-123" }
            """,
            "oauth is not supported for stdio",
        ),
        (
            """
            command = "echo"
            oauth_resource = "https://api.example.com"
            """,
            "oauth_resource is not supported for stdio",
        ),
        (
            """
            url = "https://example.com"
            bearer_token = "secret"
            """,
            "bearer_token is not supported for streamable_http",
        ),
    ],
)
def test_rejects_transport_specific_unsupported_fields(contents: str, message: str) -> None:
    # Rust: deserialize_rejects_command_and_url / env_for_http / headers_for_stdio / bearer_token.
    with pytest.raises(ValueError, match=message):
        McpServerConfig.from_toml(contents)


def test_startup_timeout_sec_precedes_milliseconds() -> None:
    cfg = McpServerConfig.from_toml(
        """
        command = "echo"
        startup_timeout_sec = 2.5
        startup_timeout_ms = 8000
        """
    )
    ms_cfg = McpServerConfig.from_toml(
        """
        command = "echo"
        startup_timeout_ms = 1500
        """
    )

    assert cfg.startup_timeout_sec == 2.5
    assert ms_cfg.startup_timeout_sec == 1.5


def test_disabled_reason_display_contract() -> None:
    # Rust: Display for McpServerDisabledReason.
    assert str(McpServerDisabledReason.unknown()) == "unknown"
    assert (
        str(McpServerDisabledReason.requirements(RequirementSource.cloud_requirements()))
        == "requirements (cloud requirements)"
    )
