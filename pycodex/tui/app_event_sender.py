"""Convenience sender for app events and outbound TUI commands.

Upstream source: ``codex/codex-rs/tui/src/app_event_sender.rs``.
The Rust module wraps an unbounded channel and provides helpers that package
common UI actions as ``AppCommand`` operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ._porting import RustTuiModule
from .app_command import AppCommand
from ..app_server_protocol.mcp import McpServerElicitationAction

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app_event_sender",
    source="codex/codex-rs/tui/src/app_event_sender.rs",
    status="complete",
)


@dataclass(frozen=True)
class AppEvent:
    """Small semantic event shape for this sender boundary."""

    kind: str
    payload: dict[str, Any]

    @classmethod
    def codex_op(cls, op: AppCommand) -> "AppEvent":
        return cls("CodexOp", {"op": op})

    @classmethod
    def submit_thread_op(cls, thread_id: Any, op: AppCommand) -> "AppEvent":
        return cls("SubmitThreadOp", {"thread_id": thread_id, "op": op})


@dataclass
class AppEventSender:
    """Wrapper around a send target, mirroring Rust ``AppEventSender``."""

    app_event_tx: Any
    inbound_logger: Callable[[AppEvent], None] | None = None
    error_logger: Callable[[Exception], None] | None = None

    @classmethod
    def new(cls, app_event_tx: Any) -> "AppEventSender":
        return cls(app_event_tx=app_event_tx)

    def send(self, event: AppEvent) -> None:
        if event.kind != "CodexOp" and self.inbound_logger is not None:
            self.inbound_logger(event)
        try:
            _send_to_target(self.app_event_tx, event)
        except Exception as exc:  # mirrors Rust swallowing channel send errors after logging
            if self.error_logger is not None:
                self.error_logger(exc)

    def interrupt(self) -> None:
        self.send(AppEvent.codex_op(AppCommand.interrupt()))

    def compact(self) -> None:
        self.send(AppEvent.codex_op(AppCommand.compact()))

    def set_thread_name(self, name: str) -> None:
        self.send(AppEvent.codex_op(AppCommand.set_thread_name(name)))

    def review(self, target: Any) -> None:
        self.send(AppEvent.codex_op(AppCommand.review(target)))

    def insert_history_cell(self, cell: Any) -> None:
        self.send(AppEvent("InsertHistoryCell", {"cell": cell}))

    def open_url_in_browser(self, url: str) -> None:
        self.send(AppEvent("OpenUrlInBrowser", {"url": str(url)}))

    def refresh_connectors(self, force_refetch: bool) -> None:
        self.send(AppEvent("RefreshConnectors", {"force_refetch": bool(force_refetch)}))

    def set_app_enabled(self, id: str, enabled: bool) -> None:
        self.send(AppEvent("SetAppEnabled", {"id": str(id), "enabled": bool(enabled)}))

    def full_screen_approval_request(self, request: Any) -> None:
        self.send(AppEvent("FullScreenApprovalRequest", {"request": request}))

    def select_agent_thread(self, thread_id: Any) -> None:
        self.send(AppEvent("SelectAgentThread", {"thread_id": thread_id}))

    def list_skills(self, cwds: list[str | Path], force_reload: bool) -> None:
        self.send(AppEvent.codex_op(AppCommand.list_skills(cwds, force_reload)))

    def realtime_conversation_audio(self, frame: Any) -> None:
        self.send(AppEvent.codex_op(AppCommand.realtime_conversation_audio(frame)))

    def user_input_answer(self, id: str, response: Any) -> None:
        self.send(AppEvent.codex_op(AppCommand.user_input_answer(id, response)))

    def exec_approval(self, thread_id: Any, id: str, decision: Any) -> None:
        self.send(AppEvent.submit_thread_op(thread_id, AppCommand.exec_approval(id, None, decision)))

    def request_permissions_response(self, thread_id: Any, id: str, response: Any) -> None:
        self.send(AppEvent.submit_thread_op(thread_id, AppCommand.request_permissions_response(id, response)))

    def patch_approval(self, thread_id: Any, id: str, decision: Any) -> None:
        self.send(AppEvent.submit_thread_op(thread_id, AppCommand.patch_approval(id, decision)))

    def resolve_elicitation(
        self,
        thread_id: Any,
        server_name: str,
        request_id: Any,
        decision: Any,
        content: Any | None,
        meta: Any | None,
    ) -> None:
        normalized_decision = (
            decision
            if isinstance(decision, McpServerElicitationAction)
            else McpServerElicitationAction.parse(str(decision).lower())
        )
        self.send(
            AppEvent.submit_thread_op(
                thread_id,
                AppCommand.resolve_elicitation(server_name, request_id, normalized_decision, content, meta),
            )
        )


def _send_to_target(target: Any, event: AppEvent) -> None:
    if hasattr(target, "send"):
        result = target.send(event)
        if isinstance(result, Exception):
            raise result
        return
    if hasattr(target, "put_nowait"):
        target.put_nowait(event)
        return
    if callable(target):
        target(event)
        return
    if isinstance(target, list):
        target.append(event)
        return
    raise TypeError("app_event_tx must be list-like, callable, or expose send/put_nowait")


__all__ = [
    "AppEvent",
    "AppEventSender",
    "RUST_MODULE",
]
