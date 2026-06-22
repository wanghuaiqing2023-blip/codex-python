"""Command execution protocol types ported from ``protocol/v2/command_exec.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

JsonValue = Any


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
class CommandExecTerminalSize:
    rows: int
    cols: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", _ensure_u16(self.rows, "rows"))
        object.__setattr__(self, "cols", _ensure_u16(self.cols, "cols"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CommandExecTerminalSize":
        _ensure_mapping(value, "CommandExecTerminalSize")
        return cls(rows=_ensure_u16(value["rows"], "rows"), cols=_ensure_u16(value["cols"], "cols"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"rows": self.rows, "cols": self.cols}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class CommandExecParams:
    command: tuple[str, ...]
    process_id: str | None = None
    tty: bool = False
    stream_stdin: bool = False
    stream_stdout_stderr: bool = False
    output_bytes_cap: int | None = None
    disable_output_cap: bool = False
    disable_timeout: bool = False
    timeout_ms: int | None = None
    cwd: Path | str | None = None
    env: Mapping[str, str | None] | None = None
    size: CommandExecTerminalSize | Mapping[str, JsonValue] | None = None
    sandbox_policy: JsonValue | None = None
    permission_profile: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _command_tuple(self.command, "command"))
        object.__setattr__(self, "process_id", _optional_str(self.process_id, "process_id"))
        object.__setattr__(self, "tty", _ensure_bool(self.tty, "tty"))
        object.__setattr__(self, "stream_stdin", _ensure_bool(self.stream_stdin, "stream_stdin"))
        object.__setattr__(
            self,
            "stream_stdout_stderr",
            _ensure_bool(self.stream_stdout_stderr, "stream_stdout_stderr"),
        )
        object.__setattr__(self, "output_bytes_cap", _optional_usize(self.output_bytes_cap, "output_bytes_cap"))
        object.__setattr__(self, "disable_output_cap", _ensure_bool(self.disable_output_cap, "disable_output_cap"))
        object.__setattr__(self, "disable_timeout", _ensure_bool(self.disable_timeout, "disable_timeout"))
        object.__setattr__(self, "timeout_ms", _optional_i64(self.timeout_ms, "timeout_ms"))
        object.__setattr__(self, "cwd", _optional_path(self.cwd, "cwd"))
        object.__setattr__(self, "env", _optional_env(self.env, "env"))
        object.__setattr__(self, "size", _optional_size(self.size, "size"))
        object.__setattr__(self, "sandbox_policy", _sandbox_policy_value(self.sandbox_policy, "sandbox_policy"))
        object.__setattr__(self, "permission_profile", _optional_str(self.permission_profile, "permission_profile"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CommandExecParams":
        _ensure_mapping(value, "CommandExecParams")
        return cls(
            command=_command_tuple(value["command"], "command"),
            process_id=_optional_str(_pick(value, "process_id", "processId"), "process_id"),
            tty=_ensure_bool(_pick(value, "tty", default=False), "tty"),
            stream_stdin=_ensure_bool(_pick(value, "stream_stdin", "streamStdin", default=False), "stream_stdin"),
            stream_stdout_stderr=_ensure_bool(
                _pick(value, "stream_stdout_stderr", "streamStdoutStderr", default=False),
                "stream_stdout_stderr",
            ),
            output_bytes_cap=_optional_usize(
                _pick(value, "output_bytes_cap", "outputBytesCap"),
                "output_bytes_cap",
            ),
            disable_output_cap=_ensure_bool(
                _pick(value, "disable_output_cap", "disableOutputCap", default=False),
                "disable_output_cap",
            ),
            disable_timeout=_ensure_bool(
                _pick(value, "disable_timeout", "disableTimeout", default=False),
                "disable_timeout",
            ),
            timeout_ms=_optional_i64(_pick(value, "timeout_ms", "timeoutMs"), "timeout_ms"),
            cwd=_optional_path(_pick(value, "cwd"), "cwd"),
            env=_optional_env(_pick(value, "env"), "env"),
            size=_optional_size(_pick(value, "size"), "size"),
            sandbox_policy=_sandbox_policy_value(_pick(value, "sandbox_policy", "sandboxPolicy"), "sandbox_policy"),
            permission_profile=_optional_str(
                _pick(value, "permission_profile", "permissionProfile"),
                "permission_profile",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "command": list(self.command),
            "process_id": self.process_id,
        }
        _put_true(result, "tty", self.tty)
        _put_true(result, "stream_stdin", self.stream_stdin)
        _put_true(result, "stream_stdout_stderr", self.stream_stdout_stderr)
        result["output_bytes_cap"] = self.output_bytes_cap
        _put_true(result, "disable_output_cap", self.disable_output_cap)
        _put_true(result, "disable_timeout", self.disable_timeout)
        result["timeout_ms"] = self.timeout_ms
        result["cwd"] = None if self.cwd is None else str(self.cwd)
        result["env"] = None if self.env is None else dict(self.env)
        result["size"] = None if self.size is None else self.size.to_mapping()
        result["sandbox_policy"] = _serialize_sandbox_policy(self.sandbox_policy, camel=False)
        result["permission_profile"] = self.permission_profile
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "command": list(self.command),
            "processId": self.process_id,
        }
        _put_true(result, "tty", self.tty)
        _put_true(result, "streamStdin", self.stream_stdin)
        _put_true(result, "streamStdoutStderr", self.stream_stdout_stderr)
        result["outputBytesCap"] = self.output_bytes_cap
        _put_true(result, "disableOutputCap", self.disable_output_cap)
        _put_true(result, "disableTimeout", self.disable_timeout)
        result["timeoutMs"] = self.timeout_ms
        result["cwd"] = None if self.cwd is None else str(self.cwd)
        result["env"] = None if self.env is None else dict(self.env)
        result["size"] = None if self.size is None else self.size.to_camel_mapping()
        result["sandboxPolicy"] = _serialize_sandbox_policy(self.sandbox_policy, camel=True)
        result["permissionProfile"] = self.permission_profile
        return result


@dataclass(frozen=True)
class CommandExecResponse:
    exit_code: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "exit_code", _ensure_i32(self.exit_code, "exit_code"))
        object.__setattr__(self, "stdout", _ensure_str(self.stdout, "stdout"))
        object.__setattr__(self, "stderr", _ensure_str(self.stderr, "stderr"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CommandExecResponse":
        _ensure_mapping(value, "CommandExecResponse")
        return cls(
            exit_code=_ensure_i32(_pick(value, "exit_code", "exitCode"), "exit_code"),
            stdout=_ensure_str(value["stdout"], "stdout"),
            stderr=_ensure_str(value["stderr"], "stderr"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"exit_code": self.exit_code, "stdout": self.stdout, "stderr": self.stderr}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"exitCode": self.exit_code, "stdout": self.stdout, "stderr": self.stderr}


@dataclass(frozen=True)
class CommandExecWriteParams:
    process_id: str
    delta_base64: str | None = None
    close_stdin: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_id", _ensure_str(self.process_id, "process_id"))
        object.__setattr__(self, "delta_base64", _optional_str(self.delta_base64, "delta_base64"))
        object.__setattr__(self, "close_stdin", _ensure_bool(self.close_stdin, "close_stdin"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CommandExecWriteParams":
        _ensure_mapping(value, "CommandExecWriteParams")
        return cls(
            process_id=_ensure_str(_pick(value, "process_id", "processId"), "process_id"),
            delta_base64=_optional_str(_pick(value, "delta_base64", "deltaBase64"), "delta_base64"),
            close_stdin=_ensure_bool(_pick(value, "close_stdin", "closeStdin", default=False), "close_stdin"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"process_id": self.process_id, "delta_base64": self.delta_base64}
        _put_true(result, "close_stdin", self.close_stdin)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"processId": self.process_id, "deltaBase64": self.delta_base64}
        _put_true(result, "closeStdin", self.close_stdin)
        return result


@dataclass(frozen=True)
class _EmptyResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None):
        if value is not None:
            _ensure_mapping(value, cls.__name__)
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class CommandExecWriteResponse(_EmptyResponse):
    pass


@dataclass(frozen=True)
class CommandExecTerminateParams:
    process_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_id", _ensure_str(self.process_id, "process_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CommandExecTerminateParams":
        _ensure_mapping(value, "CommandExecTerminateParams")
        return cls(process_id=_ensure_str(_pick(value, "process_id", "processId"), "process_id"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"process_id": self.process_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"processId": self.process_id}


@dataclass(frozen=True)
class CommandExecTerminateResponse(_EmptyResponse):
    pass


@dataclass(frozen=True)
class CommandExecResizeParams:
    process_id: str
    size: CommandExecTerminalSize | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_id", _ensure_str(self.process_id, "process_id"))
        object.__setattr__(self, "size", _size(self.size, "size"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CommandExecResizeParams":
        _ensure_mapping(value, "CommandExecResizeParams")
        return cls(
            process_id=_ensure_str(_pick(value, "process_id", "processId"), "process_id"),
            size=_size(value["size"], "size"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"process_id": self.process_id, "size": self.size.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"processId": self.process_id, "size": self.size.to_camel_mapping()}


@dataclass(frozen=True)
class CommandExecResizeResponse(_EmptyResponse):
    pass


class CommandExecOutputStream(_StringEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True)
class CommandExecOutputDeltaNotification:
    process_id: str
    stream: CommandExecOutputStream | str
    delta_base64: str
    cap_reached: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_id", _ensure_str(self.process_id, "process_id"))
        object.__setattr__(self, "stream", CommandExecOutputStream.parse(self.stream))
        object.__setattr__(self, "delta_base64", _ensure_str(self.delta_base64, "delta_base64"))
        object.__setattr__(self, "cap_reached", _ensure_bool(self.cap_reached, "cap_reached"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CommandExecOutputDeltaNotification":
        _ensure_mapping(value, "CommandExecOutputDeltaNotification")
        return cls(
            process_id=_ensure_str(_pick(value, "process_id", "processId"), "process_id"),
            stream=CommandExecOutputStream.parse(value["stream"]),
            delta_base64=_ensure_str(_pick(value, "delta_base64", "deltaBase64"), "delta_base64"),
            cap_reached=_ensure_bool(_pick(value, "cap_reached", "capReached"), "cap_reached"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "process_id": self.process_id,
            "stream": self.stream.value,
            "delta_base64": self.delta_base64,
            "cap_reached": self.cap_reached,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "processId": self.process_id,
            "stream": self.stream.value,
            "deltaBase64": self.delta_base64,
            "capReached": self.cap_reached,
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


def _optional_usize(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    return _ensure_usize(value, field_name)


def _optional_i64(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    return _ensure_i64(value, field_name)


def _optional_path(value: JsonValue, field_name: str) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError(f"{field_name} must be a path string or Path")


def _command_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result = tuple(_ensure_str(item, f"{field_name} item") for item in value)
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


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


def _size(value: JsonValue, field_name: str) -> CommandExecTerminalSize:
    if isinstance(value, CommandExecTerminalSize):
        return value
    if isinstance(value, Mapping):
        return CommandExecTerminalSize.from_mapping(value)
    raise TypeError(f"{field_name} must be CommandExecTerminalSize or mapping")


def _optional_size(value: JsonValue, field_name: str) -> CommandExecTerminalSize | None:
    if value is None:
        return None
    return _size(value, field_name)


def _sandbox_policy_value(value: JsonValue, field_name: str) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_mapping") or hasattr(value, "to_camel_mapping"):
        return value
    raise TypeError(f"{field_name} must be a SandboxPolicy-compatible mapping")


def _serialize_sandbox_policy(value: JsonValue, *, camel: bool) -> JsonValue:
    if value is None:
        return None
    if camel and hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _put_true(result: dict[str, JsonValue], key: str, value: bool) -> None:
    if value:
        result[key] = value


__all__ = [
    "CommandExecOutputDeltaNotification",
    "CommandExecOutputStream",
    "CommandExecParams",
    "CommandExecResizeParams",
    "CommandExecResizeResponse",
    "CommandExecResponse",
    "CommandExecTerminalSize",
    "CommandExecTerminateParams",
    "CommandExecTerminateResponse",
    "CommandExecWriteParams",
    "CommandExecWriteResponse",
]
