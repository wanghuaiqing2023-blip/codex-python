"""Core shell environment wrappers ported from ``core/src/exec_env.rs``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeAlias

from pycodex.protocol import ThreadId
from pycodex.protocol.config_types import ShellEnvironmentPolicy
from pycodex.protocol.shell_environment import CODEX_THREAD_ID_ENV_VAR
from pycodex.protocol.shell_environment import create_env as _protocol_create_env
from pycodex.protocol.shell_environment import create_env_from_vars as _protocol_create_env_from_vars
from pycodex.protocol.shell_environment import populate_env as _protocol_populate_env


EnvPairs: TypeAlias = Iterable[tuple[str, str]]


def _ensure_policy(policy: object) -> ShellEnvironmentPolicy:
    if not isinstance(policy, ShellEnvironmentPolicy):
        raise TypeError("policy must be a ShellEnvironmentPolicy")
    return policy


def _ensure_env_pairs(vars: object) -> EnvPairs:
    if isinstance(vars, (str, bytes)) or not isinstance(vars, Iterable):
        raise TypeError("vars must be an iterable of (str, str) pairs")
    checked: list[tuple[str, str]] = []
    for item in vars:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("vars must contain (str, str) pairs")
        key, value = item
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("vars must contain (str, str) pairs")
        checked.append((key, value))
    return checked


def create_env(
    policy: ShellEnvironmentPolicy,
    thread_id: ThreadId | None = None,
) -> dict[str, str]:
    return _protocol_create_env(_ensure_policy(policy), _thread_id_to_str(thread_id))


def create_env_from_vars(
    vars: Iterable[tuple[str, str]],
    policy: ShellEnvironmentPolicy,
    thread_id: ThreadId | None = None,
) -> dict[str, str]:
    return _protocol_create_env_from_vars(_ensure_env_pairs(vars), _ensure_policy(policy), _thread_id_to_str(thread_id))


def populate_env(
    vars: Iterable[tuple[str, str]],
    policy: ShellEnvironmentPolicy,
    thread_id: ThreadId | None = None,
) -> dict[str, str]:
    return _protocol_populate_env(_ensure_env_pairs(vars), _ensure_policy(policy), _thread_id_to_str(thread_id))


def _thread_id_to_str(thread_id: ThreadId | None) -> str | None:
    if thread_id is None:
        return None
    if isinstance(thread_id, ThreadId):
        return thread_id.to_json()
    raise TypeError("thread_id must be a ThreadId")


__all__ = [
    "CODEX_THREAD_ID_ENV_VAR",
    "create_env",
    "create_env_from_vars",
    "populate_env",
]
