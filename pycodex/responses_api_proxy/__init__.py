"""Helpers and runtime for the Rust ``codex-responses-api-proxy`` crate.

This package owns the crate-local behavior from ``read_api_key.rs``,
``dump.rs``, ``lib.rs``, and the ``main.rs`` entrypoint handoff.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, TextIO
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_UPSTREAM_URL = "https://api.openai.com/v1/responses"
ALLOWED_RESPONSES_PATH = "/v1/responses"
SHUTDOWN_PATH = "/shutdown"
REQUEST_HEADER_REPLACED_BY_PROXY = {"authorization", "host"}
RESPONSE_HEADERS_MANAGED_BY_SERVER = {
    "content-length",
    "transfer-encoding",
    "connection",
    "trailer",
    "upgrade",
}


class ResponsesApiProxyError(RuntimeError):
    """User-facing proxy helper error."""


from . import dump as _dump
from . import read_api_key as _read_api_key


@dataclass(frozen=True)
class ResponsesApiProxyArgs:
    port: int | None = None
    server_info: Path | None = None
    http_shutdown: bool = False
    upstream_url: str = DEFAULT_UPSTREAM_URL
    dump_dir: Path | None = None


@dataclass(frozen=True)
class ForwardConfig:
    upstream_url: str
    host_header: str


def build_forward_config(upstream_url: str = DEFAULT_UPSTREAM_URL) -> ForwardConfig:
    parsed = urlparse(upstream_url)
    if not parsed.scheme or not parsed.netloc:
        raise ResponsesApiProxyError(f"parsing --upstream-url: invalid url {upstream_url}")
    if parsed.hostname is None:
        raise ResponsesApiProxyError("upstream URL must include a host")
    host_header = parsed.hostname
    if parsed.port is not None:
        host_header = f"{host_header}:{parsed.port}"
    return ForwardConfig(upstream_url=upstream_url, host_header=host_header)


def is_allowed_proxy_request(method: str, url: str) -> bool:
    parsed = urlparse(url)
    return method == "POST" and parsed.path == ALLOWED_RESPONSES_PATH and not parsed.query


def is_allowed_shutdown_request(method: str, url: str, *, http_shutdown: bool) -> bool:
    parsed = urlparse(url)
    return bool(http_shutdown) and method == "GET" and parsed.path == SHUTDOWN_PATH and not parsed.query


def upstream_headers_from_request(
    headers: Iterable[tuple[str, str]],
    *,
    auth_header: str,
    host_header: str,
) -> dict[str, str]:
    forwarded = {
        name: value
        for name, value in headers
        if name.lower() not in REQUEST_HEADER_REPLACED_BY_PROXY
    }
    forwarded["Host"] = host_header
    forwarded["Authorization"] = auth_header
    return forwarded


def response_headers_for_downstream(headers: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    return [
        (name, value)
        for name, value in headers
        if name.lower() not in RESPONSE_HEADERS_MANAGED_BY_SERVER
    ]


def server_info_payload(port: int, *, pid: int | None = None) -> dict[str, int]:
    return {"port": int(port), "pid": os.getpid() if pid is None else int(pid)}


def write_server_info(path: Path, port: int, *, pid: int | None = None) -> None:
    path = Path(path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(server_info_payload(port, pid=pid), handle, separators=(",", ":"))
        handle.write("\n")


def run_main(
    args: ResponsesApiProxyArgs | Iterable[str] | None = None,
    *,
    stdin: object | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the proxy entrypoint through the existing CLI runtime.

    Rust ``src/main.rs`` parses ``Args`` and hands them to the crate library's
    ``run_main``. The Python port accepts either a ``ResponsesApiProxyArgs``
    value or raw CLI-style option tokens and then runs the package-owned
    blocking HTTP server.
    """

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    if isinstance(args, ResponsesApiProxyArgs):
        parsed_args = args
    else:
        raw_args = [] if args is None else [str(arg) for arg in args]
        if any(arg in {"-h", "--help"} for arg in raw_args):
            print(help_text(), file=out)
            return 0
        try:
            parsed_args = parse_main_args(raw_args)
        except ResponsesApiProxyError as exc:
            print(f"pycodex: {exc}", file=err)
            return 2

    try:
        auth_header = read_auth_header_for_main(stdin)
    except ResponsesApiProxyError as exc:
        message = str(exc)
        if "must be provided" in message:
            message = "No API key provided via stdin."
        print(f"pycodex: {message}", file=err)
        return 2

    return _serve_proxy(parsed_args, auth_header=auth_header, stdout=out, stderr=err)


