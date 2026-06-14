"""Queued interrupt manager for ``codex-tui::chatwidget::interrupts``.

The Rust module queues prompt overlays and deferred tool lifecycle activity while
another interrupt is visible.  Python ports the queue, resolved-prompt matching,
and FIFO flush dispatch with duck-typed event/request objects.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::interrupts",
    source="codex/codex-rs/tui/src/chatwidget/interrupts.rs",
)


@dataclass(frozen=True)
class QueuedInterrupt:
    kind: str
    payload: Any = None
    request_id: Any = None
    params: Any = None

    @classmethod
    def ExecApproval(cls, event: Any) -> "QueuedInterrupt":
        return cls("ExecApproval", payload=event)

    @classmethod
    def ApplyPatchApproval(cls, event: Any) -> "QueuedInterrupt":
        return cls("ApplyPatchApproval", payload=event)

    @classmethod
    def Elicitation(cls, request_id: Any, params: Any) -> "QueuedInterrupt":
        return cls("Elicitation", request_id=request_id, params=params)

    @classmethod
    def RequestPermissions(cls, event: Any) -> "QueuedInterrupt":
        return cls("RequestPermissions", payload=event)

    @classmethod
    def RequestUserInput(cls, event: Any) -> "QueuedInterrupt":
        return cls("RequestUserInput", payload=event)

    @classmethod
    def ItemStarted(cls, item: Any) -> "QueuedInterrupt":
        return cls("ItemStarted", payload=item)

    @classmethod
    def ItemCompleted(cls, item: Any) -> "QueuedInterrupt":
        return cls("ItemCompleted", payload=item)

    def matches_resolved_prompt(self, request: Any) -> bool:
        request_kind = _variant_name(request)
        if self.kind == "ExecApproval" and request_kind == "ExecApproval":
            return _effective_approval_id(self.payload) == str(_get(request, "id"))
        if self.kind == "ApplyPatchApproval" and request_kind in {"FileChangeApproval", "ApplyPatchApproval"}:
            return str(_get(self.payload, "call_id")) == str(_get(request, "id"))
        if self.kind == "Elicitation" and request_kind in {"McpElicitation", "Elicitation"}:
            return (
                str(_get(self.params, "server_name")) == str(_get(request, "server_name"))
                and str(self.request_id) == str(_get(request, "request_id"))
            )
        if self.kind == "RequestPermissions" and request_kind in {"PermissionsApproval", "RequestPermissions"}:
            return str(_get(self.payload, "call_id")) == str(_get(request, "id"))
        if self.kind == "RequestUserInput" and request_kind in {"UserInput", "RequestUserInput"}:
            return str(_get(self.payload, "item_id")) == str(_get(request, "call_id"))
        return False


@dataclass
class InterruptManager:
    queue: Deque[QueuedInterrupt]

    def __init__(self, queue: Any = None) -> None:
        self.queue = deque(queue or [])

    @classmethod
    def new(cls) -> "InterruptManager":
        return cls()

    def is_empty(self) -> bool:
        return not self.queue

    def push_exec_approval(self, event: Any) -> None:
        self.queue.append(QueuedInterrupt.ExecApproval(event))

    def push_apply_patch_approval(self, event: Any) -> None:
        self.queue.append(QueuedInterrupt.ApplyPatchApproval(event))

    def push_elicitation(self, request_id: Any, params: Any) -> None:
        self.queue.append(QueuedInterrupt.Elicitation(request_id, params))

    def push_request_permissions(self, event: Any) -> None:
        self.queue.append(QueuedInterrupt.RequestPermissions(event))

    def push_user_input(self, event: Any) -> None:
        self.queue.append(QueuedInterrupt.RequestUserInput(event))

    def push_item_started(self, item: Any) -> None:
        self.queue.append(QueuedInterrupt.ItemStarted(item))

    def push_item_completed(self, item: Any) -> None:
        self.queue.append(QueuedInterrupt.ItemCompleted(item))

    def remove_resolved_prompt(self, request: Any) -> bool:
        original_len = len(self.queue)
        self.queue = deque(queued for queued in self.queue if not queued.matches_resolved_prompt(request))
        return len(self.queue) != original_len

    def flush_all(self, chat: Any) -> list[QueuedInterrupt]:
        flushed: list[QueuedInterrupt] = []
        while self.queue:
            queued = self.queue.popleft()
            flushed.append(queued)
            _dispatch(chat, queued)
        return flushed


def resolved_request(kind: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, **fields}


def user_input(call_id: str, turn_id: str = "turn") -> dict[str, Any]:
    return {"thread_id": "thread-1", "item_id": call_id, "turn_id": turn_id, "questions": []}


def exec_approval(call_id: str, approval_id: str | None = None) -> dict[str, Any]:
    return {"call_id": call_id, "approval_id": approval_id, "turn_id": "turn", "command": ["true"]}


def command_execution(call_id: str) -> dict[str, Any]:
    return {"kind": "CommandExecution", "id": call_id, "command": "true", "status": "InProgress"}


def _dispatch(chat: Any, queued: QueuedInterrupt) -> None:
    handlers = {
        "ExecApproval": ("handle_exec_approval_now", (queued.payload,)),
        "ApplyPatchApproval": ("handle_apply_patch_approval_now", (queued.payload,)),
        "Elicitation": ("handle_elicitation_request_now", (queued.request_id, queued.params)),
        "RequestPermissions": ("handle_request_permissions_now", (queued.payload,)),
        "RequestUserInput": ("handle_request_user_input_now", (queued.payload,)),
        "ItemStarted": ("handle_queued_item_started_now", (queued.payload,)),
        "ItemCompleted": ("handle_queued_item_completed_now", (queued.payload,)),
    }
    method_name, args = handlers[queued.kind]
    handler = getattr(chat, method_name)
    handler(*args)


def _effective_approval_id(event: Any) -> str:
    approval_id = _get(event, "approval_id", None)
    return str(approval_id if approval_id is not None else _get(event, "call_id"))


def _variant_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("kind") or value.get("type") or value.get("variant"))
    kind = getattr(value, "kind", None) or getattr(value, "type", None) or getattr(value, "variant", None)
    if kind is not None:
        return str(kind)
    name = value.__class__.__name__
    return name.removeprefix("ResolvedAppServerRequest")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


__all__ = [
    "InterruptManager",
    "QueuedInterrupt",
    "RUST_MODULE",
    "command_execution",
    "exec_approval",
    "resolved_request",
    "user_input",
]
