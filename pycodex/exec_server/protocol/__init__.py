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


INITIALIZE_METHOD = "initialize"


INITIALIZED_METHOD = "initialized"


EXEC_METHOD = "process/start"


EXEC_READ_METHOD = "process/read"


EXEC_WRITE_METHOD = "process/write"


EXEC_TERMINATE_METHOD = "process/terminate"


EXEC_OUTPUT_DELTA_METHOD = "process/output"


EXEC_EXITED_METHOD = "process/exited"


EXEC_CLOSED_METHOD = "process/closed"


FS_READ_FILE_METHOD = "fs/readFile"


FS_WRITE_FILE_METHOD = "fs/writeFile"


FS_CREATE_DIRECTORY_METHOD = "fs/createDirectory"


FS_GET_METADATA_METHOD = "fs/getMetadata"


FS_READ_DIRECTORY_METHOD = "fs/readDirectory"


FS_REMOVE_METHOD = "fs/remove"


FS_COPY_METHOD = "fs/copy"


HTTP_REQUEST_METHOD = "http/request"


HTTP_REQUEST_BODY_DELTA_METHOD = "http/request/bodyDelta"


@dataclass(frozen=True)
class ByteChunk:
    data: bytes

    def into_inner(self) -> bytes:
        return self.data

    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @classmethod
    def from_base64(cls, value: str) -> "ByteChunk":
        return cls(base64.b64decode(value, validate=True))


@dataclass(frozen=True)
class InitializeParams:
    client_name: str
    resume_session_id: str | None = None


@dataclass(frozen=True)
class InitializeResponse:
    session_id: str


def decode_initialize_params(value: Any) -> InitializeParams:
    if not isinstance(value, Mapping):
        raise ValueError("InitializeParams must be a mapping")
    client_name = value.get("clientName")
    if not isinstance(client_name, str):
        raise ValueError("clientName must be a string")
    resume_session_id = value.get("resumeSessionId")
    if resume_session_id is not None and not isinstance(resume_session_id, str):
        raise ValueError("resumeSessionId must be a string or null")
    return InitializeParams(client_name=client_name, resume_session_id=resume_session_id)


def encode_initialize_response(value: InitializeResponse) -> dict[str, Any]:
    return {"sessionId": value.session_id}


@dataclass(frozen=True)
class ExecEnvPolicy:
    inherit: Any
    ignore_default_excludes: bool
    exclude: list[str] = field(default_factory=list)
    set: dict[str, str] = field(default_factory=dict)
    include_only: list[str] = field(default_factory=list)


def shell_environment_policy(env_policy: ExecEnvPolicy) -> ShellEnvironmentPolicy:
    return ShellEnvironmentPolicy(
        inherit=ShellEnvironmentPolicyInherit(env_policy.inherit),
        ignore_default_excludes=env_policy.ignore_default_excludes,
        exclude=tuple(env_policy.exclude),
        set_values=dict(env_policy.set),
        include_only=tuple(env_policy.include_only),
        use_profile=False,
    )


def child_env(params: ExecParams) -> dict[str, str]:
    if params.env_policy is None:
        return dict(params.env)
    env = create_shell_env(shell_environment_policy(params.env_policy), None)
    env.update(params.env)
    return env


@dataclass(frozen=True)
class ExecParams:
    process_id: ProcessId
    argv: list[str]
    cwd: str
    env: dict[str, str]
    tty: bool
    env_policy: ExecEnvPolicy | None = None
    pipe_stdin: bool = False
    arg0: str | None = None


def decode_exec_params(value: Any) -> ExecParams:
    if not isinstance(value, Mapping):
        raise ValueError("ExecParams must be a mapping")
    process_id = _decode_process_id(value.get("processId"))
    argv = value.get("argv")
    if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
        raise ValueError("argv must be a list of strings")
    cwd = value.get("cwd")
    if not isinstance(cwd, str):
        raise ValueError("cwd must be a string")
    env_value = value.get("env")
    if not isinstance(env_value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in env_value.items()
    ):
        raise ValueError("env must be an object with string values")
    tty = value.get("tty")
    if not isinstance(tty, bool):
        raise ValueError("tty must be a bool")
    pipe_stdin = value.get("pipeStdin", False)
    if not isinstance(pipe_stdin, bool):
        raise ValueError("pipeStdin must be a bool")
    arg0 = value.get("arg0")
    if arg0 is not None and not isinstance(arg0, str):
        raise ValueError("arg0 must be a string or null")
    env_policy_value = value.get("envPolicy")
    env_policy = None if env_policy_value is None else decode_exec_env_policy(env_policy_value)
    return ExecParams(
        process_id=process_id,
        argv=list(argv),
        cwd=cwd,
        env=dict(env_value),
        tty=tty,
        env_policy=env_policy,
        pipe_stdin=pipe_stdin,
        arg0=arg0,
    )


