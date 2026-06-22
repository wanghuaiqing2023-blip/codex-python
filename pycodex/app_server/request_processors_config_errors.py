"""Config-load error projection for app-server request processors.

Ported from ``codex-app-server/src/request_processors/config_errors.rs``.
The Rust helper wraps configuration load failures as JSON-RPC invalid-request
errors and adds structured ``cloudRequirements`` data when the IO error source
chain contains a ``CloudRequirementsLoadError``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.app_server.error_code import invalid_request
from pycodex.app_server_protocol import JSONRPCErrorError
from pycodex.config import CloudRequirementsLoadError, CloudRequirementsLoadErrorCode

JsonValue = Any


def cloud_requirements_load_error(err: BaseException) -> CloudRequirementsLoadError | Any | None:
    """Find the first cloud requirements error in a Python exception chain."""

    for source in _error_sources(err):
        if isinstance(source, CloudRequirementsLoadError) or _is_cloud_requirements_error(source):
            return source
    return None


def config_load_error(err: BaseException) -> JSONRPCErrorError:
    data = _cloud_requirements_data(cloud_requirements_load_error(err))
    error = invalid_request(f"failed to load configuration: {err}")
    return JSONRPCErrorError(code=error.code, message=error.message, data=data)


def _cloud_requirements_data(cloud_error: Any | None) -> dict[str, JsonValue] | None:
    if cloud_error is None:
        return None
    code = _cloud_error_code(cloud_error)
    data: dict[str, JsonValue] = {
        "reason": "cloudRequirements",
        "errorCode": _rust_debug_code(code),
        "detail": str(cloud_error),
    }
    status_code = _cloud_error_status_code(cloud_error)
    if status_code is not None:
        data["statusCode"] = status_code
    if _rust_debug_code(code) == "Auth":
        data["action"] = "relogin"
    return data


def _error_sources(err: BaseException) -> list[BaseException]:
    sources: list[BaseException] = []
    seen: set[int] = set()
    current = _first_source(err)
    while isinstance(current, BaseException) and id(current) not in seen:
        sources.append(current)
        seen.add(id(current))
        current = _first_source(current)
    return sources


def _first_source(err: BaseException) -> BaseException | None:
    for name in ("__cause__", "__context__", "source", "cause", "__wrapped__"):
        value = getattr(err, name, None)
        if callable(value):
            value = value()
        if isinstance(value, BaseException):
            return value
    return None


def _is_cloud_requirements_error(value: Any) -> bool:
    return callable(getattr(value, "code", None)) and callable(getattr(value, "status_code", None))


def _cloud_error_code(value: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get("code")
    code = getattr(value, "code", None)
    if callable(code):
        return code()
    return code


def _cloud_error_status_code(value: Any) -> int | None:
    status_code = getattr(value, "status_code", None)
    if callable(status_code):
        status_code = status_code()
    elif isinstance(value, Mapping):
        status_code = value.get("status_code")
    if status_code is None:
        return None
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        raise TypeError("cloud requirements status code must be an integer or None")
    return status_code


def _rust_debug_code(code: Any) -> str:
    if isinstance(code, CloudRequirementsLoadErrorCode):
        return _pascal_case_code(code.name)
    name = getattr(code, "name", None)
    if isinstance(name, str):
        return _pascal_case_code(name)
    value = getattr(code, "value", code)
    if isinstance(value, str):
        return _pascal_case_code(value)
    return str(value)


def _pascal_case_code(value: str) -> str:
    return "".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


__all__ = [
    "cloud_requirements_load_error",
    "config_load_error",
]
