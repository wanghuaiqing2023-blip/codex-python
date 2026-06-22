"""Bubblewrap prerequisite checks for ``codex-sandboxing``.

Rust counterpart: ``codex/codex-rs/sandboxing/src/bwrap.rs``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

from pycodex.protocol import PermissionProfile
from pycodex.sandboxing.policy_transforms import should_require_platform_sandbox


SYSTEM_BWRAP_PROGRAM = "bwrap"
MISSING_BWRAP_WARNING = (
    "Codex could not find bubblewrap on PATH. "
    "Install bubblewrap with your OS package manager. "
    "See the sandbox prerequisites: "
    "https://developers.openai.com/codex/concepts/sandboxing#prerequisites. "
    "Codex will use the bundled bubblewrap in the meantime."
)
USER_NAMESPACE_WARNING = (
    "Codex's Linux sandbox uses bubblewrap and needs access to create user namespaces."
)
WSL1_BWRAP_WARNING = (
    "Codex's Linux sandbox uses bubblewrap, which is not supported on WSL1 "
    "because WSL1 cannot create the required user namespaces. "
    "Use WSL2 for sandboxed shell commands."
)
USER_NAMESPACE_FAILURES = (
    "loopback: Failed RTM_NEWADDR",
    "loopback: Failed RTM_NEWLINK",
    "setting up uid map: Permission denied",
    "No permissions to create a new namespace",
)
SYSTEM_BWRAP_PROBE_TIMEOUT_SECONDS = 0.5
SYSTEM_BWRAP_PROBE_STDERR_LIMIT_BYTES = 64 * 1024


def system_bwrap_warning(permission_profile: PermissionProfile) -> str | None:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be PermissionProfile")
    if not should_warn_about_system_bwrap(permission_profile):
        return None
    return system_bwrap_warning_for_path(find_system_bwrap_in_path())


def should_warn_about_system_bwrap(permission_profile: PermissionProfile) -> bool:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be PermissionProfile")
    file_system_policy, network_policy = permission_profile.to_runtime_permissions()
    return should_require_platform_sandbox(
        file_system_policy,
        network_policy,
        False,
    )


def system_bwrap_warning_for_path(system_bwrap_path: str | Path | None) -> str | None:
    if is_wsl1():
        return WSL1_BWRAP_WARNING
    if system_bwrap_path is None:
        return MISSING_BWRAP_WARNING
    if not system_bwrap_has_user_namespace_access(
        Path(system_bwrap_path),
        SYSTEM_BWRAP_PROBE_TIMEOUT_SECONDS,
    ):
        return USER_NAMESPACE_WARNING
    return None


def system_bwrap_has_user_namespace_access(
    system_bwrap_path: str | Path,
    timeout_seconds: float = SYSTEM_BWRAP_PROBE_TIMEOUT_SECONDS,
) -> bool:
    try:
        output = subprocess.run(
            [
                str(system_bwrap_path),
                "--unshare-user",
                "--unshare-net",
                "--ro-bind",
                "/",
                "/",
                "/bin/true",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    return output.returncode == 0 or not is_user_namespace_failure(output.stderr)


def is_wsl1(proc_version_path: str | Path = "/proc/version") -> bool:
    try:
        proc_version = Path(proc_version_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return proc_version_indicates_wsl1(proc_version)


def proc_version_indicates_wsl1(proc_version: str) -> bool:
    text = proc_version.lower()
    remaining = text
    while True:
        marker = remaining.find("wsl")
        if marker == -1:
            break
        version_start = marker + len("wsl")
        digits = []
        for char in remaining[version_start:]:
            if not char.isascii() or not char.isdigit():
                break
            digits.append(char)
        if digits:
            try:
                return int("".join(digits)) == 1
            except ValueError:
                pass
        remaining = remaining[version_start:]
    return "microsoft" in text and "microsoft-standard" not in text


def is_user_namespace_failure(stderr: bytes | str) -> bool:
    if isinstance(stderr, bytes):
        text = stderr[:SYSTEM_BWRAP_PROBE_STDERR_LIMIT_BYTES].decode("utf-8", errors="replace")
    else:
        text = stderr[:SYSTEM_BWRAP_PROBE_STDERR_LIMIT_BYTES]
    return any(failure in text for failure in USER_NAMESPACE_FAILURES)


def find_system_bwrap_in_path(
    path: str | None = None,
    cwd: str | Path | None = None,
) -> Path | None:
    search_path = os.environ.get("PATH") if path is None else path
    if not search_path:
        return None
    cwd_path = Path.cwd() if cwd is None else Path(cwd)
    return find_system_bwrap_in_search_paths(
        [Path(part) for part in os.get_exec_path({"PATH": search_path})],
        cwd_path,
    )


def find_system_bwrap_in_search_paths(
    search_paths: Iterable[str | Path],
    cwd: str | Path,
) -> Path | None:
    cwd_path = _canonicalize_best_effort(Path(cwd))
    cwd_is_root = _is_root_path(cwd_path)
    for search_path in search_paths:
        candidate = Path(search_path) / SYSTEM_BWRAP_PROGRAM
        if not _is_executable_file(candidate):
            continue
        candidate = _canonicalize_best_effort(candidate)
        if not cwd_is_root and _path_starts_with(candidate, cwd_path):
            continue
        return candidate
    return None


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _canonicalize_best_effort(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError:
        try:
            return path.resolve(strict=False)
        except OSError:
            return path


def _is_root_path(path: Path) -> bool:
    anchor = Path(path.anchor) if path.anchor else None
    return anchor is not None and path == anchor


def _path_starts_with(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
    except ValueError:
        return False
    return True


__all__ = [
    "MISSING_BWRAP_WARNING",
    "SYSTEM_BWRAP_PROGRAM",
    "SYSTEM_BWRAP_PROBE_STDERR_LIMIT_BYTES",
    "SYSTEM_BWRAP_PROBE_TIMEOUT_SECONDS",
    "USER_NAMESPACE_FAILURES",
    "USER_NAMESPACE_WARNING",
    "WSL1_BWRAP_WARNING",
    "find_system_bwrap_in_path",
    "find_system_bwrap_in_search_paths",
    "is_user_namespace_failure",
    "is_wsl1",
    "proc_version_indicates_wsl1",
    "should_warn_about_system_bwrap",
    "system_bwrap_has_user_namespace_access",
    "system_bwrap_warning",
    "system_bwrap_warning_for_path",
]
