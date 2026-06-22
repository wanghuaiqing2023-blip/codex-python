"""Helpers and runtime for the Rust ``codex-responses-api-proxy`` crate.

This package owns the crate-local behavior from ``read_api_key.rs``,
``dump.rs``, ``lib.rs``, and the ``main.rs`` entrypoint handoff.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Iterable, TextIO
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BUFFER_SIZE = 1024
AUTH_HEADER_PREFIX = b"Bearer "
REDACTED_HEADER_VALUE = "[REDACTED]"
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


def validate_auth_header_bytes(key_bytes: bytes) -> None:
    if all(byte in b"-_" or 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122 for byte in key_bytes):
        return
    raise ResponsesApiProxyError("API key may only contain ASCII letters, numbers, '-' or '_'")


def read_auth_header_with(read_fn: Callable[[bytearray], int]) -> str:
    buf = bytearray(BUFFER_SIZE)
    buf[: len(AUTH_HEADER_PREFIX)] = AUTH_HEADER_PREFIX
    prefix_len = len(AUTH_HEADER_PREFIX)
    capacity = len(buf) - prefix_len
    total_read = 0
    saw_newline = False
    saw_eof = False

    while total_read < capacity:
        scratch = bytearray(capacity - total_read)
        try:
            read = read_fn(scratch)
        except OSError:
            _zeroize(buf)
            raise

        if read < 0:
            _zeroize(buf)
            raise ResponsesApiProxyError("read function returned a negative byte count")
        if read > len(scratch):
            _zeroize(buf)
            raise ResponsesApiProxyError("read function returned more bytes than the supplied buffer")
        if read == 0:
            saw_eof = True
            break

        newly_written = bytes(scratch[:read])
        newline_pos = newly_written.find(b"\n")
        if newline_pos >= 0:
            copy_len = newline_pos + 1
            buf[prefix_len + total_read : prefix_len + total_read + copy_len] = newly_written[:copy_len]
            total_read += copy_len
            saw_newline = True
            break

        buf[prefix_len + total_read : prefix_len + total_read + read] = newly_written
        total_read += read

    if total_read == capacity and not saw_newline and not saw_eof:
        _zeroize(buf)
        raise ResponsesApiProxyError(f"API key is too large to fit in the {BUFFER_SIZE}-byte buffer")

    total = prefix_len + total_read
    while total > prefix_len and buf[total - 1] in (ord("\n"), ord("\r")):
        total -= 1

    if total == prefix_len:
        _zeroize(buf)
        raise ResponsesApiProxyError(
            "API key must be provided via stdin (e.g. printenv OPENAI_API_KEY | codex responses-api-proxy)"
        )

    key = bytes(buf[prefix_len:total])
    try:
        validate_auth_header_bytes(key)
        header = bytes(buf[:total]).decode("utf-8")
    except UnicodeDecodeError as exc:
        _zeroize(buf)
        raise ResponsesApiProxyError("reading Authorization header from stdin as UTF-8") from exc
    except ResponsesApiProxyError:
        _zeroize(buf)
        raise

    _zeroize(buf)
    return header


def read_auth_header_from_text(text: str | bytes | None) -> str:
    if text is None:
        data = b""
    elif isinstance(text, bytes):
        data = text
    else:
        data = text.encode("utf-8")
    sent = False

    def read_once(buffer: bytearray) -> int:
        nonlocal sent
        if sent:
            return 0
        sent = True
        count = min(len(buffer), len(data))
        buffer[:count] = data[:count]
        return count

    return read_auth_header_with(read_once)


def sanitize_dump_body(body: bytes) -> object:
    if not body:
        return ""
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")


def should_redact_header(name: str) -> bool:
    lower = name.lower()
    return lower == "authorization" or "cookie" in lower


def normalize_headers_for_dump(headers: Iterable[tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "value": REDACTED_HEADER_VALUE if should_redact_header(name) else value,
        }
        for name, value in headers
    ]


@dataclass
class ExchangeDumper:
    dump_dir: Path
    _sequence: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.dump_dir = Path(self.dump_dir)
        self.dump_dir.mkdir(parents=True, exist_ok=True)

    def _next_prefix(self) -> str:
        with self._lock:
            value = self._sequence
            self._sequence += 1
        timestamp_ms = int(time.time() * 1000)
        return f"{value:06d}-{timestamp_ms}"

    def dump_request(
        self,
        method: str,
        url: str,
        headers: Iterable[tuple[str, str]],
        body: bytes,
    ) -> "ExchangeDump":
        prefix = self._next_prefix()
        request_path = self.dump_dir / f"{prefix}-request.json"
        response_path = self.dump_dir / f"{prefix}-response.json"
        request_dump = {
            "method": method,
            "url": url,
            "headers": normalize_headers_for_dump(list(headers)),
            "body": sanitize_dump_body(body),
        }
        write_json_dump(request_path, request_dump)
        return ExchangeDump(response_path)


@dataclass(frozen=True)
class ExchangeDump:
    response_path: Path

    def tee_response_body(
        self,
        status: int,
        headers: Iterable[tuple[str, str]],
        response_body: object,
    ) -> "ResponseBodyDump":
        return ResponseBodyDump(status, list(headers), response_body, self.response_path)


class ResponseBodyDump:
    def __init__(
        self,
        status: int,
        headers: list[tuple[str, str]],
        response_body: object,
        response_path: Path,
    ) -> None:
        self.status = int(status)
        self.headers = headers
        self.response_body = response_body
        self.response_path = Path(response_path)
        self.body = bytearray()
        self.dump_written = False

    def read(self, size: int = -1) -> bytes:
        chunk = self.response_body.read(size)  # type: ignore[attr-defined]
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        if not chunk:
            self.write_dump_if_needed()
            return b""
        chunk = bytes(chunk)
        self.body.extend(chunk)
        return chunk

    def write_dump_if_needed(self) -> None:
        if self.dump_written:
            return
        self.dump_written = True
        response_dump = {
            "status": self.status,
            "headers": normalize_headers_for_dump(self.headers),
            "body": sanitize_dump_body(bytes(self.body)),
        }
        write_json_dump(self.response_path, response_dump)

    def __del__(self) -> None:
        try:
            self.write_dump_if_needed()
        except Exception:
            pass


def write_json_dump(path: Path, dump: object) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(dump, handle, indent=2, ensure_ascii=False)
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
    return read_auth_header_from_text(raw)


def _serve_proxy(
    args: ResponsesApiProxyArgs,
    *,
    auth_header: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    del stdout
    exchange_dumper: ExchangeDumper | None = None
    if args.dump_dir is not None:
        try:
            exchange_dumper = ExchangeDumper(args.dump_dir)
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

                response_dump = ResponseBodyDump(
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



def _zeroize(buf: bytearray) -> None:
    for index in range(len(buf)):
        buf[index] = 0


__all__ = [
    "AUTH_HEADER_PREFIX",
    "ALLOWED_RESPONSES_PATH",
    "BUFFER_SIZE",
    "DEFAULT_UPSTREAM_URL",
    "ExchangeDump",
    "ExchangeDumper",
    "ForwardConfig",
    "REDACTED_HEADER_VALUE",
    "REQUEST_HEADER_REPLACED_BY_PROXY",
    "RESPONSE_HEADERS_MANAGED_BY_SERVER",
    "ResponsesApiProxyError",
    "ResponsesApiProxyArgs",
    "ResponseBodyDump",
    "SHUTDOWN_PATH",
    "build_forward_config",
    "is_allowed_proxy_request",
    "is_allowed_shutdown_request",
    "main",
    "normalize_headers_for_dump",
    "parse_main_args",
    "read_auth_header_from_text",
    "read_auth_header_for_main",
    "read_auth_header_with",
    "response_headers_for_downstream",
    "sanitize_dump_body",
    "server_info_payload",
    "should_redact_header",
    "help_text",
    "run_main",
    "upstream_headers_from_request",
    "validate_auth_header_bytes",
    "write_json_dump",
    "write_server_info",
]
