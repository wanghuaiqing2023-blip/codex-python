"""Imported-session ledger owned by ``ledger.rs``."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import JsonValue, now_unix_seconds

SESSION_IMPORT_LEDGER_FILE = "external_agent_session_imports.json"

def has_current_session_been_imported(codex_home: str | Path, source_path: str | Path) -> bool:
    return _ledger_contains_current_source(_load_import_ledger(Path(codex_home)), Path(source_path))

def record_imported_session(
    codex_home: str | Path,
    source_path: str | Path,
    imported_thread_id: str,
) -> None:
    codex_home = Path(codex_home)
    source_path = Path(source_path).resolve()
    content_sha256 = _session_content_sha256(source_path)
    ledger = _load_import_ledger(codex_home)
    records = ledger.setdefault("records", [])
    if any(
        Path(record.get("source_path", "")) == source_path
        and record.get("content_sha256") == content_sha256
        for record in records
    ):
        return
    records.append(
        {
            "source_path": str(source_path),
            "content_sha256": content_sha256,
            "imported_thread_id": str(imported_thread_id),
            "imported_at": now_unix_seconds(),
        }
    )
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / SESSION_IMPORT_LEDGER_FILE).write_text(
        json.dumps(ledger, indent=2),
        encoding="utf-8",
    )

def _load_import_ledger(codex_home: Path) -> dict[str, JsonValue]:
    path = codex_home / SESSION_IMPORT_LEDGER_FILE
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"records": []}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid external agent session import ledger")
    data.setdefault("records", [])
    return data

def _ledger_contains_current_source(ledger: dict[str, JsonValue], source_path: Path) -> bool:
    source_path = source_path.resolve()
    content_sha256 = _session_content_sha256(source_path)
    return any(
        Path(record.get("source_path", "")) == source_path
        and record.get("content_sha256") == content_sha256
        for record in ledger.get("records", [])
        if isinstance(record, dict)
    )

def _session_content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

__all__ = ["has_current_session_been_imported", "record_imported_session"]
