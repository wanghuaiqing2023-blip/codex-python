"""Exec approval elicitation owned by ``exec_approval.rs``."""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pycodex.protocol import Op, ReviewDecision

from .outgoing_message import OutgoingMessageSender


@dataclass(frozen=True, slots=True)
class ExecApprovalElicitRequestParams:
    message: str
    requested_schema: Any
    thread_id: str
    codex_elicitation: str
    codex_mcp_tool_call_id: str
    codex_event_id: str
    codex_call_id: str
    codex_command: Sequence[str]
    codex_cwd: Path
    codex_parsed_cmd: Sequence[Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "requestedSchema": self.requested_schema,
            "threadId": self.thread_id,
            "codex_elicitation": self.codex_elicitation,
            "codex_mcp_tool_call_id": self.codex_mcp_tool_call_id,
            "codex_event_id": self.codex_event_id,
            "codex_call_id": self.codex_call_id,
            "codex_command": list(self.codex_command),
            "codex_cwd": str(self.codex_cwd),
            "codex_parsed_cmd": [_mapping(item) for item in self.codex_parsed_cmd],
        }


@dataclass(frozen=True, slots=True)
class ExecApprovalResponse:
    decision: ReviewDecision

    @classmethod
    def from_mapping(cls, value: Any) -> "ExecApprovalResponse":
        if not isinstance(value, Mapping):
            return cls(ReviewDecision.denied())
        try:
            return cls(ReviewDecision.from_mapping(value.get("decision", "denied")))
        except (TypeError, ValueError):
            return cls(ReviewDecision.denied())


async def handle_exec_approval_request(
    command: Sequence[str],
    cwd: Path,
    outgoing: OutgoingMessageSender,
    codex: Any,
    request_id: Any,
    tool_call_id: str,
    event_id: str,
    call_id: str,
    approval_id: str,
    codex_parsed_cmd: Sequence[Any],
    thread_id: str,
) -> asyncio.Task[None]:
    escaped = shlex.join(str(part) for part in command)
    params = ExecApprovalElicitRequestParams(
        message=f"Allow Codex to run `{escaped}` in `{cwd}`?",
        requested_schema={"type": "object", "properties": {}},
        thread_id=str(thread_id),
        codex_elicitation="exec-approval",
        codex_mcp_tool_call_id=str(tool_call_id),
        codex_event_id=str(event_id),
        codex_call_id=str(call_id),
        codex_command=tuple(str(part) for part in command),
        codex_cwd=Path(cwd),
        codex_parsed_cmd=tuple(codex_parsed_cmd),
    )
    response = await outgoing.send_request("elicitation/create", params.to_mapping())
    return asyncio.create_task(_on_exec_approval_response(approval_id, event_id, response, codex))


async def _on_exec_approval_response(
    approval_id: str,
    event_id: str,
    receiver: asyncio.Future[Any],
    codex: Any,
) -> None:
    try:
        value = await receiver
    except Exception:
        value = {}
    response = ExecApprovalResponse.from_mapping(value)
    await codex.submit(Op.exec_approval(approval_id, response.decision, event_id))


def _mapping(value: Any) -> Any:
    to_mapping = getattr(value, "to_mapping", None)
    return to_mapping() if callable(to_mapping) else value
