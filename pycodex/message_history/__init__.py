"""Python API boundary for Rust crate ``codex-message-history``."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MessageHistoryNotImplementedError(NotImplementedError):
    """Raised when message history persistence behavior is not ported yet."""


@dataclass(frozen=True)
class HistoryEntry:
    session_id: str
    ts: int
    text: str


@dataclass(frozen=True)
class HistoryConfig:
    codex_home: Path
    persistence: Any
    max_bytes: int | None = None

    @classmethod
    def new(cls, codex_home: str | Path, history: Any) -> "HistoryConfig":
        return cls(
            codex_home=Path(codex_home),
            persistence=getattr(history, "persistence", history),
            max_bytes=getattr(history, "max_bytes", None),
        )


async def append_entry(text: str, conversation_id: Any, config: HistoryConfig) -> None:
    if _persistence_is_none(config.persistence):
        return

    path = _history_filepath(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "session_id": str(conversation_id),
        "ts": int(time.time()),
        "text": str(text),
    }
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
    _enforce_history_limit(path, config.max_bytes)


async def history_metadata(config: HistoryConfig) -> tuple[int, int]:
    path = _history_filepath(config)
    try:
        stat = path.stat()
    except OSError:
        return (0, 0)
    log_id = _log_identity(stat)
    try:
        count = path.read_bytes().count(b"\n")
    except OSError:
        count = 0
    return (log_id, count)


def lookup(log_id: int, offset: int, config: HistoryConfig) -> HistoryEntry | None:
    path = _history_filepath(config)
    try:
        stat = path.stat()
    except OSError:
        return None
    if int(log_id or 0) != 0 and _log_identity(stat) != int(log_id):
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index != int(offset):
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    return None
                return HistoryEntry(
                    session_id=str(data["session_id"]),
                    ts=int(data["ts"]),
                    text=str(data["text"]),
                )
    except (OSError, KeyError, TypeError, ValueError):
        return None
    return None


def _history_filepath(config: HistoryConfig) -> Path:
    return Path(config.codex_home) / "history.jsonl"


def _persistence_is_none(value: Any) -> bool:
    raw = getattr(value, "value", value)
    if raw is None:
        return False
    text = str(raw).lower().replace("_", "-")
    return text in {"none", "historypersistence.none"}


def _log_identity(stat: os.stat_result) -> int:
    if os.name == "nt":
        # Rust uses std::os::windows::fs::MetadataExt::creation_time(), i.e.
        # FILETIME 100ns ticks since 1601-01-01. Python exposes Windows ctime
        # as creation time in Unix nanoseconds.
        return int(getattr(stat, "st_ctime_ns", int(stat.st_ctime * 1_000_000_000)) // 100) + 116_444_736_000_000_000
    return int(getattr(stat, "st_ino", 0) or 0)


def _enforce_history_limit(path: Path, max_bytes: int | None) -> None:
    if max_bytes is None:
        return
    try:
        max_value = int(max_bytes)
    except (TypeError, ValueError):
        return
    if max_value <= 0:
        return
    try:
        data = path.read_bytes()
    except OSError:
        return
    if len(data) <= max_value:
        return
    lines = data.splitlines(keepends=True)
    if not lines:
        return
    newest_len = len(lines[-1])
    trim_target = max(int(max_value * 0.8), 1, newest_len)
    tail: list[bytes] = []
    total = 0
    for line in reversed(lines):
        if tail and total + len(line) > trim_target:
            break
        tail.append(line)
        total += len(line)
    path.write_bytes(b"".join(reversed(tail)))


__all__ = [
    "HistoryConfig",
    "HistoryEntry",
    "MessageHistoryNotImplementedError",
    "append_entry",
    "history_metadata",
    "lookup",
]
