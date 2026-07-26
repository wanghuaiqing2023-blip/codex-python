"""Permission-profile capture through the elevated command runner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pycodex.protocol import PermissionProfile


@dataclass(frozen=True)
class ElevatedSandboxProfileCaptureRequest:
    permission_profile: PermissionProfile
    permission_profile_cwd: Path
    codex_home: Path
    command: tuple[str, ...]
    cwd: Path
    env_map: Mapping[str, str]
    timeout_ms: int | None = None
    use_private_desktop: bool = True
    proxy_enforced: bool = False
    read_roots_override: tuple[Path, ...] | None = None
    read_roots_include_platform_defaults: bool = False
    write_roots_override: tuple[Path, ...] | None = None
    deny_read_paths_override: tuple[Path, ...] = ()
    deny_write_paths_override: tuple[Path, ...] = ()


if os.name == "nt":
    from .windows_impl import CaptureResult
    from .windows_impl import run_windows_sandbox_capture_for_permission_profile
else:
    from .stub import CaptureResult
    from .stub import run_windows_sandbox_capture_for_permission_profile


__all__ = [
    "CaptureResult",
    "ElevatedSandboxProfileCaptureRequest",
    "run_windows_sandbox_capture_for_permission_profile",
]
