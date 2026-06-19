"""Filesystem path helpers ported from ``codex-state/src/paths.rs``."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path


async def file_modified_time_utc(path: Path | str) -> datetime | None:
    """Return a file's modified time as UTC, or ``None`` on metadata errors.

    Rust's ``file_modified_time_utc`` awaits ``tokio::fs::metadata`` and returns
    ``None`` when metadata or modified-time extraction fails.
    """

    try:
        stat_result = await asyncio.to_thread(Path(path).stat)
    except (FileNotFoundError, OSError):
        return None
    try:
        return datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


__all__ = ["file_modified_time_utc"]
