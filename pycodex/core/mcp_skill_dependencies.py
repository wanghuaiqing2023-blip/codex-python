"""MCP skill dependency helpers ported from ``core/src/mcp_skill_dependencies.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


DEFAULT_MCP_SERVER_ENVIRONMENT_ID = "local"
SKILL_MCP_DEPENDENCY_PROMPT_ID = "skill_mcp_dependency_install"
MCP_DEPENDENCY_OPTION_INSTALL = "Install"
MCP_DEPENDENCY_OPTION_SKIP = "Continue anyway"


@dataclass(frozen=True)
class SkillToolDependency:
    type: str
    value: str
    transport: str | None = None
    url: str | None = None
    command: str | None = None


@dataclass(frozen=True)
class SkillDependencies:
    tools: tuple[SkillToolDependency, ...] = ()


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    dependencies: SkillDependencies | None = None
    description: str = ""
    short_description: str | None = None
    interface: object | None = None
    policy: object | None = None
    path_to_skills_md: Path | str | None = None
    scope: str = "user"
    plugin_id: str | None = None


@dataclass(frozen=True)
class McpServerTransportConfig:
    kind: str
    command: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    env_vars: tuple[str, ...] = ()
    cwd: str | None = None
    url: str | None = None
    bearer_token_env_var: str | None = None
    http_headers: Mapping[str, str] | None = None
    env_http_headers: Mapping[str, str] | None = None

    @classmethod
    def stdio(cls, command: str) -> "McpServerTransportConfig":
        return cls(kind="stdio", command=command)

    @classmethod
    def streamable_http(cls, url: str) -> "McpServerTransportConfig":
        return cls(kind="streamable_http", url=url)


@dataclass(frozen=True)
class McpServerConfig:
    transport: McpServerTransportConfig
    environment_id: str = DEFAULT_MCP_SERVER_ENVIRONMENT_ID
    enabled: bool = True
    required: bool = False
    supports_parallel_tool_calls: bool = False
    disabled_reason: str | None = None
    startup_timeout_sec: int | None = None
    tool_timeout_sec: int | None = None
    default_tools_approval_mode: str | None = None
    enabled_tools: tuple[str, ...] | None = None
    disabled_tools: tuple[str, ...] | None = None
    scopes: tuple[str, ...] | None = None
    oauth: object | None = None
    oauth_resource: str | None = None
    tools: Mapping[str, object] = field(default_factory=dict)


def format_missing_mcp_dependencies(missing: Mapping[str, McpServerConfig]) -> str:
    return ", ".join(sorted(missing.keys()))


def canonical_mcp_key(transport: str, identifier: str, fallback: str) -> str:
    identifier = identifier.strip()
    if not identifier:
        return fallback
    return f"mcp__{transport}__{identifier}"


def canonical_mcp_server_key(name: str, config: McpServerConfig) -> str:
    transport = config.transport
    if transport.kind == "stdio":
        return canonical_mcp_key("stdio", transport.command or "", name)
    if transport.kind == "streamable_http":
        return canonical_mcp_key("streamable_http", transport.url or "", name)
    return name


def canonical_mcp_dependency_key(dependency: SkillToolDependency) -> str:
    transport = dependency.transport or "streamable_http"
    if transport.lower() == "streamable_http":
        if dependency.url is None:
            raise ValueError("missing url for streamable_http dependency")
        return canonical_mcp_key("streamable_http", dependency.url, dependency.value)
    if transport.lower() == "stdio":
        if dependency.command is None:
            raise ValueError("missing command for stdio dependency")
        return canonical_mcp_key("stdio", dependency.command, dependency.value)
    raise ValueError(f"unsupported transport {transport}")


def mcp_dependency_to_server_config(dependency: SkillToolDependency) -> McpServerConfig:
    transport = dependency.transport or "streamable_http"
    if transport.lower() == "streamable_http":
        if dependency.url is None:
            raise ValueError("missing url for streamable_http dependency")
        return McpServerConfig(
            transport=McpServerTransportConfig.streamable_http(dependency.url),
        )
    if transport.lower() == "stdio":
        if dependency.command is None:
            raise ValueError("missing command for stdio dependency")
        return McpServerConfig(
            transport=McpServerTransportConfig.stdio(dependency.command),
        )
    raise ValueError(f"unsupported transport {transport}")


def collect_missing_mcp_dependencies(
    mentioned_skills: tuple[SkillMetadata, ...] | list[SkillMetadata],
    installed: Mapping[str, McpServerConfig],
) -> dict[str, McpServerConfig]:
    missing: dict[str, McpServerConfig] = {}
    installed_keys = {
        canonical_mcp_server_key(name, config)
        for name, config in installed.items()
    }
    seen_canonical_keys: set[str] = set()

    for skill in mentioned_skills:
        dependencies = skill.dependencies
        if dependencies is None:
            continue
        for tool in dependencies.tools:
            if tool.type.lower() != "mcp":
                continue
            try:
                dependency_key = canonical_mcp_dependency_key(tool)
            except ValueError:
                continue
            if dependency_key in installed_keys or dependency_key in seen_canonical_keys:
                continue
            try:
                config = mcp_dependency_to_server_config(tool)
            except ValueError:
                continue
            missing[tool.value] = config
            seen_canonical_keys.add(dependency_key)
    return missing


def filter_prompted_mcp_dependencies(
    missing: Mapping[str, McpServerConfig],
    prompted: set[str] | frozenset[str],
) -> dict[str, McpServerConfig]:
    if not prompted:
        return dict(missing)
    return {
        name: config
        for name, config in missing.items()
        if canonical_mcp_server_key(name, config) not in prompted
    }


__all__ = [
    "DEFAULT_MCP_SERVER_ENVIRONMENT_ID",
    "MCP_DEPENDENCY_OPTION_INSTALL",
    "MCP_DEPENDENCY_OPTION_SKIP",
    "SKILL_MCP_DEPENDENCY_PROMPT_ID",
    "McpServerConfig",
    "McpServerTransportConfig",
    "SkillDependencies",
    "SkillMetadata",
    "SkillToolDependency",
    "canonical_mcp_dependency_key",
    "canonical_mcp_key",
    "canonical_mcp_server_key",
    "collect_missing_mcp_dependencies",
    "filter_prompted_mcp_dependencies",
    "format_missing_mcp_dependencies",
    "mcp_dependency_to_server_config",
]
