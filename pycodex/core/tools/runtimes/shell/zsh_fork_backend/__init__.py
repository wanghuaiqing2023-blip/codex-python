"""Zsh-fork backend dispatch owned by Rust ``zsh_fork_backend.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PreparedUnifiedExecSpawn:
    exec_request: Any
    spawn_lifecycle: Any


async def maybe_run_shell_command(
    req: Any,
    attempt: Any,
    ctx: Any,
    command: Iterable[str],
) -> Any | None:
    from .imp import maybe_run_shell_command as run_impl

    return await run_impl(req, attempt, ctx, tuple(command))


async def maybe_prepare_unified_exec(
    req: Any,
    attempt: Any,
    ctx: Any,
    exec_request: Any,
    zsh_fork_config: Any,
) -> PreparedUnifiedExecSpawn | None:
    from .imp import maybe_prepare_unified_exec as prepare_impl

    return await prepare_impl(req, attempt, ctx, exec_request, zsh_fork_config)


__all__ = [
    "PreparedUnifiedExecSpawn",
    "maybe_prepare_unified_exec",
    "maybe_run_shell_command",
]
