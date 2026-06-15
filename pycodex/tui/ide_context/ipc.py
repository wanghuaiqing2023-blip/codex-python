"""Private IPC protocol helpers for TUI `/ide` context.

Upstream source: ``codex/codex-rs/tui/src/ide_context/ipc.rs``.

The Python port covers request/response framing and error semantics. Real Unix
socket / Windows named-pipe transport remains an explicit platform boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import tempfile
import time
import uuid
from typing import Any, BinaryIO, Dict, Optional, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ide_context::ipc",
    source="codex/codex-rs/tui/src/ide_context/ipc.rs",
    status="complete",
)

IDE_CONTEXT_REQUEST_TIMEOUT = 5.0
MAX_IPC_FRAME_BYTES = 256 * 1024 * 1024
TUI_SOURCE_CLIENT_ID = "codex-tui"
OPEN_IDE_HINT = "Open this project in VS Code or Cursor with the Codex extension active."
IDE_DID_NOT_PROVIDE_CONTEXT_HINT = "The IDE extension did not provide context."
KEEP_TRYING_HINT = "Codex will keep trying on future messages."


@dataclass(frozen=True)
class IdeContextError(Exception):
    kind: str
    detail: Any = None

    def __str__(self) -> str:
        if self.kind == "Connect":
            return f"failed to connect to IDE context provider: {self.detail}"
        if self.kind == "Send":
            return f"failed to request IDE context: {self.detail}"
        if self.kind == "Read":
            return f"failed to read IDE context: {self.detail}"
        if self.kind == "InvalidResponse":
            return f"invalid IDE context response: {self.detail}"
        if self.kind == "ResponseTooLarge":
            return "IDE context response exceeded maximum size"
        if self.kind == "RequestFailed":
            return "IDE context request failed"
        return "IDE context is not supported on this platform"

    def user_facing_hint(self) -> str:
        if self.kind == "Connect":
            return OPEN_IDE_HINT
        if self.kind == "RequestFailed" and self.detail == "no-client-found":
            return OPEN_IDE_HINT
        if self.kind == "RequestFailed":
            return f"{IDE_DID_NOT_PROVIDE_CONTEXT_HINT} Try /ide again."
        if self.kind == "ResponseTooLarge":
            return (
                "The selected IDE context is too large. Clear any large selection in your IDE "
                "and try /ide again."
            )
        if self.kind == "Send":
            return "Codex could not request IDE context. Try /ide again."
        if self.kind in {"Read", "InvalidResponse"}:
            return "Codex could not read IDE context. Try /ide again."
        return str(self)

    def prompt_skip_hint(self) -> str:
        if self.kind == "ResponseTooLarge":
            return "The selected IDE context is too large. Clear any large selection in your IDE."
        if self.kind == "Connect":
            return OPEN_IDE_HINT
        if self.kind == "RequestFailed" and self.detail == "no-client-found":
            return OPEN_IDE_HINT
        if self.kind == "Read" and _is_timed_out(self.detail):
            return "Codex timed out waiting for IDE context. It will keep trying on future messages."
        if self.kind == "RequestFailed" and self.detail == "client-disconnected":
            return hint_with_retry("The IDE connection changed while Codex was requesting context.")
        if self.kind == "RequestFailed" and self.detail == "request-timeout":
            return hint_with_retry("The IDE extension did not answer in time.")
        if self.kind == "RequestFailed" and self.detail == "request-version-mismatch":
            return "The connected IDE extension is not compatible with this IDE context request."
        if self.kind == "RequestFailed" and self.detail == "no-handler-for-request":
            return "The connected IDE client does not support IDE context requests."
        if self.kind == "Send":
            return hint_with_retry("Codex lost the IDE connection while requesting context.")
        if self.kind == "InvalidResponse":
            return hint_with_retry("Codex received an unexpected IDE context response.")
        if self.kind == "RequestFailed":
            return hint_with_retry(IDE_DID_NOT_PROVIDE_CONTEXT_HINT)
        if self.kind == "Read":
            return hint_with_retry("Codex could not read IDE context.")
        return str(self)


def hint_with_retry(message: str) -> str:
    return f"{message} {KEEP_TRYING_HINT}"


IdeContextStream = Any


def fetch_ide_context(workspace_root: Union[str, Path]) -> Any:
    if os.name != "posix" and sys.platform != "win32":
        raise IdeContextError("UnsupportedPlatform")
    return fetch_ide_context_from_socket(
        default_ipc_socket_path(),
        workspace_root,
        IDE_CONTEXT_REQUEST_TIMEOUT,
    )


def default_ipc_socket_path() -> Path:
    if sys.platform == "win32":
        return Path(r"\\.\pipe\codex-ipc")
    if sys.platform != "win32":
        uid = getattr(__import__("os"), "getuid", lambda: 0)()
        return Path(tempfile.gettempdir()) / "codex-ipc" / f"ipc-{uid}.sock"
    return Path()


def fetch_ide_context_from_socket(
    socket_path: Union[str, Path],
    workspace_root: Union[str, Path],
    timeout: float,
) -> Any:
    deadline = time.monotonic() + timeout
    try:
        stream = connect_stream(socket_path, deadline)
    except OSError as exc:
        raise IdeContextError("Connect", exc) from exc
    return fetch_ide_context_from_stream(stream, workspace_root, None, deadline)


def connect_stream(socket_path: Union[str, Path], deadline: float) -> Any:
    if sys.platform == "win32":
        from .windows_pipe import WindowsPipeStream

        return WindowsPipeStream.connect(Path(socket_path), deadline)
    if os.name == "posix":
        return UnixDeadlineStream.connect(Path(socket_path), deadline)
    raise IdeContextError("UnsupportedPlatform")


@dataclass
class UnixDeadlineStream:
    stream: Any
    deadline: float

    @classmethod
    def connect(cls, socket_path: Union[str, Path], deadline: float) -> "UnixDeadlineStream":
        stream = connect_unix_stream_before_deadline(Path(socket_path), deadline)
        wrapped = cls.new(stream, deadline)
        validate_unix_peer_owner(wrapped)
        return wrapped

    @classmethod
    def new(cls, stream: Any, deadline: float) -> "UnixDeadlineStream":
        return cls(stream, deadline)

    def set_deadline(self, deadline: float) -> None:
        self.deadline = deadline

    def wait_for_ready(self, *args: Any, **kwargs: Any) -> None:
        ensure_deadline_not_expired(self.deadline)

    def read(self, size: int) -> bytes:
        if size <= 0:
            return b""
        while True:
            self.wait_for_ready()
            self.stream.settimeout(_remaining_timeout(self.deadline))
            try:
                return self.stream.recv(size)
            except InterruptedError:
                continue
            except BlockingIOError:
                continue
            except TimeoutError as exc:
                raise deadline_timeout_io_error() from exc

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        while True:
            self.wait_for_ready()
            self.stream.settimeout(_remaining_timeout(self.deadline))
            try:
                return self.stream.send(data)
            except InterruptedError:
                continue
            except BlockingIOError:
                continue
            except TimeoutError as exc:
                raise deadline_timeout_io_error() from exc

    def flush(self) -> None:
        return None


def answer_unsupported_request(stream: BinaryIO, message: Dict[str, Any]) -> None:
    request_id = message.get("requestId")
    if isinstance(request_id, str):
        _write_outbound_frame(
            stream,
            {
                "type": "response",
                "requestId": request_id,
                "resultType": "error",
                "error": "no-handler-for-request",
            },
        )


def fetch_ide_context_from_stream(
    stream: BinaryIO,
    workspace_root: Union[str, Path],
    request_id: Optional[str] = None,
    deadline: Optional[float] = None,
) -> Any:
    request_id = request_id or str(uuid.uuid4())
    deadline = deadline or time.monotonic() + IDE_CONTEXT_REQUEST_TIMEOUT
    write_ide_context_request(stream, request_id, workspace_root)
    response = read_response_frame(stream, request_id, deadline)
    return extract_ide_context(response)


def write_ide_context_request(
    stream: BinaryIO,
    request_id: str,
    workspace_root: Union[str, Path],
) -> None:
    write_frame(
        stream,
        {
            "type": "request",
            "requestId": request_id,
            "sourceClientId": TUI_SOURCE_CLIENT_ID,
            "version": 0,
            "method": "ide-context",
            "params": {"workspaceRoot": str(workspace_root)},
        },
    )


def write_frame(stream: BinaryIO, message: Dict[str, Any]) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(payload) > 0xFFFFFFFF:
        raise OSError("IDE context payload exceeds u32 length")
    _stream_write_all(stream, len(payload).to_bytes(4, "little"))
    _stream_write_all(stream, payload)
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def read_frame(stream: BinaryIO, deadline: Optional[float] = None) -> Dict[str, Any]:
    len_bytes = read_exact_before_deadline(stream, 4, deadline)
    length = int.from_bytes(len_bytes, "little")
    if length > MAX_IPC_FRAME_BYTES:
        raise IdeContextError("ResponseTooLarge")
    payload = read_exact_before_deadline(stream, length, deadline)
    try:
        value = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise IdeContextError("InvalidResponse", f"invalid JSON payload: {exc}") from exc
    if not isinstance(value, dict):
        raise IdeContextError("InvalidResponse", "IDE context frame payload was not an object")
    return value


def read_exact_before_deadline(
    stream: BinaryIO,
    size: int,
    deadline: Optional[float] = None,
) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        ensure_deadline_not_expired(deadline)
        part = _stream_read(stream, size - len(chunks))
        if part == b"":
            raise IdeContextError("Read", EOFError("failed to fill whole IDE context frame"))
        chunks.extend(part)
    ensure_deadline_not_expired(deadline)
    return bytes(chunks)


def read_response_frame(
    stream: BinaryIO,
    request_id: str,
    deadline: Optional[float] = None,
) -> Dict[str, Any]:
    while True:
        ensure_deadline_not_expired(deadline)
        message = read_frame(stream, deadline)
        message_type = message.get("type")
        if message_type == "response":
            if message.get("requestId") == request_id:
                return message
        elif message_type == "broadcast":
            continue
        elif message_type == "client-discovery-request":
            discovery_request_id = message.get("requestId")
            if isinstance(discovery_request_id, str):
                _write_outbound_frame(
                    stream,
                    {
                        "type": "client-discovery-response",
                        "requestId": discovery_request_id,
                        "response": {"canHandle": False},
                    },
                )
        elif message_type == "client-discovery-response":
            continue
        elif message_type == "request":
            answer_unsupported_request(stream, message)
        elif isinstance(message_type, str):
            raise IdeContextError("InvalidResponse", f"unexpected IDE context message type: {message_type}")
        else:
            raise IdeContextError("InvalidResponse", "IDE context message did not include a type")


def ensure_deadline_not_expired(deadline: Optional[float]) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise timeout_error()


def timeout_error() -> IdeContextError:
    return IdeContextError("Read", TimeoutError("timed out waiting for IDE context"))


def deadline_timeout_io_error() -> TimeoutError:
    return TimeoutError("timed out waiting for IDE context")


def extract_ide_context(response: Dict[str, Any]) -> Any:
    ensure_success_response(response)
    try:
        return response["result"]["ideContext"]
    except Exception as exc:
        raise IdeContextError(
            "InvalidResponse",
            "ide-context response did not include result.ideContext",
        ) from exc


def ensure_success_response(response: Dict[str, Any]) -> None:
    result_type = response.get("resultType")
    if result_type == "success":
        return
    if result_type == "error":
        raise IdeContextError("RequestFailed", response.get("error", "unknown error"))
    raise IdeContextError("InvalidResponse", "response did not include a success or error resultType")


def connect_unix_stream_before_deadline(socket_path: Path, deadline: float) -> socket.socket:
    validate_unix_socket_path(socket_path)
    stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stream.settimeout(_remaining_timeout(deadline))
    try:
        stream.connect(str(socket_path))
    except Exception:
        stream.close()
        raise
    return stream


def validate_unix_socket_path(socket_path: Union[str, Path]) -> None:
    if os.name != "posix":
        return
    path = Path(socket_path)
    uid = os.getuid()
    parent = path.parent
    if not parent:
        raise PermissionError("IDE context socket has no parent directory")
    parent_metadata = os.stat(str(parent), follow_symlinks=False)
    if not stat.S_ISDIR(parent_metadata.st_mode) or parent_metadata.st_uid != uid:
        raise PermissionError("IDE context socket directory is not owned by the current user")
    if parent_metadata.st_mode & 0o022:
        raise PermissionError("IDE context socket directory is writable by other users")
    socket_metadata = os.stat(str(path), follow_symlinks=False)
    if not stat.S_ISSOCK(socket_metadata.st_mode) or socket_metadata.st_uid != uid:
        raise PermissionError("IDE context socket is not owned by the current user")


def validate_unix_peer_owner(stream: UnixDeadlineStream) -> None:
    if os.name != "posix":
        return
    sock = stream.stream
    if hasattr(socket, "SO_PEERCRED"):
        credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _pid, uid, _gid = struct.unpack("3i", credentials)
        if uid != os.getuid():
            raise PermissionError("IDE context provider is not owned by the current user")


def _is_timed_out(value: Any) -> bool:
    return isinstance(value, TimeoutError) or "timed out" in str(value).lower()


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise deadline_timeout_io_error()
    return remaining


def _stream_read(stream: BinaryIO, size: int) -> bytes:
    try:
        part = stream.read(size)
        if isinstance(part, int):
            buffer = bytearray(size)
            read_count = part
            return bytes(buffer[:read_count])
        return part
    except TypeError:
        buffer = bytearray(size)
        read_count = stream.read(buffer)
        return bytes(buffer[:read_count])


def _stream_write_all(stream: BinaryIO, data: bytes) -> None:
    written = 0
    while written < len(data):
        result = stream.write(data[written:])
        if result is None:
            return
        if result == 0:
            raise OSError("failed to write whole IDE context frame")
        written += int(result)


def _write_outbound_frame(stream: BinaryIO, message: Dict[str, Any]) -> None:
    if isinstance(stream, io.BytesIO):
        position = stream.tell()
        stream.seek(0, io.SEEK_END)
        write_frame(stream, message)
        stream.seek(position)
        return
    write_frame(stream, message)


__all__ = [
    "IDE_CONTEXT_REQUEST_TIMEOUT",
    "IDE_DID_NOT_PROVIDE_CONTEXT_HINT",
    "IdeContextError",
    "IdeContextStream",
    "KEEP_TRYING_HINT",
    "MAX_IPC_FRAME_BYTES",
    "OPEN_IDE_HINT",
    "RUST_MODULE",
    "TUI_SOURCE_CLIENT_ID",
    "UnixDeadlineStream",
    "answer_unsupported_request",
    "connect_stream",
    "connect_unix_stream_before_deadline",
    "deadline_timeout_io_error",
    "default_ipc_socket_path",
    "ensure_deadline_not_expired",
    "ensure_success_response",
    "extract_ide_context",
    "fetch_ide_context",
    "fetch_ide_context_from_socket",
    "fetch_ide_context_from_stream",
    "hint_with_retry",
    "read_exact_before_deadline",
    "read_frame",
    "read_response_frame",
    "timeout_error",
    "validate_unix_peer_owner",
    "validate_unix_socket_path",
    "write_frame",
    "write_ide_context_request",
]