def decode_exec_env_policy(value: Any) -> ExecEnvPolicy:
    if not isinstance(value, Mapping):
        raise ValueError("ExecEnvPolicy must be a mapping")
    inherit = value.get("inherit")
    if not isinstance(inherit, str):
        raise ValueError("inherit must be a string")
    ignore_default_excludes = value.get("ignoreDefaultExcludes")
    if not isinstance(ignore_default_excludes, bool):
        raise ValueError("ignoreDefaultExcludes must be a bool")
    exclude = value.get("exclude", [])
    include_only = value.get("includeOnly", [])
    set_values = value.get("set", {})
    if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
        raise ValueError("exclude must be a list of strings")
    if not isinstance(include_only, list) or not all(isinstance(item, str) for item in include_only):
        raise ValueError("includeOnly must be a list of strings")
    if not isinstance(set_values, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in set_values.items()
    ):
        raise ValueError("set must be an object with string values")
    return ExecEnvPolicy(
        inherit=ShellEnvironmentPolicyInherit(inherit),
        ignore_default_excludes=ignore_default_excludes,
        exclude=list(exclude),
        set=dict(set_values),
        include_only=list(include_only),
    )


@dataclass(frozen=True)
class ExecResponse:
    process_id: ProcessId


def encode_exec_response(value: ExecResponse) -> dict[str, Any]:
    return {"processId": value.process_id.as_str()}


@dataclass(frozen=True)
class ReadParams:
    process_id: ProcessId
    after_seq: int | None = None
    max_bytes: int | None = None
    wait_ms: int | None = None


def decode_read_params(value: Any) -> ReadParams:
    if not isinstance(value, Mapping):
        raise ValueError("ReadParams must be a mapping")
    return ReadParams(
        process_id=_decode_process_id(value.get("processId")),
        after_seq=_decode_optional_int(value.get("afterSeq"), "afterSeq"),
        max_bytes=_decode_optional_int(value.get("maxBytes"), "maxBytes"),
        wait_ms=_decode_optional_int(value.get("waitMs"), "waitMs"),
    )


def encode_read_params(value: ReadParams) -> dict[str, Any]:
    return {
        "processId": value.process_id.as_str(),
        "afterSeq": value.after_seq,
        "maxBytes": value.max_bytes,
        "waitMs": value.wait_ms,
    }


