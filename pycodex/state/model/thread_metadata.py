"""Thread metadata model types ported from ``codex-state/src/model/thread_metadata.rs``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import AskForApproval, ReasoningEffort, SandboxPolicy, SessionSource, ThreadId, ThreadSource

JsonValue = Any

MIN_EPOCH_MILLIS = 1_577_836_800_000


class SortKey(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class Anchor:
    ts: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", _datetime_utc(self.ts, "ts"))


@dataclass(frozen=True)
class ThreadsPage:
    items: tuple["ThreadMetadata", ...]
    next_anchor: Anchor | None
    num_scanned_rows: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(_thread_metadata(item, "items item") for item in self.items))
        if self.next_anchor is not None and not isinstance(self.next_anchor, Anchor):
            raise TypeError("next_anchor must be an Anchor or None")
        _ensure_usize(self.num_scanned_rows, "num_scanned_rows")


@dataclass(frozen=True)
class ExtractionOutcome:
    metadata: "ThreadMetadata"
    memory_mode: str | None
    parse_errors: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _thread_metadata(self.metadata, "metadata"))
        object.__setattr__(self, "memory_mode", _optional_str(self.memory_mode, "memory_mode"))
        _ensure_usize(self.parse_errors, "parse_errors")


@dataclass
class ThreadMetadata:
    id: ThreadId
    rollout_path: Path
    created_at: datetime
    updated_at: datetime
    source: str
    thread_source: ThreadSource | None
    agent_nickname: str | None
    agent_role: str | None
    agent_path: str | None
    model_provider: str
    model: str | None
    reasoning_effort: ReasoningEffort | None
    cwd: Path
    cli_version: str
    title: str
    preview: str | None
    sandbox_policy: str
    approval_mode: str
    tokens_used: int
    first_user_message: str | None
    archived_at: datetime | None
    git_sha: str | None
    git_branch: str | None
    git_origin_url: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ThreadId):
            raise TypeError("id must be a ThreadId")
        self.rollout_path = _path(self.rollout_path, "rollout_path")
        self.created_at = _datetime_utc(self.created_at, "created_at")
        self.updated_at = _datetime_utc(self.updated_at, "updated_at")
        self.source = _required_str(self.source, "source")
        self.thread_source = _optional_thread_source(self.thread_source)
        self.agent_nickname = _optional_str(self.agent_nickname, "agent_nickname")
        self.agent_role = _optional_str(self.agent_role, "agent_role")
        self.agent_path = _optional_str(self.agent_path, "agent_path")
        self.model_provider = _required_str(self.model_provider, "model_provider")
        self.model = _optional_str(self.model, "model")
        self.reasoning_effort = _optional_reasoning_effort(self.reasoning_effort)
        self.cwd = _path(self.cwd, "cwd")
        self.cli_version = _required_str(self.cli_version, "cli_version")
        self.title = _required_str(self.title, "title")
        self.preview = _optional_str(self.preview, "preview")
        self.sandbox_policy = _required_str(self.sandbox_policy, "sandbox_policy")
        self.approval_mode = _required_str(self.approval_mode, "approval_mode")
        _ensure_i64(self.tokens_used, "tokens_used")
        self.first_user_message = _optional_str(self.first_user_message, "first_user_message")
        self.archived_at = _optional_datetime_utc(self.archived_at, "archived_at")
        self.git_sha = _optional_str(self.git_sha, "git_sha")
        self.git_branch = _optional_str(self.git_branch, "git_branch")
        self.git_origin_url = _optional_str(self.git_origin_url, "git_origin_url")

    def prefer_existing_git_info(self, existing: "ThreadMetadata") -> None:
        existing = _thread_metadata(existing, "existing")
        if existing.git_sha is not None:
            self.git_sha = existing.git_sha
        if existing.git_branch is not None:
            self.git_branch = existing.git_branch
        if existing.git_origin_url is not None:
            self.git_origin_url = existing.git_origin_url

    def diff_fields(self, other: "ThreadMetadata") -> list[str]:
        other = _thread_metadata(other, "other")
        diffs: list[str] = []
        for field_name in (
            "id",
            "rollout_path",
            "created_at",
            "updated_at",
            "source",
            "agent_nickname",
            "agent_role",
            "agent_path",
            "model_provider",
            "model",
            "reasoning_effort",
            "cwd",
            "cli_version",
            "title",
            "preview",
            "sandbox_policy",
            "approval_mode",
            "tokens_used",
            "first_user_message",
            "archived_at",
            "git_sha",
            "git_branch",
            "git_origin_url",
        ):
            if getattr(self, field_name) != getattr(other, field_name):
                diffs.append(field_name)
        return diffs


@dataclass
class ThreadMetadataBuilder:
    id: ThreadId
    rollout_path: Path
    created_at: datetime
    source: SessionSource
    updated_at: datetime | None = None
    thread_source: ThreadSource | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    agent_path: str | None = None
    model_provider: str | None = None
    cwd: Path = field(default_factory=Path)
    cli_version: str | None = None
    sandbox_policy: SandboxPolicy = field(default_factory=SandboxPolicy.new_read_only_policy)
    approval_mode: AskForApproval = AskForApproval.ON_REQUEST
    archived_at: datetime | None = None
    git_sha: str | None = None
    git_branch: str | None = None
    git_origin_url: str | None = None

    @classmethod
    def new(
        cls,
        id: ThreadId,
        rollout_path: Path | str,
        created_at: datetime,
        source: SessionSource,
    ) -> "ThreadMetadataBuilder":
        return cls(id=id, rollout_path=Path(rollout_path), created_at=created_at, source=source)

    def __post_init__(self) -> None:
        if not isinstance(self.id, ThreadId):
            raise TypeError("id must be a ThreadId")
        self.rollout_path = _path(self.rollout_path, "rollout_path")
        self.created_at = _datetime_utc(self.created_at, "created_at")
        if not isinstance(self.source, SessionSource):
            raise TypeError("source must be a SessionSource")
        self.updated_at = _optional_datetime_utc(self.updated_at, "updated_at")
        self.thread_source = _optional_thread_source(self.thread_source)
        self.agent_nickname = _optional_str(self.agent_nickname, "agent_nickname")
        self.agent_role = _optional_str(self.agent_role, "agent_role")
        self.agent_path = _optional_str(self.agent_path, "agent_path")
        self.model_provider = _optional_str(self.model_provider, "model_provider")
        self.cwd = _path(self.cwd, "cwd")
        self.cli_version = _optional_str(self.cli_version, "cli_version")
        if not isinstance(self.sandbox_policy, SandboxPolicy):
            raise TypeError("sandbox_policy must be a SandboxPolicy")
        if not isinstance(self.approval_mode, AskForApproval):
            self.approval_mode = AskForApproval.parse(str(self.approval_mode))
        self.archived_at = _optional_datetime_utc(self.archived_at, "archived_at")
        self.git_sha = _optional_str(self.git_sha, "git_sha")
        self.git_branch = _optional_str(self.git_branch, "git_branch")
        self.git_origin_url = _optional_str(self.git_origin_url, "git_origin_url")

    def build(self, default_provider: str) -> ThreadMetadata:
        created_at = canonicalize_datetime(self.created_at)
        updated_at = canonicalize_datetime(self.updated_at) if self.updated_at is not None else created_at
        agent_path = self.agent_path
        if agent_path is None:
            source_agent_path = self.source.get_agent_path()
            agent_path = str(source_agent_path) if source_agent_path is not None else None
        return ThreadMetadata(
            id=self.id,
            rollout_path=self.rollout_path,
            created_at=created_at,
            updated_at=updated_at,
            source=enum_to_string(self.source),
            thread_source=self.thread_source,
            agent_nickname=self.agent_nickname,
            agent_role=self.agent_role,
            agent_path=agent_path,
            model_provider=self.model_provider or _required_str(default_provider, "default_provider"),
            model=None,
            reasoning_effort=None,
            cwd=self.cwd,
            cli_version=self.cli_version or "",
            title="",
            preview=None,
            sandbox_policy=enum_to_string(self.sandbox_policy),
            approval_mode=enum_to_string(self.approval_mode),
            tokens_used=0,
            first_user_message=None,
            archived_at=canonicalize_datetime(self.archived_at) if self.archived_at is not None else None,
            git_sha=self.git_sha,
            git_branch=self.git_branch,
            git_origin_url=self.git_origin_url,
        )


@dataclass(frozen=True)
class ThreadRow:
    id: str
    rollout_path: str
    created_at: int
    updated_at: int
    source: str
    thread_source: str | None
    agent_nickname: str | None
    agent_role: str | None
    agent_path: str | None
    model_provider: str
    model: str | None
    reasoning_effort: str | None
    cwd: str
    cli_version: str
    title: str
    preview: str
    sandbox_policy: str
    approval_mode: str
    tokens_used: int
    first_user_message: str
    archived_at: int | None
    git_sha: str | None
    git_branch: str | None
    git_origin_url: str | None

    @classmethod
    def from_mapping(cls, row: Mapping[str, JsonValue]) -> "ThreadRow":
        return cls(
            id=_required_str(row.get("id"), "id"),
            rollout_path=_required_str(row.get("rollout_path"), "rollout_path"),
            created_at=_required_i64(row.get("created_at"), "created_at"),
            updated_at=_required_i64(row.get("updated_at"), "updated_at"),
            source=_required_str(row.get("source"), "source"),
            thread_source=_optional_str(row.get("thread_source"), "thread_source"),
            agent_nickname=_optional_str(row.get("agent_nickname"), "agent_nickname"),
            agent_role=_optional_str(row.get("agent_role"), "agent_role"),
            agent_path=_optional_str(row.get("agent_path"), "agent_path"),
            model_provider=_required_str(row.get("model_provider"), "model_provider"),
            model=_optional_str(row.get("model"), "model"),
            reasoning_effort=_optional_str(row.get("reasoning_effort"), "reasoning_effort"),
            cwd=_required_str(row.get("cwd"), "cwd"),
            cli_version=_required_str(row.get("cli_version"), "cli_version"),
            title=_required_str(row.get("title"), "title"),
            preview=_required_str(row.get("preview"), "preview"),
            sandbox_policy=_required_str(row.get("sandbox_policy"), "sandbox_policy"),
            approval_mode=_required_str(row.get("approval_mode"), "approval_mode"),
            tokens_used=_required_i64(row.get("tokens_used"), "tokens_used"),
            first_user_message=_required_str(row.get("first_user_message"), "first_user_message"),
            archived_at=_optional_i64(row.get("archived_at"), "archived_at"),
            git_sha=_optional_str(row.get("git_sha"), "git_sha"),
            git_branch=_optional_str(row.get("git_branch"), "git_branch"),
            git_origin_url=_optional_str(row.get("git_origin_url"), "git_origin_url"),
        )

    def to_thread_metadata(self) -> ThreadMetadata:
        return ThreadMetadata(
            id=ThreadId.from_string(self.id),
            rollout_path=Path(self.rollout_path),
            created_at=epoch_millis_to_datetime(self.created_at),
            updated_at=epoch_millis_to_datetime(self.updated_at),
            source=self.source,
            thread_source=ThreadSource.parse(self.thread_source) if self.thread_source is not None else None,
            agent_nickname=self.agent_nickname,
            agent_role=self.agent_role,
            agent_path=self.agent_path,
            model_provider=self.model_provider,
            model=self.model,
            reasoning_effort=parse_reasoning_effort_lossy(self.reasoning_effort),
            cwd=Path(self.cwd),
            cli_version=self.cli_version,
            title=self.title,
            preview=self.preview or None,
            sandbox_policy=self.sandbox_policy,
            approval_mode=self.approval_mode,
            tokens_used=self.tokens_used,
            first_user_message=self.first_user_message or None,
            archived_at=epoch_seconds_to_datetime(self.archived_at) if self.archived_at is not None else None,
            git_sha=self.git_sha,
            git_branch=self.git_branch,
            git_origin_url=self.git_origin_url,
        )


@dataclass(frozen=True)
class BackfillStats:
    scanned: int = 0
    upserted: int = 0
    failed: int = 0

    def __post_init__(self) -> None:
        _ensure_usize(self.scanned, "scanned")
        _ensure_usize(self.upserted, "upserted")
        _ensure_usize(self.failed, "failed")


def anchor_from_item(item: ThreadMetadata, sort_key: SortKey) -> Anchor:
    item = _thread_metadata(item, "item")
    if not isinstance(sort_key, SortKey):
        sort_key = SortKey(str(sort_key))
    return Anchor(ts=item.created_at if sort_key is SortKey.CREATED_AT else item.updated_at)


def canonicalize_datetime(dt: datetime) -> datetime:
    try:
        return epoch_millis_to_datetime(datetime_to_epoch_millis(dt))
    except ValueError:
        return _datetime_utc(dt, "dt")


def datetime_to_epoch_millis(dt: datetime) -> int:
    normalized = _datetime_utc(dt, "dt")
    return int(normalized.timestamp() * 1000)


def datetime_to_epoch_seconds(dt: datetime) -> int:
    normalized = _datetime_utc(dt, "dt")
    return int(normalized.timestamp())


def epoch_millis_to_datetime(value: int) -> datetime:
    _ensure_i64(value, "value")
    millis = value * 1000 if value < MIN_EPOCH_MILLIS else value
    seconds, milliseconds = divmod(millis, 1000)
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=milliseconds * 1000)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"invalid unix timestamp millis: {value}") from exc


def epoch_seconds_to_datetime(value: int) -> datetime:
    _ensure_i64(value, "value")
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"invalid unix timestamp seconds: {value}") from exc


def enum_to_string(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    raw_value = getattr(value, "value", None)
    if isinstance(raw_value, str):
        return raw_value
    if isinstance(value, SessionSource):
        return str(value)
    if isinstance(value, SandboxPolicy):
        return value.type
    to_json = getattr(value, "to_json", None)
    if callable(to_json):
        rendered = to_json()
        return rendered if isinstance(rendered, str) else json.dumps(rendered, separators=(",", ":"))
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return json.dumps(to_mapping(), separators=(",", ":"))
    return str(value)


def parse_reasoning_effort_lossy(value: str | None) -> ReasoningEffort | None:
    if value is None:
        return None
    try:
        return ReasoningEffort.parse(value)
    except Exception:
        return None


def _thread_metadata(value: JsonValue, name: str) -> ThreadMetadata:
    if not isinstance(value, ThreadMetadata):
        raise TypeError(f"{name} must be ThreadMetadata")
    return value


def _optional_thread_source(value: JsonValue) -> ThreadSource | None:
    if value is None:
        return None
    if isinstance(value, ThreadSource):
        return value
    return ThreadSource.parse(str(value))


def _optional_reasoning_effort(value: JsonValue) -> ReasoningEffort | None:
    if value is None:
        return None
    if isinstance(value, ReasoningEffort):
        return value
    return ReasoningEffort.parse(str(value))


def _path(value: JsonValue, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a string or Path")
    return Path(value)


def _datetime_utc(value: JsonValue, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_datetime_utc(value: JsonValue, name: str) -> datetime | None:
    if value is None:
        return None
    return _datetime_utc(value, name)


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _required_str(value, name)


def _ensure_i64(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _required_i64(value: JsonValue, name: str) -> int:
    _ensure_i64(value, name)
    return value


def _optional_i64(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    return _required_i64(value, name)


def _ensure_usize(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


__all__ = [
    "Anchor",
    "BackfillStats",
    "ExtractionOutcome",
    "SortDirection",
    "SortKey",
    "ThreadMetadata",
    "ThreadMetadataBuilder",
    "ThreadRow",
    "ThreadsPage",
    "anchor_from_item",
    "canonicalize_datetime",
    "datetime_to_epoch_millis",
    "datetime_to_epoch_seconds",
    "enum_to_string",
    "epoch_millis_to_datetime",
    "epoch_seconds_to_datetime",
    "parse_reasoning_effort_lossy",
]
