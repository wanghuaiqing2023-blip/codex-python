"""MCP elicitation tracking from ``codex-mcp/src/elicitation.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from pycodex.protocol import ElicitationAction
from pycodex.protocol.config_types import AskForApproval
from pycodex.protocol.models import PermissionProfile

from .mcp import (
    McpPermissionPromptAutoApproveContext,
    mcp_permission_prompt_is_auto_approved,
)


@dataclass(frozen=True)
class ElicitationReviewRequest:
    server_name: str
    request_id: Any
    elicitation: Any


class ElicitationReviewer(Protocol):
    async def review(
        self,
        request: ElicitationReviewRequest,
    ) -> Any | None: ...


ElicitationReviewerHandle = ElicitationReviewer


class ElicitationRequestManager:
    def __init__(
        self,
        approval_policy: AskForApproval,
        permission_profile: PermissionProfile,
        reviewer: ElicitationReviewerHandle | None = None,
    ) -> None:
        self.approval_policy = approval_policy
        self.permission_profile = permission_profile
        self.reviewer = reviewer
        self._auto_deny = False
        self._requests: dict[tuple[str, Any], asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    def auto_deny(self) -> bool:
        return self._auto_deny

    def set_auto_deny(self, auto_deny: bool) -> None:
        self._auto_deny = bool(auto_deny)

    async def resolve(
        self,
        server_name: str,
        request_id: Any,
        response: Any,
    ) -> None:
        async with self._lock:
            future = self._requests.pop((server_name, request_id), None)
        if future is None:
            raise ValueError("elicitation request not found")
        if not future.done():
            future.set_result(response)

    def make_sender(self, server_name: str, tx_event: Any = None) -> Any:
        async def send(request_id: Any, elicitation: Any) -> Any:
            if self._auto_deny:
                return _decline()
            if (
                mcp_permission_prompt_is_auto_approved(
                    self.approval_policy,
                    self.permission_profile,
                    McpPermissionPromptAutoApproveContext(),
                )
                and _can_auto_accept_elicitation(elicitation)
            ):
                return _response(ElicitationAction.ACCEPT, {}, None)
            if elicitation_is_rejected_by_policy(self.approval_policy):
                return _decline()
            if self.reviewer is not None:
                reviewed = await self.reviewer.review(
                    ElicitationReviewRequest(
                        server_name,
                        request_id,
                        elicitation,
                    )
                )
                if reviewed is not None:
                    return reviewed

            future = asyncio.get_running_loop().create_future()
            async with self._lock:
                self._requests[(server_name, request_id)] = future
            await _send_event(tx_event, server_name, request_id, elicitation)
            return await future

        return send


def elicitation_is_rejected_by_policy(approval_policy: AskForApproval | str) -> bool:
    value = getattr(approval_policy, "value", approval_policy)
    return value == AskForApproval.NEVER.value


def _can_auto_accept_elicitation(elicitation: Any) -> bool:
    if isinstance(elicitation, dict):
        if "url" in elicitation or "elicitationId" in elicitation:
            return False
        schema = elicitation.get("requestedSchema", elicitation.get("requested_schema", {}))
    else:
        if getattr(elicitation, "url", None) is not None:
            return False
        schema = getattr(elicitation, "requested_schema", {})
    properties = (
        schema.get("properties", {})
        if isinstance(schema, dict)
        else getattr(schema, "properties", {})
    )
    return not properties


def _decline() -> Any:
    return _response(ElicitationAction.DECLINE, None, None)


def _response(action: ElicitationAction, content: Any, meta: Any) -> Any:
    from pycodex.rmcp_client import ElicitationResponse

    return ElicitationResponse(action, content, meta)


async def _send_event(
    sender: Any,
    server_name: str,
    request_id: Any,
    elicitation: Any,
) -> None:
    if sender is None:
        return
    event = {
        "id": "mcp_elicitation_request",
        "type": "elicitation_request",
        "server_name": server_name,
        "request_id": request_id,
        "request": elicitation,
    }
    method = getattr(sender, "send", None)
    result = method(event) if callable(method) else sender(event) if callable(sender) else None
    if hasattr(result, "__await__"):
        await result


__all__ = [
    "ElicitationRequestManager",
    "ElicitationReviewRequest",
    "ElicitationReviewer",
    "ElicitationReviewerHandle",
    "elicitation_is_rejected_by_policy",
]
