"""Windows sandbox read-root grants.

Ported from ``codex/codex-rs/core/src/windows_sandbox_read_grants.rs``.

The Rust implementation validates a requested read root, canonicalizes it, and
then delegates to ``windows_sandbox::run_setup_refresh_with_extra_read_roots``.
This stdlib-only port keeps the same validation boundary and exposes the setup
refresh call as an injectable callback rather than pretending to implement the
Windows sandbox setup refresh in pure Python.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import sys
from pathlib import Path
from typing import TypeAlias

from pycodex.protocol.models import PermissionProfile

WindowsSandboxSetupRefresher: TypeAlias = Callable[
    [PermissionProfile, Path, Path, Mapping[str, str], Path, Sequence[Path]],
    object,
]


class WindowsSandboxReadGrantError(ValueError):
    pass


def run_setup_refresh_with_extra_read_roots(
    permission_profile: PermissionProfile,
    permission_profile_cwd: Path,
    command_cwd: Path,
    env_map: Mapping[str, str],
    codex_home: Path,
    extra_read_roots: Sequence[Path],
) -> object:
    if sys.platform != "win32":
        return None
    raise NotImplementedError("windows sandbox setup refresh is not implemented in the stdlib port")


def grant_read_root_non_elevated(
    permission_profile: PermissionProfile,
    permission_profile_cwd: Path | str,
    command_cwd: Path | str,
    env_map: Mapping[str, str],
    codex_home: Path | str,
    read_root: Path | str,
    *,
    setup_refresher: WindowsSandboxSetupRefresher | None = None,
) -> Path:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    permission_profile_cwd = _path_arg(permission_profile_cwd, "permission_profile_cwd")
    command_cwd = _path_arg(command_cwd, "command_cwd")
    codex_home = _path_arg(codex_home, "codex_home")
    read_root = _path_arg(read_root, "read_root")
    env_map = _env_map_arg(env_map)

    if not read_root.is_absolute():
        raise WindowsSandboxReadGrantError(f"path must be absolute: {read_root}")
    if not read_root.exists():
        raise WindowsSandboxReadGrantError(f"path does not exist: {read_root}")
    if not read_root.is_dir():
        raise WindowsSandboxReadGrantError(f"path must be a directory: {read_root}")

    canonical_root = read_root.resolve(strict=True)
    refresher = setup_refresher or run_setup_refresh_with_extra_read_roots
    refresher(
        permission_profile,
        permission_profile_cwd,
        command_cwd,
        env_map,
        codex_home,
        (canonical_root,),
    )
    return canonical_root


def _path_arg(value: Path | str, label: str) -> Path:
    if not isinstance(value, Path | str):
        raise TypeError(f"{label} must be a path")
    return Path(value)


def _env_map_arg(value: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("env_map must be a mapping")
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise TypeError("env_map must map strings to strings")
    return dict(value)


__all__ = [
    "WindowsSandboxReadGrantError",
    "WindowsSandboxSetupRefresher",
    "grant_read_root_non_elevated",
    "run_setup_refresh_with_extra_read_roots",
]
