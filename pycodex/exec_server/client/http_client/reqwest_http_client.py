"""Python interface for Rust ``codex-exec-server``."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
import binascii
import errno
import hashlib
from functools import total_ordering
import inspect
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import struct
import sys
import time
import tomllib
from typing import Any
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request, method_not_found
from pycodex.app_server_protocol.jsonrpc_lite import (
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    PermissionProfile,
    RequestId,
    WindowsSandboxLevel,
)
from pycodex.sandboxing import (
    SandboxCommand,
    SandboxManager,
    SandboxTransformRequest,
    SandboxablePreference,
)
from pycodex.protocol.shell_environment import create_env as create_shell_env
from pycodex.utils.absolute_path import AbsolutePathBuf



from pycodex.file_system import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecutorFileSystem,
    FileMetadata,
    FileSystemSandboxContext,
    ReadDirectoryEntry,
    RemoveOptions,
)
from pycodex.file_system import FileSystemResult


@dataclass(frozen=True)
class PendingReqwestHttpBodyStream:
    request_id: str
    chunks: list[bytes]


class ReqwestHttpRequestRunner:
    def __init__(self, timeout_ms: int | None = None) -> None:
        self.timeout_ms = timeout_ms

    @classmethod
    def new(cls, timeout_ms: int | None = None) -> "ReqwestHttpRequestRunner":
        return cls(timeout_ms)

    async def run(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, PendingReqwestHttpBodyStream | None] | JSONRPCErrorError:
        return await asyncio.to_thread(self._run_sync, params)

    def _run_sync(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, PendingReqwestHttpBodyStream | None] | JSONRPCErrorError:
        method_error = _validate_http_method(params.method)
        if method_error is not None:
            return invalid_params(f"http/request method is invalid: {method_error}")
        parsed_url = urlsplit(params.url)
        if not parsed_url.scheme:
            return invalid_params("http/request url is invalid: relative URL without a base")
        if parsed_url.scheme not in ("http", "https"):
            return invalid_params(
                f"http/request only supports http and https URLs, got {parsed_url.scheme}"
            )
        if not parsed_url.netloc:
            return invalid_params("http/request url is invalid: relative URL without a base")

        headers_error = self.build_headers(params.headers)
        if isinstance(headers_error, JSONRPCErrorError):
            return headers_error

        body = None if params.body is None else params.body.into_inner()
        request = Request(
            params.url,
            data=body,
            method=params.method,
        )
        for header in params.headers:
            request.add_header(header.name, header.value)
        timeout = None if params.timeout_ms is None else params.timeout_ms / 1000

        try:
            response_obj = urlopen(request, timeout=timeout)
        except HTTPError as exc:
            response_obj = exc
        except Exception as exc:
            return internal_error(f"http/request failed: {exc}")

        try:
            status = int(getattr(response_obj, "status", getattr(response_obj, "code", 0)))
            headers = self.response_headers(response_obj.headers.items())
            chunks: list[bytes] = []
            while True:
                chunk = response_obj.read(64 * 1024)
                if not chunk:
                    break
                chunks.append(bytes(chunk))
        except Exception as exc:
            return internal_error(f"failed to read http/request response body: {exc}")
        finally:
            close = getattr(response_obj, "close", None)
            if close is not None:
                close()

        if params.stream_response:
            return (
                HttpRequestResponse(status=status, headers=headers, body=ByteChunk(b"")),
                PendingReqwestHttpBodyStream(params.request_id, chunks),
            )
        return (
            HttpRequestResponse(status=status, headers=headers, body=ByteChunk(b"".join(chunks))),
            None,
        )

    @staticmethod
    async def stream_body(
        pending_stream: PendingReqwestHttpBodyStream,
        notifications: Any,
    ) -> None:
        seq = 1
        for chunk in pending_stream.chunks:
            delta = HttpRequestBodyDeltaNotification(
                request_id=pending_stream.request_id,
                seq=seq,
                delta=ByteChunk(chunk),
                done=False,
                error=None,
            )
            if not await send_body_delta(notifications, delta):
                return
            seq += 1
        await send_body_delta(
            notifications,
            HttpRequestBodyDeltaNotification(
                request_id=pending_stream.request_id,
                seq=seq,
                delta=ByteChunk(b""),
                done=True,
                error=None,
            ),
        )

    @staticmethod
    def build_headers(headers: list[HttpHeader]) -> dict[str, str] | JSONRPCErrorError:
        result: dict[str, str] = {}
        for header in headers:
            name_error = _validate_http_header_name(header.name)
            if name_error is not None:
                return invalid_params(f"http/request header name is invalid: {name_error}")
            value_error = _validate_http_header_value(header.value)
            if value_error is not None:
                return invalid_params(
                    f"http/request header value is invalid for {header.name}: {value_error}"
                )
            result[header.name] = header.value
        return result

    @staticmethod
    def response_headers(headers: Any) -> list[HttpHeader]:
        result: list[HttpHeader] = []
        for name, value in headers:
            try:
                text = str(value)
            except Exception:
                continue
            result.append(HttpHeader(str(name), text))
        return result


class ReqwestHttpClient:
    async def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        runner = ReqwestHttpRequestRunner.new(params.timeout_ms)
        result = await runner.run(replace(params, stream_response=False))
        if isinstance(result, JSONRPCErrorError):
            raise ExecServerError.http_request(result.message)
        response, _ = result
        return response

    async def http_request_stream(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, HttpResponseBodyStream]:
        runner = ReqwestHttpRequestRunner.new(params.timeout_ms)
        result = await runner.run(replace(params, stream_response=True))
        if isinstance(result, JSONRPCErrorError):
            raise ExecServerError.http_request(result.message)
        response, pending_stream = result
        if pending_stream is None:
            raise ExecServerError.protocol("http request stream did not return a response body stream")
        return response, HttpResponseBodyStream.local(pending_stream.chunks)


_HTTP_TOKEN_SEPARATORS = set('()<>@,;:\\"/[]?={} \t')


def _validate_http_method(method: str) -> str | None:
    if not method:
        return "empty method"
    for ch in method:
        if ord(ch) < 33 or ord(ch) > 126 or ch in _HTTP_TOKEN_SEPARATORS:
            return f"invalid token character {ch!r}"
    return None


def _validate_http_header_name(name: str) -> str | None:
    if not name:
        return "empty header name"
    for ch in name:
        if ord(ch) < 33 or ord(ch) > 126 or ch in _HTTP_TOKEN_SEPARATORS:
            return f"invalid token character {ch!r}"
    return None


def _validate_http_header_value(value: str) -> str | None:
    if "\r" in value or "\n" in value:
        return "header value contains a newline"
    return None


from pycodex.exec_server.client import ExecServerError
from pycodex.exec_server.client.http_client.response_body_stream import HttpResponseBodyStream, send_body_delta
from pycodex.exec_server.protocol import ByteChunk, HttpHeader, HttpRequestBodyDeltaNotification, HttpRequestParams, HttpRequestResponse
