"""Rust-aligned owner for ``codex-rollout::metadata``."""

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

BACKFILL_BATCH_SIZE = 200

BACKFILL_STATUS_RUNNING = "running"

BACKFILL_STATUS_COMPLETE = "complete"

def parse_timestamp_to_utc(timestamp: str) -> datetime | None:
    """Parse Rust rollout metadata timestamps into UTC datetimes."""

    try:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)
    except ValueError:
        parsed = _parse_rfc3339(timestamp)
        return parsed.astimezone(timezone.utc) if parsed is not None else None

def builder_from_session_meta(
    session_meta: SessionMetaLine | Mapping[str, Any],
    rollout_path: Path,
) -> ThreadMetadataBuilder | None:
    """Build thread metadata from the first Rust ``RolloutItem::SessionMeta``."""

    try:
        line = session_meta if isinstance(session_meta, SessionMetaLine) else SessionMetaLine.from_mapping(dict(session_meta))
    except (KeyError, TypeError, ValueError):
        return None

    created_at = parse_timestamp_to_utc(line.meta.timestamp)
    if created_at is None:
        return None

    git = line.git
    return ThreadMetadataBuilder(
        id=line.meta.id,
        rollout_path=Path(rollout_path),
        created_at=created_at,
        source=line.meta.source,
        thread_source=line.meta.thread_source,
        agent_nickname=line.meta.agent_nickname,
        agent_role=line.meta.agent_role,
        agent_path=line.meta.agent_path,
        model_provider=line.meta.model_provider,
        cwd=Path(line.meta.cwd),
        cli_version=line.meta.cli_version,
        git_sha=git.commit_hash.to_json() if git is not None and git.commit_hash is not None else None,
        git_branch=git.branch if git is not None else None,
        git_origin_url=git.repository_url if git is not None else None,
    )

def builder_from_items(items: Sequence[Any], rollout_path: Path) -> ThreadMetadataBuilder | None:
    """Build metadata from rollout items, falling back to the rollout filename."""

    for item in items:
        payload: Any | None = None
        if isinstance(item, SessionMetaLine):
            payload = item
        elif isinstance(item, Mapping):
            item_type = item.get("type")
            if item_type == "session_meta":
                payload = item.get("payload")
            elif {"id", "timestamp", "cwd", "originator", "cli_version"}.issubset(item.keys()):
                payload = item
        if payload is not None:
            builder = builder_from_session_meta(payload, rollout_path)
            if builder is not None:
                return builder

    parsed = parse_timestamp_uuid_from_filename(Path(rollout_path).name)
    if parsed is None:
        return None
    created_at, thread_id = parsed
    return ThreadMetadataBuilder(
        id=ThreadId.from_string(thread_id),
        rollout_path=Path(rollout_path),
        created_at=created_at,
        source=SessionSource.default(),
    )

def backfill_watermark_for_path(codex_home: Path, path: Path) -> str:
    """Return the Rust metadata backfill watermark key for a rollout path."""

    home = Path(codex_home)
    rollout_path = Path(path)
    try:
        value = rollout_path.relative_to(home)
    except ValueError:
        value = rollout_path
    return value.as_posix()

def extract_metadata_from_rollout(rollout_path: Path, default_provider: str = "") -> ExtractionOutcome:
    """Extract thread metadata from a rollout JSONL file."""

    path = Path(rollout_path)
    items: list[dict[str, Any]] = []
    parse_errors = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"failed to read session file: {path}") from exc

    for raw_line in lines:
        if not raw_line.strip():
            continue
        try:
            line = json.loads(raw_line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if isinstance(line, Mapping):
            items.append(dict(line))
        else:
            parse_errors += 1

    if not items:
        raise ValueError(f"empty session file: {path}")

    builder = builder_from_items(items, path)
    if builder is None:
        raise ValueError(f"rollout missing metadata builder: {path}")

    metadata = builder.build(default_provider)
    updated_at = _file_modified_time(path)
    if updated_at is not None:
        metadata = replace(metadata, updated_at=updated_at)

    memory_mode: str | None = None
    for item in reversed(items):
        if item.get("type") != "session_meta":
            continue
        payload = item.get("payload")
        if isinstance(payload, Mapping):
            value = payload.get("memory_mode")
            if value is not None:
                memory_mode = str(value)
                break

    return ExtractionOutcome(metadata=metadata, memory_mode=memory_mode, parse_errors=parse_errors)

def collect_rollout_paths(root: Path) -> list[Path]:
    """Collect rollout JSONL paths under a root, matching Rust metadata.rs."""

    root = Path(root)
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("rollout-*.jsonl")
        if path.is_file() and path.name.startswith("rollout-") and path.name.endswith(".jsonl")
    )

