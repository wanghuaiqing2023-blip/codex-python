"""Cloud requirements loader helpers ported from ``codex-config``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

ConfigRequirementsToml = dict[str, Any]
CloudRequirementsFactory = (
    Awaitable[ConfigRequirementsToml | None]
    | Callable[[], Awaitable[ConfigRequirementsToml | None] | ConfigRequirementsToml | None]
)


class CloudRequirementsLoadErrorCode(str, Enum):
    AUTH = "auth"
    TIMEOUT = "timeout"
    PARSE = "parse"
    REQUEST_FAILED = "request_failed"
    INTERNAL = "internal"


@dataclass(frozen=True)
class CloudRequirementsLoadError(Exception):
    code_value: CloudRequirementsLoadErrorCode
    message: str
    status_code_value: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code_value, CloudRequirementsLoadErrorCode):
            object.__setattr__(self, "code_value", CloudRequirementsLoadErrorCode(str(self.code_value)))
        if self.status_code_value is not None and not isinstance(self.status_code_value, int):
            raise TypeError("status_code must be an int or None")

    @classmethod
    def new(
        cls,
        code: CloudRequirementsLoadErrorCode | str,
        status_code: int | None,
        message: str,
    ) -> "CloudRequirementsLoadError":
        error_code = (
            code if isinstance(code, CloudRequirementsLoadErrorCode) else CloudRequirementsLoadErrorCode(str(code))
        )
        return cls(error_code, str(message), status_code)

    def code(self) -> CloudRequirementsLoadErrorCode:
        return self.code_value

    def status_code(self) -> int | None:
        return self.status_code_value

    def __str__(self) -> str:
        return self.message


class CloudRequirementsLoader:
    def __init__(self, future: CloudRequirementsFactory | None = None) -> None:
        self._future = future if future is not None else _default_future
        self._task: asyncio.Task[ConfigRequirementsToml | None] | None = None
        self._resolved = False
        self._result: ConfigRequirementsToml | None = None
        self._error: BaseException | None = None

    @classmethod
    def new(cls, future: CloudRequirementsFactory) -> "CloudRequirementsLoader":
        return cls(future)

    async def get(self) -> ConfigRequirementsToml | None:
        if self._resolved:
            if self._error is not None:
                raise self._error
            return self._clone_result(self._result)

        if self._task is None:
            self._task = asyncio.create_task(_call_future(self._future))

        try:
            result = await self._task
        except BaseException as exc:
            self._error = exc
            self._resolved = True
            raise

        self._result = self._clone_result(result)
        self._resolved = True
        return self._clone_result(result)

    def __repr__(self) -> str:
        return "CloudRequirementsLoader()"

    @staticmethod
    def _clone_result(result: ConfigRequirementsToml | None) -> ConfigRequirementsToml | None:
        if result is None:
            return None
        return dict(result)


async def _default_future() -> None:
    return None


async def _call_future(future: CloudRequirementsFactory) -> ConfigRequirementsToml | None:
    value = future() if callable(future) else future
    if isinstance(value, Awaitable):
        value = await value
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("cloud requirements loader must resolve to a mapping or None")
    return dict(value)


__all__ = [
    "CloudRequirementsLoadError",
    "CloudRequirementsLoadErrorCode",
    "CloudRequirementsLoader",
]
