"""Runtime environment resolution from ``codex-mcp/src/runtime.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.config.mcp_types import McpServerConfig


@dataclass(frozen=True)
class SandboxState:
    sandbox_policy: Any
    codex_linux_sandbox_exe: Path | None
    sandbox_cwd: Path
    permission_profile: Any | None = None
    use_legacy_landlock: bool = False

    def to_mapping(self) -> dict[str, Any]:
        result = {
            "sandboxPolicy": self.sandbox_policy,
            "codexLinuxSandboxExe": (
                str(self.codex_linux_sandbox_exe)
                if self.codex_linux_sandbox_exe is not None
                else None
            ),
            "sandboxCwd": str(self.sandbox_cwd),
            "useLegacyLandlock": self.use_legacy_landlock,
        }
        if self.permission_profile is not None:
            result["permissionProfile"] = self.permission_profile
        return result


@dataclass(frozen=True)
class McpRuntimeContext:
    environment_manager: Any
    local_stdio_fallback_cwd: Path

    def __init__(
        self,
        environment_manager: Any,
        local_stdio_fallback_cwd: Path | str,
    ) -> None:
        object.__setattr__(self, "environment_manager", environment_manager)
        object.__setattr__(
            self,
            "local_stdio_fallback_cwd",
            Path(local_stdio_fallback_cwd),
        )

    def resolve_server_environment(
        self,
        server_name: str,
        config: McpServerConfig,
    ) -> Any | None:
        getter = getattr(self.environment_manager, "get_environment", None)
        environment = getter(config.environment_id) if callable(getter) else None
        if environment is not None:
            if not config.is_local_environment():
                _ensure_remote_stdio_cwd(server_name, config)
            return environment

        if config.is_local_environment():
            if config.transport.kind == "stdio":
                raise ValueError(
                    f"local stdio MCP server `{server_name}` requires a local environment"
                )
            return None

        raise ValueError(
            f"MCP server `{server_name}` references unknown environment id "
            f"`{config.environment_id}`"
        )


def _ensure_remote_stdio_cwd(server_name: str, config: McpServerConfig) -> None:
    transport = config.transport
    if transport.kind != "stdio":
        return
    cwd = transport.cwd
    if cwd is None:
        raise ValueError(
            f"remote stdio MCP server `{server_name}` requires an absolute cwd"
        )
    if not Path(cwd).is_absolute():
        raise ValueError(
            f"remote stdio MCP server `{server_name}` requires an absolute cwd, "
            f"got `{cwd}`"
        )


__all__ = ["McpRuntimeContext", "SandboxState"]
