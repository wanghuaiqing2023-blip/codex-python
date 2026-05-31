"""request_permissions tool handler ported from Codex core."""

from __future__ import annotations

import json
import inspect
from pathlib import Path
from typing import Any, Callable

from pycodex.core.handler_utils import normalize_request_permissions_response
from pycodex.core.tool_context import FunctionToolOutput, ToolPayload
from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import (
    FileSystemPermissions,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    NetworkPermissions,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
    ToolName,
)

JsonValue = Any

REQUEST_PERMISSIONS_TOOL_NAME = "request_permissions"

RequestPermissionsCallback = Callable[
    [str, RequestPermissionsArgs],
    RequestPermissionsResponse | dict[str, JsonValue] | None,
]


def request_permissions_tool_description() -> str:
    return (
        "Request additional filesystem or network permissions from the user and wait for the client "
        "to grant a subset of the requested permission profile. Granted permissions apply automatically "
        "to later shell-like commands in the current turn, or for the rest of the session if the client "
        "approves them at session scope."
    )


def create_request_permissions_tool(description: str) -> dict[str, JsonValue]:
    if not isinstance(description, str):
        raise TypeError("description must be a string")
    return {
        "type": "function",
        "name": REQUEST_PERMISSIONS_TOOL_NAME,
        "description": description,
        "strict": False,
        "defer_loading": None,
        "output_schema": None,
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional short explanation for why additional permissions are needed.",
                },
                "permissions": _permission_profile_schema(),
            },
            "required": ["permissions"],
            "additionalProperties": False,
        },
    }


class RequestPermissionsHandler:
    def __init__(self, request_callback: RequestPermissionsCallback | None = None) -> None:
        if request_callback is not None and not callable(request_callback):
            raise TypeError("request_callback must be callable or None")
        self._request_callback = request_callback

    def tool_name(self) -> ToolName:
        return ToolName.plain(REQUEST_PERMISSIONS_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_request_permissions_tool(request_permissions_tool_description())

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type == "function"

    def handle(
        self,
        invocation_or_payload: Any,
        *,
        call_id: str = "",
        cwd: str | Path | None = None,
    ) -> FunctionToolOutput | Any:
        if not isinstance(call_id, str):
            raise TypeError("call_id must be a string")
        invocation_call_id = getattr(invocation_or_payload, "call_id", None)
        if call_id == "" and isinstance(invocation_call_id, str):
            call_id = invocation_call_id
        effective_cwd = cwd
        if effective_cwd is None:
            turn = getattr(invocation_or_payload, "turn", None)
            effective_cwd = getattr(turn, "cwd", None)
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model(
                "request_permissions handler received unsupported payload"
            )
        arguments = payload.arguments
        if arguments is None:
            raise FunctionCallError.respond_to_model(
                "request_permissions handler received unsupported payload"
            )

        args = parse_request_permissions_arguments(arguments, cwd=effective_cwd)
        args = normalize_request_permissions_args(args)
        if args.permissions.is_empty():
            raise FunctionCallError.respond_to_model(
                "request_permissions requires at least one permission"
            )

        response = None
        if self._request_callback is not None:
            response = self._request_callback(call_id, args)
        else:
            session = getattr(invocation_or_payload, "session", None)
            requester = getattr(session, "request_permissions_for_cwd", None)
            if callable(requester):
                response = requester(
                    getattr(invocation_or_payload, "turn", None),
                    call_id,
                    args,
                    effective_cwd,
                    getattr(invocation_or_payload, "cancellation_token", None),
                )
        if inspect.isawaitable(response):
            return _await_request_permissions_response(response, args, effective_cwd)
        if response is None:
            raise _request_permissions_cancelled_error()
        return _request_permissions_output(response, args, effective_cwd)


async def _await_request_permissions_response(
    response: Any,
    args: RequestPermissionsArgs,
    cwd: str | Path | None,
) -> FunctionToolOutput:
    response = await response
    if response is None:
        raise _request_permissions_cancelled_error()
    return _request_permissions_output(response, args, cwd)


def _request_permissions_cancelled_error() -> FunctionCallError:
    return FunctionCallError.respond_to_model(
        "request_permissions was cancelled before receiving a response"
    )


def _request_permissions_output(
    response: RequestPermissionsResponse | dict[str, JsonValue],
    args: RequestPermissionsArgs,
    cwd: str | Path | None,
) -> FunctionToolOutput:
    if not isinstance(args, RequestPermissionsArgs):
        raise TypeError("args must be RequestPermissionsArgs")
    if not isinstance(response, RequestPermissionsResponse):
        response = RequestPermissionsResponse.from_mapping(response)
    response = normalize_request_permissions_response(
        args.permissions,
        response,
        Path(cwd) if cwd is not None else Path.cwd(),
    )
    content = json.dumps(response.to_mapping(), separators=(",", ":"))
    return FunctionToolOutput.from_text(content, True)


def parse_request_permissions_arguments(
    arguments: str,
    *,
    cwd: str | Path | None = None,
) -> RequestPermissionsArgs:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        decoded = json.loads(arguments)
        args = RequestPermissionsArgs.from_mapping(decoded)
        return normalize_request_permission_paths(args, cwd=cwd)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse function arguments: {err}"
        ) from err


