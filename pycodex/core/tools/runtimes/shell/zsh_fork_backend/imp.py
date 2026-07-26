"""Platform implementation for the zsh-fork backend inline Rust module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pycodex.protocol import ExecToolCallOutput

from .. import ESCALATE_SOCKET_ENV_VAR, _is_unix_platform
from ..unix_escalation import prepare_unified_exec_zsh_fork, try_run_zsh_fork


@dataclass
class ZshForkSpawnLifecycle:
    escalation_session: Any

    def inherited_fds(self) -> list[int]:
        env = getattr(self.escalation_session, "env", None)
        env_value = env() if callable(env) else env
        if not isinstance(env_value, Mapping):
            return []
        try:
            return [int(env_value.get(ESCALATE_SOCKET_ENV_VAR))]
        except (TypeError, ValueError):
            return []

    def after_spawn(self) -> None:
        close_client_socket = getattr(self.escalation_session, "close_client_socket", None)
        if callable(close_client_socket):
            close_client_socket()


async def maybe_run_shell_command(
    req: Any,
    attempt: Any,
    ctx: Any,
    command: Iterable[str],
) -> ExecToolCallOutput | None:
    if not _is_unix_platform():
        return None
    result = await try_run_zsh_fork(req, attempt, ctx, tuple(command))
    if result is None or isinstance(result, ExecToolCallOutput):
        return result
    raise TypeError("try_run_zsh_fork must return ExecToolCallOutput or None")


async def maybe_prepare_unified_exec(
    req: Any,
    attempt: Any,
    ctx: Any,
    exec_request: Any,
    zsh_fork_config: Any,
):
    if not _is_unix_platform():
        return None
    shell_zsh_path = getattr(zsh_fork_config, "shell_zsh_path", None)
    wrapper_exe = getattr(zsh_fork_config, "main_execve_wrapper_exe", None)
    if shell_zsh_path is None or wrapper_exe is None:
        return None
    prepared = await prepare_unified_exec_zsh_fork(
        req,
        attempt,
        ctx,
        exec_request,
        shell_zsh_path,
        wrapper_exe,
    )
    if prepared is None:
        return None

    from . import PreparedUnifiedExecSpawn

    return PreparedUnifiedExecSpawn(
        exec_request=prepared.exec_request,
        spawn_lifecycle=ZshForkSpawnLifecycle(prepared.escalation_session),
    )


__all__ = [
    "ZshForkSpawnLifecycle",
    "maybe_prepare_unified_exec",
    "maybe_run_shell_command",
]
