"""Programmable SSE server derived from ``streaming_sse.rs``."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterable


@dataclass(frozen=True)
class StreamingSseChunk:
    data: bytes
    delay: float = 0.0

    @classmethod
    def text(cls, data: str, *, delay: float = 0.0) -> "StreamingSseChunk":
        return cls(data.encode("utf-8"), delay)


class StreamingSseServer:
    def __init__(
        self,
        server: ThreadingHTTPServer,
        thread: threading.Thread,
        requests: list[bytes],
        lock: threading.Lock,
    ) -> None:
        self._server = server
        self._thread = thread
        self._requests = requests
        self._lock = lock

    def uri(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    async def requests(self) -> list[bytes]:
        with self._lock:
            return list(self._requests)

    async def wait_for_request_count(self, count: int, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while len(await self.requests()) < count:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for {count} SSE requests")
            await asyncio.sleep(0.02)

    async def shutdown(self) -> None:
        await asyncio.to_thread(self._server.shutdown)
        await asyncio.to_thread(self._server.server_close)
        await asyncio.to_thread(self._thread.join, 5.0)


async def start_streaming_sse_server(
    chunks: Iterable[StreamingSseChunk],
    *,
    status: int = 200,
) -> StreamingSseServer:
    sequence = tuple(chunks)
    requests: list[bytes] = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length)
            with lock:
                requests.append(body)
            self.send_response(status)
            self.send_header("content-type", "text/event-stream")
            self.send_header("connection", "close")
            self.end_headers()
            for chunk in sequence:
                if chunk.delay:
                    time.sleep(chunk.delay)
                self.wfile.write(chunk.data)
                self.wfile.flush()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, name="core-test-streaming-sse", daemon=True)
    thread.start()
    return StreamingSseServer(server, thread, requests, lock)


__all__ = ["StreamingSseChunk", "StreamingSseServer", "start_streaming_sse_server"]
