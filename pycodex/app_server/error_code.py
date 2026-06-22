"""JSON-RPC error helpers ported from ``codex-app-server/src/error_code.rs``."""

from __future__ import annotations

from typing import Any

from pycodex.app_server_protocol import JSONRPCErrorError

INVALID_REQUEST_ERROR_CODE = -32600
METHOD_NOT_FOUND_ERROR_CODE = -32601
INVALID_PARAMS_ERROR_CODE = -32602
INTERNAL_ERROR_CODE = -32603
OVERLOADED_ERROR_CODE = -32001
INPUT_TOO_LARGE_ERROR_CODE = "input_too_large"


def invalid_request(message: Any) -> JSONRPCErrorError:
    return _error(INVALID_REQUEST_ERROR_CODE, message)


def method_not_found(message: Any) -> JSONRPCErrorError:
    return _error(METHOD_NOT_FOUND_ERROR_CODE, message)


def invalid_params(message: Any) -> JSONRPCErrorError:
    return _error(INVALID_PARAMS_ERROR_CODE, message)


def internal_error(message: Any) -> JSONRPCErrorError:
    return _error(INTERNAL_ERROR_CODE, message)


def _error(code: int, message: Any) -> JSONRPCErrorError:
    return JSONRPCErrorError(code=code, message=str(message), data=None)


__all__ = [
    "INPUT_TOO_LARGE_ERROR_CODE",
    "INTERNAL_ERROR_CODE",
    "INVALID_PARAMS_ERROR_CODE",
    "INVALID_REQUEST_ERROR_CODE",
    "METHOD_NOT_FOUND_ERROR_CODE",
    "OVERLOADED_ERROR_CODE",
    "internal_error",
    "invalid_params",
    "invalid_request",
    "method_not_found",
]
