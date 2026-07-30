"""JSON-RPC output channel owned by ``outgoing_message.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class OutgoingNotificationMeta:
    request_id: Any | None = None
    thread_id: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.request_id is not None:
            result["requestId"] = self.request_id
        if self.thread_id is not None:
            result["threadId"] = self.thread_id
        return result


class OutgoingMessageSender:
    def __init__(self, queue: asyncio.Queue[dict[str, Any]] | None = None) -> None:
        self._queue = queue or asyncio.Queue()
        self._next_request_id = 0
        self._callbacks: dict[Any, asyncio.Future[Any]] = {}

    async def send_request(self, method: str, params: Any | None = None) -> asyncio.Future[Any]:
        request_id = self._next_request_id
        self._next_request_id += 1
        callback = asyncio.get_running_loop().create_future()
        self._callbacks[request_id] = callback
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        await self._queue.put(message)
        return callback

    async def notify_client_response(self, request_id: Any, result: Any) -> None:
        callback = self._callbacks.pop(request_id, None)
        if callback is not None and not callback.done():
            callback.set_result(result)

    async def notify_client_error(self, request_id: Any, error: Any) -> None:
        callback = self._callbacks.pop(request_id, None)
        if callback is not None and not callback.done():
            callback.set_exception(RuntimeError(str(error)))

    async def send_response(self, request_id: Any, response: Any) -> None:
        await self._queue.put({"jsonrpc": "2.0", "id": request_id, "result": _mapping_value(response)})

    async def send_error(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: Any | None = None,
    ) -> None:
        error: dict[str, Any] = {"code": int(code), "message": str(message)}
        if data is not None:
            error["data"] = data
        await self._queue.put({"jsonrpc": "2.0", "id": request_id, "error": error})

    async def send_notification(self, method: str, params: Any | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        await self._queue.put(message)

    async def send_event_as_notification(
        self,
        event: Any,
        meta: OutgoingNotificationMeta | None = None,
    ) -> None:
        params = _mapping_value(event)
        if not isinstance(params, Mapping):
            params = {"event": params}
        else:
            params = dict(params)
        if meta is not None:
            params["_meta"] = meta.to_mapping()
        await self.send_notification("codex/event", params)

    async def receive(self) -> dict[str, Any]:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()


def _mapping_value(value: Any) -> Any:
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return to_mapping()
    if isinstance(value, Mapping):
        return dict(value)
    return value
