"""Turn metadata helpers ported from ``core/src/turn_metadata.rs``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from pycodex.protocol import (
    PermissionProfile,
    ReasoningEffort,
    ThreadSource,
    WindowsSandboxLevel,
)

from .git_info import (
    get_git_remote_urls_assume_git_repo,
    get_git_repo_root,
    get_has_changes,
    get_head_commit_hash,
)
from .sandbox_tags import permission_profile_sandbox_tag
from .string_utils import to_ascii_json_string

MODEL_KEY = "model"
REASONING_EFFORT_KEY = "reasoning_effort"
TURN_STARTED_AT_UNIX_MS_KEY = "turn_started_at_unix_ms"
USER_INPUT_REQUESTED_DURING_TURN_KEY = "user_input_requested_during_turn"


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
    session_id: str | None = None
    thread_id: str | None = None
    thread_source: ThreadSource | str | None = None
    turn_id: str | None = None
    workspaces: dict[str, TurnMetadataWorkspace] = field(default_factory=dict)
    sandbox: str | None = None

    def to_mapping(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.thread_id is not None:
            data["thread_id"] = self.thread_id
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
        metadata[TURN_STARTED_AT_UNIX_MS_KEY] = int(turn_started_at_unix_ms)
    if responsesapi_client_metadata is not None:
        for key, value in responsesapi_client_metadata.items():
            if key == TURN_STARTED_AT_UNIX_MS_KEY:
                continue
            metadata.setdefault(str(key), str(value))
    return to_ascii_json_string(metadata)


def build_turn_metadata_bag(
    session_id: str | None = None,
    thread_id: str | None = None,
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
        session_id=session_id,
        thread_id=thread_id,
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

    if latest_git_commit_hash is None and associated_remote_urls is None and has_changes is None and sandbox is None:
        return None

    return build_turn_metadata_bag(
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
        thread_source: ThreadSource | str | None,
        turn_id: str,
        cwd: Path | str,
        permission_profile: PermissionProfile,
        windows_sandbox_level: WindowsSandboxLevel,
        enforce_managed_network: bool,
    ) -> "TurnMetadataState":
        return cls(
            session_id=session_id,
            thread_id=thread_id,
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

    def mark_user_input_requested_during_turn(self) -> None:
        self.user_input_requested_during_turn = True

    def set_responsesapi_client_metadata(self, responsesapi_client_metadata: Mapping[str, str]) -> None:
        self.responsesapi_client_metadata = {
            str(key): str(value)
            for key, value in responsesapi_client_metadata.items()
        }

    def set_turn_started_at_unix_ms(self, turn_started_at_unix_ms: int) -> None:
        self.turn_started_at_unix_ms = int(turn_started_at_unix_ms)

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


__all__ = [
    "MODEL_KEY",
    "McpTurnMetadataContext",
    "REASONING_EFFORT_KEY",
    "TURN_STARTED_AT_UNIX_MS_KEY",
    "TurnMetadataBag",
    "TurnMetadataState",
    "TurnMetadataWorkspace",
    "USER_INPUT_REQUESTED_DURING_TURN_KEY",
    "WorkspaceGitMetadata",
    "build_turn_metadata_bag",
    "build_turn_metadata_header",
    "merge_turn_metadata",
]
