from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Callable, TextIO

from pycodex.app_server_protocol import JSONRPCMessage


async def start_stdio_connection(
    incoming_message_handler: Callable[[Any], Any],
    outgoing_queue: asyncio.Queue[Any],
    connection_closed_handler: Callable[[], Any],
    *,
    stdin: TextIO,
    stdout: TextIO,
    connection_id: int = 0,
) -> None:
    """Run the Rust newline-delimited JSON stdio reader and writer tasks."""

    writer = asyncio.create_task(
        _write_stdio_messages(outgoing_queue, stdout, connection_id),
        name="app-server-stdio-writer",
    )
    try:
        while True:
            line = await asyncio.to_thread(stdin.readline)
            if line in ("", b""):
                break
            if not line.strip():
                continue
            message = JSONRPCMessage.from_mapping(json.loads(line)).value
            await _maybe_await(incoming_message_handler(message))
        await outgoing_queue.join()
    finally:
        await _maybe_await(connection_closed_handler())
        writer.cancel()
        try:
            await writer
        except asyncio.CancelledError:
            pass


async def _write_stdio_messages(
    queue: asyncio.Queue[Any],
    stdout: TextIO,
    connection_id: int,
) -> None:
    while True:
        envelope = await queue.get()
        try:
            if envelope.kind == "ToConnection" and envelope.connection_id != connection_id:
                continue
            payload = envelope.message.payload
            mapping = payload.to_mapping() if hasattr(payload, "to_mapping") else payload
            await asyncio.to_thread(_write_json_line, stdout, mapping)
            if envelope.write_complete is not None and not envelope.write_complete.done():
                envelope.write_complete.set_result(None)
        finally:
            queue.task_done()


def _write_json_line(stdout: TextIO, value: Any) -> None:
    stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


__all__ = ["start_stdio_connection"]
