"""Length-prefixed Unix sockets with optional descriptor passing."""

from __future__ import annotations

import asyncio
import json
import socket as _socket
import struct
from array import array
from pathlib import Path
from typing import Any

MAX_FDS_PER_MESSAGE = 16
LENGTH_PREFIX_SIZE = 4
MAX_DATAGRAM_SIZE = 8192


def encode_length(length: int) -> bytes:
    if isinstance(length, bool) or not isinstance(length, int):
        raise TypeError("message length must be an integer")
    if length < 0 or length > 0xFFFF_FFFF:
        raise ValueError(f"message too large: {length}")
    return struct.pack("<I", length)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _json_payload(message: Any) -> bytes:
    return json.dumps(
        message,
        default=_json_default,
        separators=(",", ":"),
    ).encode("utf-8")


def _fd_ancillary(fds: tuple[int, ...]) -> list[tuple[int, int, bytes]]:
    if len(fds) > MAX_FDS_PER_MESSAGE:
        raise ValueError(f"too many fds: {len(fds)}")
    if not fds:
        return []
    if not hasattr(_socket, "SCM_RIGHTS"):
        raise OSError(
            "SCM_RIGHTS file descriptor passing is not supported on this platform"
        )
    return [
        (
            _socket.SOL_SOCKET,
            _socket.SCM_RIGHTS,
            array("i", fds).tobytes(),
        )
    ]


def _extract_ancillary_fds(
    ancillary: list[tuple[int, int, bytes]],
) -> tuple[int, ...]:
    if not hasattr(_socket, "SCM_RIGHTS"):
        return ()
    result: list[int] = []
    for level, kind, data in ancillary:
        if level != _socket.SOL_SOCKET or kind != _socket.SCM_RIGHTS:
            continue
        values = array("i")
        usable = len(data) - len(data) % values.itemsize
        values.frombytes(data[:usable])
        result.extend(int(fd) for fd in values)
    return tuple(result)


def _control_size() -> int:
    if not hasattr(_socket, "CMSG_SPACE"):
        return 0
    return _socket.CMSG_SPACE(MAX_FDS_PER_MESSAGE * array("i").itemsize)


def _coerce_fd_tuple(
    fds: tuple[int, ...] | list[int] | None,
) -> tuple[int, ...]:
    result = () if fds is None else tuple(fds)
    if any(isinstance(fd, bool) or not isinstance(fd, int) for fd in result):
        raise TypeError("fds must contain integer file descriptors")
    return result


