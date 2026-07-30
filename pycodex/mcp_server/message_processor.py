"""MCP request dispatch owned by ``message_processor.rs``."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Mapping, MutableMapping

from pycodex import __version__
from pycodex.core.thread_manager import ThreadManager
from pycodex.protocol import Op, SessionSource, Submission

from .codex_tool_config import (
    CodexToolCallParam,
    CodexToolCallReplyParam,
    create_tool_for_codex_tool_call_param,
    create_tool_for_codex_tool_call_reply_param,
)
from .codex_tool_runner import (
    create_call_tool_result_with_thread_id,
    run_codex_tool_session,
    run_codex_tool_session_reply,
)
from .outgoing_message import OutgoingMessageSender


ConfigFactory = Callable[[CodexToolCallParam], Any]


class MessageProcessor:
    def __init__(
        self,
        outgoing: OutgoingMessageSender,
        *,
        thread_manager: Any | None = None,
        config_factory: ConfigFactory | None = None,
    ) -> None:
        self.outgoing = outgoing
        self.initialized = False
        self.thread_manager = thread_manager or ThreadManager.new(session_source=SessionSource.mcp())
        self.config_factory = config_factory
        self.running_requests: MutableMapping[Any, str] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    async def process_message(self, message: Mapping[str, Any]) -> None:
        if "method" in message and "id" in message:
            await self.process_request(message)
            return
        if "method" in message:
            await self.process_notification(message)
            return
        if "result" in message:
            await self.process_response(message)
            return
        if "error" in message:
            await self.process_error(message)

    async def process_request(self, request: Mapping[str, Any]) -> None:
        request_id = request.get("id")
        method = str(request.get("method", ""))
        params = request.get("params")
        if not isinstance(params, Mapping):
            params = {}

        if method == "initialize":
            await self._handle_initialize(request_id, params)
        elif method == "ping":
            await self.outgoing.send_response(request_id, {})
        elif method == "tools/list":
            await self.outgoing.send_response(
                request_id,
                {
                    "tools": [
                        create_tool_for_codex_tool_call_param(),
                        create_tool_for_codex_tool_call_reply_param(),
                    ]
                },
            )
        elif method == "tools/call":
            await self._handle_call_tool(request_id, params)
        elif method in {
            "tasks/get",
            "tasks/get_info",
            "tasks/list",
            "tasks/get_result",
            "tasks/cancel",
        }:
            await self._method_not_found(request_id, method)
        else:
            await self._method_not_found(request_id, method)

    async def process_response(self, response: Mapping[str, Any]) -> None:
        await self.outgoing.notify_client_response(response.get("id"), response.get("result"))

    async def process_error(self, error: Mapping[str, Any]) -> None:
        await self.outgoing.notify_client_error(error.get("id"), error.get("error"))

    async def process_notification(self, notification: Mapping[str, Any]) -> None:
        if notification.get("method") != "notifications/cancelled":
            return
        params = notification.get("params")
        if not isinstance(params, Mapping):
            return
        request_id = params.get("requestId")
        thread_id = self.running_requests.get(request_id)
        if thread_id is None:
            return
        try:
            thread = await _maybe_await(self.thread_manager.get_thread(thread_id))
            submission = Submission(id=str(request_id), op=Op.simple("interrupt"))
            await _maybe_await(thread.submit_with_id(submission))
        finally:
            self.running_requests.pop(request_id, None)

    async def wait_pending(self) -> None:
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        await self.wait_pending()
        shutdown = getattr(self.thread_manager, "shutdown_all", None)
        if callable(shutdown):
            await _maybe_await(shutdown())

    async def _handle_initialize(self, request_id: Any, params: Mapping[str, Any]) -> None:
        if self.initialized:
            await self.outgoing.send_error(request_id, -32600, "initialize called more than once")
            return
        protocol_version = params.get("protocolVersion")
        self.initialized = True
        await self.outgoing.send_response(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {
                    "name": "codex-mcp-server",
                    "title": "Codex",
                    "version": __version__,
                    "user_agent": f"pycodex/{__version__}",
                },
            },
        )

    async def _handle_call_tool(self, request_id: Any, params: Mapping[str, Any]) -> None:
        name = params.get("name")
        arguments = params.get("arguments")
        if name == "codex":
            await self._handle_codex(request_id, arguments)
            return
        if name == "codex-reply":
            await self._handle_reply(request_id, arguments)
            return
        await self.outgoing.send_response(
            request_id,
            {
                "content": [{"type": "text", "text": f"Unknown tool '{name}'"}],
                "isError": True,
            },
        )

    async def _handle_codex(self, request_id: Any, arguments: Any) -> None:
        if not isinstance(arguments, Mapping):
            await self.outgoing.send_response(
                request_id,
                {
                    "content": [{
                        "type": "text",
                        "text": "Missing arguments for codex tool-call; the `prompt` field is required.",
                    }],
                    "isError": True,
                },
            )
            return
        try:
            parsed = CodexToolCallParam.from_mapping(arguments)
            prompt, config = await self._build_config(parsed)
        except Exception as exc:
            await self.outgoing.send_response(
                request_id,
                {
                    "content": [{
                        "type": "text",
                        "text": f"Failed to parse configuration for Codex tool: {exc}",
                    }],
                    "isError": True,
                },
            )
            return
        self._spawn(
            run_codex_tool_session(
                request_id,
                prompt,
                config,
                self.outgoing,
                self.thread_manager,
                self.running_requests,
            )
        )

    async def _handle_reply(self, request_id: Any, arguments: Any) -> None:
        if not isinstance(arguments, Mapping):
            await self.outgoing.send_response(
                request_id,
                {
                    "content": [{
                        "type": "text",
                        "text": (
                            "Missing arguments for codex-reply tool-call; "
                            "the `thread_id` and `prompt` fields are required."
                        ),
                    }],
                    "isError": True,
                },
            )
            return
        try:
            parsed = CodexToolCallReplyParam.from_mapping(arguments)
            thread_id = parsed.get_thread_id()
            thread = await _maybe_await(self.thread_manager.get_thread(thread_id))
        except Exception as exc:
            await self.outgoing.send_response(
                request_id,
                create_call_tool_result_with_thread_id(
                    str(arguments.get("threadId") or arguments.get("conversationId") or ""),
                    f"Session not found for thread_id: {arguments.get('threadId') or arguments.get('conversationId')}: {exc}",
                    True,
                ),
            )
            return
        self._spawn(
            run_codex_tool_session_reply(
                thread_id,
                thread,
                self.outgoing,
                request_id,
                parsed.prompt,
                self.running_requests,
            )
        )

    async def _build_config(self, parsed: CodexToolCallParam) -> tuple[str, Any]:
        if self.config_factory is None:
            return await parsed.into_config()
        result = self.config_factory(parsed)
        result = await _maybe_await(result)
        if isinstance(result, tuple) and len(result) == 2:
            return str(result[0]), result[1]
        return parsed.prompt, result

    async def _method_not_found(self, request_id: Any, method: str) -> None:
        await self.outgoing.send_error(
            request_id,
            -32601,
            f"method not found: {method}",
            {"method": method},
        )

    def _spawn(self, awaitable: Any) -> None:
        task = asyncio.create_task(awaitable)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value
