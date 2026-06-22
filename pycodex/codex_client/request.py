"""Request data contracts for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/request.rs``
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


CONTENT_ENCODING = "content-encoding"
CONTENT_TYPE = "content-type"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
ZSTD_MAX_BLOCK_SIZE = 128 * 1024


class RequestCompression(str, Enum):
    NONE = "none"
    ZSTD = "zstd"


@dataclass(frozen=True)
class RequestBody:
    kind: str
    value: Any

    @classmethod
    def json(cls, value: Any) -> "RequestBody":
        return cls("json", value)

    @classmethod
    def raw(cls, value: bytes | bytearray | memoryview | str) -> "RequestBody":
        if isinstance(value, str):
            data = value.encode()
        else:
            data = bytes(value)
        return cls("raw", data)

    def json_value(self) -> Any | None:
        if self.kind == "json":
            return self.value
        return None


@dataclass(frozen=True)
class PreparedRequestBody:
    headers: dict[str, str]
    body: bytes | None

    def body_bytes(self) -> bytes:
        return self.body or b""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    headers: Mapping[str, str] | None = None
    body: RequestBody | None = None
    compression: RequestCompression = RequestCompression.NONE
    timeout: float | None = None

    @classmethod
    def new(cls, method: str, url: str) -> "Request":
        return cls(method=method, url=url)

    def with_json(self, body: Any) -> "Request":
        return Request(
            method=self.method,
            url=self.url,
            headers=self.headers,
            body=RequestBody.json(body),
            compression=self.compression,
            timeout=self.timeout,
        )

    def with_raw_body(self, body: bytes | bytearray | memoryview | str) -> "Request":
        return Request(
            method=self.method,
            url=self.url,
            headers=self.headers,
            body=RequestBody.raw(body),
            compression=self.compression,
            timeout=self.timeout,
        )

    def with_compression(self, compression: RequestCompression) -> "Request":
        return Request(
            method=self.method,
            url=self.url,
            headers=self.headers,
            body=self.body,
            compression=compression,
            timeout=self.timeout,
        )

    def with_headers(self, headers: Mapping[str, str]) -> "Request":
        return Request(
            method=self.method,
            url=self.url,
            headers=dict(headers),
            body=self.body,
            compression=self.compression,
            timeout=self.timeout,
        )

    def prepare_body_for_send(self) -> PreparedRequestBody:
        headers = _clone_headers(self.headers)
        if self.body is None:
            return PreparedRequestBody(headers=headers, body=None)

        if self.body.kind == "raw":
            if self.compression != RequestCompression.NONE:
                raise ValueError("request compression cannot be used with raw bodies")
            return PreparedRequestBody(headers=headers, body=bytes(self.body.value))

        json_bytes = json.dumps(
            self.body.value,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        if self.compression != RequestCompression.NONE:
            if _contains_header(headers, CONTENT_ENCODING):
                raise ValueError(
                    "request compression was requested but content-encoding is already set"
                )
            json_bytes = _compress_json_body(json_bytes, self.compression)
            headers[CONTENT_ENCODING] = self.compression.value

        if not _contains_header(headers, CONTENT_TYPE):
            headers[CONTENT_TYPE] = "application/json"

        return PreparedRequestBody(headers=headers, body=json_bytes)


def _clone_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    return dict(headers or {})


def _contains_header(headers: Mapping[str, str], name: str) -> bool:
    name_lower = name.lower()
    return any(key.lower() == name_lower for key in headers)


def _compress_json_body(body: bytes, compression: RequestCompression) -> bytes:
    if compression == RequestCompression.ZSTD:
        return _zstd_raw_frame(body)
    raise ValueError(f"unsupported request compression: {compression.value}")


def _zstd_raw_frame(body: bytes) -> bytes:
    """Return a valid dependency-light Zstandard frame containing raw blocks.

    Rust uses ``zstd::stream::encode_all(..., 3)``. The Python port avoids a
    third-party compressor, so it emits a standards-compliant Zstandard frame
    whose blocks are stored uncompressed. HTTP peers still receive a real
    ``Content-Encoding: zstd`` body; exact zstd level-3 byte identity remains a
    native-library boundary.
    """

    size = len(body)
    descriptor, content_size = _zstd_single_segment_header(size)
    chunks = [ZSTD_MAGIC, descriptor, content_size]
    if size == 0:
        chunks.append((1).to_bytes(3, "little"))
        return b"".join(chunks)

    offset = 0
    while offset < size:
        block = body[offset : offset + ZSTD_MAX_BLOCK_SIZE]
        offset += len(block)
        is_last = 1 if offset >= size else 0
        block_header = (len(block) << 3) | is_last
        chunks.append(block_header.to_bytes(3, "little"))
        chunks.append(block)
    return b"".join(chunks)


def _zstd_single_segment_header(size: int) -> tuple[bytes, bytes]:
    single_segment = 0x20
    if size < 256:
        return bytes([single_segment]), bytes([size])
    if size < 256 + 65536:
        return bytes([single_segment | 0x01]), (size - 256).to_bytes(2, "little")
    if size < 2**32:
        return bytes([single_segment | 0x02]), size.to_bytes(4, "little")
    return bytes([single_segment | 0x03]), size.to_bytes(8, "little")
