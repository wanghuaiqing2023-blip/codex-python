"""Lite JSON-RPC envelope types ported from ``jsonrpc_lite.rs``.

Rust keeps these messages deliberately lighter than JSON-RPC 2.0: app-server
messages neither require nor emit a top-level ``jsonrpc: "2.0"`` field.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import RequestId

JsonValue = Any

JSONRPC_VERSION = "2.0"
Result = JsonValue


@dataclass(frozen=True)
class JSONRPCRequest:
    id: RequestId | str | int
    method: str
    params: JsonValue | None = None
    trace: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", RequestId.from_value(self.id))
        object.__setattr__(self, "method", _ensure_str(self.method, "method"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "JSONRPCRequest":
        data = _mapping(value, "JSONRPCRequest")
        return cls(
            id=RequestId.from_value(data["id"]),
            method=_ensure_str(data["method"], "method"),
            params=copy.deepcopy(data["params"]) if "params" in data else None,
            trace=copy.deepcopy(data["trace"]) if "trace" in data else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"id": self.id.to_json(), "method": self.method}
        _put_optional(result, "params", self.params)
        _put_optional(result, "trace", self.trace)
        return result


@dataclass(frozen=True)
class JSONRPCNotification:
    method: str
    params: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _ensure_str(self.method, "method"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "JSONRPCNotification":
        data = _mapping(value, "JSONRPCNotification")
        return cls(
            method=_ensure_str(data["method"], "method"),
            params=copy.deepcopy(data["params"]) if "params" in data else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"method": self.method}
        _put_optional(result, "params", self.params)
        return result


@dataclass(frozen=True)
class JSONRPCResponse:
    id: RequestId | str | int
    result: Result

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", RequestId.from_value(self.id))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "JSONRPCResponse":
        data = _mapping(value, "JSONRPCResponse")
        return cls(id=RequestId.from_value(data["id"]), result=copy.deepcopy(data["result"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id.to_json(), "result": copy.deepcopy(self.result)}


@dataclass(frozen=True)
class JSONRPCErrorError:
    code: int
    message: str
    data: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _ensure_i64(self.code, "code"))
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "JSONRPCErrorError":
        data = _mapping(value, "JSONRPCErrorError")
        return cls(
            code=_ensure_i64(data["code"], "code"),
            message=_ensure_str(data["message"], "message"),
            data=copy.deepcopy(data["data"]) if "data" in data else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"code": self.code, "message": self.message}
        _put_optional(result, "data", self.data)
        return result


@dataclass(frozen=True)
class JSONRPCError:
    error: JSONRPCErrorError | Mapping[str, JsonValue]
    id: RequestId | str | int

    def __post_init__(self) -> None:
        if isinstance(self.error, Mapping):
            object.__setattr__(self, "error", JSONRPCErrorError.from_mapping(self.error))
        elif not isinstance(self.error, JSONRPCErrorError):
            raise TypeError("error must be a JSONRPCErrorError or mapping")
        object.__setattr__(self, "id", RequestId.from_value(self.id))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "JSONRPCError":
        data = _mapping(value, "JSONRPCError")
        return cls(error=JSONRPCErrorError.from_mapping(data["error"]), id=RequestId.from_value(data["id"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"error": self.error.to_mapping(), "id": self.id.to_json()}


@dataclass(frozen=True)
class JSONRPCMessage:
    value: JSONRPCRequest | JSONRPCNotification | JSONRPCResponse | JSONRPCError

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "JSONRPCMessage":
        data = _mapping(value, "JSONRPCMessage")
        has_method = "method" in data
        has_id = "id" in data
        if has_method and has_id:
            return cls(JSONRPCRequest.from_mapping(data))
        if has_method:
            return cls(JSONRPCNotification.from_mapping(data))
        if "error" in data and has_id:
            return cls(JSONRPCError.from_mapping(data))
        if "result" in data and has_id:
            return cls(JSONRPCResponse.from_mapping(data))
        raise ValueError("mapping is not a lite JSON-RPC request, notification, response, or error")

    def to_mapping(self) -> dict[str, JsonValue]:
        return self.value.to_mapping()

    @property
    def kind(self) -> str:
        if isinstance(self.value, JSONRPCRequest):
            return "request"
        if isinstance(self.value, JSONRPCNotification):
            return "notification"
        if isinstance(self.value, JSONRPCResponse):
            return "response"
        return "error"


def _put_optional(result: dict[str, JsonValue], key: str, value: JsonValue | None) -> None:
    if value is not None:
        result[key] = copy.deepcopy(value)


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


_I64_MIN = -(2**63)
_I64_MAX = 2**63 - 1


def _ensure_i64(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if not _I64_MIN <= value <= _I64_MAX:
        raise ValueError(f"{field_name} must fit in i64")
    return value


__all__ = [
    "JSONRPC_VERSION",
    "JSONRPCError",
    "JSONRPCErrorError",
    "JSONRPCMessage",
    "JSONRPCNotification",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "RequestId",
    "Result",
]
