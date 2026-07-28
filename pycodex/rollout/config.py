"""Rust-aligned owner for ``codex-rollout::config``."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable
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

@runtime_checkable
class RolloutConfigView(Protocol):
    """Structural mirror of Rust ``RolloutConfigView``."""

    @property
    def codex_home(self) -> Path: ...

    @property
    def sqlite_home(self) -> Path: ...

    @property
    def cwd(self) -> Path: ...

    @property
    def model_provider_id(self) -> str: ...

    @property
    def generate_memories(self) -> bool: ...


@dataclass(frozen=True)
class RolloutConfig:
    """Python semantic mirror of Rust ``codex-rollout/src/config.rs``."""

    codex_home: Path
    sqlite_home: Path
    cwd: Path
    model_provider_id: str
    generate_memories: bool

    @classmethod
    def from_view(cls, view: object) -> "RolloutConfig":
        return cls(
            codex_home=_config_path(view, "codex_home"),
            sqlite_home=_config_path(view, "sqlite_home"),
            cwd=_config_path(view, "cwd"),
            model_provider_id=str(_config_value(view, "model_provider_id")),
            generate_memories=bool(_config_value(view, "generate_memories")),
        )

Config = RolloutConfig

def _config_value(config: object, name: str, *, default: object | None = None) -> object:
    if isinstance(config, Mapping):
        value = config.get(name, default)
    else:
        value = getattr(config, name, default)
    if callable(value):
        return value()
    if value is None:
        return default
    return value

def _config_path(config: object, name: str, *, default: Path | None = None) -> Path:
    value = _config_value(config, name, default=default)
    if value is None:
        raise AttributeError(f"config is missing {name}")
    return Path(os.fspath(value))



__all__ = ['Config', 'RolloutConfig', 'RolloutConfigView']
