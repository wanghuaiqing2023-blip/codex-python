"""Daily diagnostic logging for the Windows sandbox.

Rust owner: ``codex-windows-sandbox::logging`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import os
import sys
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, TextIO


LOG_COMMAND_PREVIEW_LIMIT = 200
LOG_FILE_PREFIX = "sandbox"
LOG_FILE_SUFFIX = "log"
MAX_LOG_FILES = 90
_LOCK = threading.Lock()


def log_file_path_for_utc_date(base_dir: str | Path, value: date) -> Path:
    if not isinstance(value, date):
        raise TypeError("value must be a date")
    return Path(base_dir) / f"{LOG_FILE_PREFIX}.{value:%Y-%m-%d}.{LOG_FILE_SUFFIX}"


def current_log_file_path(base_dir: str | Path) -> Path:
    return log_file_path_for_utc_date(base_dir, datetime.now(timezone.utc).date())


def current_log_file_path_for_codex_home(codex_home: str | Path) -> Path:
    from .setup import sandbox_dir

    return current_log_file_path(sandbox_dir(codex_home))


def log_writer(base_dir: str | Path) -> TextIO | None:
    directory = Path(base_dir)
    if not directory.is_dir():
        return None
    _prune_old_logs(directory)
    try:
        return current_log_file_path(directory).open("a", encoding="utf-8", newline="")
    except OSError:
        return None


def log_start(command: Iterable[str], base_dir: str | Path | None = None) -> None:
    log_note(f"START: {_preview(command)}", base_dir)


def log_success(command: Iterable[str], base_dir: str | Path | None = None) -> None:
    log_note(f"SUCCESS: {_preview(command)}", base_dir)


def log_failure(command: Iterable[str], detail: str, base_dir: str | Path | None = None) -> None:
    log_note(f"FAILURE: {_preview(command)} ({detail})", base_dir)


def debug_log(message: str, base_dir: str | Path | None = None) -> None:
    if os.environ.get("SBX_DEBUG") == "1":
        _append_line(f"DEBUG: {message}", base_dir)
        print(message, file=sys.stderr)


def log_note(message: str, base_dir: str | Path | None = None) -> None:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    executable = Path(sys.executable).name or "proc"
    _append_line(f"[{timestamp} {executable}] {message}", base_dir)


def _append_line(line: str, base_dir: str | Path | None) -> None:
    if base_dir is None:
        return
    with _LOCK:
        stream = log_writer(base_dir)
        if stream is None:
            return
        with stream:
            stream.write(line + "\n")


def _preview(command: Iterable[str]) -> str:
    joined = " ".join(str(part) for part in command)
    encoded = joined.encode("utf-8")
    if len(encoded) <= LOG_COMMAND_PREVIEW_LIMIT:
        return joined
    return encoded[:LOG_COMMAND_PREVIEW_LIMIT].decode("utf-8", errors="ignore")


def _prune_old_logs(directory: Path) -> None:
    try:
        logs = sorted(
            directory.glob(f"{LOG_FILE_PREFIX}.*.{LOG_FILE_SUFFIX}"),
            key=lambda path: path.name,
            reverse=True,
        )
        for path in logs[MAX_LOG_FILES - 1 :]:
            path.unlink(missing_ok=True)
    except OSError:
        pass


__all__ = [
    "LOG_FILE_PREFIX",
    "LOG_FILE_SUFFIX",
    "MAX_LOG_FILES",
    "current_log_file_path",
    "current_log_file_path_for_codex_home",
    "debug_log",
    "log_failure",
    "log_file_path_for_utc_date",
    "log_note",
    "log_start",
    "log_success",
    "log_writer",
]
