"""Rust-aligned owner for ``codex-rollout::search``."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from pycodex.protocol import SessionSource
from pycodex.protocol.models import ResponseItem
from pycodex.protocol.protocol import (
    USER_MESSAGE_BEGIN,
    CompactedItem,
    EventMsg,
    InitialHistory,
    ResumedHistory,
    RolloutItem,
    ThreadId,
    ThreadRolledBackEvent,
    TurnContextItem,
)
from pycodex.utils.string import sanitize_metric_tag_value

from pycodex.protocol.protocol import GitInfo, SessionMeta, SessionMetaLine
from pycodex.state.model.backfill_state import BackfillState
from pycodex.state.model.thread_metadata import (
    Anchor,
    BackfillStats,
    ExtractionOutcome,
    ThreadMetadata,
    ThreadMetadataBuilder,
)
from pycodex.rollout import ARCHIVED_SESSIONS_SUBDIR, SESSIONS_SUBDIR

MATCH_CONTEXT_BEFORE_CHARS = 48

MATCH_CONTEXT_AFTER_CHARS = 96

def search_rollout_paths(
    rg_command: Path | str | None,
    codex_home: Path | str,
    archived: bool,
    search_term: str,
) -> set[Path]:
    """Return rollout JSONL paths whose raw file body contains the JSON-escaped term.

    Rust uses ripgrep first and falls back to an async filesystem scan.  Python
    keeps the semantic fallback path as the primary implementation to avoid a
    hard dependency on an external ``rg`` binary.
    """

    _ = rg_command
    root = Path(codex_home) / (ARCHIVED_SESSIONS_SUBDIR if archived else SESSIONS_SUBDIR)
    if not root.exists():
        return set()
    escaped = _json_escaped_search_term(search_term).casefold()
    matches: set[Path] = set()
    for path in root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                if any(escaped in line.casefold() for line in file):
                    matches.add(path)
        except OSError:
            raise
        except UnicodeDecodeError:
            continue
    return matches

def first_rollout_content_match_snippet(path: Path | str, search_term: str) -> str | None:
    json_search_term = _json_escaped_search_term(search_term).casefold()
    needle = search_term.casefold()
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if json_search_term not in line.casefold():
                continue
            text = _conversation_text_from_jsonl_line(line)
            if text is None:
                continue
            snippet = _excerpt_around_match(text, needle)
            if snippet is not None:
                return snippet
    return None

def _json_escaped_search_term(search_term: str) -> str:
    serialized = json.dumps(search_term, ensure_ascii=False)
    return serialized[1:-1]

def _conversation_text_from_jsonl_line(line: str) -> str | None:
    try:
        rollout_line = json.loads(line.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(rollout_line, Mapping):
        return None
    item_type = rollout_line.get("type")
    payload = rollout_line.get("payload")
    if item_type == "event_msg":
        return _conversation_text_from_event_msg(payload)
    if item_type == "response_item":
        return _conversation_text_from_response_item(payload)
    return None

def _conversation_text_from_event_msg(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    event_type = payload.get("type")
    if event_type == "user_message":
        text = _strip_user_message_prefix(str(payload.get("message", "")))
        return text or None
    if event_type == "agent_message":
        text = str(payload.get("message", "")).strip()
        return text or None
    return None

def _conversation_text_from_response_item(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    if payload.get("type") != "message" or payload.get("role") not in {"user", "assistant"}:
        return None
    content = payload.get("content")
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") in {"input_text", "output_text"} and isinstance(item.get("text"), str):
            parts.append(item["text"])
    text = " ".join(parts).strip()
    return text or None

def _excerpt_around_match(text: str, needle: str) -> str | None:
    normalized = _normalize_preview_text(text)
    match_start = normalized.casefold().find(needle)
    if match_start < 0:
        return None
    match_end = match_start + len(needle)
    excerpt_start = _char_start_before(normalized, match_start, MATCH_CONTEXT_BEFORE_CHARS)
    excerpt_end = _char_end_after(normalized, match_end, MATCH_CONTEXT_AFTER_CHARS)
    excerpt = normalized[excerpt_start:excerpt_end].strip()
    if not excerpt:
        return None
    prefix = "... " if excerpt_start > 0 else ""
    suffix = " ..." if excerpt_end < len(normalized) else ""
    return f"{prefix}{excerpt}{suffix}"

def _normalize_preview_text(text: str) -> str:
    return " ".join(text.split())

def _char_start_before(text: str, index: int, chars_before: int) -> int:
    return max(0, index - chars_before)

def _char_end_after(text: str, index: int, chars_after: int) -> int:
    return min(len(text), index + chars_after)

from pycodex.rollout.list import _strip_user_message_prefix

__all__ = ['MATCH_CONTEXT_AFTER_CHARS', 'MATCH_CONTEXT_BEFORE_CHARS', 'first_rollout_content_match_snippet', 'search_rollout_paths']
