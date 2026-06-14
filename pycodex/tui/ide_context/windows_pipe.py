"""Windows named-pipe transport boundary for IDE context IPC.

Upstream source: ``codex/codex-rs/tui/src/ide_context/windows_pipe.rs``.

Rust implements Win32 overlapped pipe I/O and same-user SID validation here.
The Python port exposes the semantic wrappers and timeout helpers while leaving
native Win32 transport calls as explicit platform boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ide_context::windows_pipe",
    source="codex/codex-rs/tui/src/ide_context/windows_pipe.rs",
)

TRUE = 1
FALSE = 0
NULL_HANDLE = 0
U32_MAX = 0xFFFFFFFF


@dataclass
class WindowsPipeStream:
    handle: Any
    deadline: float

    @classmethod
    def connect(cls, *args: Any, **kwargs: Any) -> "WindowsPipeStream":
        return not_ported(RUST_MODULE, "WindowsPipeStream.connect")

    def set_deadline(self, deadline: float) -> None:
        self.deadline = deadline

    def read(self, buf: bytearray | memoryview) -> int:
        if len(buf) == 0:
            return 0
        return not_ported(RUST_MODULE, "WindowsPipeStream.read")

    def write(self, buf: bytes | bytearray | memoryview) -> int:
        if len(buf) == 0:
            return 0
        return not_ported(RUST_MODULE, "WindowsPipeStream.write")

    def flush(self) -> None:
        return None


def read(stream: WindowsPipeStream, buf: bytearray | memoryview) -> int:
    return stream.read(buf)


def write(stream: WindowsPipeStream, buf: bytes | bytearray | memoryview) -> int:
    return stream.write(buf)


def flush(stream: WindowsPipeStream) -> None:
    stream.flush()


@dataclass
class OverlappedOperation:
    event: Any = None
    overlapped: Any = None

    @classmethod
    def new(cls, *args: Any, **kwargs: Any) -> "OverlappedOperation":
        return not_ported(RUST_MODULE, "OverlappedOperation.new")

    def as_mut_ptr(self) -> Any:
        return self.overlapped

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "OverlappedOperation.complete")

    def cancel_and_timeout(self, *args: Any, **kwargs: Any) -> TimeoutError:
        return timeout_io_error()


@dataclass(frozen=True)
class OwnedHandle:
    handle: Any

    def raw(self) -> Any:
        return self.handle


def drop(_handle: OwnedHandle) -> None:
    return None


@dataclass(frozen=True)
class TokenUserBuffer:
    buffer: bytes

    def sid(self) -> Any:
        if len(self.buffer) == 0:
            raise ValueError("token user buffer is too small")
        return not_ported(RUST_MODULE, "TokenUserBuffer.sid")


def validate_pipe_server_owner(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "validate_pipe_server_owner")


def open_process_token(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "open_process_token")


def token_user(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "token_user")


def remaining_timeout_ms(deadline: float) -> int:
    now = time.monotonic()
    if now >= deadline:
        return 0
    millis = max(1, int((deadline - now) * 1000))
    return min(U32_MAX, millis)


def timeout_io_error() -> TimeoutError:
    return TimeoutError("timed out waiting for IDE context")


__all__ = [
    "FALSE",
    "NULL_HANDLE",
    "OverlappedOperation",
    "OwnedHandle",
    "RUST_MODULE",
    "TRUE",
    "TokenUserBuffer",
    "WindowsPipeStream",
    "drop",
    "flush",
    "open_process_token",
    "read",
    "remaining_timeout_ms",
    "timeout_io_error",
    "token_user",
    "validate_pipe_server_owner",
    "write",
]
