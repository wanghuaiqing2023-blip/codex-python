"""Turn-scoped state helpers ported from Codex core.

Rust source: codex/codex-rs/core/src/state/turn.rs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol.models import (
    AdditionalPermissionProfile,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    NetworkPermissions,
)
from pycodex.protocol.request_permissions import (
    RequestPermissionProfile,
    RequestPermissionsResponse,
)


class MailboxDeliveryPhase(str, Enum):
    CURRENT_TURN = "current_turn"
    NEXT_TURN = "next_turn"


class TaskKind(str, Enum):
    REGULAR = "regular"
    REVIEW = "review"
    COMPACT = "compact"


@dataclass
class RunningTask:
    """Lightweight Python coordinate for Rust RunningTask.

    The Rust struct carries async task handles and extension data. PyCodex keeps
    this as a generic holder until the session task runtime needs the full
    behavior.
    """

    done: Any = None
    kind: TaskKind = TaskKind.REGULAR
    task: Any = None
    cancellation_token: Any = None
    handle: Any = None
    turn_context: Any = None
    turn_extension_data: Any = None
    timer: Any = None


@dataclass
class PendingRequestPermissions:
    tx_response: Any
    requested_permissions: RequestPermissionProfile
    cwd: Path

    def __post_init__(self) -> None:
        if not isinstance(self.requested_permissions, RequestPermissionProfile):
            raise TypeError("requested_permissions must be RequestPermissionProfile")
        if not isinstance(self.cwd, Path):
            if not isinstance(self.cwd, str):
                raise TypeError("cwd must be a string or Path")
            self.cwd = Path(self.cwd)


@dataclass
class TurnState:
    pending_input: Any = None
    mailbox_delivery_phase: MailboxDeliveryPhase = MailboxDeliveryPhase.CURRENT_TURN
    tool_calls: int = 0
    has_memory_citation: bool = False
    token_usage_at_turn_start: Any = None
    pending_approvals: dict[str, Any] = field(default_factory=dict)
    pending_request_permissions: dict[str, PendingRequestPermissions] = field(
        default_factory=dict
    )
    pending_user_input: dict[str, Any] = field(default_factory=dict)
    pending_elicitations: dict[tuple[str, Any], Any] = field(default_factory=dict)
    pending_dynamic_tools: dict[str, Any] = field(default_factory=dict)
    _granted_permissions: AdditionalPermissionProfile | None = None
    _strict_auto_review_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mailbox_delivery_phase, MailboxDeliveryPhase):
            self.mailbox_delivery_phase = MailboxDeliveryPhase(self.mailbox_delivery_phase)
        if isinstance(self.tool_calls, bool) or not isinstance(self.tool_calls, int):
            raise TypeError("tool_calls must be an integer")
        if not isinstance(self.has_memory_citation, bool):
            raise TypeError("has_memory_citation must be a bool")
        if self._granted_permissions is not None and not isinstance(
            self._granted_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("granted permissions must be AdditionalPermissionProfile")
        if not isinstance(self._strict_auto_review_enabled, bool):
            raise TypeError("strict_auto_review_enabled must be a bool")

    def insert_pending_approval(self, key: str, tx: Any) -> Any | None:
        _require_str_key(key)
        return _dict_insert(self.pending_approvals, key, tx)

    def remove_pending_approval(self, key: str) -> Any | None:
        _require_str_key(key)
        return self.pending_approvals.pop(key, None)

    def clear_pending_waiters(self) -> None:
        self.pending_approvals.clear()
        self.pending_request_permissions.clear()
        self.pending_user_input.clear()
        self.pending_elicitations.clear()
        self.pending_dynamic_tools.clear()

    def insert_pending_request_permissions(
        self,
        key: str,
        pending_request_permissions: PendingRequestPermissions,
    ) -> PendingRequestPermissions | None:
        _require_str_key(key)
        if not isinstance(pending_request_permissions, PendingRequestPermissions):
            raise TypeError(
                "pending_request_permissions must be PendingRequestPermissions"
            )
        return _dict_insert(
            self.pending_request_permissions,
            key,
            pending_request_permissions,
        )

    def remove_pending_request_permissions(
        self,
        key: str,
    ) -> PendingRequestPermissions | None:
        _require_str_key(key)
        return self.pending_request_permissions.pop(key, None)

    def insert_pending_user_input(self, key: str, tx: Any) -> Any | None:
        _require_str_key(key)
        return _dict_insert(self.pending_user_input, key, tx)

    def remove_pending_user_input(self, key: str) -> Any | None:
        _require_str_key(key)
        return self.pending_user_input.pop(key, None)

    def insert_pending_elicitation(
        self,
        server_name: str,
        request_id: Any,
        tx: Any,
    ) -> Any | None:
        _require_str_key(server_name, "server_name")
        return _dict_insert(self.pending_elicitations, (server_name, request_id), tx)

    def remove_pending_elicitation(self, server_name: str, request_id: Any) -> Any | None:
        _require_str_key(server_name, "server_name")
        return self.pending_elicitations.pop((server_name, request_id), None)

    def insert_pending_dynamic_tool(self, key: str, tx: Any) -> Any | None:
        _require_str_key(key)
        return _dict_insert(self.pending_dynamic_tools, key, tx)

    def remove_pending_dynamic_tool(self, key: str) -> Any | None:
        _require_str_key(key)
        return self.pending_dynamic_tools.pop(key, None)

    def accept_mailbox_delivery_for_current_turn(self) -> None:
        self.set_mailbox_delivery_phase(MailboxDeliveryPhase.CURRENT_TURN)

    def accepts_mailbox_delivery_for_current_turn(self) -> bool:
        return self.mailbox_delivery_phase is MailboxDeliveryPhase.CURRENT_TURN

    def set_mailbox_delivery_phase(self, phase: MailboxDeliveryPhase | str) -> None:
        self.mailbox_delivery_phase = MailboxDeliveryPhase(phase)

    def record_granted_permissions(self, permissions: AdditionalPermissionProfile) -> None:
        if not isinstance(permissions, AdditionalPermissionProfile):
            raise TypeError("permissions must be AdditionalPermissionProfile")
        self._granted_permissions = merge_permission_profiles(
            self._granted_permissions,
            permissions,
        )

    def granted_permissions(self) -> AdditionalPermissionProfile | None:
        return self._granted_permissions

    def enable_strict_auto_review(self) -> None:
        self._strict_auto_review_enabled = True

    def strict_auto_review_enabled(self) -> bool:
        return self._strict_auto_review_enabled


@dataclass
class ActiveTurn:
    task: RunningTask | None = None
    turn_state: TurnState = field(default_factory=TurnState)


def merge_permission_profiles(
    base: AdditionalPermissionProfile | None,
    permissions: AdditionalPermissionProfile | None,
) -> AdditionalPermissionProfile | None:
    """Mirror codex_sandboxing::policy_transforms::merge_permission_profiles."""

    if permissions is None:
        return base
    if base is None:
        return None if permissions.is_empty() else permissions

    network = _merge_network_permissions(base.network, permissions.network)
    file_system = _merge_file_system_permissions(base.file_system, permissions.file_system)
    merged = AdditionalPermissionProfile(network=network, file_system=file_system)
    return None if merged.is_empty() else merged


def response_sender(value: RequestPermissionsResponse | None = None) -> dict[str, Any]:
    """Small test-friendly stand-in for Rust oneshot::Sender."""

    return {"value": value}


def _merge_network_permissions(
    base: NetworkPermissions | None,
    permissions: NetworkPermissions | None,
) -> NetworkPermissions | None:
    if (base is not None and base.enabled is True) or (
        permissions is not None and permissions.enabled is True
    ):
        return NetworkPermissions(enabled=True)
    return None


def _merge_file_system_permissions(
    base: FileSystemPermissions | None,
    permissions: FileSystemPermissions | None,
) -> FileSystemPermissions | None:
    if base is None:
        return permissions
    if permissions is None:
        return base

    entries: list[FileSystemSandboxEntry] = []
    for entry in (*base.entries, *permissions.entries):
        if entry not in entries:
            entries.append(entry)
    merged = FileSystemPermissions(
        entries=tuple(entries),
        glob_scan_max_depth=_merge_glob_scan_max_depth(
            base.entries,
            base.glob_scan_max_depth,
            permissions.entries,
            permissions.glob_scan_max_depth,
        ),
    )
    return None if merged.is_empty() else merged


def _merge_glob_scan_max_depth(
    left_entries: tuple[FileSystemSandboxEntry, ...],
    left_depth: int | None,
    right_entries: tuple[FileSystemSandboxEntry, ...],
    right_depth: int | None,
) -> int | None:
    left_effective = _effective_glob_scan_depth(left_entries, left_depth)
    right_effective = _effective_glob_scan_depth(right_entries, right_depth)
    if left_effective == "unbounded" or right_effective == "unbounded":
        return None
    if isinstance(left_effective, int) and isinstance(right_effective, int):
        return max(left_effective, right_effective)
    if isinstance(left_effective, int):
        return left_effective
    if isinstance(right_effective, int):
        return right_effective
    return None


def _effective_glob_scan_depth(
    entries: tuple[FileSystemSandboxEntry, ...],
    depth: int | None,
) -> int | str | None:
    has_deny_glob = any(
        entry.access is FileSystemAccessMode.DENY
        and getattr(entry.path, "type", None) == "glob_pattern"
        for entry in entries
    )
    if not has_deny_glob:
        return None
    return depth if depth is not None else "unbounded"


def _dict_insert(store: dict[Any, Any], key: Any, value: Any) -> Any | None:
    previous = store.get(key)
    store[key] = value
    return previous


def _require_str_key(key: str, label: str = "key") -> None:
    if not isinstance(key, str):
        raise TypeError(f"{label} must be a string")


__all__ = [
    "ActiveTurn",
    "MailboxDeliveryPhase",
    "PendingRequestPermissions",
    "RunningTask",
    "TaskKind",
    "TurnState",
    "merge_permission_profiles",
    "response_sender",
]
