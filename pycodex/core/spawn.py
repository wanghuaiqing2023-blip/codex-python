"""Child process spawn request helpers.

Ported from the pure request/environment portions of
``codex/codex-rs/core/src/spawn.rs``. This module intentionally does not spawn
processes; actual subprocess, process-group, stdio, and kill-on-drop behavior
remain runtime responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping

from pycodex.protocol import NetworkSandboxPolicy


CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR = "CODEX_SANDBOX_NETWORK_DISABLED"
CODEX_SANDBOX_ENV_VAR = "CODEX_SANDBOX"


class StdioPolicy(str, Enum):
    REDIRECT_FOR_SHELL_TOOL = "RedirectForShellTool"
    INHERIT = "Inherit"


@dataclass(frozen=True)
class SpawnChildRequest:
    program: Path
    args: tuple[str, ...]
    arg0: str | None
    cwd: Path
    network_sandbox_policy: NetworkSandboxPolicy
    network: object | None
    stdio_policy: StdioPolicy
    env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.program, Path):
            object.__setattr__(self, "program", Path(self.program))
        if isinstance(self.args, (str, bytes)) or not isinstance(self.args, tuple):
            object.__setattr__(self, "args", tuple(_string_sequence(self.args, "args")))
        if self.arg0 is not None and not isinstance(self.arg0, str):
            raise TypeError("arg0 must be a string or None")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.network_sandbox_policy, NetworkSandboxPolicy):
            object.__setattr__(
                self,
                "network_sandbox_policy",
                NetworkSandboxPolicy.parse(self.network_sandbox_policy),
            )
        if not isinstance(self.stdio_policy, StdioPolicy):
            object.__setattr__(self, "stdio_policy", StdioPolicy(self.stdio_policy))
        object.__setattr__(self, "env", _string_mapping(self.env, "env"))

    def effective_env(self) -> dict[str, str]:
        env = dict(self.env)
        if not self.network_sandbox_policy.is_enabled():
            env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR] = "1"
        return env


def build_spawn_child_request(
    program: str | Path,
    args: tuple[str, ...] | list[str],
    *,
    arg0: str | None,
    cwd: str | Path,
    network_sandbox_policy: NetworkSandboxPolicy,
    network: object | None = None,
    stdio_policy: StdioPolicy = StdioPolicy.REDIRECT_FOR_SHELL_TOOL,
    env: Mapping[str, str] | None = None,
) -> SpawnChildRequest:
    return SpawnChildRequest(
        program=Path(program),
        args=tuple(_string_sequence(args, "args")),
        arg0=arg0,
        cwd=Path(cwd),
        network_sandbox_policy=network_sandbox_policy,
        network=network,
        stdio_policy=stdio_policy,
        env=_string_mapping(env or {}, "env"),
    )


def _string_sequence(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must contain only strings")
    return tuple(value)


def _string_mapping(value: Mapping[str, str], label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise TypeError(f"{label} must contain string keys and values")
    return dict(value)


__all__ = [
    "CODEX_SANDBOX_ENV_VAR",
    "CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR",
    "SpawnChildRequest",
    "StdioPolicy",
    "build_spawn_child_request",
]
