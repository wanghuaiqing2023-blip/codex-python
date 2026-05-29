"""request_permissions tool handler ported from Codex core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from pycodex.core.tool_context import FunctionToolOutput, ToolPayload
from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import (
    FileSystemPermissions,
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
        return payload.type in {"function", "tool_search"}

    def handle(
        self,
        invocation_or_payload: Any,
        *,
        call_id: str = "",
        cwd: str | Path | None = None,
    ) -> FunctionToolOutput:
        if not isinstance(call_id, str):
            raise TypeError("call_id must be a string")
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

        args = parse_request_permissions_arguments(arguments, cwd=cwd)
        args = normalize_request_permissions_args(args)
        if args.permissions.is_empty():
            raise FunctionCallError.respond_to_model(
                "request_permissions requires at least one permission"
            )

        response = None if self._request_callback is None else self._request_callback(call_id, args)
        if response is None:
            raise FunctionCallError.respond_to_model(
                "request_permissions was cancelled before receiving a response"
            )
        if not isinstance(response, RequestPermissionsResponse):
            response = RequestPermissionsResponse.from_mapping(response)
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
    return args


def _normalize_permission_path(path: Path, base: Path) -> Path:
    if not isinstance(path, Path):
        path = Path(path)
    if path.is_absolute():
        return path
    return base / path


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
    return RequestPermissionProfile(
        file_system=FileSystemPermissions(read=read, write=write)
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