class ExecOutputStream(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    PTY = "pty"


@dataclass(frozen=True)
class ProcessOutputChunk:
    seq: int
    stream: ExecOutputStream
    chunk: ByteChunk


@dataclass(frozen=True)
class ReadResponse:
    chunks: list[ProcessOutputChunk]
    next_seq: int
    exited: bool
    exit_code: int | None
    closed: bool
    failure: str | None = None


def encode_read_response(value: ReadResponse) -> dict[str, Any]:
    return {
        "chunks": [
            {
                "seq": chunk.seq,
                "stream": chunk.stream.value,
                "chunk": chunk.chunk.to_base64(),
            }
            for chunk in value.chunks
        ],
        "nextSeq": value.next_seq,
        "exited": value.exited,
        "exitCode": value.exit_code,
        "closed": value.closed,
        "failure": value.failure,
    }


def decode_read_response(value: Any) -> ReadResponse:
    if not isinstance(value, Mapping):
        raise ValueError("ReadResponse must be a mapping")
    chunks_value = value.get("chunks")
    if not isinstance(chunks_value, list):
        raise ValueError("chunks must be a list")
    chunks: list[ProcessOutputChunk] = []
    for chunk_value in chunks_value:
        if not isinstance(chunk_value, Mapping):
            raise ValueError("chunk must be a mapping")
        stream_value = chunk_value.get("stream")
        chunk_b64 = chunk_value.get("chunk")
        if not isinstance(stream_value, str) or not isinstance(chunk_b64, str):
            raise ValueError("stream and chunk are required")
        seq = _decode_optional_int(chunk_value.get("seq"), "seq")
        if seq is None:
            raise ValueError("seq must be an integer")
        chunks.append(
            ProcessOutputChunk(
                seq=seq,
                stream=ExecOutputStream(stream_value),
                chunk=ByteChunk.from_base64(chunk_b64),
            )
        )
    next_seq = _decode_optional_int(value.get("nextSeq"), "nextSeq")
    if next_seq is None:
        raise ValueError("nextSeq must be an integer")
    exited = value.get("exited")
    closed = value.get("closed")
    if not isinstance(exited, bool):
        raise ValueError("exited must be a bool")
    if not isinstance(closed, bool):
        raise ValueError("closed must be a bool")
    exit_code = _decode_optional_int(value.get("exitCode"), "exitCode")
    failure = value.get("failure")
    if failure is not None and not isinstance(failure, str):
        raise ValueError("failure must be a string or null")
    return ReadResponse(
        chunks=chunks,
        next_seq=next_seq,
        exited=exited,
        exit_code=exit_code,
        closed=closed,
        failure=failure,
    )


@dataclass(frozen=True)
class WriteParams:
    process_id: ProcessId
    chunk: ByteChunk


def decode_write_params(value: Any) -> WriteParams:
    if not isinstance(value, Mapping):
        raise ValueError("WriteParams must be a mapping")
    chunk = value.get("chunk")
    if not isinstance(chunk, str):
        raise ValueError("chunk must be a base64 string")
    return WriteParams(process_id=_decode_process_id(value.get("processId")), chunk=ByteChunk.from_base64(chunk))


def encode_write_params(value: WriteParams) -> dict[str, Any]:
    return {
        "processId": value.process_id.as_str(),
        "chunk": value.chunk.to_base64(),
    }


class WriteStatus(str, Enum):
    ACCEPTED = "accepted"
    UNKNOWN_PROCESS = "unknownProcess"
    STDIN_CLOSED = "stdinClosed"
    STARTING = "starting"


@dataclass(frozen=True)
class WriteResponse:
    status: WriteStatus


def encode_write_response(value: WriteResponse) -> dict[str, Any]:
    return {"status": value.status.value}


def decode_write_response(value: Any) -> WriteResponse:
    if not isinstance(value, Mapping):
        raise ValueError("WriteResponse must be a mapping")
    status = value.get("status")
    if not isinstance(status, str):
        raise ValueError("status must be a string")
    return WriteResponse(WriteStatus(status))


@dataclass(frozen=True)
class TerminateParams:
    process_id: ProcessId


def decode_terminate_params(value: Any) -> TerminateParams:
    if not isinstance(value, Mapping):
        raise ValueError("TerminateParams must be a mapping")
    return TerminateParams(process_id=_decode_process_id(value.get("processId")))


def encode_terminate_params(value: TerminateParams) -> dict[str, Any]:
    return {"processId": value.process_id.as_str()}


@dataclass(frozen=True)
class TerminateResponse:
    running: bool


def encode_terminate_response(value: TerminateResponse) -> dict[str, Any]:
    return {"running": value.running}


def decode_terminate_response(value: Any) -> TerminateResponse:
    if not isinstance(value, Mapping):
        raise ValueError("TerminateResponse must be a mapping")
    running = value.get("running")
    if not isinstance(running, bool):
        raise ValueError("running must be a bool")
    return TerminateResponse(running=running)


def _decode_process_id(value: Any) -> ProcessId:
    if not isinstance(value, str):
        raise ValueError("processId must be a string")
    return ProcessId.new(value)


def _decode_optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer or null")
    return value


@dataclass(frozen=True)
class FsReadFileParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsReadFileResponse:
    data_base64: str


@dataclass(frozen=True)
class FsWriteFileParams:
    path: str
    data_base64: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsWriteFileResponse:
    pass


@dataclass(frozen=True)
class FsCreateDirectoryParams:
    path: str
    recursive: bool | None = None
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsCreateDirectoryResponse:
    pass


@dataclass(frozen=True)
class FsGetMetadataParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsGetMetadataResponse:
    is_directory: bool
    is_file: bool
    is_symlink: bool
    created_at_ms: int
    modified_at_ms: int


@dataclass(frozen=True)
class FsReadDirectoryParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsReadDirectoryEntry:
    file_name: str
    is_directory: bool
    is_file: bool


@dataclass(frozen=True)
class FsReadDirectoryResponse:
    entries: list[FsReadDirectoryEntry]


@dataclass(frozen=True)
class FsRemoveParams:
    path: str
    recursive: bool | None = None
    force: bool | None = None
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsRemoveResponse:
    pass


@dataclass(frozen=True)
class FsCopyParams:
    source_path: str
    destination_path: str
    recursive: bool
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsCopyResponse:
    pass


@dataclass(frozen=True)
class HttpHeader:
    name: str
    value: str


@dataclass(frozen=True)
class HttpRequestParams:
    method: str
    url: str
    headers: list[HttpHeader]
    request_id: str
    body: ByteChunk | None = None
    timeout_ms: int | None = None
    stream_response: bool = False


def decode_http_header(value: Any) -> HttpHeader:
    if not isinstance(value, Mapping):
        raise ValueError("HttpHeader must be a mapping")
    name = value.get("name")
    header_value = value.get("value")
    if not isinstance(name, str):
        raise ValueError("header name must be a string")
    if not isinstance(header_value, str):
        raise ValueError("header value must be a string")
    return HttpHeader(name=name, value=header_value)


def encode_http_header(value: HttpHeader) -> dict[str, Any]:
    return {"name": value.name, "value": value.value}


def decode_http_request_params(value: Any) -> HttpRequestParams:
    if not isinstance(value, Mapping):
        raise ValueError("HttpRequestParams must be a mapping")
    method = value.get("method")
    url = value.get("url")
    request_id = value.get("requestId")
    if not isinstance(method, str):
        raise ValueError("method must be a string")
    if not isinstance(url, str):
        raise ValueError("url must be a string")
    if not isinstance(request_id, str):
        raise ValueError("requestId must be a string")
    headers_value = value.get("headers", [])
    if not isinstance(headers_value, list):
        raise ValueError("headers must be a list")
    body_value = value.get("bodyBase64")
    if body_value is not None and not isinstance(body_value, str):
        raise ValueError("bodyBase64 must be a base64 string or null")
    stream_response = value.get("streamResponse", False)
    if not isinstance(stream_response, bool):
        raise ValueError("streamResponse must be a bool")
    return HttpRequestParams(
        method=method,
        url=url,
        headers=[decode_http_header(item) for item in headers_value],
        request_id=request_id,
        body=None if body_value is None else ByteChunk.from_base64(body_value),
        timeout_ms=_decode_optional_int(value.get("timeoutMs"), "timeoutMs"),
        stream_response=stream_response,
    )


@dataclass(frozen=True)
class HttpRequestResponse:
    status: int
    headers: list[HttpHeader]
    body: ByteChunk


def encode_http_request_response(value: HttpRequestResponse) -> dict[str, Any]:
    return {
        "status": value.status,
        "headers": [encode_http_header(header) for header in value.headers],
        "bodyBase64": value.body.to_base64(),
    }


@dataclass(frozen=True)
class HttpRequestBodyDeltaNotification:
    request_id: str
    seq: int
    delta: ByteChunk
    done: bool = False
    error: str | None = None


def decode_http_request_body_delta_notification(value: Any) -> HttpRequestBodyDeltaNotification:
    if isinstance(value, HttpRequestBodyDeltaNotification):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("http/request/bodyDelta params must be an object")
    request_id = value.get("requestId")
    if not isinstance(request_id, str):
        raise ValueError("http/request/bodyDelta requestId must be a string")
    seq = _decode_optional_int(value.get("seq"), "seq")
    if seq is None:
        raise ValueError("http/request/bodyDelta seq must be an integer")
    delta = value.get("deltaBase64")
    if not isinstance(delta, str):
        raise ValueError("http/request/bodyDelta deltaBase64 must be a base64 string")
    done = value.get("done", False)
    if not isinstance(done, bool):
        raise ValueError("http/request/bodyDelta done must be a boolean")
    error = value.get("error")
    if error is not None and not isinstance(error, str):
        raise ValueError("http/request/bodyDelta error must be a string")
    return HttpRequestBodyDeltaNotification(
        request_id=request_id,
        seq=seq,
        delta=ByteChunk.from_base64(delta),
        done=done,
        error=error,
    )


def encode_http_request_body_delta_notification(value: HttpRequestBodyDeltaNotification) -> dict[str, Any]:
    return _without_none(
        {
            "requestId": value.request_id,
            "seq": value.seq,
            "deltaBase64": value.delta.to_base64(),
            "done": value.done,
            "error": value.error,
        }
    )


@dataclass(frozen=True)
class ExecOutputDeltaNotification:
    process_id: ProcessId
    seq: int
    stream: ExecOutputStream
    chunk: ByteChunk


def encode_exec_output_delta_notification(value: ExecOutputDeltaNotification) -> dict[str, Any]:
    return {
        "processId": value.process_id.as_str(),
        "seq": value.seq,
        "stream": value.stream.value,
        "chunk": value.chunk.to_base64(),
    }


@dataclass(frozen=True)
class ExecExitedNotification:
    process_id: ProcessId
    seq: int
    exit_code: int


def encode_exec_exited_notification(value: ExecExitedNotification) -> dict[str, Any]:
    return {"processId": value.process_id.as_str(), "seq": value.seq, "exitCode": value.exit_code}


@dataclass(frozen=True)
class ExecClosedNotification:
    process_id: ProcessId
    seq: int


def encode_exec_closed_notification(value: ExecClosedNotification) -> dict[str, Any]:
    return {"processId": value.process_id.as_str(), "seq": value.seq}


from pycodex.exec_server.local_file_system import _without_none
from pycodex.exec_server.process_id import ProcessId
