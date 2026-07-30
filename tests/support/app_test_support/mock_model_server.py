from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from .responses import create_final_assistant_message_sse_response


class MockResponsesServer:
    def __init__(self, responses: list[str], *, enforce_count: bool) -> None:
        if not responses:
            raise ValueError("at least one response is required")
        self._responses = responses
        self._enforce_count = enforce_count
        self._calls = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def uri(self) -> str:
        if self._server is None:
            raise RuntimeError("mock responses server is not running")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    @property
    def calls(self) -> int:
        return self._calls

    def start(self) -> "MockResponsesServer":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                if not self.path.rstrip("/").endswith("/responses"):
                    self.send_response(404)
                    self.end_headers()
                    return
                index = owner._calls
                owner._calls += 1
                if index >= len(owner._responses):
                    self.send_response(500)
                    self.end_headers()
                    return
                body = owner._responses[index].encode()
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._enforce_count and self._calls != len(self._responses):
            raise AssertionError(
                f"expected {len(self._responses)} response calls, got {self._calls}"
            )


async def create_mock_responses_server_sequence(
    responses: list[str],
) -> MockResponsesServer:
    return MockResponsesServer(responses, enforce_count=True).start()


async def create_mock_responses_server_sequence_unchecked(
    responses: list[str],
) -> MockResponsesServer:
    return MockResponsesServer(responses, enforce_count=False).start()


async def create_mock_responses_server_repeating_assistant(
    message: str,
) -> MockResponsesServer:
    body = create_final_assistant_message_sse_response(message)
    return MockResponsesServer([body] * 100, enforce_count=False).start()
