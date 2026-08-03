"""Local deterministic Responses API fixture for conversation E2E tests."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def _responses_sse(*events: dict[str, object]) -> bytes:
    chunks: list[str] = []
    for event in events:
        kind = str(event["type"])
        chunks.append(f"event: {kind}\n")
        if len(event) > 1:
            chunks.append(f"data: {json.dumps(event, separators=(',', ':'))}\n")
        chunks.append("\n")
    return "".join(chunks).encode("utf-8")


def _completed_text_response(response_id: str, message_id: str, text: str) -> bytes:
    return _responses_sse(
        {"type": "response.created", "response": {"id": response_id}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": message_id,
                "content": [{"type": "output_text", "text": text}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "usage": {
                    "input_tokens": 4,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 6,
                },
            },
        },
    )


class _SseFixtureServer:
    def __init__(
        self,
        body: bytes | tuple[bytes, ...],
        *,
        response_delay_seconds: float = 0.0,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        self._bodies = (body,) if isinstance(body, bytes) else tuple(body)
        if not self._bodies:
            raise ValueError("at least one SSE fixture body is required")
        self._response_delay_seconds = float(response_delay_seconds)
        self._response_headers = dict(response_headers or {})
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.requests: list[tuple[str, str]] = []
        self.request_bodies: list[bytes] = []
        self._lock = threading.Lock()
        self._body_index = 0

    def __enter__(self) -> "_SseFixtureServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
                length = int(self.headers.get("content-length") or "0")
                request_body = self.rfile.read(length) if length else b""
                with outer._lock:
                    outer.requests.append(("POST", self.path))
                    outer.request_bodies.append(request_body)
                    index = min(outer._body_index, len(outer._bodies) - 1)
                    body = outer._bodies[index]
                    outer._body_index += 1
                if not self.path.rstrip("/").endswith("/responses"):
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                for name, value in outer._response_headers.items():
                    self.send_header(str(name), str(value))
                self.end_headers()
                if outer._response_delay_seconds > 0:
                    time.sleep(outer._response_delay_seconds)
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("server not started")
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"