def main(
    argv: Iterable[str] | None = None,
    *,
    stdin: object | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    return run_main(argv, stdin=stdin, stdout=stdout, stderr=stderr)


def help_text() -> str:
    return "Usage: codex responses-api-proxy [OPTIONS]"


def parse_main_args(argv: Iterable[str]) -> ResponsesApiProxyArgs:
    args = list(argv)
    port: int | None = None
    server_info: Path | None = None
    http_shutdown = False
    upstream_url = DEFAULT_UPSTREAM_URL
    dump_dir: Path | None = None

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--port":
            if index + 1 >= len(args):
                raise ResponsesApiProxyError("--port requires a value")
            try:
                port = int(args[index + 1])
            except ValueError as exc:
                raise ResponsesApiProxyError("--port expects an integer") from exc
            index += 2
            continue
        if arg == "--server-info":
            if index + 1 >= len(args):
                raise ResponsesApiProxyError("--server-info requires a value")
            server_info = Path(args[index + 1])
            index += 2
            continue
        if arg == "--http-shutdown":
            http_shutdown = True
            index += 1
            continue
        if arg == "--upstream-url":
            if index + 1 >= len(args):
                raise ResponsesApiProxyError("--upstream-url requires a value")
            upstream_url = args[index + 1]
            index += 2
            continue
        if arg == "--dump-dir":
            if index + 1 >= len(args):
                raise ResponsesApiProxyError("--dump-dir requires a value")
            dump_dir = Path(args[index + 1])
            index += 2
            continue
        raise ResponsesApiProxyError(f"Unknown argument for responses-api-proxy: {arg}")

    return ResponsesApiProxyArgs(
        port=port,
        server_info=server_info,
        http_shutdown=http_shutdown,
        upstream_url=upstream_url,
        dump_dir=dump_dir,
    )


def read_auth_header_for_main(stdin: object | None) -> str:
    if stdin is None:
        source = sys.stdin.buffer if hasattr(sys.stdin, "buffer") else sys.stdin
        raw = source.read()
    elif isinstance(stdin, (bytes, str)):
        raw = stdin
    elif hasattr(stdin, "buffer"):
        raw = stdin.buffer.read()
    elif hasattr(stdin, "read"):
        raw = stdin.read()
    else:
        raw = b""
    return _read_api_key.read_auth_header_from_text(raw)


def _serve_proxy(
    args: ResponsesApiProxyArgs,
    *,
    auth_header: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    del stdout
    exchange_dumper: _dump.ExchangeDumper | None = None
    if args.dump_dir is not None:
        try:
            exchange_dumper = _dump.ExchangeDumper(args.dump_dir)
        except OSError as exc:
            print(f"pycodex: creating --dump-dir: {exc}", file=stderr)
            return 2

    try:
        forward_config = build_forward_config(args.upstream_url)
    except ResponsesApiProxyError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    host, selected_port = ("127.0.0.1", args.port or 0)
    http_shutdown = args.http_shutdown

    class _ResponsesApiProxyHandler(BaseHTTPRequestHandler):
        server_version = "responses-api-proxy"

        def _write_server_error(self, status: int, message: str) -> None:
            self.send_response(status)
            if status != 403:
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            if status != 403:
                self.wfile.write(message.encode("utf-8"))

        def _forward(self) -> None:
            parsed = urlparse(self.path)
            if not is_allowed_proxy_request(self.command, self.path):
                self._write_server_error(403, "forbidden")
                return

            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length else b""
            request_headers = list(self.headers.items())
            upstream_headers = upstream_headers_from_request(
                request_headers,
                auth_header=auth_header,
                host_header=forward_config.host_header,
            )
            request = Request(
                forward_config.upstream_url,
                data=body,
                headers=upstream_headers,
                method="POST",
            )

            response_path: Path | None = None
            if exchange_dumper is not None:
                try:
                    exchange_dump = exchange_dumper.dump_request(
                        self.command,
                        parsed.path,
                        request_headers,
                        body,
                    )
                    response_path = exchange_dump.response_path
                except OSError as exc:
                    print(f"responses-api-proxy failed to dump request: {exc}", file=stderr)
                    response_path = None

            response: object | None = None
            try:
                try:
                    response = urlopen(request, timeout=30)
                except HTTPError as exc:
                    response = exc

                status = getattr(response, "status", None)
                if status is None:
                    status = getattr(response, "code", 500)
                if status is None:
                    status = 500

                self.send_response(status)
                response_headers = list(response.headers.items()) if response is not None else []
                forwarded_response_headers = [*response_headers_for_downstream(response_headers)]
                for name, value in forwarded_response_headers:
                    self.send_header(name, value)
                self.end_headers()

                if response_path is None:
                    while True:
                        chunk = response.read(8192)  # type: ignore[attr-defined]
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                    return

                response_dump = _dump.ResponseBodyDump(
                    status,
                    forwarded_response_headers,
                    response,
                    response_path,
                )
                while True:
                    chunk = response_dump.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except Exception as exc:
                print(f"responses-api-proxy forwarding error: {exc}", file=stderr)
                self._write_server_error(500, "internal error")
            finally:
                if response is not None and hasattr(response, "close"):
                    try:
                        response.close()
                    except Exception:
                        pass

        def do_POST(self) -> None:
            self._forward()

        def do_GET(self) -> None:
            if not is_allowed_shutdown_request(self.command, self.path, http_shutdown=http_shutdown):
                self._write_server_error(403, "forbidden")
                return

            self.send_response(200)
            self.end_headers()
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, fmt: str, *args_: object) -> None:
            del fmt
            del args_

    server = ThreadingHTTPServer((host, selected_port), _ResponsesApiProxyHandler)
    bound_addr = server.server_address

    if args.server_info is not None:
        try:
            write_server_info(args.server_info, bound_addr[1])
        except OSError as exc:
            print(f"failed to write server info file: {exc}", file=stderr)
            return 2

    print(f"responses-api-proxy listening on {bound_addr[0]}:{bound_addr[1]}", file=stderr)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()

    return 0



__all__ = [
    "ALLOWED_RESPONSES_PATH",
    "DEFAULT_UPSTREAM_URL",
    "ForwardConfig",
    "REQUEST_HEADER_REPLACED_BY_PROXY",
    "RESPONSE_HEADERS_MANAGED_BY_SERVER",
    "ResponsesApiProxyError",
    "ResponsesApiProxyArgs",
    "SHUTDOWN_PATH",
    "build_forward_config",
    "is_allowed_proxy_request",
    "is_allowed_shutdown_request",
    "main",
    "parse_main_args",
    "read_auth_header_for_main",
    "response_headers_for_downstream",
    "server_info_payload",
    "help_text",
    "run_main",
    "upstream_headers_from_request",
    "write_server_info",
]
