"""Shell environment policy application.

Ported from ``codex/codex-rs/protocol/src/shell_environment.rs``.
"""

from __future__ import annotations

import fnmatch
import os
import sys
from collections.abc import Iterable

from .config_types import ShellEnvironmentPolicy, ShellEnvironmentPolicyInherit


CODEX_THREAD_ID_ENV_VAR = "CODEX_THREAD_ID"
WINDOWS_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"

UNIX_CORE_ENV_VARS = (
    "PATH",
    "SHELL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "USER",
)

WINDOWS_CORE_ENV_VARS = (
    "PATH",
    "PATHEXT",
    "SHELL",
    "COMSPEC",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "USERNAME",
    "USERDOMAIN",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMW6432",
    "PROGRAMDATA",
    "LOCALAPPDATA",
    "APPDATA",
    "TEMP",
    "TMP",
    "TMPDIR",
    "POWERSHELL",
    "PWSH",
)


def create_env(policy: ShellEnvironmentPolicy, thread_id: str | None = None) -> dict[str, str]:
    return create_env_from_vars(os.environ.items(), policy, thread_id)


def create_env_from_vars(
    vars: Iterable[tuple[str, str]],
    policy: ShellEnvironmentPolicy,
    thread_id: str | None = None,
) -> dict[str, str]:
    _validate_policy(policy)
    env_map = populate_env(vars, policy, thread_id)
    if sys.platform == "win32" and not any(key.lower() == "pathext" for key in env_map):
        env_map["PATHEXT"] = WINDOWS_DEFAULT_PATHEXT
    return env_map


def populate_env(
    vars: Iterable[tuple[str, str]],
    policy: ShellEnvironmentPolicy,
    thread_id: str | None = None,
) -> dict[str, str]:
    _validate_policy(policy)
    pairs = _normalize_vars(vars)
    if thread_id is not None and not isinstance(thread_id, str):
        raise TypeError("thread_id must be a string or None")
    if policy.inherit is ShellEnvironmentPolicyInherit.ALL:
        env_map = dict(pairs)
    elif policy.inherit is ShellEnvironmentPolicyInherit.NONE:
        env_map = {}
    elif policy.inherit is ShellEnvironmentPolicyInherit.CORE:
        allowed = WINDOWS_CORE_ENV_VARS if sys.platform == "win32" else UNIX_CORE_ENV_VARS
        env_map = {key: value for key, value in pairs if _matches_any_case_insensitive(key, allowed)}
    else:
        raise ValueError(f"unknown shell environment inherit policy: {policy.inherit}")

    if not policy.ignore_default_excludes:
        default_excludes = ("*KEY*", "*SECRET*", "*TOKEN*")
        env_map = {key: value for key, value in env_map.items() if not _matches_any_pattern(key, default_excludes)}

    if policy.exclude:
        env_map = {key: value for key, value in env_map.items() if not _matches_any_pattern(key, policy.exclude)}

    env_map.update(policy.set_values)

    if policy.include_only:
        env_map = {key: value for key, value in env_map.items() if _matches_any_pattern(key, policy.include_only)}

    if thread_id is not None:
        env_map[CODEX_THREAD_ID_ENV_VAR] = thread_id

    return env_map


def _validate_policy(policy: ShellEnvironmentPolicy) -> None:
    if not isinstance(policy, ShellEnvironmentPolicy):
        raise TypeError("policy must be a ShellEnvironmentPolicy")


def _normalize_vars(vars: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in vars:
        if not isinstance(item, tuple | list) or len(item) != 2:
            raise TypeError("environment variables must be key/value pairs")
        key, value = item
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("environment variable keys and values must be strings")
        pairs.append((key, value))
    return pairs


def _matches_any_case_insensitive(name: str, candidates: Iterable[str]) -> bool:
    lowered = name.lower()
    return any(lowered == candidate.lower() for candidate in candidates)


def _matches_any_pattern(name: str, patterns: Iterable[str]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern.lower()) for pattern in patterns)
