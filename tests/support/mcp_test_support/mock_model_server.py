"""Ordered Responses API fixture derived from ``mock_model_server.rs``."""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _MockResponsesServer:
    def __init__(
        self,
        server: ThreadingHTTPServer,
        thread: threading.Thread,
        requests: list[bytes],
        lock: threading.Lock,
        expected_calls: int,
    ) -> None:
        self._server = server
        self._thread = thread
        self._requests = requests
        self._lock = lock
        self._expected_calls = expected_calls
        host, port = server.server_address[:2]
        self.base_url = f"http://{host}:{port}/v1"

    async def requests(self) -> list[bytes]:
        with self._lock:
            return list(self._requests)

    async def shutdown(self) -> None:
        await asyncio.to_thread(self._server.shutdown)
        await asyncio.to_thread(self._server.server_close)
        await asyncio.to_thread(self._thread.join, 5.0)
        actual = len(await self.requests())
        if actual != self._expected_calls:
            raise AssertionError(
                f"expected {self._expected_calls} Responses calls, received {actual}"
            )


async def create_mock_responses_server(responses: list[str]) -> _MockResponsesServer:
    bodies = tuple(responses)
    requests: list[bytes] = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/responses":
                self.send_error(404)
                return
            length = int(self.headers.get("content-length", "0"))
            request_body = self.rfile.read(length)
            with lock:
                call_number = len(requests)
                requests.append(request_body)
            if call_number >= len(bodies):
                self.send_error(500, f"no response for {call_number}")
                return
            body = bodies[call_number].encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, name="mcp-test-model", daemon=True)
    thread.start()
    return _MockResponsesServer(server, thread, requests, lock, len(bodies))


__all__ = ["create_mock_responses_server"]
