"""Guardian approval request data contracts ported from ``codex-core``.

Rust source:
- ``codex/codex-rs/core/src/guardian/approval_request.rs``
- ``codex/codex-rs/core/src/guardian/mod.rs``
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol import (
    AdditionalPermissionProfile,
    GuardianCommandSource,
    NetworkApprovalProtocol,
    SandboxPermissions,
)
from pycodex.protocol.request_permissions import RequestPermissionProfile
from pycodex.core.guardian.prompt import (
    GUARDIAN_MAX_ACTION_STRING_TOKENS,
    guardian_truncate_text,
)

JsonValue = Any
TRUNCATION_TAG = "truncated"


def _string_tuple(values: object, label: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise TypeError(f"{label} must be a sequence of strings")
    items = tuple(values)
    if any(not isinstance(value, str) for value in items):
        raise TypeError(f"{label} must contain only strings")
    return items


def _path_json(value: Path | str) -> str:
    return Path(value).as_posix()


def _enum_json(value: object) -> JsonValue:
    return value.value if isinstance(value, Enum) else value


def _mapping_json(value: object) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Path):
        return _path_json(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, AdditionalPermissionProfile):
        return value.to_mapping()
    if isinstance(value, RequestPermissionProfile):
        return value.to_mapping()
    if isinstance(value, GuardianNetworkAccessTrigger):
        return value.to_json()
    if isinstance(value, GuardianMcpAnnotations):
        return value.to_json()
    if isinstance(value, Mapping):
        return {str(key): _mapping_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mapping_json(item) for item in value]
    return value


def _set_optional(target: dict[str, JsonValue], key: str, value: object) -> None:
    if value is not None:
        target[key] = _mapping_json(value)


def _non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be a non-empty string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string or None")
    return value


@dataclass(frozen=True)
class GuardianNetworkAccessTrigger:
    """Rust ``GuardianNetworkAccessTrigger`` for network approval requests."""

    call_id: str
    tool_name: str
    command: tuple[str, ...]
    cwd: Path
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None = None
    justification: str | None = None
    tty: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id:
            raise TypeError("call_id must be a non-empty string")
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise TypeError("tool_name must be a non-empty string")
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and not isinstance(
            self.additional_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")
        if self.tty is not None and not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool or None")

    def to_json(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "callId": self.call_id,
            "toolName": self.tool_name,
            "command": list(self.command),
            "cwd": _path_json(self.cwd),
            "sandboxPermissions": self.sandbox_permissions.value,
        }
        _set_optional(data, "additionalPermissions", self.additional_permissions)
        _set_optional(data, "justification", self.justification)
        _set_optional(data, "tty", self.tty)
        return data


@dataclass(frozen=True)
class GuardianMcpAnnotations:
    destructive_hint: bool | None = None
    open_world_hint: bool | None = None
    read_only_hint: bool | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("destructive_hint", self.destructive_hint),
            ("open_world_hint", self.open_world_hint),
            ("read_only_hint", self.read_only_hint),
        ):
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{label} must be a bool or None")

    def to_json(self) -> dict[str, bool]:
        data: dict[str, bool] = {}
        if self.destructive_hint is not None:
            data["destructive_hint"] = self.destructive_hint
        if self.open_world_hint is not None:
            data["open_world_hint"] = self.open_world_hint
        if self.read_only_hint is not None:
            data["read_only_hint"] = self.read_only_hint
        return data


@dataclass(frozen=True)
class GuardianApprovalRequest:
    kind: str
    data: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if self.kind not in {
            "shell",
            "exec_command",
            "execve",
            "apply_patch",
            "network_access",
            "mcp_tool_call",
            "request_permissions",
        }:
            raise ValueError(f"unknown guardian approval request kind: {self.kind}")
        if not isinstance(self.data, Mapping):
            raise TypeError("data must be a mapping")
        object.__setattr__(self, "data", dict(self.data))

    @classmethod
    def shell(
        cls,
        *,
        id: str,
        command: tuple[str, ...] | list[str],
        cwd: Path | str,
        sandbox_permissions: SandboxPermissions | str,
        additional_permissions: AdditionalPermissionProfile | None = None,
        justification: str | None = None,
    ) -> "GuardianApprovalRequest":
        return cls(
            "shell",
            {
                "id": _non_empty_string(id, "id"),
                "command": _string_tuple(command, "command"),
                "cwd": Path(cwd),
                "sandbox_permissions": SandboxPermissions(sandbox_permissions),
                "additional_permissions": additional_permissions,
                "justification": _optional_string(justification, "justification"),
            },
        )

    @classmethod
    def exec_command(
        cls,
        *,
        id: str,
        command: tuple[str, ...] | list[str],
        cwd: Path | str,
        sandbox_permissions: SandboxPermissions | str,
        tty: bool,
        additional_permissions: AdditionalPermissionProfile | None = None,
        justification: str | None = None,
    ) -> "GuardianApprovalRequest":
        if not isinstance(tty, bool):
            raise TypeError("tty must be a bool")
        return cls(
            "exec_command",
            {
                "id": _non_empty_string(id, "id"),
                "command": _string_tuple(command, "command"),
                "cwd": Path(cwd),
                "sandbox_permissions": SandboxPermissions(sandbox_permissions),
                "additional_permissions": additional_permissions,
                "justification": _optional_string(justification, "justification"),
                "tty": tty,
            },
        )

    @classmethod
    def execve(
        cls,
        *,
        id: str,
        source: GuardianCommandSource | str,
        program: str,
        argv: tuple[str, ...] | list[str],
        cwd: Path | str,
        additional_permissions: AdditionalPermissionProfile | None = None,
    ) -> "GuardianApprovalRequest":
        return cls(
            "execve",
            {
                "id": _non_empty_string(id, "id"),
                "source": GuardianCommandSource(source),
                "program": _non_empty_string(program, "program"),
                "argv": _string_tuple(argv, "argv"),
                "cwd": Path(cwd),
                "additional_permissions": additional_permissions,
            },
        )

    @classmethod
    def apply_patch(
        cls,
        *,
        id: str,
        cwd: Path | str,
        files: tuple[Path | str, ...] | list[Path | str],
        patch: str,
    ) -> "GuardianApprovalRequest":
        if not isinstance(patch, str):
            raise TypeError("patch must be a string")
        return cls(
            "apply_patch",
            {
                "id": _non_empty_string(id, "id"),
                "cwd": Path(cwd),
                "files": tuple(Path(file) for file in files),
                "patch": patch,
            },
        )

    @classmethod
    def network_access(
        cls,
        *,
        id: str,
        turn_id: str,
        target: str,
        host: str,
        protocol: NetworkApprovalProtocol | str,
        port: int,
        trigger: GuardianNetworkAccessTrigger | None = None,
    ) -> "GuardianApprovalRequest":
        if isinstance(port, bool) or not isinstance(port, int):
            raise TypeError("port must be an integer")
        if not 0 <= port <= 65535:
            raise ValueError("port must fit in u16")
        if trigger is not None and not isinstance(trigger, GuardianNetworkAccessTrigger):
            raise TypeError("trigger must be GuardianNetworkAccessTrigger or None")
        return cls(
            "network_access",
            {
                "id": _non_empty_string(id, "id"),
                "turn_id": _non_empty_string(turn_id, "turn_id"),
                "target": _non_empty_string(target, "target"),
                "host": _non_empty_string(host, "host"),
                "protocol": NetworkApprovalProtocol.parse(protocol) if isinstance(protocol, str) else protocol,
                "port": port,
                "trigger": trigger,
            },
        )

    @classmethod
    def request_permissions(
        cls,
        *,
        id: str,
        turn_id: str,
        permissions: RequestPermissionProfile,
        reason: str | None = None,
    ) -> "GuardianApprovalRequest":
        if not isinstance(permissions, RequestPermissionProfile):
            raise TypeError("permissions must be RequestPermissionProfile")
        return cls(
            "request_permissions",
            {
                "id": _non_empty_string(id, "id"),
                "turn_id": _non_empty_string(turn_id, "turn_id"),
                "reason": _optional_string(reason, "reason"),
                "permissions": permissions,
            },
        )

    @classmethod
    def mcp_tool_call(
        cls,
        *,
        id: str,
        server: str,
        tool_name: str,
        arguments: JsonValue | None = None,
        connector_id: str | None = None,
        connector_name: str | None = None,
        connector_description: str | None = None,
        tool_title: str | None = None,
        tool_description: str | None = None,
        annotations: GuardianMcpAnnotations | None = None,
    ) -> "GuardianApprovalRequest":
        if annotations is not None and not isinstance(annotations, GuardianMcpAnnotations):
            raise TypeError("annotations must be GuardianMcpAnnotations or None")
        return cls(
            "mcp_tool_call",
            {
                "id": _non_empty_string(id, "id"),
                "server": _non_empty_string(server, "server"),
                "tool_name": _non_empty_string(tool_name, "tool_name"),
                "arguments": arguments,
                "connector_id": _optional_string(connector_id, "connector_id"),
                "connector_name": _optional_string(connector_name, "connector_name"),
                "connector_description": _optional_string(connector_description, "connector_description"),
                "tool_title": _optional_string(tool_title, "tool_title"),
                "tool_description": _optional_string(tool_description, "tool_description"),
                "annotations": annotations,
            },
        )


@dataclass(frozen=True)
class FormattedGuardianAction:
    text: str
    truncated: bool


def guardian_approval_request_to_json(action: GuardianApprovalRequest) -> dict[str, JsonValue]:
    if not isinstance(action, GuardianApprovalRequest):
        raise TypeError("action must be GuardianApprovalRequest")
    data = action.data
    if action.kind == "shell":
        return _command_json("shell", data, tty=None)
    if action.kind == "exec_command":
        return _command_json("exec_command", data, tty=bool(data["tty"]))
    if action.kind == "execve":
        result: dict[str, JsonValue] = {
            "tool": _guardian_command_source_tool_name(data["source"]),
            "program": data["program"],
            "argv": list(data["argv"]),
            "cwd": _path_json(data["cwd"]),
        }
        _set_optional(result, "additional_permissions", data.get("additional_permissions"))
        return result
    if action.kind == "apply_patch":
        return {
            "tool": "apply_patch",
            "cwd": _path_json(data["cwd"]),
            "files": [_path_json(file) for file in data["files"]],
            "patch": data["patch"],
        }
    if action.kind == "network_access":
        result: dict[str, JsonValue] = {
            "tool": "network_access",
            "target": data["target"],
            "host": data["host"],
            "protocol": _enum_json(data["protocol"]),
            "port": data["port"],
        }
        _set_optional(result, "trigger", data.get("trigger"))
        return result
    if action.kind == "mcp_tool_call":
        result = {
            "tool": "mcp_tool_call",
            "server": data["server"],
            "tool_name": data["tool_name"],
        }
        for key in (
            "arguments",
            "connector_id",
            "connector_name",
            "connector_description",
            "tool_title",
            "tool_description",
            "annotations",
        ):
            _set_optional(result, key, data.get(key))
        return result
    if action.kind == "request_permissions":
        result = {
            "tool": "request_permissions",
            "turn_id": data["turn_id"],
            "permissions": _mapping_json(data["permissions"]),
        }
        _set_optional(result, "reason", data.get("reason"))
        return result
    raise AssertionError("unreachable guardian approval request kind")


def _command_json(tool: str, data: Mapping[str, JsonValue], *, tty: bool | None) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {
        "tool": tool,
        "command": list(data["command"]),
        "cwd": _path_json(data["cwd"]),
        "sandbox_permissions": _enum_json(data["sandbox_permissions"]),
    }
    _set_optional(result, "additional_permissions", data.get("additional_permissions"))
    _set_optional(result, "justification", data.get("justification"))
    _set_optional(result, "tty", tty)
    return result


def _guardian_command_source_tool_name(source: object) -> str:
    parsed = GuardianCommandSource(source)
    if parsed == GuardianCommandSource.SHELL:
        return "shell"
    if parsed == GuardianCommandSource.UNIFIED_EXEC:
        return "exec_command"
    raise AssertionError("unreachable guardian command source")


def guardian_assessment_action(action: GuardianApprovalRequest) -> dict[str, JsonValue]:
    if not isinstance(action, GuardianApprovalRequest):
        raise TypeError("action must be GuardianApprovalRequest")
    data = action.data
    if action.kind == "shell":
        return {
            "type": "command",
            "source": "shell",
            "command": shlex.join(data["command"]),
            "cwd": _path_json(data["cwd"]),
        }
    if action.kind == "exec_command":
        return {
            "type": "command",
            "source": "unified_exec",
            "command": shlex.join(data["command"]),
            "cwd": _path_json(data["cwd"]),
        }
    if action.kind == "execve":
        return {
            "type": "execve",
            "source": _enum_json(data["source"]),
            "program": data["program"],
            "argv": list(data["argv"]),
            "cwd": _path_json(data["cwd"]),
        }
    if action.kind == "apply_patch":
        return {
            "type": "apply_patch",
            "cwd": _path_json(data["cwd"]),
            "files": [_path_json(file) for file in data["files"]],
        }
    if action.kind == "network_access":
        return {
            "type": "network_access",
            "target": data["target"],
            "host": data["host"],
            "protocol": _enum_json(data["protocol"]),
            "port": data["port"],
        }
    if action.kind == "mcp_tool_call":
        return {
            "type": "mcp_tool_call",
            "server": data["server"],
            "tool_name": data["tool_name"],
            "connector_id": data.get("connector_id"),
            "connector_name": data.get("connector_name"),
            "tool_title": data.get("tool_title"),
        }
    if action.kind == "request_permissions":
        return {
            "type": "request_permissions",
            "reason": data.get("reason"),
            "permissions": _mapping_json(data["permissions"]),
        }
    raise AssertionError("unreachable guardian approval request kind")


def guardian_reviewed_action(action: GuardianApprovalRequest) -> dict[str, JsonValue]:
    if not isinstance(action, GuardianApprovalRequest):
        raise TypeError("action must be GuardianApprovalRequest")
    data = action.data
    if action.kind == "shell":
        return {
            "type": "shell",
            "sandbox_permissions": _enum_json(data["sandbox_permissions"]),
            "additional_permissions": _mapping_json(data.get("additional_permissions")),
        }
    if action.kind == "exec_command":
        return {
            "type": "unified_exec",
            "sandbox_permissions": _enum_json(data["sandbox_permissions"]),
            "additional_permissions": _mapping_json(data.get("additional_permissions")),
            "tty": data["tty"],
        }
    if action.kind == "execve":
        return {
            "type": "execve",
            "source": _enum_json(data["source"]),
            "program": data["program"],
            "additional_permissions": _mapping_json(data.get("additional_permissions")),
        }
    if action.kind == "apply_patch":
        return {"type": "apply_patch"}
    if action.kind == "network_access":
        return {
            "type": "network_access",
            "protocol": _enum_json(data["protocol"]),
            "port": data["port"],
        }
    if action.kind == "mcp_tool_call":
        return {
            "type": "mcp_tool_call",
            "server": data["server"],
            "tool_name": data["tool_name"],
            "connector_id": data.get("connector_id"),
            "connector_name": data.get("connector_name"),
            "tool_title": data.get("tool_title"),
        }
    if action.kind == "request_permissions":
        return {"type": "request_permissions"}
    raise AssertionError("unreachable guardian approval request kind")


def guardian_request_target_item_id(request: GuardianApprovalRequest) -> str | None:
    if not isinstance(request, GuardianApprovalRequest):
        raise TypeError("request must be GuardianApprovalRequest")
    if request.kind == "network_access":
        return None
    return str(request.data["id"])


def guardian_request_turn_id(request: GuardianApprovalRequest, default_turn_id: str) -> str:
    if not isinstance(request, GuardianApprovalRequest):
        raise TypeError("request must be GuardianApprovalRequest")
    if not isinstance(default_turn_id, str):
        raise TypeError("default_turn_id must be a string")
    if request.kind in {"network_access", "request_permissions"}:
        return str(request.data["turn_id"])
    return default_turn_id


def format_guardian_action_pretty(action: GuardianApprovalRequest) -> FormattedGuardianAction:
    value = guardian_approval_request_to_json(action)
    truncated_value, truncated = _truncate_guardian_action_value(value)
    return FormattedGuardianAction(
        json.dumps(truncated_value, indent=2, sort_keys=True, ensure_ascii=False),
        truncated,
    )


def _truncate_guardian_action_value(value: JsonValue) -> tuple[JsonValue, bool]:
    if isinstance(value, str):
        return guardian_truncate_text(value, GUARDIAN_MAX_ACTION_STRING_TOKENS)
    if isinstance(value, list):
        truncated = False
        values: list[JsonValue] = []
        for item in value:
            item, item_truncated = _truncate_guardian_action_value(item)
            truncated = truncated or item_truncated
            values.append(item)
        return values, truncated
    if isinstance(value, dict):
        truncated = False
        values: dict[str, JsonValue] = {}
        for key in sorted(value):
            item, item_truncated = _truncate_guardian_action_value(value[key])
            truncated = truncated or item_truncated
            values[key] = item
        return values, truncated
    return value, False


__all__ = [
    "FormattedGuardianAction",
    "GuardianApprovalRequest",
    "GuardianMcpAnnotations",
    "GuardianNetworkAccessTrigger",
    "format_guardian_action_pretty",
    "guardian_approval_request_to_json",
    "guardian_assessment_action",
    "guardian_request_target_item_id",
    "guardian_request_turn_id",
    "guardian_reviewed_action",
]
