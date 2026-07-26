"""Linux sandbox spawning owned by ``codex-core::landlock``."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pycodex.core.spawn import SpawnChildRequest, StdioPolicy
from pycodex.linux_sandbox import build_linux_sandbox_spawn_child_request
from pycodex.protocol import PermissionProfile

LinuxSandboxSpawner = Callable[[SpawnChildRequest], Any | Awaitable[Any]]


async def spawn_command_under_linux_sandbox(
    codex_linux_sandbox_exe: str | Path,
    command: Sequence[str],
    command_cwd: str | Path,
    permission_profile: PermissionProfile,
    sandbox_policy_cwd: str | Path,
    use_legacy_landlock: bool,
    stdio_policy: StdioPolicy,
    network: object | None,
    env: Mapping[str, str] | None,
    *,
    spawn_child_async: LinuxSandboxSpawner,
) -> Any:
    if not callable(spawn_child_async):
        raise TypeError("spawn_child_async must be callable")
    request = build_linux_sandbox_spawn_child_request(
        codex_linux_sandbox_exe,
        command,
        command_cwd,
        permission_profile,
        sandbox_policy_cwd,
        use_legacy_landlock,
        stdio_policy,
        env=env or {},
        network=network,
    )
    result = spawn_child_async(request)
    if inspect.isawaitable(result):
        return await result
    return result


__all__ = ["spawn_command_under_linux_sandbox"]
