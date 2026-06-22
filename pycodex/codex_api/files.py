"""OpenAI file upload helpers from Rust ``codex-api/src/files.rs``."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from .auth import AuthProvider


OPENAI_FILE_URI_PREFIX = "sediment://"
OPENAI_FILE_UPLOAD_LIMIT_BYTES = 512 * 1024 * 1024
OPENAI_FILE_REQUEST_TIMEOUT = 60.0
OPENAI_FILE_FINALIZE_TIMEOUT = 30.0
OPENAI_FILE_FINALIZE_RETRY_DELAY = 0.25
OPENAI_FILE_USE_CASE = "codex"


@dataclass(frozen=True)
class UploadedOpenAiFile:
    file_id: str
    uri: str
    download_url: str
    file_name: str
    file_size_bytes: int
    mime_type: str | None
    path: Path


@dataclass(frozen=True)
class OpenAiFileError(Exception):
    kind: str
    path: Path | None = None
    source: BaseException | None = None
    size_bytes: int | None = None
    limit_bytes: int | None = None
    url: str | None = None
    status: int | None = None
    body: str | None = None
    file_id: str | None = None
    message: str | None = None

    @classmethod
    def missing_path(cls, path: Path) -> "OpenAiFileError":
        return cls("missing_path", path=path)

    @classmethod
    def not_a_file(cls, path: Path) -> "OpenAiFileError":
        return cls("not_a_file", path=path)

    @classmethod
    def read_file(cls, path: Path, source: BaseException) -> "OpenAiFileError":
        return cls("read_file", path=path, source=source)

    @classmethod
    def file_too_large(cls, path: Path, size_bytes: int, limit_bytes: int) -> "OpenAiFileError":
        return cls("file_too_large", path=path, size_bytes=size_bytes, limit_bytes=limit_bytes)

    @classmethod
    def request(cls, url: str, source: BaseException) -> "OpenAiFileError":
        return cls("request", url=url, source=source)

    @classmethod
    def unexpected_status(cls, url: str, status: int, body: str) -> "OpenAiFileError":
        return cls("unexpected_status", url=url, status=status, body=body)

    @classmethod
    def decode(cls, url: str, source: BaseException) -> "OpenAiFileError":
        return cls("decode", url=url, source=source)

    @classmethod
    def upload_not_ready(cls, file_id: str) -> "OpenAiFileError":
        return cls("upload_not_ready", file_id=file_id)

    @classmethod
    def upload_failed(cls, file_id: str, message: str) -> "OpenAiFileError":
        return cls("upload_failed", file_id=file_id, message=message)

    def __str__(self) -> str:
        if self.kind == "missing_path":
            return f"path `{self.path}` does not exist"
        if self.kind == "not_a_file":
            return f"path `{self.path}` is not a file"
        if self.kind == "read_file":
            return f"path `{self.path}` cannot be read: {self.source}"
        if self.kind == "file_too_large":
            return (
                f"file `{self.path}` is too large: {self.size_bytes} bytes exceeds "
                f"the limit of {self.limit_bytes} bytes"
            )
        if self.kind == "request":
            return f"failed to send OpenAI file request to {self.url}: {self.source}"
        if self.kind == "unexpected_status":
            return f"OpenAI file request to {self.url} failed with status {self.status}: {self.body}"
        if self.kind == "decode":
            return f"failed to parse OpenAI file response from {self.url}: {self.source}"
        if self.kind == "upload_not_ready":
            return f"OpenAI file upload for `{self.file_id}` is not ready yet"
        if self.kind == "upload_failed":
            return f"OpenAI file upload for `{self.file_id}` failed: {self.message}"
        return self.kind


@dataclass(frozen=True)
class OpenAiFileResponse:
    status: int
    body: str = ""

    def is_success(self) -> bool:
        return 200 <= self.status <= 299


@runtime_checkable
class OpenAiFileTransport(Protocol):
    def create_file(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
        timeout: float,
    ) -> OpenAiFileResponse:
        ...

    def upload_file(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> OpenAiFileResponse:
        ...

    def finalize_file(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
        timeout: float,
    ) -> OpenAiFileResponse:
        ...


def openai_file_uri(file_id: str) -> str:
    return f"{OPENAI_FILE_URI_PREFIX}{file_id}"


async def upload_local_file(
    base_url: str,
    auth: AuthProvider,
    path: str | Path,
    *,
    transport: OpenAiFileTransport,
    monotonic: Any = time.monotonic,
    sleep: Any = asyncio.sleep,
    upload_limit_bytes: int = OPENAI_FILE_UPLOAD_LIMIT_BYTES,
    finalize_timeout: float = OPENAI_FILE_FINALIZE_TIMEOUT,
) -> UploadedOpenAiFile:
    file_path = Path(path)
    try:
        stat = file_path.stat()
    except FileNotFoundError as exc:
        raise OpenAiFileError.missing_path(file_path) from exc
    except OSError as exc:
        raise OpenAiFileError.read_file(file_path, exc) from exc

    if not file_path.is_file():
        raise OpenAiFileError.not_a_file(file_path)
    if stat.st_size > upload_limit_bytes:
        raise OpenAiFileError.file_too_large(file_path, stat.st_size, upload_limit_bytes)

    file_name = file_path.name or "file"
    trimmed_base = base_url.rstrip("/")
    create_url = f"{trimmed_base}/files"
    headers = auth.to_auth_headers()
    create_body = {
        "file_name": file_name,
        "file_size": stat.st_size,
        "use_case": OPENAI_FILE_USE_CASE,
    }
    create_response = await _send_or_request_error(
        create_url,
        transport.create_file(create_url, headers, create_body, OPENAI_FILE_REQUEST_TIMEOUT),
    )
    _raise_for_status(create_url, create_response)
    create_payload = _decode_json(create_url, create_response.body)
    file_id = _required_str(create_payload, "file_id", create_url)
    upload_url = _required_str(create_payload, "upload_url", create_url)

    try:
        upload_body = file_path.read_bytes()
    except OSError as exc:
        raise OpenAiFileError.read_file(file_path, exc) from exc
    upload_response = await _send_or_request_error(
        upload_url,
        transport.upload_file(
            upload_url,
            {"x-ms-blob-type": "BlockBlob", "content-length": str(stat.st_size)},
            upload_body,
            OPENAI_FILE_REQUEST_TIMEOUT,
        ),
    )
    _raise_for_status(upload_url, upload_response)

    finalize_url = f"{trimmed_base}/files/{file_id}/uploaded"
    started_at = monotonic()
    while True:
        finalize_response = await _send_or_request_error(
            finalize_url,
            transport.finalize_file(finalize_url, headers, {}, OPENAI_FILE_REQUEST_TIMEOUT),
        )
        _raise_for_status(finalize_url, finalize_response)
        finalize_payload = _decode_json(finalize_url, finalize_response.body)
        status = _required_str(finalize_payload, "status", finalize_url)
        if status == "success":
            download_url = _optional_str_field(finalize_payload, "download_url", finalize_url)
            if download_url is None:
                raise OpenAiFileError.upload_failed(file_id, "missing download_url")
            response_file_name = _optional_str_field(finalize_payload, "file_name", finalize_url)
            mime_type = _optional_str_field(finalize_payload, "mime_type", finalize_url)
            return UploadedOpenAiFile(
                file_id=file_id,
                uri=openai_file_uri(file_id),
                download_url=download_url,
                file_name=response_file_name if isinstance(response_file_name, str) else file_name,
                file_size_bytes=stat.st_size,
                mime_type=mime_type if isinstance(mime_type, str) else None,
                path=file_path,
            )
        if status == "retry":
            if monotonic() - started_at >= finalize_timeout:
                raise OpenAiFileError.upload_not_ready(file_id)
            await _maybe_await(sleep(OPENAI_FILE_FINALIZE_RETRY_DELAY))
            continue
        error_message = _optional_str_field(finalize_payload, "error_message", finalize_url)
        raise OpenAiFileError.upload_failed(
            file_id,
            error_message if isinstance(error_message, str) else "upload finalization returned an error",
        )


async def _send_or_request_error(url: str, value: Any) -> OpenAiFileResponse:
    try:
        response = await _maybe_await(value)
    except OpenAiFileError:
        raise
    except BaseException as exc:
        raise OpenAiFileError.request(url, exc) from exc
    if not isinstance(response, OpenAiFileResponse):
        raise OpenAiFileError.request(url, TypeError("transport must return OpenAiFileResponse"))
    return response


def _raise_for_status(url: str, response: OpenAiFileResponse) -> None:
    if not response.is_success():
        raise OpenAiFileError.unexpected_status(url, response.status, response.body)


def _decode_json(url: str, body: str) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OpenAiFileError.decode(url, exc) from exc
    if not isinstance(value, dict):
        raise OpenAiFileError.decode(url, TypeError("response JSON must be an object"))
    return value


def _required_str(value: Mapping[str, Any], key: str, url: str) -> str:
    result = value.get(key)
    if not isinstance(result, str):
        raise OpenAiFileError.decode(url, TypeError(f"missing string field {key}"))
    return result


def _optional_str_field(value: Mapping[str, Any], key: str, url: str) -> str | None:
    result = value.get(key)
    if result is None:
        return None
    if not isinstance(result, str):
        raise OpenAiFileError.decode(url, TypeError(f"field {key} must be a string"))
    return result


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "OPENAI_FILE_FINALIZE_RETRY_DELAY",
    "OPENAI_FILE_FINALIZE_TIMEOUT",
    "OPENAI_FILE_REQUEST_TIMEOUT",
    "OPENAI_FILE_UPLOAD_LIMIT_BYTES",
    "OPENAI_FILE_URI_PREFIX",
    "OPENAI_FILE_USE_CASE",
    "OpenAiFileError",
    "OpenAiFileResponse",
    "OpenAiFileTransport",
    "UploadedOpenAiFile",
    "openai_file_uri",
    "upload_local_file",
]
