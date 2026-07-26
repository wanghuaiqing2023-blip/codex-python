"""Non-Windows implementation selected by the crate root.

Rust owner: inline module ``codex-windows-sandbox::stub``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaptureResult:
    exit_code: int = 0
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    cancelled: bool = False


def _unsupported() -> OSError:
    return OSError("Windows sandbox is only available on Windows")


def run_windows_sandbox_capture(
    _permission_profile: Any,
    _permission_profile_cwd: str | Path,
    _codex_home: str | Path,
    _command: list[str] | tuple[str, ...],
    _cwd: str | Path,
    _env_map: dict[str, str],
    _timeout_ms: int | None,
    _use_private_desktop: bool,
    *,
    is_cancelled: Any = None,
) -> CaptureResult:
    del is_cancelled
    raise _unsupported()


def run_windows_sandbox_legacy_preflight(
    _permission_profile: Any,
    _permission_profile_cwd: str | Path,
    _codex_home: str | Path,
    _cwd: str | Path,
    _env_map: dict[str, str],
) -> None:
    raise _unsupported()


__all__ = [
    "CaptureResult",
    "run_windows_sandbox_capture",
    "run_windows_sandbox_legacy_preflight",
]
