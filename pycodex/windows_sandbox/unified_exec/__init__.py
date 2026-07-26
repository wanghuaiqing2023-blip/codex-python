"""Unified Windows sandbox process spawning.

Rust owner: ``codex-windows-sandbox::unified_exec``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from . import backends


def spawn_windows_sandbox_session_legacy(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: Sequence[str],
    cwd: str | Path,
    env_map: Mapping[str, str],
    timeout_ms: int | None,
    additional_deny_read_paths: Sequence[str | Path],
    additional_deny_write_paths: Sequence[str | Path],
    tty: bool,
    stdin_open: bool,
    use_private_desktop: bool,
):
    return backends.legacy.spawn_windows_sandbox_session_legacy(
        permission_profile,
        permission_profile_cwd,
        codex_home,
        command,
        cwd,
        env_map,
        timeout_ms,
        additional_deny_read_paths,
        additional_deny_write_paths,
        tty,
        stdin_open,
        use_private_desktop,
    )


def spawn_windows_sandbox_session_elevated_for_permission_profile(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: Sequence[str],
    cwd: str | Path,
    env_map: Mapping[str, str],
    timeout_ms: int | None,
    read_roots_override: Sequence[str | Path] | None,
    read_roots_include_platform_defaults: bool,
    write_roots_override: Sequence[str | Path] | None,
    deny_read_paths_override: Sequence[str | Path],
    deny_write_paths_override: Sequence[str | Path],
    tty: bool,
    stdin_open: bool,
    use_private_desktop: bool,
):
    return (
        backends.elevated
        .spawn_windows_sandbox_session_elevated_for_permission_profile(
            permission_profile,
            permission_profile_cwd,
            codex_home,
            command,
            cwd,
            env_map,
            timeout_ms,
            read_roots_override,
            read_roots_include_platform_defaults,
            write_roots_override,
            deny_read_paths_override,
            deny_write_paths_override,
            tty,
            stdin_open,
            use_private_desktop,
        )
    )


__all__ = [
    "spawn_windows_sandbox_session_elevated_for_permission_profile",
    "spawn_windows_sandbox_session_legacy",
]