class AsyncSocket:
    def __init__(self, sock: _socket.socket) -> None:
        self.socket = sock

    @classmethod
    def from_fd(cls, fd: int) -> "AsyncSocket":
        if isinstance(fd, bool) or not isinstance(fd, int):
            raise TypeError("fd must be an integer")
        return cls(_socket.socket(fileno=fd))

    @classmethod
    def pair(cls) -> tuple["AsyncSocket", "AsyncSocket"]:
        if not hasattr(_socket, "socketpair") or not hasattr(_socket, "AF_UNIX"):
            raise OSError("socketpair is not supported on this platform")
        left, right = _socket.socketpair(_socket.AF_UNIX, _socket.SOCK_STREAM)
        return cls(left), cls(right)

    async def send_with_fds(
        self,
        message: Any,
        fds: tuple[int, ...] | list[int] | None = None,
    ) -> None:
        fd_tuple = _coerce_fd_tuple(fds)
        payload = _json_payload(message)
        frame = encode_length(len(payload)) + payload
        if fd_tuple:
            await asyncio.to_thread(
                self.socket.sendmsg,
                [frame],
                _fd_ancillary(fd_tuple),
            )
        else:
            await asyncio.to_thread(self.socket.sendall, frame)

    async def receive_with_fds(
        self,
        cls: Any | None = None,
    ) -> tuple[Any, tuple[int, ...]]:
        header, fds = await self._recv_exact_with_fds(LENGTH_PREFIX_SIZE)
        if len(header) != LENGTH_PREFIX_SIZE:
            raise EOFError("socket closed while receiving frame header")
        payload_len = struct.unpack("<I", header)[0]
        payload = await self._recv_exact(payload_len)
        if len(payload) != payload_len:
            raise EOFError("socket closed while receiving frame payload")
        decoded = json.loads(payload.decode("utf-8"))
        if cls is not None and hasattr(cls, "from_mapping"):
            decoded = cls.from_mapping(decoded)
        return decoded, fds

    async def send(self, message: Any) -> None:
        await self.send_with_fds(message)

    async def receive(self, cls: Any | None = None) -> Any:
        message, _ = await self.receive_with_fds(cls)
        return message

    def into_inner(self) -> _socket.socket:
        sock = self.socket
        self.socket = None  # type: ignore[assignment]
        return sock

    async def _recv_exact(self, count: int) -> bytes:
        data = bytearray()
        while len(data) < count:
            chunk = await asyncio.to_thread(
                self.socket.recv,
                count - len(data),
            )
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)

    async def _recv_exact_with_fds(
        self,
        count: int,
    ) -> tuple[bytes, tuple[int, ...]]:
        if hasattr(self.socket, "recvmsg"):
            chunk, ancillary, _flags, _addr = await asyncio.to_thread(
                self.socket.recvmsg,
                count,
                _control_size(),
            )
            fds = _extract_ancillary_fds(list(ancillary))
        else:
            chunk = await asyncio.to_thread(self.socket.recv, count)
            fds = ()
        data = bytearray(chunk)
        while len(data) < count:
            chunk = await asyncio.to_thread(
                self.socket.recv,
                count - len(data),
            )
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data), fds


class AsyncDatagramSocket:
    def __init__(self, sock: _socket.socket) -> None:
        self.socket = sock

    @classmethod
    def from_raw_fd(cls, fd: int) -> "AsyncDatagramSocket":
        if isinstance(fd, bool) or not isinstance(fd, int):
            raise TypeError("fd must be an integer")
        return cls(_socket.socket(fileno=fd))

    @classmethod
    def pair(cls) -> tuple["AsyncDatagramSocket", "AsyncDatagramSocket"]:
        if not hasattr(_socket, "socketpair") or not hasattr(_socket, "AF_UNIX"):
            raise OSError("socketpair is not supported on this platform")
        left, right = _socket.socketpair(_socket.AF_UNIX, _socket.SOCK_DGRAM)
        return cls(left), cls(right)

    async def send_with_fds(
        self,
        data: bytes,
        fds: tuple[int, ...] | list[int] | None = None,
    ) -> None:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("datagram data must be bytes-like")
        payload = bytes(data)
        ancillary = _fd_ancillary(_coerce_fd_tuple(fds))
        written = (
            await asyncio.to_thread(self.socket.sendmsg, [payload], ancillary)
            if ancillary
            else await asyncio.to_thread(self.socket.send, payload)
        )
        if written != len(payload):
            raise OSError(
                f"short datagram write: wrote {written} bytes out of {len(payload)}"
            )

    async def receive_with_fds(self) -> tuple[bytes, tuple[int, ...]]:
        if hasattr(self.socket, "recvmsg"):
            data, ancillary, _flags, _addr = await asyncio.to_thread(
                self.socket.recvmsg,
                MAX_DATAGRAM_SIZE,
                _control_size(),
            )
            return data, _extract_ancillary_fds(list(ancillary))
        return await asyncio.to_thread(
            self.socket.recv,
            MAX_DATAGRAM_SIZE,
        ), ()

    def into_inner(self) -> _socket.socket:
        sock = self.socket
        self.socket = None  # type: ignore[assignment]
        return sock


__all__ = [
    "AsyncDatagramSocket",
    "AsyncSocket",
    "LENGTH_PREFIX_SIZE",
    "MAX_DATAGRAM_SIZE",
    "MAX_FDS_PER_MESSAGE",
    "encode_length",
]
