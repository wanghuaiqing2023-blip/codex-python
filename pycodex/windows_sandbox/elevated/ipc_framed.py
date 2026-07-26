"""Length-prefixed IPC protocol for the elevated command runner.

Rust owner: ``codex-windows-sandbox::elevated::ipc_framed``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
import io
import json
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol import PermissionProfile


MAX_FRAME_LEN = 8 * 1024 * 1024
IPC_PROTOCOL_VERSION = 2


class OutputStream(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True)
class SpawnRequest:
    command: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    permission_profile: PermissionProfile
    permission_profile_cwd: Path
    codex_home: Path
    real_codex_home: Path
    cap_sids: tuple[str, ...]
    timeout_ms: int | None
    tty: bool
    stdin_open: bool = False
    use_private_desktop: bool = False

    def to_mapping(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "cwd": str(self.cwd),
            "env": dict(self.env),
            "permission_profile": self.permission_profile.to_mapping(),
            "permission_profile_cwd": str(self.permission_profile_cwd),
            "codex_home": str(self.codex_home),
            "real_codex_home": str(self.real_codex_home),
            "cap_sids": list(self.cap_sids),
            "timeout_ms": self.timeout_ms,
            "tty": self.tty,
            "stdin_open": self.stdin_open,
            "use_private_desktop": self.use_private_desktop,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SpawnRequest":
        return cls(
            command=tuple(str(item) for item in value["command"]),
            cwd=Path(value["cwd"]),
            env={str(key): str(item) for key, item in value["env"].items()},
            permission_profile=PermissionProfile.from_mapping(value["permission_profile"]),
            permission_profile_cwd=Path(value["permission_profile_cwd"]),
            codex_home=Path(value["codex_home"]),
            real_codex_home=Path(value["real_codex_home"]),
            cap_sids=tuple(str(item) for item in value["cap_sids"]),
            timeout_ms=value.get("timeout_ms"),
            tty=bool(value["tty"]),
            stdin_open=bool(value.get("stdin_open", False)),
            use_private_desktop=bool(value.get("use_private_desktop", False)),
        )


@dataclass(frozen=True)
class SpawnReady:
    process_id: int


@dataclass(frozen=True)
class OutputPayload:
    data_b64: str
    stream: OutputStream


@dataclass(frozen=True)
class StdinPayload:
    data_b64: str


@dataclass(frozen=True)
class ResizePayload:
    rows: int
    cols: int


@dataclass(frozen=True)
class ExitPayload:
    exit_code: int
    timed_out: bool


@dataclass(frozen=True)
class ErrorPayload:
    message: str
    code: str


@dataclass(frozen=True)
class EmptyPayload:
    pass


Payload = (
    SpawnRequest
    | SpawnReady
    | OutputPayload
    | StdinPayload
    | ResizePayload
    | ExitPayload
    | ErrorPayload
    | EmptyPayload
)


@dataclass(frozen=True)
class Message:
    type: str
    payload: Payload

    @classmethod
    def spawn_request(cls, payload: SpawnRequest) -> "Message":
        return cls("spawn_request", payload)

    @classmethod
    def spawn_ready(cls, payload: SpawnReady) -> "Message":
        return cls("spawn_ready", payload)

    @classmethod
    def output(cls, payload: OutputPayload) -> "Message":
        return cls("output", payload)

    @classmethod
    def stdin(cls, payload: StdinPayload) -> "Message":
        return cls("stdin", payload)

    @classmethod
    def close_stdin(cls) -> "Message":
        return cls("close_stdin", EmptyPayload())

    @classmethod
    def resize(cls, payload: ResizePayload) -> "Message":
        return cls("resize", payload)

    @classmethod
    def exit(cls, payload: ExitPayload) -> "Message":
        return cls("exit", payload)

    @classmethod
    def error(cls, payload: ErrorPayload) -> "Message":
        return cls("error", payload)

    @classmethod
    def terminate(cls) -> "Message":
        return cls("terminate", EmptyPayload())

    def to_mapping(self) -> dict[str, Any]:
        payload = self.payload
        if isinstance(payload, SpawnRequest):
            value = payload.to_mapping()
        elif isinstance(payload, OutputPayload):
            value = {"data_b64": payload.data_b64, "stream": payload.stream.value}
        elif isinstance(payload, StdinPayload):
            value = {"data_b64": payload.data_b64}
        elif isinstance(payload, SpawnReady):
            value = {"process_id": payload.process_id}
        elif isinstance(payload, ResizePayload):
            value = {"rows": payload.rows, "cols": payload.cols}
        elif isinstance(payload, ExitPayload):
            value = {"exit_code": payload.exit_code, "timed_out": payload.timed_out}
        elif isinstance(payload, ErrorPayload):
            value = {"message": payload.message, "code": payload.code}
        else:
            value = {}
        return {"type": self.type, "payload": value}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Message":
        message_type = str(value["type"])
        payload = value.get("payload", {})
        if not isinstance(payload, Mapping):
            raise ValueError("runner message payload must contain an object")
        constructors = {
            "spawn_request": lambda: SpawnRequest.from_mapping(payload),
            "spawn_ready": lambda: SpawnReady(int(payload["process_id"])),
            "output": lambda: OutputPayload(
                str(payload["data_b64"]),
                OutputStream(str(payload["stream"])),
            ),
            "stdin": lambda: StdinPayload(str(payload["data_b64"])),
            "close_stdin": EmptyPayload,
            "resize": lambda: ResizePayload(int(payload["rows"]), int(payload["cols"])),
            "exit": lambda: ExitPayload(
                int(payload["exit_code"]),
                bool(payload["timed_out"]),
            ),
            "error": lambda: ErrorPayload(
                str(payload["message"]),
                str(payload["code"]),
            ),
            "terminate": EmptyPayload,
        }
        try:
            parsed = constructors[message_type]()
        except KeyError as exc:
            raise ValueError(f"unknown runner message type: {message_type}") from exc
        return cls(message_type, parsed)


@dataclass(frozen=True)
class FramedMessage:
    version: int
    message: Message

    def to_mapping(self) -> dict[str, Any]:
        return {"version": self.version, **self.message.to_mapping()}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FramedMessage":
        return cls(int(value["version"]), Message.from_mapping(value))


def encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_bytes(data: str) -> bytes:
    return base64.b64decode(data, validate=True)


def write_frame(stream: io.RawIOBase, message: FramedMessage) -> None:
    payload = json.dumps(
        message.to_mapping(),
        separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > MAX_FRAME_LEN:
        raise ValueError(f"frame too large: {len(payload)}")
    stream.write(len(payload).to_bytes(4, "little") + payload)
    stream.flush()


def read_frame(stream: io.RawIOBase) -> FramedMessage | None:
    length_bytes = stream.read(4)
    if not length_bytes or len(length_bytes) < 4:
        return None
    length = int.from_bytes(length_bytes, "little")
    if length > MAX_FRAME_LEN:
        raise ValueError(f"frame too large: {length}")
    payload = _read_exact(stream, length)
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("runner frame must contain an object")
    return FramedMessage.from_mapping(value)


def _read_exact(stream: io.RawIOBase, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("runner pipe closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


__all__ = [
    "EmptyPayload",
    "ErrorPayload",
    "ExitPayload",
    "FramedMessage",
    "IPC_PROTOCOL_VERSION",
    "Message",
    "OutputPayload",
    "OutputStream",
    "ResizePayload",
    "SpawnReady",
    "SpawnRequest",
    "StdinPayload",
    "decode_bytes",
    "encode_bytes",
    "read_frame",
    "write_frame",
]
