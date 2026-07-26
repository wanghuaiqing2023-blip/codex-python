"""Grant sandbox users read/execute access to the Codex app runtime cache."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

from ....acl import (
    FILE_GENERIC_EXECUTE,
    FILE_GENERIC_READ,
    ensure_allow_mask_aces,
    path_mask_allows,
)


def ensure_codex_app_runtime_bin_readable(
    sandbox_group_sid: object,
    refresh_errors: list[str],
    log: TextIO,
) -> None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        profile = os.environ.get("USERPROFILE")
        if profile:
            local_app_data = str(Path(profile) / "AppData" / "Local")
    if not local_app_data:
        return

    runtime_bin_dir = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
    if not runtime_bin_dir.is_dir():
        return

    read_execute_mask = FILE_GENERIC_READ | FILE_GENERIC_EXECUTE
    try:
        has_access = path_mask_allows(
            runtime_bin_dir,
            (sandbox_group_sid,),
            read_execute_mask,
        )
    except OSError as exc:
        message = (
            f"runtime bin read/execute mask check failed on {runtime_bin_dir} "
            f"for sandbox_group: {exc}"
        )
        refresh_errors.append(message)
        _log_line(log, f"{message}; continuing")
        has_access = False
    if has_access:
        return

    _log_line(
        log,
        f"granting read/execute ACE to {runtime_bin_dir} for sandbox users",
    )
    try:
        ensure_allow_mask_aces(
            runtime_bin_dir,
            (sandbox_group_sid,),
            read_execute_mask,
        )
    except OSError as exc:
        message = (
            f"grant read/execute ACE failed on {runtime_bin_dir} "
            f"for sandbox_group: {exc}"
        )
        refresh_errors.append(message)
        _log_line(log, message)


def _log_line(log: TextIO, message: str) -> None:
    log.write(message + "\n")


__all__ = ["ensure_codex_app_runtime_bin_readable"]