def normalize_request_permission_paths(
    args: RequestPermissionsArgs,
    *,
    cwd: str | Path | None = None,
) -> RequestPermissionsArgs:
    if not isinstance(args, RequestPermissionsArgs):
        raise TypeError("args must be RequestPermissionsArgs")
    if cwd is None:
        return args
    base = Path(cwd)
    if not base.is_absolute():
        raise ValueError("cwd must be an absolute path")
    permissions = args.permissions
    file_system = permissions.file_system
    if file_system is None:
        return args
    normalized_entries: list[FileSystemSandboxEntry] = []
    changed = False
    for entry in file_system.entries:
        if entry.path.type != "path" or entry.path.path is None:
            normalized_entries.append(entry)
            continue
        normalized_path = _normalize_permission_path(entry.path.path, base)
        changed = changed or normalized_path != entry.path.path
        normalized_entries.append(
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(normalized_path),
                entry.access,
            )
        )
    if not changed:
        return args
    normalized_file_system = FileSystemPermissions(
        entries=tuple(normalized_entries),
        glob_scan_max_depth=file_system.glob_scan_max_depth,
    )
    normalized_permissions = RequestPermissionProfile(
        network=permissions.network,
        file_system=normalized_file_system,
    )
    return RequestPermissionsArgs(
        permissions=normalized_permissions,
        reason=args.reason,
    )


def normalize_request_permissions_args(args: RequestPermissionsArgs) -> RequestPermissionsArgs:
    if not isinstance(args, RequestPermissionsArgs):
        raise TypeError("args must be RequestPermissionsArgs")
    permissions = args.permissions
    network = permissions.network
    if network is not None and network.is_empty():
        network = None

    file_system = permissions.file_system
    if file_system is not None:
        entries: list[FileSystemSandboxEntry] = []
        for entry in file_system.entries:
            if entry.path.type == "glob_pattern" and entry.access is not FileSystemAccessMode.DENY:
                raise FunctionCallError.respond_to_model(
                    "glob file system permissions only support deny-read entries"
                )
            normalized_entry = _normalize_additional_permission_entry(entry)
            if normalized_entry not in entries:
                entries.append(normalized_entry)
        normalized_file_system = FileSystemPermissions(
            entries=tuple(entries),
            glob_scan_max_depth=file_system.glob_scan_max_depth,
        )
        file_system = None if normalized_file_system.is_empty() else normalized_file_system

    normalized_permissions = RequestPermissionProfile(network=network, file_system=file_system)
    if normalized_permissions == permissions:
        return args
    return RequestPermissionsArgs(permissions=normalized_permissions, reason=args.reason)


def _normalize_permission_path(path: Path, base: Path) -> Path:
    if not isinstance(path, Path):
        path = Path(path)
    if path.is_absolute():
        return path
    return base / path


def _normalize_additional_permission_entry(entry: FileSystemSandboxEntry) -> FileSystemSandboxEntry:
    if entry.path.type != "path" or entry.path.path is None:
        return entry
    normalized_path = _canonicalize_preserving_nested_symlinks(entry.path.path)
    if normalized_path == entry.path.path:
        return entry
    return FileSystemSandboxEntry(FileSystemPath.explicit_path(normalized_path), entry.access)


def _canonicalize_preserving_nested_symlinks(path: Path) -> Path:
    if not path.is_absolute() or _has_nested_symlink_ancestor(path):
        return path
    try:
        return path.resolve(strict=False)
    except OSError:
        return path


def _has_nested_symlink_ancestor(path: Path) -> bool:
    for ancestor in (path, *path.parents):
        try:
            is_symlink = ancestor.is_symlink()
        except OSError:
            continue
        if is_symlink and ancestor.parent.parent != ancestor.parent:
            return True
    return False


def _permission_profile_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "network": {
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "Set to true to request network access.",
                    }
                },
                "additionalProperties": False,
            },
            "file_system": {
                "type": "object",
                "properties": {
                    "read": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths to grant read access to.",
                    },
                    "write": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths to grant write access to.",
                    },
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def request_profile_with_network() -> RequestPermissionProfile:
    return RequestPermissionProfile(network=NetworkPermissions(enabled=True))


def request_profile_with_file_system(
    *,
    read: tuple[str, ...] = (),
    write: tuple[str, ...] = (),
) -> RequestPermissionProfile:
    entries = tuple(
        FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.READ)
        for path in read
    ) + tuple(
        FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.WRITE)
        for path in write
    )
    return RequestPermissionProfile(
        file_system=FileSystemPermissions(entries=entries)
    )


__all__ = [
    "REQUEST_PERMISSIONS_TOOL_NAME",
    "RequestPermissionsCallback",
    "RequestPermissionsHandler",
    "create_request_permissions_tool",
    "normalize_request_permission_paths",
    "normalize_request_permissions_args",
    "parse_request_permissions_arguments",
    "request_permissions_tool_description",
    "request_profile_with_file_system",
    "request_profile_with_network",
]
