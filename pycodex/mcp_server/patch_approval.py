"""Patch approval elicitation owned by ``patch_approval.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol import Op, ReviewDecision

from .outgoing_message import OutgoingMessageSender


@dataclass(frozen=True, slots=True)
class PatchApprovalElicitRequestParams:
    message: str
    requested_schema: Any
    thread_id: str
    codex_elicitation: str
    codex_mcp_tool_call_id: str
    codex_event_id: str
    codex_call_id: str
    codex_reason: str | None
    codex_grant_root: Path | None
    codex_changes: Mapping[Any, Any]

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "message": self.message,
            "requestedSchema": self.requested_schema,
            "threadId": self.thread_id,
            "codex_elicitation": self.codex_elicitation,
            "codex_mcp_tool_call_id": self.codex_mcp_tool_call_id,
            "codex_event_id": self.codex_event_id,
            "codex_call_id": self.codex_call_id,
            "codex_changes": {str(path): _mapping(change) for path, change in self.codex_changes.items()},
        }
        if self.codex_reason is not None:
            result["codex_reason"] = self.codex_reason
        if self.codex_grant_root is not None:
            result["codex_grant_root"] = str(self.codex_grant_root)
        return result


@dataclass(frozen=True, slots=True)
class PatchApprovalResponse:
    decision: ReviewDecision

    @classmethod
    def from_mapping(cls, value: Any) -> "PatchApprovalResponse":
        if not isinstance(value, Mapping):
            return cls(ReviewDecision.denied())
        try:
            return cls(ReviewDecision.from_mapping(value.get("decision", "denied")))
        except (TypeError, ValueError):
            return cls(ReviewDecision.denied())


async def handle_patch_approval_request(
    call_id: str,
    reason: str | None,
    grant_root: Path | None,
    changes: Mapping[Any, Any],
    outgoing: OutgoingMessageSender,
    codex: Any,
    request_id: Any,
    tool_call_id: str,
    event_id: str,
    thread_id: str,
) -> asyncio.Task[None]:
    message = "\n".join(
        part for part in (reason, "Allow Codex to apply proposed code changes?") if part
    )
    params = PatchApprovalElicitRequestParams(
        message=message,
        requested_schema={"type": "object", "properties": {}},
        thread_id=str(thread_id),
        codex_elicitation="patch-approval",
        codex_mcp_tool_call_id=str(tool_call_id),
        codex_event_id=str(event_id),
        codex_call_id=str(call_id),
        codex_reason=reason,
        codex_grant_root=Path(grant_root) if grant_root is not None else None,
        codex_changes=dict(changes),
    )
    response = await outgoing.send_request("elicitation/create", params.to_mapping())
    return asyncio.create_task(on_patch_approval_response(call_id, response, codex))


async def on_patch_approval_response(
    approval_id: str,
    receiver: asyncio.Future[Any],
    codex: Any,
) -> None:
    try:
        value = await receiver
    except Exception:
        value = {}
    response = PatchApprovalResponse.from_mapping(value)
    await codex.submit(Op.patch_approval(approval_id, response.decision))


def _mapping(value: Any) -> Any:
    to_mapping = getattr(value, "to_mapping", None)
    return to_mapping() if callable(to_mapping) else value
