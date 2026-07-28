"""Default MCP client notification and elicitation handler."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .rmcp_client import ElicitationResponse, SendElicitation

_LOG = logging.getLogger(__name__)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class LoggingClientHandler:
    def __init__(self, client_info: Any, send_elicitation: SendElicitation) -> None:
        self._client_info = client_info
        self._send_elicitation = send_elicitation

    async def create_elicitation(
        self,
        request: Any,
        *,
        request_id: Any,
    ) -> ElicitationResponse:
        return await self._send_elicitation(request_id, request)

    async def on_cancelled(self, params: Any) -> None:
        _LOG.info(
            "MCP server cancelled request (request_id: %s, reason: %r)",
            _field(params, "requestId", _field(params, "request_id")),
            _field(params, "reason"),
        )

    async def on_progress(self, params: Any) -> None:
        _LOG.info(
            "MCP server progress notification (token: %r, progress: %s, total: %r, message: %r)",
            _field(params, "progressToken", _field(params, "progress_token")),
            _field(params, "progress"),
            _field(params, "total"),
            _field(params, "message"),
        )

    async def on_resource_updated(self, params: Any) -> None:
        _LOG.info("MCP server resource updated (uri: %s)", _field(params, "uri"))

    async def on_resource_list_changed(self) -> None:
        _LOG.info("MCP server resource list changed")

    async def on_tool_list_changed(self) -> None:
        _LOG.info("MCP server tool list changed")

    async def on_prompt_list_changed(self) -> None:
        _LOG.info("MCP server prompt list changed")

    def get_info(self) -> Any:
        return self._client_info

    async def on_logging_message(self, params: Any) -> None:
        level = str(_field(params, "level", "info")).lower()
        logger_name = _field(params, "logger")
        data = _field(params, "data")
        message = "MCP server log message (level: %s, logger: %r, data: %s)"
        args = (level, logger_name, data)
        if level in {"emergency", "alert", "critical", "error"}:
            _LOG.error(message, *args)
        elif level == "warning":
            _LOG.warning(message, *args)
        elif level in {"notice", "info"}:
            _LOG.info(message, *args)
        else:
            _LOG.debug(message, *args)

    async def handle_notification(self, method: str, params: Any) -> None:
        handlers = {
            "notifications/cancelled": self.on_cancelled,
            "notifications/progress": self.on_progress,
            "notifications/resources/updated": self.on_resource_updated,
            "notifications/message": self.on_logging_message,
        }
        handler = handlers.get(method)
        if handler is not None:
            await handler(params)
        elif method == "notifications/resources/list_changed":
            await self.on_resource_list_changed()
        elif method == "notifications/tools/list_changed":
            await self.on_tool_list_changed()
        elif method == "notifications/prompts/list_changed":
            await self.on_prompt_list_changed()


__all__ = ["LoggingClientHandler"]
