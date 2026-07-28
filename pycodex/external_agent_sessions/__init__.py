"""Rust-aligned root module for ``codex-external-agent-sessions``."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonValue = Any

SESSION_TITLE_MAX_LEN = 120

@dataclass(frozen=True)
class ExternalAgentSessionMigration:
    path: Path
    cwd: Path
    title: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "cwd", Path(self.cwd))

@dataclass(frozen=True)
class ConversationMessage:
    role: str
    text: str
    timestamp: int | None = None

@dataclass(frozen=True)
class ImportedExternalAgentSession:
    cwd: Path
    title: str | None
    rollout_items: list[dict[str, JsonValue]]

@dataclass(frozen=True)
class PendingSessionImport:
    source_path: Path
    session: ImportedExternalAgentSession

class PrepareSessionImportsError(Exception):
    pass

class SessionNotDetected(PrepareSessionImportsError):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__(f"external agent session was not detected for import: {self.path}")

def prepare_pending_session_imports(
    codex_home: str | Path,
    requested_sessions: list[ExternalAgentSessionMigration],
    detected_sessions: list[ExternalAgentSessionMigration],
) -> list[PendingSessionImport]:
    detected_session_paths = {session.path for session in detected_sessions}
    pending: list[PendingSessionImport] = []
    for session in requested_sessions:
        try:
            has_been_imported = has_current_session_been_imported(codex_home, session.path)
        except OSError:
            continue
        if session.path not in detected_session_paths and not has_been_imported:
            raise SessionNotDetected(session.path)
        if has_been_imported:
            continue
        imported_session = _load_importable_session(session.path)
        if imported_session is None:
            continue
        pending.append(PendingSessionImport(session.path, imported_session))
    return pending

def prepare_validated_session_imports(
    codex_home: str | Path,
    requested_sessions: list[ExternalAgentSessionMigration],
) -> list[PendingSessionImport]:
    pending: list[PendingSessionImport] = []
    for session in requested_sessions:
        if has_current_session_been_imported(codex_home, session.path):
            continue
        imported_session = _load_importable_session(session.path)
        if imported_session is not None:
            pending.append(PendingSessionImport(session.path, imported_session))
    return pending

def summarize_for_label(text: str) -> str:
    return truncate((text.splitlines() or [""])[0].strip(), SESSION_TITLE_MAX_LEN)

def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(max_len - 3, 0)] + "..."

def now_unix_seconds() -> int:
    return int(time.time())

def _load_importable_session(path: str | Path) -> ImportedExternalAgentSession | None:
    imported_session = load_session_for_import(path)
    if imported_session is None or not imported_session.cwd.is_dir():
        return None
    return imported_session

from .detect import detect_recent_sessions
from .export import load_session_for_import
from .ledger import has_current_session_been_imported, record_imported_session
from .records import SessionSummary, summarize_session

__all__ = [
    "ExternalAgentSessionMigration", "ImportedExternalAgentSession",
    "PendingSessionImport", "PrepareSessionImportsError", "SessionNotDetected",
    "SessionSummary", "detect_recent_sessions",
    "has_current_session_been_imported", "load_session_for_import",
    "prepare_pending_session_imports", "prepare_validated_session_imports",
    "record_imported_session", "summarize_session",
]
