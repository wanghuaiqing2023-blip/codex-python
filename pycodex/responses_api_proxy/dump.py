"""Request/response dump handling owned by ``dump.rs``."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REDACTED_HEADER_VALUE = "[REDACTED]"


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


def normalize_headers_for_dump(
    headers: Iterable[tuple[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "value": REDACTED_HEADER_VALUE
            if should_redact_header(name)
            else value,
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
        return ResponseBodyDump(
            status,
            list(headers),
            response_body,
            self.response_path,
        )


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


__all__ = [
    "ExchangeDump",
    "ExchangeDumper",
    "REDACTED_HEADER_VALUE",
    "ResponseBodyDump",
    "normalize_headers_for_dump",
    "sanitize_dump_body",
    "should_redact_header",
    "write_json_dump",
]
