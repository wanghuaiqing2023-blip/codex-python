"""MCP client service with Codex elicitation metadata preservation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .logging_client_handler import LoggingClientHandler
from .rmcp_client import (
    ElicitationPauseState,
    ElicitationResponse,
    SendElicitation,
)

MCP_PROGRESS_TOKEN_META_KEY = "progressToken"


def restore_context_meta(request: Any, context_meta: Mapping[str, Any]) -> Any:
    restored = deepcopy(request)
    meta = {
        str(key): deepcopy(value)
        for key, value in context_meta.items()
        if key != MCP_PROGRESS_TOKEN_META_KEY
    }
    if not meta:
        return restored
    if isinstance(restored, Mapping):
        result = dict(restored)
        request_meta = result.get("_meta")
        merged = dict(request_meta) if isinstance(request_meta, Mapping) else {}
        merged.update(meta)
        result["_meta"] = merged
        return result
    current = getattr(restored, "meta", None)
    merged = dict(current) if isinstance(current, Mapping) else {}
    merged.update(meta)
    setattr(restored, "meta", merged)
    return restored


def elicitation_response_result(response: ElicitationResponse) -> dict[str, Any]:
    action = (
        response.action.value
        if hasattr(response.action, "value")
        else str(response.action)
    )
    result: dict[str, Any] = {"action": action}
    if response.content is not None:
        result["content"] = response.content
    if response.meta is not None:
        result["_meta"] = response.meta
    return result


class ElicitationClientService:
    def __init__(
        self,
        client_info: Any,
        send_elicitation: SendElicitation,
        pause_state: ElicitationPauseState,
    ) -> None:
        self._handler = LoggingClientHandler(client_info, send_elicitation)
        self._send_elicitation = send_elicitation
        self._pause_state = pause_state

    async def handle_request(
        self,
        request: Any,
        *,
        request_id: Any,
        context_meta: Mapping[str, Any] | None = None,
    ) -> Any:
        method = request.get("method") if isinstance(request, Mapping) else None
        if method != "elicitation/create":
            raise ValueError(f"unsupported MCP server request: {method}")
        params = request.get("params", {})
        restored = restore_context_meta(params, context_meta or {})
        with self._pause_state.enter():
            response = await self._send_elicitation(request_id, restored)
        return elicitation_response_result(response)

    async def handle_notification(self, method: str, params: Any) -> None:
        await self._handler.handle_notification(method, params)

    def get_info(self) -> Any:
        return self._handler.get_info()


__all__ = [
    "ElicitationClientService",
    "MCP_PROGRESS_TOKEN_META_KEY",
    "elicitation_response_result",
    "restore_context_meta",
]
