"""MCP startup state handling for Rust ``chatwidget::mcp_startup``.

The Rust implementation is an impl block on ``ChatWidget``. Python represents
that module-owned behavior with a small semantic state model so startup rounds,
headers, warnings, and queued-input release points can be tested without
fabricating the whole widget/runtime stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::mcp_startup", source="codex/codex-rs/tui/src/chatwidget/mcp_startup.rs", status="complete")

MCP_STARTUP_SINGLE_HEADER_PREFIX = "Booting MCP server:"
MCP_STARTUP_MULTI_HEADER_PREFIX = "Starting MCP servers"


class McpStartupStatusKind(Enum):
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class McpStartupStatus:
    kind: McpStartupStatusKind
    error: Optional[str] = None

    @classmethod
    def starting(cls) -> "McpStartupStatus":
        return cls(McpStartupStatusKind.STARTING)

    @classmethod
    def ready(cls) -> "McpStartupStatus":
        return cls(McpStartupStatusKind.READY)

    @classmethod
    def failed(cls, error: str) -> "McpStartupStatus":
        return cls(McpStartupStatusKind.FAILED, error)

    @classmethod
    def cancelled(cls) -> "McpStartupStatus":
        return cls(McpStartupStatusKind.CANCELLED)

    def is_starting(self) -> bool:
        return self.kind is McpStartupStatusKind.STARTING

    def is_terminal(self) -> bool:
        return self.kind is not McpStartupStatusKind.STARTING


@dataclass(frozen=True)
class McpServerStatusUpdatedNotification:
    name: str
    status: Union[str, McpStartupStatusKind]
    error: Optional[str] = None


@dataclass
class McpStartupModel:
    expected_servers: Optional[Set[str]] = None
    startup_status: Optional[Dict[str, McpStartupStatus]] = None
    ignore_updates_until_next_start: bool = False
    allow_terminal_only_next_round: bool = False
    pending_next_round_saw_starting: bool = False
    pending_next_round: Dict[str, McpStartupStatus] = field(default_factory=dict)
    status_header: str = ""
    task_running: bool = False
    warnings: List[str] = field(default_factory=list)
    redraw_requests: int = 0
    task_running_updates: int = 0
    reasoning_restores: int = 0
    queued_input_releases: int = 0

    def set_mcp_startup_expected_servers(self, server_names: Iterable[str]) -> None:
        self.expected_servers = set(server_names)

    def update_mcp_startup_status(
        self,
        server: str,
        status: McpStartupStatus,
        complete_when_settled: bool,
    ) -> None:
        activated_pending_round = False
        if self.ignore_updates_until_next_start:
            if status.is_starting() and not self.pending_next_round_saw_starting:
                self.pending_next_round.clear()
                self.allow_terminal_only_next_round = False
            self.pending_next_round_saw_starting = self.pending_next_round_saw_starting or status.is_starting()
            self.pending_next_round[server] = status
            if self.expected_servers is None:
                return
            saw_full_round = not self.expected_servers or all(name in self.pending_next_round for name in self.expected_servers)
            saw_starting = any(state.is_starting() for state in self.pending_next_round.values())
            if not (saw_full_round and (saw_starting or self.allow_terminal_only_next_round)):
                return
            self.ignore_updates_until_next_start = False
            self.allow_terminal_only_next_round = False
            self.pending_next_round_saw_starting = False
            activated_pending_round = True
            startup_status = dict(self.pending_next_round)
            self.pending_next_round.clear()
        else:
            if status.kind is McpStartupStatusKind.FAILED and status.error is not None:
                self.on_warning(status.error)
            startup_status = dict(self.startup_status or {})
            startup_status[server] = status

        if activated_pending_round:
            for state in startup_status.values():
                if state.kind is McpStartupStatusKind.FAILED and state.error is not None:
                    self.on_warning(state.error)

        self.startup_status = startup_status
        self.update_task_running_state()

        if complete_when_settled and self._is_settled_against_expected():
            current = self.startup_status or {}
            failed = sorted(name for name, state in current.items() if state.kind is McpStartupStatusKind.FAILED)
            cancelled = sorted(name for name, state in current.items() if state.kind is McpStartupStatusKind.CANCELLED)
            self.finish_mcp_startup(failed, cancelled)
            return

        self._update_status_header_for_starting()
        self.request_redraw()

    def finish_mcp_startup(self, failed: List[str], cancelled: List[str]) -> None:
        if cancelled:
            self.on_warning(
                "MCP startup interrupted. The following servers were not initialized: "
                + ", ".join(cancelled)
            )
        parts: List[str] = []
        if failed:
            parts.append("failed: " + ", ".join(failed))
        if parts:
            self.on_warning("MCP startup incomplete (" + "; ".join(parts) + ")")

        owned_status = self.status_header_is_mcp_startup_owned()
        self.startup_status = None
        self.ignore_updates_until_next_start = True
        self.allow_terminal_only_next_round = False
        self.pending_next_round.clear()
        self.pending_next_round_saw_starting = False
        self.update_task_running_state()
        if self.task_running and owned_status:
            self.restore_reasoning_status_header()
        self.maybe_send_next_queued_input()
        self.request_redraw()

    def finish_mcp_startup_after_lag(self) -> None:
        if self.ignore_updates_until_next_start:
            if not self.pending_next_round:
                self.pending_next_round_saw_starting = False
            self.allow_terminal_only_next_round = True
        if self.startup_status is None:
            return

        server_names = set(self.startup_status)
        if self.expected_servers is not None:
            server_names.update(self.expected_servers)
        failed: List[str] = []
        cancelled: List[str] = []
        for name in sorted(server_names):
            state = self.startup_status.get(name)
            if state is None or state.kind in {McpStartupStatusKind.CANCELLED, McpStartupStatusKind.STARTING}:
                cancelled.append(name)
            elif state.kind is McpStartupStatusKind.FAILED:
                failed.append(name)
        self.finish_mcp_startup(sorted(set(failed)), sorted(set(cancelled)))

    def status_header_is_mcp_startup_owned(self) -> bool:
        return self.status_header.startswith(MCP_STARTUP_SINGLE_HEADER_PREFIX) or self.status_header.startswith(MCP_STARTUP_MULTI_HEADER_PREFIX)

    def on_mcp_server_status_updated(self, notification: McpServerStatusUpdatedNotification) -> None:
        state = _notification_status(notification)
        self.update_mcp_startup_status(notification.name, state, complete_when_settled=True)

    def on_warning(self, message: str) -> None:
        self.warnings.append(message)

    def set_status_header(self, header: str) -> None:
        self.status_header = header

    def restore_reasoning_status_header(self) -> None:
        self.reasoning_restores += 1

    def maybe_send_next_queued_input(self) -> None:
        self.queued_input_releases += 1

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def update_task_running_state(self) -> None:
        self.task_running_updates += 1

    def _is_settled_against_expected(self) -> bool:
        current = self.startup_status
        expected = self.expected_servers
        return (
            current is not None
            and expected is not None
            and bool(current)
            and all(name in current for name in expected)
            and all(state.is_terminal() for state in current.values())
        )

    def _update_status_header_for_starting(self) -> None:
        current = self.startup_status or {}
        starting = sorted(name for name, state in current.items() if state.is_starting())
        if not starting:
            return
        total = len(current)
        first = starting[0]
        if total > 1:
            completed = total - len(starting)
            shown = starting[:3]
            if len(starting) > 3:
                shown.append("...")
            self.set_status_header(f"{MCP_STARTUP_MULTI_HEADER_PREFIX} ({completed}/{total}): {', '.join(shown)}")
        else:
            self.set_status_header(f"{MCP_STARTUP_SINGLE_HEADER_PREFIX} {first}")


def _notification_status(notification: McpServerStatusUpdatedNotification) -> McpStartupStatus:
    raw = notification.status.value if isinstance(notification.status, McpStartupStatusKind) else str(notification.status).lower()
    if raw == "starting":
        return McpStartupStatus.starting()
    if raw == "ready":
        return McpStartupStatus.ready()
    if raw == "failed":
        return McpStartupStatus.failed(notification.error or f"MCP client for `{notification.name}` failed to start")
    if raw == "cancelled":
        return McpStartupStatus.cancelled()
    raise ValueError(f"unsupported MCP startup status: {notification.status!r}")


__all__ = [
    "MCP_STARTUP_MULTI_HEADER_PREFIX",
    "MCP_STARTUP_SINGLE_HEADER_PREFIX",
    "McpServerStatusUpdatedNotification",
    "McpStartupModel",
    "McpStartupStatus",
    "McpStartupStatusKind",
    "RUST_MODULE",
]
