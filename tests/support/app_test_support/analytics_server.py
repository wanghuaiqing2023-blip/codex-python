from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


class AnalyticsEventsServer:
    def __init__(self) -> None:
        self.requests: list[bytes] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def uri(self) -> str:
        if self._server is None:
            raise RuntimeError("analytics server is not running")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> "AnalyticsEventsServer":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("content-length") or "0")
                body = self.rfile.read(length) if length else b""
                if self.path != "/codex/analytics-events/events":
                    self.send_response(404)
                else:
                    owner.requests.append(body)
                    self.send_response(200)
                self.end_headers()

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


async def start_analytics_events_server() -> AnalyticsEventsServer:
    return AnalyticsEventsServer().start()
