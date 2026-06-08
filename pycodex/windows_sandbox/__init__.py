"""Python interface for Rust ``codex-windows-sandbox``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaptureResult:
    exit_code: int
    stdout: bytes = b""
    stderr: bytes = b""


def run_windows_sandbox_capture(*args: Any, **kwargs: Any) -> CaptureResult:
    raise NotImplementedError("codex-windows-sandbox capture runtime is not ported")


def run_windows_sandbox_capture_with_filesystem_overrides(*args: Any, **kwargs: Any) -> CaptureResult:
    raise NotImplementedError("codex-windows-sandbox capture runtime is not ported")


def run_windows_sandbox_legacy_preflight(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError("codex-windows-sandbox legacy preflight is not ported")


def resolve_windows_deny_read_paths(file_system_sandbox_policy: Any, cwd: str | Path) -> list[Path]:
    if hasattr(file_system_sandbox_policy, "get_unreadable_roots_with_cwd"):
        return [Path(path) for path in file_system_sandbox_policy.get_unreadable_roots_with_cwd(Path(cwd))]
    return []


class WindowsSandboxTokenMode(str):
    pass


@dataclass(frozen=True)
class ResolvedWindowsSandboxPermissions:
    permission_profile: Any


def token_mode_for_permission_profile(permission_profile: Any) -> WindowsSandboxTokenMode:
    return WindowsSandboxTokenMode(str(permission_profile))


SETUP_VERSION = 1
SandboxSetupRequest = SetupRootOverrides = SetupErrorReport = SetupFailure = ElevatedSandboxProfileCaptureRequest = object
SetupErrorCode = object
LaunchDesktop = object
ConptyInstance = object
PipeSpawnHandles = object
StderrMode = StdinMode = object
LocalSid = object


def quote_windows_arg(arg: str) -> str:
    if not arg or any(ch.isspace() or ch == '"' for ch in arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def to_wide(value: str) -> list[int]:
    return [*value.encode("utf-16-le"), 0, 0]


def sanitize_setup_metric_tag_value(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def current_log_file_path(*args: Any, **kwargs: Any) -> None:
    return None


current_log_file_path_for_codex_home = current_log_file_path
log_file_path_for_utc_date = current_log_file_path
log_note = lambda *args, **kwargs: None
log_writer = lambda *args, **kwargs: None
canonicalize_path = lambda path: Path(path)
workspace_write_root_contains_path = lambda root, path: Path(path).is_relative_to(Path(root)) if hasattr(Path(path), "is_relative_to") else False
workspace_write_root_overlaps_path = lambda root, path: False
is_command_cwd_root = lambda command_cwd, root: Path(command_cwd) == Path(root)
