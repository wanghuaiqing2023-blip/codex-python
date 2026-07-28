"""Recent external-session detection owned by ``detect.rs``."""

from __future__ import annotations

from pathlib import Path

from . import ExternalAgentSessionMigration, now_unix_seconds
from .ledger import _ledger_contains_current_source, _load_import_ledger
from .records import summarize_session

SESSION_IMPORT_MAX_COUNT = 50

SESSION_IMPORT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

def detect_recent_sessions(
    external_agent_home: str | Path,
    codex_home: str | Path,
) -> list[ExternalAgentSessionMigration]:
    external_agent_home = Path(external_agent_home)
    codex_home = Path(codex_home)
    projects_root = external_agent_home / "projects"
    if not projects_root.is_dir():
        return []
    now = now_unix_seconds()
    ledger = _load_import_ledger(codex_home)
    candidates: list[tuple[int, ExternalAgentSessionMigration]] = []
    for project_path in projects_root.iterdir():
        if not project_path.is_dir():
            continue
        try:
            entries = list(project_path.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.suffix != ".jsonl":
                continue
            try:
                summary = summarize_session(path)
                if summary is None:
                    continue
                if _ledger_contains_current_source(ledger, path):
                    continue
            except OSError:
                continue
            if not _is_recent_enough(now, summary.latest_timestamp):
                continue
            if not summary.migration.cwd.is_dir():
                continue
            candidates.append((summary.latest_timestamp, summary.migration))
    candidates.sort(key=lambda item: (-item[0], str(item[1].path)))
    return [migration for _, migration in candidates[:SESSION_IMPORT_MAX_COUNT]]

def _is_recent_enough(now: int, latest_timestamp: int) -> bool:
    return latest_timestamp >= max(0, now - SESSION_IMPORT_MAX_AGE_SECONDS)

__all__ = ["detect_recent_sessions"]
