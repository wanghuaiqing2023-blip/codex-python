"""Session JSONL logging for Rust ``codex-tui::session_log``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="session_log", source="codex/codex-rs/tui/src/session_log.rs")


@dataclass
class SessionLogger:
    _file: Optional[Any] = None
    _lock: Lock = field(default_factory=Lock)

    @classmethod
    def new(cls) -> "SessionLogger":
        return cls()

    def open(self, path: Union[str, os.PathLike]) -> None:
        target = Path(path)
        if target.parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        handle = target.open("w", encoding="utf-8")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        if self._file is None:
            self._file = handle
        else:
            handle.close()

    def write_json_line(self, value: Dict[str, Any]) -> None:
        if self._file is None:
            return
        with self._lock:
            self._file.write(json.dumps(value, separators=(",", ":"), default=_json_default))
            self._file.write("\n")
            self._file.flush()

    def is_enabled(self) -> bool:
        return self._file is not None

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


LOGGER = SessionLogger.new()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return str(value)


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def maybe_init(config: Any, env: Optional[Dict[str, str]] = None, logger: Optional[SessionLogger] = None) -> None:
    source = os.environ if env is None else env
    enabled = source.get("CODEX_TUI_RECORD_SESSION") in {"1", "true", "TRUE", "yes", "YES"}
    if not enabled:
        return

    active_logger = LOGGER if logger is None else logger
    if "CODEX_TUI_SESSION_LOG_PATH" in source:
        path = Path(source["CODEX_TUI_SESSION_LOG_PATH"])
    else:
        filename = f"session-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
        path = Path(_field(config, "log_dir")) / filename

    active_logger.open(path)
    provider = _field(config, "model_provider", {})
    active_logger.write_json_line(
        {
            "ts": now_ts(),
            "dir": "meta",
            "kind": "session_start",
            "cwd": _field(config, "cwd"),
            "model": _field(config, "model"),
            "model_provider_id": _field(config, "model_provider_id"),
            "model_provider_name": _field(provider, "name"),
        }
    )


def log_inbound_app_event(event: Any, logger: Optional[SessionLogger] = None) -> None:
    active_logger = LOGGER if logger is None else logger
    if not active_logger.is_enabled():
        return

    kind = _field(event, "kind", type(event).__name__)
    payload = _field(event, "payload", {})
    if kind == "NewSession":
        value = {"ts": now_ts(), "dir": "to_tui", "kind": "new_session"}
    elif kind == "ClearUi":
        value = {"ts": now_ts(), "dir": "to_tui", "kind": "clear_ui"}
    elif kind == "InsertHistoryCell":
        cell = payload.get("cell") if isinstance(payload, dict) else None
        lines = _transcript_line_count(cell)
        value = {"ts": now_ts(), "dir": "to_tui", "kind": "insert_history_cell", "lines": lines}
    elif kind == "StartFileSearch":
        query = payload.get("query") if isinstance(payload, dict) else None
        value = {"ts": now_ts(), "dir": "to_tui", "kind": "file_search_start", "query": query}
    elif kind == "FileSearchResult":
        query = payload.get("query") if isinstance(payload, dict) else None
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        value = {"ts": now_ts(), "dir": "to_tui", "kind": "file_search_result", "query": query, "matches": len(matches)}
    elif kind == "PetPreviewLoaded":
        result = payload.get("result") if isinstance(payload, dict) else None
        value = {
            "ts": now_ts(),
            "dir": "to_tui",
            "kind": "app_event",
            "variant": "PetPreviewLoaded",
            "request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "ok": not isinstance(result, Exception),
        }
    elif kind == "PetSelectionLoaded":
        result = payload.get("result") if isinstance(payload, dict) else None
        value = {
            "ts": now_ts(),
            "dir": "to_tui",
            "kind": "app_event",
            "variant": "PetSelectionLoaded",
            "request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "pet_id": payload.get("pet_id") if isinstance(payload, dict) else None,
            "ok": not isinstance(result, Exception),
        }
    else:
        value = {"ts": now_ts(), "dir": "to_tui", "kind": "app_event", "variant": kind}
    active_logger.write_json_line(value)


def _transcript_line_count(cell: Any) -> int:
    if cell is None:
        return 0
    transcript_lines = getattr(cell, "transcript_lines", None)
    if callable(transcript_lines):
        return len(transcript_lines(65535))
    lines = getattr(cell, "lines", None)
    if lines is not None:
        return len(lines)
    return 0


def log_outbound_op(op: Any, logger: Optional[SessionLogger] = None) -> None:
    active_logger = LOGGER if logger is None else logger
    if active_logger.is_enabled():
        write_record("from_tui", "op", op, active_logger)


def log_session_end(logger: Optional[SessionLogger] = None) -> None:
    active_logger = LOGGER if logger is None else logger
    if active_logger.is_enabled():
        active_logger.write_json_line({"ts": now_ts(), "dir": "meta", "kind": "session_end"})


def write_record(dir: str, kind: str, obj: Any, logger: Optional[SessionLogger] = None) -> None:
    active_logger = LOGGER if logger is None else logger
    active_logger.write_json_line({"ts": now_ts(), "dir": dir, "kind": kind, "payload": obj})


__all__ = [
    "LOGGER",
    "RUST_MODULE",
    "SessionLogger",
    "log_inbound_app_event",
    "log_outbound_op",
    "log_session_end",
    "maybe_init",
    "now_ts",
    "write_record",
]

