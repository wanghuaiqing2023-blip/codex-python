"""Process protocol types ported from ``protocol/v2/process.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

JsonValue = Any
UNSET = object()


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


@dataclass(frozen=True)
class ProcessTerminalSize:
    rows: int
    cols: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", _ensure_u16(self.rows, "rows"))
        object.__setattr__(self, "cols", _ensure_u16(self.cols, "cols"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ProcessTerminalSize":
        _ensure_mapping(value, "ProcessTerminalSize")
        return cls(rows=_ensure_u16(value["rows"], "rows"), cols=_ensure_u16(value["cols"], "cols"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"rows": self.rows, "cols": self.cols}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class ProcessSpawnParams:
    command: tuple[str, ...]
    process_handle: str
    cwd: Path | str
    tty: bool = False
    stream_stdin: bool = False
    stream_stdout_stderr: bool = False
    output_bytes_cap: int | None | object = UNSET
    timeout_ms: int | None | object = UNSET
    env: Mapping[str, str | None] | None = None
    size: ProcessTerminalSize | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _command_tuple(self.command, "command"))
        object.__setattr__(self, "process_handle", _ensure_str(self.process_handle, "process_handle"))
        object.__setattr__(self, "cwd", _absolute_path(self.cwd, "cwd"))
        object.__setattr__(self, "tty", _ensure_bool(self.tty, "tty"))
        object.__setattr__(self, "stream_stdin", _ensure_bool(self.stream_stdin, "stream_stdin"))
        object.__setattr__(
            self,
            "stream_stdout_stderr",
            _ensure_bool(self.stream_stdout_stderr, "stream_stdout_stderr"),
        )
        object.__setattr__(
            self,
            "output_bytes_cap",
            _double_option_usize(self.output_bytes_cap, "output_bytes_cap"),
        )
        object.__setattr__(self, "timeout_ms", _double_option_i64(self.timeout_ms, "timeout_ms"))
        object.__setattr__(self, "env", _optional_env(self.env, "env"))
        object.__setattr__(self, "size", _optional_size(self.size, "size"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ProcessSpawnParams":
        _ensure_mapping(value, "ProcessSpawnParams")
        return cls(
            command=_command_tuple(value["command"], "command"),
            process_handle=_ensure_str(_pick(value, "process_handle", "processHandle"), "process_handle"),
            cwd=_absolute_path(value["cwd"], "cwd"),
            tty=_ensure_bool(_pick(value, "tty", default=False), "tty"),
            stream_stdin=_ensure_bool(_pick(value, "stream_stdin", "streamStdin", default=False), "stream_stdin"),
            stream_stdout_stderr=_ensure_bool(
                _pick(value, "stream_stdout_stderr", "streamStdoutStderr", default=False),
                "stream_stdout_stderr",
            ),
            output_bytes_cap=_double_option_usize(
                _pick(value, "output_bytes_cap", "outputBytesCap", default=UNSET),
                "output_bytes_cap",
            ),
            timeout_ms=_double_option_i64(_pick(value, "timeout_ms", "timeoutMs", default=UNSET), "timeout_ms"),
            env=_optional_env(_pick(value, "env"), "env"),
            size=_optional_size(_pick(value, "size"), "size"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "command": list(self.command),
            "process_handle": self.process_handle,
            "cwd": str(self.cwd),
        }
        _put_true(result, "tty", self.tty)
        _put_true(result, "stream_stdin", self.stream_stdin)
        _put_true(result, "stream_stdout_stderr", self.stream_stdout_stderr)
        _put_if_set(result, "output_bytes_cap", self.output_bytes_cap)
        _put_if_set(result, "timeout_ms", self.timeout_ms)
        _put_optional(result, "env", None if self.env is None else dict(self.env))
        _put_optional(result, "size", None if self.size is None else self.size.to_mapping())
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "command": list(self.command),
            "processHandle": self.process_handle,
            "cwd": str(self.cwd),
        }
        _put_true(result, "tty", self.tty)
        _put_true(result, "streamStdin", self.stream_stdin)
        _put_true(result, "streamStdoutStderr", self.stream_stdout_stderr)
        _put_if_set(result, "outputBytesCap", self.output_bytes_cap)
        _put_if_set(result, "timeoutMs", self.timeout_ms)
        _put_optional(result, "env", None if self.env is None else dict(self.env))
        _put_optional(result, "size", None if self.size is None else self.size.to_camel_mapping())
        return result


@dataclass(frozen=True)
class ProcessSpawnResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ProcessSpawnResponse":
        if value is not None:
            _ensure_mapping(value, "ProcessSpawnResponse")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class ProcessWriteStdinParams:
    process_handle: str
    delta_base64: str | None = None
    close_stdin: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_handle", _ensure_str(self.process_handle, "process_handle"))
        object.__setattr__(self, "delta_base64", _optional_str(self.delta_base64, "delta_base64"))
        object.__setattr__(self, "close_stdin", _ensure_bool(self.close_stdin, "close_stdin"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ProcessWriteStdinParams":
        _ensure_mapping(value, "ProcessWriteStdinParams")
        return cls(
            process_handle=_ensure_str(_pick(value, "process_handle", "processHandle"), "process_handle"),
            delta_base64=_optional_str(_pick(value, "delta_base64", "deltaBase64"), "delta_base64"),
            close_stdin=_ensure_bool(_pick(value, "close_stdin", "closeStdin", default=False), "close_stdin"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"process_handle": self.process_handle, "delta_base64": self.delta_base64}
        _put_true(result, "close_stdin", self.close_stdin)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"processHandle": self.process_handle, "deltaBase64": self.delta_base64}
        _put_true(result, "closeStdin", self.close_stdin)
        return result


@dataclass(frozen=True)
class ProcessWriteStdinResponse(ProcessSpawnResponse):
    pass


@dataclass(frozen=True)
class ProcessKillParams:
    process_handle: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_handle", _ensure_str(self.process_handle, "process_handle"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ProcessKillParams":
        _ensure_mapping(value, "ProcessKillParams")
        return cls(process_handle=_ensure_str(_pick(value, "process_handle", "processHandle"), "process_handle"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"process_handle": self.process_handle}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"processHandle": self.process_handle}


@dataclass(frozen=True)
class ProcessKillResponse(ProcessSpawnResponse):
    pass


@dataclass(frozen=True)
class ProcessResizePtyParams:
    process_handle: str
    size: ProcessTerminalSize | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_handle", _ensure_str(self.process_handle, "process_handle"))
        object.__setattr__(self, "size", _size(self.size, "size"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ProcessResizePtyParams":
        _ensure_mapping(value, "ProcessResizePtyParams")
        return cls(
            process_handle=_ensure_str(_pick(value, "process_handle", "processHandle"), "process_handle"),
            size=_size(value["size"], "size"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"process_handle": self.process_handle, "size": self.size.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"processHandle": self.process_handle, "size": self.size.to_camel_mapping()}


@dataclass(frozen=True)
class ProcessResizePtyResponse(ProcessSpawnResponse):
    pass


class ProcessOutputStream(_StringEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True)
class ProcessOutputDeltaNotification:
    process_handle: str
    stream: ProcessOutputStream | str
    delta_base64: str
    cap_reached: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_handle", _ensure_str(self.process_handle, "process_handle"))
        object.__setattr__(self, "stream", ProcessOutputStream.parse(self.stream))
        object.__setattr__(self, "delta_base64", _ensure_str(self.delta_base64, "delta_base64"))
        object.__setattr__(self, "cap_reached", _ensure_bool(self.cap_reached, "cap_reached"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ProcessOutputDeltaNotification":
        _ensure_mapping(value, "ProcessOutputDeltaNotification")
        return cls(
            process_handle=_ensure_str(_pick(value, "process_handle", "processHandle"), "process_handle"),
            stream=ProcessOutputStream.parse(value["stream"]),
            delta_base64=_ensure_str(_pick(value, "delta_base64", "deltaBase64"), "delta_base64"),
            cap_reached=_ensure_bool(_pick(value, "cap_reached", "capReached"), "cap_reached"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "process_handle": self.process_handle,
            "stream": self.stream.value,
            "delta_base64": self.delta_base64,
            "cap_reached": self.cap_reached,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "processHandle": self.process_handle,
            "stream": self.stream.value,
            "deltaBase64": self.delta_base64,
            "capReached": self.cap_reached,
        }


@dataclass(frozen=True)
class ProcessExitedNotification:
    process_handle: str
    exit_code: int
    stdout: str
    stdout_cap_reached: bool
    stderr: str
    stderr_cap_reached: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_handle", _ensure_str(self.process_handle, "process_handle"))
        object.__setattr__(self, "exit_code", _ensure_i32(self.exit_code, "exit_code"))
        object.__setattr__(self, "stdout", _ensure_str(self.stdout, "stdout"))
        object.__setattr__(self, "stdout_cap_reached", _ensure_bool(self.stdout_cap_reached, "stdout_cap_reached"))
        object.__setattr__(self, "stderr", _ensure_str(self.stderr, "stderr"))
        object.__setattr__(self, "stderr_cap_reached", _ensure_bool(self.stderr_cap_reached, "stderr_cap_reached"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ProcessExitedNotification":
        _ensure_mapping(value, "ProcessExitedNotification")
        return cls(
            process_handle=_ensure_str(_pick(value, "process_handle", "processHandle"), "process_handle"),
            exit_code=_ensure_i32(_pick(value, "exit_code", "exitCode"), "exit_code"),
            stdout=_ensure_str(value["stdout"], "stdout"),
            stdout_cap_reached=_ensure_bool(
                _pick(value, "stdout_cap_reached", "stdoutCapReached"),
                "stdout_cap_reached",
            ),
            stderr=_ensure_str(value["stderr"], "stderr"),
            stderr_cap_reached=_ensure_bool(
                _pick(value, "stderr_cap_reached", "stderrCapReached"),
                "stderr_cap_reached",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "process_handle": self.process_handle,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stdout_cap_reached": self.stdout_cap_reached,
            "stderr": self.stderr,
            "stderr_cap_reached": self.stderr_cap_reached,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "processHandle": self.process_handle,
            "exitCode": self.exit_code,
            "stdout": self.stdout,
            "stdoutCapReached": self.stdout_cap_reached,
            "stderr": self.stderr,
            "stderrCapReached": self.stderr_cap_reached,
        }


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _ensure_u16(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**16 - 1:
        raise TypeError(f"{field_name} must be an unsigned 16-bit integer")
    return value


def _ensure_i32(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < -(2**31) or value > 2**31 - 1:
        raise TypeError(f"{field_name} must be a signed 32-bit integer")
    return value


def _ensure_i64(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < -(2**63) or value > 2**63 - 1:
        raise TypeError(f"{field_name} must be a signed 64-bit integer")
    return value


def _ensure_usize(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _absolute_path(value: JsonValue, field_name: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str):
        path = Path(value)
    else:
        raise TypeError(f"{field_name} must be a path string or Path")
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return path


def _command_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result = tuple(_ensure_str(item, f"{field_name} item") for item in value)
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _double_option_usize(value: JsonValue, field_name: str) -> int | None | object:
    if value is UNSET or value is None:
        return value
    return _ensure_usize(value, field_name)


def _double_option_i64(value: JsonValue, field_name: str) -> int | None | object:
    if value is UNSET or value is None:
        return value
    return _ensure_i64(value, field_name)


def _optional_env(value: JsonValue, field_name: str) -> dict[str, str | None] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    result: dict[str, str | None] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be strings")
        result[key] = _optional_str(item, f"{field_name}[{key}]")
    return result


def _size(value: JsonValue, field_name: str) -> ProcessTerminalSize:
    if isinstance(value, ProcessTerminalSize):
        return value
    if isinstance(value, Mapping):
        return ProcessTerminalSize.from_mapping(value)
    raise TypeError(f"{field_name} must be ProcessTerminalSize or mapping")


def _optional_size(value: JsonValue, field_name: str) -> ProcessTerminalSize | None:
    if value is None:
        return None
    return _size(value, field_name)


def _put_true(result: dict[str, JsonValue], key: str, value: bool) -> None:
    if value:
        result[key] = value


def _put_optional(result: dict[str, JsonValue], key: str, value: JsonValue) -> None:
    if value is not None:
        result[key] = value


def _put_if_set(result: dict[str, JsonValue], key: str, value: JsonValue) -> None:
    if value is not UNSET:
        result[key] = value


__all__ = [
    "ProcessExitedNotification",
    "ProcessKillParams",
    "ProcessKillResponse",
    "ProcessOutputDeltaNotification",
    "ProcessOutputStream",
    "ProcessResizePtyParams",
    "ProcessResizePtyResponse",
    "ProcessSpawnParams",
    "ProcessSpawnResponse",
    "ProcessTerminalSize",
    "ProcessWriteStdinParams",
    "ProcessWriteStdinResponse",
    "UNSET",
]
