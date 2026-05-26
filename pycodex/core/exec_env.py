"""Core shell environment wrappers ported from ``core/src/exec_env.rs``."""

from __future__ import annotations

from collections.abc import Iterable

from pycodex.protocol import ThreadId
from pycodex.protocol.config_types import ShellEnvironmentPolicy
from pycodex.protocol.shell_environment import CODEX_THREAD_ID_ENV_VAR
from pycodex.protocol.shell_environment import create_env as _protocol_create_env
from pycodex.protocol.shell_environment import create_env_from_vars as _protocol_create_env_from_vars
from pycodex.protocol.shell_environment import populate_env as _protocol_populate_env


def create_env(
    policy: ShellEnvironmentPolicy,
    thread_id: ThreadId | str | None = None,
) -> dict[str, str]:
    return _protocol_create_env(policy, _thread_id_to_str(thread_id))


def create_env_from_vars(
    vars: Iterable[tuple[str, str]],
    policy: ShellEnvironmentPolicy,
    thread_id: ThreadId | str | None = None,
) -> dict[str, str]:
    return _protocol_create_env_from_vars(vars, policy, _thread_id_to_str(thread_id))


def populate_env(
    vars: Iterable[tuple[str, str]],
    policy: ShellEnvironmentPolicy,
    thread_id: ThreadId | str | None = None,
) -> dict[str, str]:
    return _protocol_populate_env(vars, policy, _thread_id_to_str(thread_id))


def _thread_id_to_str(thread_id: ThreadId | str | None) -> str | None:
    if thread_id is None:
        return None
    if isinstance(thread_id, ThreadId):
        return thread_id.to_json()
    return str(thread_id)


__all__ = [
    "CODEX_THREAD_ID_ENV_VAR",
    "create_env",
    "create_env_from_vars",
    "populate_env",
]
