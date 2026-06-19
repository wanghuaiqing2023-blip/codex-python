"""Filesystem request processor projection.

Ported from ``codex-app-server/src/request_processors/fs_processor.rs``.
The Rust module is a thin app-server bridge from protocol requests to the
local environment filesystem plus ``FsWatchManager``. Python keeps the same
boundary: concrete filesystem and watch implementations are injected by the
environment/watch managers.
"""

from __future__ import annotations

import base64
import binascii
import inspect
from collections.abc import Mapping
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server.fs_watch import FsWatchManager
from pycodex.app_server_protocol import (
    FsCopyParams,
    FsCopyResponse,
    FsCreateDirectoryParams,
    FsCreateDirectoryResponse,
    FsGetMetadataParams,
    FsGetMetadataResponse,
    FsReadDirectoryEntry,
    FsReadDirectoryParams,
    FsReadDirectoryResponse,
    FsReadFileParams,
    FsReadFileResponse,
    FsRemoveParams,
    FsRemoveResponse,
    FsUnwatchParams,
    FsUnwatchResponse,
    FsWatchParams,
    FsWatchResponse,
    FsWriteFileParams,
    FsWriteFileResponse,
    JSONRPCErrorError,
)

JsonValue = Any


class FsRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class FsRequestProcessor:
    def __init__(self, environment_manager: Any, fs_watch_manager: FsWatchManager) -> None:
        self.environment_manager = environment_manager
        self.fs_watch_manager = fs_watch_manager

    @classmethod
    def new(cls, environment_manager: Any, fs_watch_manager: FsWatchManager) -> "FsRequestProcessor":
        return cls(environment_manager, fs_watch_manager)

    def file_system(self) -> Any:
        environment = _optional_call(self.environment_manager, "try_local_environment")
        if environment is None:
            raise FsRequestProcessorError(internal_error("local filesystem is not configured"))
        filesystem = _optional_call(environment, "get_filesystem")
        if filesystem is None:
            filesystem = _get(environment, "filesystem", default=None)
        if filesystem is None:
            raise FsRequestProcessorError(internal_error("local filesystem is not configured"))
        return filesystem

    async def connection_closed(self, connection_id: Any) -> None:
        await self.fs_watch_manager.connection_closed(connection_id)

    async def read_file(self, params: FsReadFileParams | Mapping[str, JsonValue]) -> FsReadFileResponse:
        params = _params(FsReadFileParams, params)
        try:
            data = await _maybe_await(_call(self.file_system(), "read_file", params.path, None))
        except Exception as exc:
            raise FsRequestProcessorError(map_fs_error(exc)) from exc
        return FsReadFileResponse(data_base64=base64.b64encode(bytes(data)).decode("ascii"))

    async def write_file(self, params: FsWriteFileParams | Mapping[str, JsonValue]) -> FsWriteFileResponse:
        params = _params(FsWriteFileParams, params)
        try:
            data = base64.b64decode(params.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FsRequestProcessorError(
                invalid_request(f"fs/writeFile requires valid base64 dataBase64: {exc}")
            ) from exc
        try:
            await _maybe_await(_call(self.file_system(), "write_file", params.path, data, None))
        except Exception as exc:
            raise FsRequestProcessorError(map_fs_error(exc)) from exc
        return FsWriteFileResponse()

    async def create_directory(
        self,
        params: FsCreateDirectoryParams | Mapping[str, JsonValue],
    ) -> FsCreateDirectoryResponse:
        params = _params(FsCreateDirectoryParams, params)
        try:
            await _maybe_await(
                _call(
                    self.file_system(),
                    "create_directory",
                    params.path,
                    {"recursive": True if params.recursive is None else params.recursive},
                    None,
                )
            )
        except Exception as exc:
            raise FsRequestProcessorError(map_fs_error(exc)) from exc
        return FsCreateDirectoryResponse()

    async def get_metadata(
        self,
        params: FsGetMetadataParams | Mapping[str, JsonValue],
    ) -> FsGetMetadataResponse:
        params = _params(FsGetMetadataParams, params)
        try:
            metadata = await _maybe_await(_call(self.file_system(), "get_metadata", params.path, None))
        except Exception as exc:
            raise FsRequestProcessorError(map_fs_error(exc)) from exc
        return FsGetMetadataResponse(
            is_directory=bool(_get(metadata, "is_directory")),
            is_file=bool(_get(metadata, "is_file")),
            is_symlink=bool(_get(metadata, "is_symlink")),
            created_at_ms=int(_get(metadata, "created_at_ms")),
            modified_at_ms=int(_get(metadata, "modified_at_ms")),
        )

    async def read_directory(
        self,
        params: FsReadDirectoryParams | Mapping[str, JsonValue],
    ) -> FsReadDirectoryResponse:
        params = _params(FsReadDirectoryParams, params)
        try:
            entries = await _maybe_await(_call(self.file_system(), "read_directory", params.path, None))
        except Exception as exc:
            raise FsRequestProcessorError(map_fs_error(exc)) from exc
        return FsReadDirectoryResponse(
            entries=tuple(
                FsReadDirectoryEntry(
                    file_name=_get(entry, "file_name"),
                    is_directory=bool(_get(entry, "is_directory")),
                    is_file=bool(_get(entry, "is_file")),
                )
                for entry in entries
            )
        )

    async def remove(self, params: FsRemoveParams | Mapping[str, JsonValue]) -> FsRemoveResponse:
        params = _params(FsRemoveParams, params)
        try:
            await _maybe_await(
                _call(
                    self.file_system(),
                    "remove",
                    params.path,
                    {
                        "recursive": True if params.recursive is None else params.recursive,
                        "force": True if params.force is None else params.force,
                    },
                    None,
                )
            )
        except Exception as exc:
            raise FsRequestProcessorError(map_fs_error(exc)) from exc
        return FsRemoveResponse()

    async def copy(self, params: FsCopyParams | Mapping[str, JsonValue]) -> FsCopyResponse:
        params = _params(FsCopyParams, params)
        try:
            await _maybe_await(
                _call(
                    self.file_system(),
                    "copy",
                    params.source_path,
                    params.destination_path,
                    {"recursive": params.recursive},
                    None,
                )
            )
        except Exception as exc:
            raise FsRequestProcessorError(map_fs_error(exc)) from exc
        return FsCopyResponse()

    async def watch(self, connection_id: Any, params: FsWatchParams | Mapping[str, JsonValue]) -> FsWatchResponse:
        self.file_system()
        try:
            return await self.fs_watch_manager.watch(connection_id, params)
        except JSONRPCErrorError as exc:
            raise FsRequestProcessorError(exc) from exc

    async def unwatch(
        self,
        connection_id: Any,
        params: FsUnwatchParams | Mapping[str, JsonValue],
    ) -> FsUnwatchResponse:
        self.file_system()
        try:
            return await self.fs_watch_manager.unwatch(connection_id, params)
        except JSONRPCErrorError as exc:
            raise FsRequestProcessorError(exc) from exc


def map_fs_error(error: BaseException) -> JSONRPCErrorError:
    if _is_invalid_input(error):
        return invalid_request(str(error))
    return internal_error(str(error))


def _is_invalid_input(error: BaseException) -> bool:
    if isinstance(error, ValueError):
        return True
    errno = getattr(error, "errno", None)
    if errno == 22:
        return True
    kind = getattr(error, "kind", None)
    if callable(kind):
        kind = kind()
    return str(kind).lower() in {"invalidinput", "invalid_input", "invalid input"}


def _params(cls: type, value: Any) -> Any:
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping):
        return cls.from_mapping(value)
    return value


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _optional_call(obj: Any, name: str, *args: Any) -> Any:
    method = _callable(obj, name)
    if method is None:
        return None
    return method(*args)


def _call(obj: Any, name: str, *args: Any) -> Any:
    method = _callable(obj, name)
    if method is None:
        raise AttributeError(name)
    return method(*args)


def _callable(obj: Any, name: str) -> Any:
    value = getattr(obj, name, None)
    return value if callable(value) else None


def _get(obj: Any, name: str, *, default: Any = ...):
    if isinstance(obj, Mapping):
        if name in obj:
            return obj[name]
        camel = _snake_to_camel(name)
        if camel in obj:
            return obj[camel]
    elif hasattr(obj, name):
        return getattr(obj, name)
    if default is not ...:
        return default
    raise AttributeError(name)


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


__all__ = [
    "FsRequestProcessor",
    "FsRequestProcessorError",
    "map_fs_error",
]
