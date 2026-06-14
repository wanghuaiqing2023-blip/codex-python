"""Private IPC protocol helpers for TUI `/ide` context.

Upstream source: ``codex/codex-rs/tui/src/ide_context/ipc.rs``.

The Python port covers request/response framing and error semantics. Real Unix
socket / Windows named-pipe transport remains an explicit platform boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, BinaryIO

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ide_context::ipc",
    source="codex/codex-rs/tui/src/ide_context/ipc.rs",
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


def fetch_ide_context(workspace_root: str | Path) -> Any:
    return not_ported(RUST_MODULE, "fetch_ide_context")


def default_ipc_socket_path() -> Path:
    if sys.platform == "win32":
        return Path(r"\\.\pipe\codex-ipc")
    if sys.platform != "win32":
        uid = getattr(__import__("os"), "getuid", lambda: 0)()
        return Path(tempfile.gettempdir()) / "codex-ipc" / f"ipc-{uid}.sock"
    return Path()


def fetch_ide_context_from_socket(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "fetch_ide_context_from_socket")


def connect_stream(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "connect_stream")


@dataclass
class UnixDeadlineStream:
    stream: Any
    deadline: float

    @classmethod
    def connect(cls, *args: Any, **kwargs: Any) -> "UnixDeadlineStream":
        return not_ported(RUST_MODULE, "UnixDeadlineStream.connect")

    @classmethod
    def new(cls, stream: Any, deadline: float) -> "UnixDeadlineStream":
        return cls(stream, deadline)

    def set_deadline(self, deadline: float) -> None:
        self.deadline = deadline

    def wait_for_ready(self, *args: Any, **kwargs: Any) -> None:
        return not_ported(RUST_MODULE, "UnixDeadlineStream.wait_for_ready")


def answer_unsupported_request(stream: BinaryIO, message: dict[str, Any]) -> None:
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


def fetch_ide_context_from_stream(stream: BinaryIO, workspace_root: str | Path, request_id: str | None = None) -> Any:
    request_id = request_id or "request-id"
    write_ide_context_request(stream, request_id, workspace_root)
    response = read_response_frame(stream, request_id, time.monotonic() + IDE_CONTEXT_REQUEST_TIMEOUT)
    return extract_ide_context(response)


def write_ide_context_request(stream: BinaryIO, request_id: str, workspace_root: str | Path) -> None:
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


def write_frame(stream: BinaryIO, message: dict[str, Any]) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(payload) > 0xFFFFFFFF:
        raise OSError("IDE context payload exceeds u32 length")
    stream.write(len(payload).to_bytes(4, "little"))
    stream.write(payload)
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def read_frame(stream: BinaryIO, deadline: float | None = None) -> dict[str, Any]:
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


def read_exact_before_deadline(stream: BinaryIO, size: int, deadline: float | None = None) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        ensure_deadline_not_expired(deadline)
        part = stream.read(size - len(chunks))
        if part == b"":
            raise IdeContextError("Read", EOFError("failed to fill whole IDE context frame"))
        chunks.extend(part)
    ensure_deadline_not_expired(deadline)
    return bytes(chunks)


def read_response_frame(stream: BinaryIO, request_id: str, deadline: float | None = None) -> dict[str, Any]:
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


def ensure_deadline_not_expired(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise timeout_error()


def timeout_error() -> IdeContextError:
    return IdeContextError("Read", TimeoutError("timed out waiting for IDE context"))


def deadline_timeout_io_error() -> TimeoutError:
    return TimeoutError("timed out waiting for IDE context")


def extract_ide_context(response: dict[str, Any]) -> Any:
    ensure_success_response(response)
    try:
        return response["result"]["ideContext"]
    except Exception as exc:
        raise IdeContextError(
            "InvalidResponse",
            "ide-context response did not include result.ideContext",
        ) from exc


def ensure_success_response(response: dict[str, Any]) -> None:
    result_type = response.get("resultType")
    if result_type == "success":
        return
    if result_type == "error":
        raise IdeContextError("RequestFailed", response.get("error", "unknown error"))
    raise IdeContextError("InvalidResponse", "response did not include a success or error resultType")


def connect_unix_stream_before_deadline(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "connect_unix_stream_before_deadline")


def validate_unix_socket_path(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "validate_unix_socket_path")


def validate_unix_peer_owner(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "validate_unix_peer_owner")


def _is_timed_out(value: Any) -> bool:
    return isinstance(value, TimeoutError) or "timed out" in str(value).lower()


def _write_outbound_frame(stream: BinaryIO, message: dict[str, Any]) -> None:
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
