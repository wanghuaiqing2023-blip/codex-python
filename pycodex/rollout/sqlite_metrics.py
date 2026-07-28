"""Rust-aligned owner for ``codex-rollout::sqlite_metrics``."""

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

ORIGINATOR_TAG = "originator"

OTHER_ORIGINATOR_TAG_VALUE = "other"

KNOWN_ORIGINATOR_TAG_VALUES = frozenset(
    {
        "codex_desktop",
        "codex-app-server",
        "codex_mcp_server",
        "codex_cli_rs",
        "codex-tui",
        "codex_vscode",
        "none",
        "codex_exec",
        "codex-cli",
        "codex_sdk_ts",
        "codex-app-server-sdk",
    }
)

class SqliteMetricsRecorder:
    """Semantic mirror of rollout ``sqlite_metrics.rs`` telemetry wrapper."""

    def __init__(self, metrics: Any, originator: str) -> None:
        self.metrics = metrics
        self.originator = bounded_originator_tag_value(originator)

    def counter(self, name: str, inc: int, tags: Sequence[tuple[str, str]]) -> object:
        return self.metrics.counter(name, inc, with_originator(tags, self.originator))

    def record_duration(self, name: str, duration: Any, tags: Sequence[tuple[str, str]]) -> object:
        return self.metrics.record_duration(name, duration, with_originator(tags, self.originator))

def sqlite_metrics_recorder(metrics: Any, originator: str) -> SqliteMetricsRecorder:
    return SqliteMetricsRecorder(metrics, originator)

def bounded_originator_tag_value(originator: str) -> str:
    sanitized = sanitize_metric_tag_value(originator)
    if sanitized in KNOWN_ORIGINATOR_TAG_VALUES:
        return sanitized
    return OTHER_ORIGINATOR_TAG_VALUE

def with_originator(tags: Sequence[tuple[str, str]], originator: str) -> list[tuple[str, str]]:
    return [*tags, (ORIGINATOR_TAG, originator)]



__all__ = ['KNOWN_ORIGINATOR_TAG_VALUES', 'ORIGINATOR_TAG', 'OTHER_ORIGINATOR_TAG_VALUE', 'SqliteMetricsRecorder', 'bounded_originator_tag_value', 'sqlite_metrics_recorder', 'with_originator']