def _runtime_call(runtime: Any, name: str, *args: Any) -> Any:
    method = getattr(runtime, name, None)
    if not callable(method):
        raise NotImplementedError(f"backfill runtime missing {name}()")
    return method(*args)

def _state_status(state: Any) -> str | None:
    return state.get("status") if isinstance(state, Mapping) else getattr(state, "status", None)

def _state_last_watermark(state: Any) -> str | None:
    return state.get("last_watermark") if isinstance(state, Mapping) else getattr(state, "last_watermark", None)

def _set_memory_mode(runtime: Any, thread_id: str, memory_mode: str) -> None:
    setter = getattr(runtime, "set_thread_memory_mode", None)
    if callable(setter):
        setter(thread_id, memory_mode)

def backfill_sessions(runtime: Any, codex_home: Path, default_provider: str = "") -> BackfillStats:
    """Backfill rollout metadata into a state runtime.

    The runtime is intentionally protocol-shaped: it must provide the same
    method names used by Rust ``StateRuntime`` for this module boundary.
    """

    state = _runtime_call(runtime, "get_backfill_state")
    if _state_status(state) == BACKFILL_STATUS_COMPLETE:
        return BackfillStats()

    claimed = _runtime_call(runtime, "try_claim_backfill")
    if not claimed:
        return BackfillStats()

    state = _runtime_call(runtime, "get_backfill_state")
    if _state_status(state) != BACKFILL_STATUS_RUNNING:
        _runtime_call(runtime, "mark_backfill_running")
        state = BackfillState(status=BACKFILL_STATUS_RUNNING, last_watermark=_state_last_watermark(state))

    codex_home = Path(codex_home)
    rollout_entries: list[tuple[str, Path, bool]] = []
    for root, archived in (
        (codex_home / SESSIONS_SUBDIR, False),
        (codex_home / ARCHIVED_SESSIONS_SUBDIR, True),
    ):
        for path in collect_rollout_paths(root):
            rollout_entries.append((backfill_watermark_for_path(codex_home, path), path, archived))
    rollout_entries.sort(key=lambda entry: entry[0])

    last_state_watermark = _state_last_watermark(state)
    if last_state_watermark is not None:
        rollout_entries = [entry for entry in rollout_entries if entry[0] > last_state_watermark]

    scanned = upserted = failed = 0
    last_watermark = last_state_watermark
    for batch_start in range(0, len(rollout_entries), BACKFILL_BATCH_SIZE):
        batch = rollout_entries[batch_start : batch_start + BACKFILL_BATCH_SIZE]
        for watermark, path, archived in batch:
            scanned += 1
            try:
                outcome = extract_metadata_from_rollout(path, default_provider)
                metadata = replace(outcome.metadata, cwd=normalize_cwd_for_state_db(outcome.metadata.cwd))
                getter = getattr(runtime, "get_thread", None)
                if callable(getter):
                    existing = getter(metadata.id)
                    if existing is not None:
                        metadata.prefer_existing_git_info(existing)
                if archived and metadata.archived_at is None:
                    metadata = replace(metadata, archived_at=metadata.updated_at)
                _runtime_call(runtime, "upsert_thread", metadata)
                _set_memory_mode(runtime, metadata.id, outcome.memory_mode or "enabled")
                upserted += 1
            except Exception:
                failed += 1
        if batch:
            last_watermark = batch[-1][0]
            _runtime_call(runtime, "checkpoint_backfill", last_watermark)

    _runtime_call(runtime, "mark_backfill_complete", last_watermark)
    return BackfillStats(scanned=scanned, upserted=upserted, failed=failed)

from pycodex.rollout.list import _file_modified_time, _parse_rfc3339, parse_timestamp_uuid_from_filename
from pycodex.rollout.state_db import normalize_cwd_for_state_db

__all__ = ['BACKFILL_BATCH_SIZE', 'BACKFILL_STATUS_COMPLETE', 'BACKFILL_STATUS_RUNNING', 'backfill_sessions', 'backfill_watermark_for_path', 'builder_from_items', 'builder_from_session_meta', 'collect_rollout_paths', 'extract_metadata_from_rollout', 'parse_timestamp_to_utc']
