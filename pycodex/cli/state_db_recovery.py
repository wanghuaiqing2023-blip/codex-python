"""Local state database startup recovery helpers.

Ported from ``codex/codex-rs/cli/src/state_db_recovery.rs``.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
from typing import Callable

from pycodex.state import runtime_db_paths

ConfirmCallback = Callable[[str], bool]


def startup_error(error: BaseException) -> object | None:
    """Return an embedded local state DB startup error when one is present."""

    for candidate in (error, error.__cause__, error.__context__):
        if candidate is not None and hasattr(candidate, "state_db_path") and hasattr(candidate, "detail"):
            return candidate
    return None


def is_locked(detail: str) -> bool:
    """Return whether a state DB startup detail describes lock contention."""

    if not isinstance(detail, str):
        raise TypeError("detail must be a string")
    detail = detail.lower()
    return "database is locked" in detail or "database is busy" in detail


def sqlite_paths(db_path: str | Path) -> tuple[Path, Path, Path]:
    """Return the SQLite database path and its WAL/SHM sidecar paths."""

    path = Path(db_path)
    return (path, Path(f"{path}-wal"), Path(f"{path}-shm"))


def backup_path(path: str | Path, repair_suffix: str) -> Path:
    """Rename ``path`` to the first available Codex repair backup path."""

    source = Path(path)
    if not source.name:
        raise OSError(f"cannot create a repair backup name for {source}")
    sequence = 0
    while True:
        candidate = source.with_name(f"{source.name}.{repair_suffix}.{sequence}.bak")
        if not candidate.exists():
            source.rename(candidate)
            return candidate
        sequence += 1


def repair_files(startup_error: object, repair_suffix: str | None = None) -> list[Path]:
    """Back up repairable local SQLite state files for a startup error."""

    state_db_path = startup_error.state_db_path()  # type: ignore[attr-defined]
    state_path = Path(state_db_path)
    sqlite_home = state_path.parent
    suffix = repair_suffix or f"codex-repair-{int(time.time())}"
    backups: list[Path] = []

    if sqlite_home.exists():
        if not sqlite_home.is_dir():
            backups.append(backup_path(sqlite_home, suffix))
            sqlite_home.mkdir(parents=True, exist_ok=True)
    else:
        sqlite_home.mkdir(parents=True, exist_ok=True)

    for db in runtime_db_paths(sqlite_home):
        for path in sqlite_paths(db.path):
            if path.exists():
                backups.append(backup_path(path, suffix))

    if not backups:
        raise OSError("no repairable Codex local data files were found")
    return backups


def confirm_repair(startup_error: object, confirm: ConfirmCallback | None = None) -> bool:
    """Print safe-repair guidance and ask whether Codex should repair local data."""

    print("Codex couldn't start because its local database appears to be damaged.", file=sys.stderr)
    print(
        "Codex can try a safe repair by backing up those files and rebuilding them.",
        file=sys.stderr,
    )
    print_technical_details(startup_error)
    confirm_fn = confirm or _confirm_stdin
    return confirm_fn("Repair Codex local data now? [y/N]: ")


def print_locked_guidance(startup_error: object) -> None:
    """Print user guidance for local state database lock contention."""

    print(
        "Codex couldn't start because another Codex process is using its local data.",
        file=sys.stderr,
    )
    print("Quit any other copies of Codex that may still be running, then try again.", file=sys.stderr)
    print_technical_details(startup_error)


def print_diagnostic_guidance(startup_error: object) -> None:
    """Print user guidance for damaged local state database diagnostics."""

    print("Codex couldn't start because its local database appears to be damaged.", file=sys.stderr)
    print("Run `codex doctor` to check your setup and get next-step guidance.", file=sys.stderr)
    print("If this keeps happening, share the technical details below when asking for help.", file=sys.stderr)
    print_technical_details(startup_error)


def print_repair_backups(backups: list[str | Path]) -> None:
    """Print the local state DB repair backup paths."""

    print("Backed up Codex local data before repair:", file=sys.stderr)
    for backup in backups:
        print(f"  {Path(backup)}", file=sys.stderr)
    print("Retrying startup with rebuilt local data...", file=sys.stderr)


def print_technical_details(startup_error: object) -> None:
    """Print the local state DB startup error's technical details."""

    print("Technical details:", file=sys.stderr)
    print(f"  Location: {startup_error.state_db_path()}", file=sys.stderr)  # type: ignore[attr-defined]
    print(f"  Cause: {startup_error.detail()}", file=sys.stderr)  # type: ignore[attr-defined]


def _confirm_stdin(prompt: str) -> bool:
    response = input(prompt)
    return response.strip().lower() in {"y", "yes"}
