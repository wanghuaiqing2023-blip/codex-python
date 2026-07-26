"""Non-Windows cfg branch for elevated permission-profile capture."""

from __future__ import annotations

from dataclasses import dataclass

from . import ElevatedSandboxProfileCaptureRequest


@dataclass(frozen=True)
class CaptureResult:
    exit_code: int = 0
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False


def run_windows_sandbox_capture_for_permission_profile(
    _request: ElevatedSandboxProfileCaptureRequest,
) -> CaptureResult:
    raise OSError("Windows sandbox is only available on Windows")


__all__ = [
    "CaptureResult",
    "run_windows_sandbox_capture_for_permission_profile",
]
