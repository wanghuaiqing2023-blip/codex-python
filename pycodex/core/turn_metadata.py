"""Turn metadata helpers ported from ``core/src/turn_metadata.rs``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping

from pycodex.protocol import (
    PermissionProfile,
    ReasoningEffort,
    ThreadId,
    ThreadSource,
    WindowsSandboxLevel,
)

from pycodex.git_utils import (
    get_git_remote_urls_assume_git_repo,
    get_git_repo_root,
    get_has_changes,
    get_head_commit_hash,
)
from .sandbox_tags import permission_profile_sandbox_tag
from pycodex.utils.string import to_ascii_json_string

MODEL_KEY = "model"
REASONING_EFFORT_KEY = "reasoning_effort"
TURN_STARTED_AT_UNIX_MS_KEY = "turn_started_at_unix_ms"
USER_INPUT_REQUESTED_DURING_TURN_KEY = "user_input_requested_during_turn"
REQUEST_KIND_KEY = "request_kind"
COMPACTION_KEY = "compaction"
WINDOW_ID_KEY = "window_id"
FORKED_FROM_THREAD_ID_KEY = "forked_from_thread_id"
_CLIENT_METADATA_RESERVED_KEYS = frozenset(
    {
        "session_id",
        "thread_id",
        "turn_id",
        TURN_STARTED_AT_UNIX_MS_KEY,
        FORKED_FROM_THREAD_ID_KEY,
        REQUEST_KIND_KEY,
        COMPACTION_KEY,
        WINDOW_ID_KEY,
    }
)


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class CompactionTrigger(_StringEnum):
    AUTO = "auto"


class CompactionReason(_StringEnum):
    CONTEXT_LIMIT = "context_limit"


class CompactionImplementation(_StringEnum):
    RESPONSES_COMPACTION_V2 = "responses_compaction_v2"


class CompactionPhase(_StringEnum):
    MID_TURN = "mid_turn"


class CompactionStrategy(_StringEnum):
    MEMENTO = "memento"


@dataclass(frozen=True)
class CompactionTurnMetadata:
    trigger: CompactionTrigger | str
    reason: CompactionReason | str
    implementation: CompactionImplementation | str
    phase: CompactionPhase | str
    strategy: CompactionStrategy | str = CompactionStrategy.MEMENTO

    def to_mapping(self) -> dict[str, str]:
        return {
            "trigger": _enum_value(self.trigger),
            "reason": _enum_value(self.reason),
            "implementation": _enum_value(self.implementation),
            "phase": _enum_value(self.phase),
            "strategy": _enum_value(self.strategy),
        }


@dataclass(frozen=True)
class McpTurnMetadataContext:
    model: str
    reasoning_effort: ReasoningEffort | str | None = None


@dataclass(frozen=True)
class WorkspaceGitMetadata:
    associated_remote_urls: dict[str, str] | None = None
    latest_git_commit_hash: str | None = None
    has_changes: bool | None = None

    def is_empty(self) -> bool:
        return (
            self.associated_remote_urls is None
            and self.latest_git_commit_hash is None
            and self.has_changes is None
        )


@dataclass(frozen=True)
class TurnMetadataWorkspace:
    associated_remote_urls: dict[str, str] | None = None
    latest_git_commit_hash: str | None = None
    has_changes: bool | None = None

    @classmethod
    def from_git_metadata(cls, value: WorkspaceGitMetadata) -> "TurnMetadataWorkspace":
        return cls(
            associated_remote_urls=value.associated_remote_urls,
            latest_git_commit_hash=value.latest_git_commit_hash,
            has_changes=value.has_changes,
        )

    def to_mapping(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.associated_remote_urls is not None:
            data["associated_remote_urls"] = dict(sorted(self.associated_remote_urls.items()))
        if self.latest_git_commit_hash is not None:
            data["latest_git_commit_hash"] = self.latest_git_commit_hash
        if self.has_changes is not None:
            data["has_changes"] = self.has_changes
        return data


@dataclass(frozen=True)
class TurnMetadataBag:
    request_kind: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    forked_from_thread_id: ThreadId | str | None = None
    thread_source: ThreadSource | str | None = None
    turn_id: str | None = None
    workspaces: dict[str, TurnMetadataWorkspace] = field(default_factory=dict)
    sandbox: str | None = None

    def to_mapping(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.request_kind is not None:
            data[REQUEST_KIND_KEY] = self.request_kind
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.thread_id is not None:
            data["thread_id"] = self.thread_id
        if self.forked_from_thread_id is not None:
            data[FORKED_FROM_THREAD_ID_KEY] = _thread_id_value(self.forked_from_thread_id)
        if self.thread_source is not None:
            data["thread_source"] = _enum_value(self.thread_source)
        if self.turn_id is not None:
            data["turn_id"] = self.turn_id
        if self.workspaces:
            data["workspaces"] = {
                key: value.to_mapping()
                for key, value in sorted(self.workspaces.items(), key=lambda item: item[0])
            }
        if self.sandbox is not None:
            data["sandbox"] = self.sandbox
        return data

    def to_header_value(self) -> str | None:
        try:
            return to_ascii_json_string(self.to_mapping())
        except (TypeError, ValueError):
            return None


def merge_turn_metadata(
    header: str,
    turn_started_at_unix_ms: int | None = None,
    responsesapi_client_metadata: Mapping[str, str] | None = None,
) -> str | None:
    if turn_started_at_unix_ms is None and responsesapi_client_metadata is None:
        return None
    try:
        metadata = json.loads(header)
    except json.JSONDecodeError:
        return None
    if not isinstance(metadata, dict):
        return None

    if turn_started_at_unix_ms is not None:
        _ensure_i64(turn_started_at_unix_ms, TURN_STARTED_AT_UNIX_MS_KEY)
        metadata[TURN_STARTED_AT_UNIX_MS_KEY] = turn_started_at_unix_ms
    if responsesapi_client_metadata is not None:
        for key, value in responsesapi_client_metadata.items():
            _ensure_str(key, "responsesapi_client_metadata key")
            _ensure_str(value, "responsesapi_client_metadata value")
            if key in _CLIENT_METADATA_RESERVED_KEYS:
                continue
            metadata.setdefault(key, value)
    return to_ascii_json_string(metadata)


def build_turn_metadata_bag(
    request_kind: str | None = None,
    session_id: str | None = None,
    thread_id: str | None = None,
    forked_from_thread_id: ThreadId | str | None = None,
    thread_source: ThreadSource | str | None = None,
    turn_id: str | None = None,
    sandbox: str | None = None,
    repo_root: str | None = None,
    workspace_git_metadata: WorkspaceGitMetadata | None = None,
) -> TurnMetadataBag:
    workspaces: dict[str, TurnMetadataWorkspace] = {}
    if repo_root is not None and workspace_git_metadata is not None and not workspace_git_metadata.is_empty():
        workspaces[repo_root] = TurnMetadataWorkspace.from_git_metadata(workspace_git_metadata)
    return TurnMetadataBag(
        request_kind=request_kind,
        session_id=session_id,
        thread_id=thread_id,
        forked_from_thread_id=forked_from_thread_id,
        thread_source=thread_source,
        turn_id=turn_id,
        workspaces=workspaces,
        sandbox=sandbox,
    )


def build_turn_metadata_header(cwd: Path | str, sandbox: str | None = None) -> str | None:
    cwd = Path(cwd)
    repo_root_path = get_git_repo_root(cwd)
    repo_root = str(repo_root_path) if repo_root_path is not None else None

    head_commit_hash = get_head_commit_hash(cwd)
    associated_remote_urls = get_git_remote_urls_assume_git_repo(cwd)
    has_changes = get_has_changes(cwd)
    latest_git_commit_hash = str(head_commit_hash) if head_commit_hash is not None else None

    return build_turn_metadata_bag(
        request_kind="memory",
        sandbox=sandbox,
        repo_root=repo_root,
        workspace_git_metadata=WorkspaceGitMetadata(
            associated_remote_urls=associated_remote_urls,
            latest_git_commit_hash=latest_git_commit_hash,
            has_changes=has_changes,
        ),
    ).to_header_value()


class TurnMetadataState:
    @classmethod
    def new(
        cls,
        session_id: str,
        thread_id: str,
        *args: object,
        forked_from_thread_id: ThreadId | str | None = None,
        thread_source: ThreadSource | str | None = None,
        turn_id: str | None = None,
        cwd: Path | str | None = None,
        permission_profile: PermissionProfile | None = None,
        windows_sandbox_level: WindowsSandboxLevel | None = None,
        enforce_managed_network: bool | None = None,
    ) -> "TurnMetadataState":
        if args:
            if len(args) == 6:
                # Backward-compatible Python order:
                # thread_source, turn_id, cwd, permission_profile, windows_sandbox_level, enforce_managed_network.
                (
                    thread_source,
                    turn_id,
                    cwd,
                    permission_profile,
                    windows_sandbox_level,
                    enforce_managed_network,
                ) = args  # type: ignore[assignment]
            elif len(args) == 7:
                # Rust order:
                # forked_from_thread_id, thread_source, turn_id, cwd, permission_profile,
                # windows_sandbox_level, enforce_managed_network.
                (
                    forked_from_thread_id,
                    thread_source,
                    turn_id,
                    cwd,
                    permission_profile,
                    windows_sandbox_level,
                    enforce_managed_network,
                ) = args  # type: ignore[assignment]
            else:
                raise TypeError("unexpected TurnMetadataState.new arguments")
        if turn_id is None or cwd is None or permission_profile is None or windows_sandbox_level is None or enforce_managed_network is None:
            raise TypeError("missing TurnMetadataState.new arguments")
        return cls(
            session_id=session_id,
            thread_id=thread_id,
            forked_from_thread_id=forked_from_thread_id,
            thread_source=thread_source,
            turn_id=turn_id,
            cwd=cwd,
            permission_profile=permission_profile,
            windows_sandbox_level=windows_sandbox_level,
            enforce_managed_network=enforce_managed_network,
        )

    def __init__(
        self,
        session_id: str,
        thread_id: str,
        forked_from_thread_id: ThreadId | str | None,
        thread_source: ThreadSource | str | None,
        turn_id: str,
        cwd: Path | str,
        permission_profile: PermissionProfile,
        windows_sandbox_level: WindowsSandboxLevel,
        enforce_managed_network: bool,
    ) -> None:
        self.cwd = Path(cwd)
        self.repo_root = _repo_root_string(self.cwd)
        sandbox = permission_profile_sandbox_tag(
            permission_profile,
            windows_sandbox_level,
            enforce_managed_network,
        )
        self.base_metadata = build_turn_metadata_bag(
            session_id=session_id,
            thread_id=thread_id,
            forked_from_thread_id=forked_from_thread_id,
            thread_source=thread_source,
            turn_id=turn_id,
            sandbox=sandbox,
        )
        self.base_header = self.base_metadata.to_header_value() or "{}"
        self.enriched_header: str | None = None
        self.turn_started_at_unix_ms: int | None = None
        self.responsesapi_client_metadata: dict[str, str] | None = None
        self.user_input_requested_during_turn = False

    def current_header_value(self) -> str | None:
        header = self.enriched_header or self.base_header
        return (
            merge_turn_metadata(
                header,
                self.turn_started_at_unix_ms,
                self.responsesapi_client_metadata,
            )
            or header
        )

    def current_meta_value_for_mcp_request(
        self,
        context: McpTurnMetadataContext,
    ) -> dict[str, object] | None:
        header = self.current_header_value()
        if header is None:
            return None
        try:
            metadata = json.loads(header)
        except json.JSONDecodeError:
            return None
        if not isinstance(metadata, dict):
            return None

        metadata[MODEL_KEY] = str(context.model)
        if context.reasoning_effort is None:
            metadata.pop(REASONING_EFFORT_KEY, None)
        else:
            metadata[REASONING_EFFORT_KEY] = _enum_value(context.reasoning_effort)
        if self.user_input_requested_during_turn:
            metadata[USER_INPUT_REQUESTED_DURING_TURN_KEY] = True
        else:
            metadata.pop(USER_INPUT_REQUESTED_DURING_TURN_KEY, None)
        return metadata

    def _current_header_value_for_model_request_kind(self, window_id: str, request_kind: str) -> str | None:
        header = self.current_header_value()
        if header is None:
            return None
        try:
            metadata = json.loads(header)
        except json.JSONDecodeError:
            return None
        if not isinstance(metadata, dict):
            return None
        metadata[REQUEST_KIND_KEY] = request_kind
        metadata[WINDOW_ID_KEY] = window_id
        return to_ascii_json_string(metadata)

    def current_header_value_for_model_request(self, window_id: str) -> str | None:
        return self._current_header_value_for_model_request_kind(window_id, "turn")

    def current_header_value_for_prewarm(self, window_id: str) -> str | None:
        return self._current_header_value_for_model_request_kind(window_id, "prewarm")

    def current_header_value_for_compaction(
        self,
        window_id: str,
        compaction: CompactionTurnMetadata,
    ) -> str | None:
        header = self._current_header_value_for_model_request_kind(window_id, "compaction")
        if header is None:
            return None
        try:
            metadata = json.loads(header)
        except json.JSONDecodeError:
            return None
        if not isinstance(metadata, dict):
            return None
        if not isinstance(compaction, CompactionTurnMetadata):
            raise TypeError("compaction must be a CompactionTurnMetadata")
        metadata[COMPACTION_KEY] = compaction.to_mapping()
        return to_ascii_json_string(metadata)

    def mark_user_input_requested_during_turn(self) -> None:
        self.user_input_requested_during_turn = True

    def set_responsesapi_client_metadata(self, responsesapi_client_metadata: Mapping[str, str]) -> None:
        if not isinstance(responsesapi_client_metadata, Mapping):
            raise TypeError("responsesapi_client_metadata must be a mapping")
        self.responsesapi_client_metadata = {
            key: value
            for key, value in responsesapi_client_metadata.items()
            if _ensure_metadata_pair(key, value)
        }

    def set_turn_started_at_unix_ms(self, turn_started_at_unix_ms: int) -> None:
        _ensure_i64(turn_started_at_unix_ms, TURN_STARTED_AT_UNIX_MS_KEY)
        self.turn_started_at_unix_ms = turn_started_at_unix_ms

    def enrich_with_git_metadata(self) -> None:
        if self.repo_root is None:
            return
        metadata = WorkspaceGitMetadata(
            associated_remote_urls=get_git_remote_urls_assume_git_repo(self.cwd),
            latest_git_commit_hash=(
                str(head_hash)
                if (head_hash := get_head_commit_hash(self.cwd)) is not None
                else None
            ),
            has_changes=get_has_changes(self.cwd),
        )
        enriched = build_turn_metadata_bag(
            session_id=self.base_metadata.session_id,
            thread_id=self.base_metadata.thread_id,
            forked_from_thread_id=self.base_metadata.forked_from_thread_id,
            thread_source=self.base_metadata.thread_source,
            turn_id=self.base_metadata.turn_id,
            sandbox=self.base_metadata.sandbox,
            repo_root=self.repo_root,
            workspace_git_metadata=metadata,
        )
        if enriched.workspaces:
            self.enriched_header = enriched.to_header_value()

    def spawn_git_enrichment_task(self) -> None:
        self.enrich_with_git_metadata()

    def cancel_git_enrichment_task(self) -> None:
        return None


def _repo_root_string(cwd: Path) -> str | None:
    repo_root = get_git_repo_root(cwd)
    return str(repo_root) if repo_root is not None else None


def _enum_value(value: object) -> str:
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


def _thread_id_value(value: ThreadId | str) -> str:
    if isinstance(value, ThreadId):
        return value.to_json()
    return _enum_value(value)


def _ensure_metadata_pair(key: object, value: object) -> bool:
    _ensure_str(key, "responsesapi_client_metadata key")
    _ensure_str(value, "responsesapi_client_metadata value")
    return True


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_i64(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


__all__ = [
    "MODEL_KEY",
    "COMPACTION_KEY",
    "CompactionImplementation",
    "CompactionPhase",
    "CompactionReason",
    "CompactionStrategy",
    "CompactionTrigger",
    "CompactionTurnMetadata",
    "FORKED_FROM_THREAD_ID_KEY",
    "McpTurnMetadataContext",
    "REASONING_EFFORT_KEY",
    "REQUEST_KIND_KEY",
    "TURN_STARTED_AT_UNIX_MS_KEY",
    "TurnMetadataBag",
    "TurnMetadataState",
    "TurnMetadataWorkspace",
    "USER_INPUT_REQUESTED_DURING_TURN_KEY",
    "WINDOW_ID_KEY",
    "WorkspaceGitMetadata",
    "build_turn_metadata_bag",
    "build_turn_metadata_header",
    "merge_turn_metadata",
]
