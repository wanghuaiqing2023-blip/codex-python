"""Python port of ``codex-hooks::schema``."""


from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import replace
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    HookCompletedEvent,
    HookEventName,
    HookExecutionMode,
    HookHandlerType,
    HookOutputEntry,
    HookOutputEntryKind,
    HookPromptFragment,
    HookRunStatus,
    HookRunSummary,
    HookScope,
    HookSource,
    HookTrustStatus,
    ThreadId,
    TruncationPolicyConfig,
)
from pycodex.config.hook_config import HookStateToml
from pycodex.config.hook_config import HookEventsToml
from pycodex.config.hook_config import HookHandlerConfig
from pycodex.config.hook_config import HooksFile
from pycodex.config.hook_config import MatcherGroup
from pycodex.config.fingerprint import version_for_toml
from pycodex.config.state import ConfigLayerStackOrdering
from pycodex.utils.output_truncation import approx_token_count
from pycodex.utils.output_truncation import formatted_truncate_text

from .events.common import SubagentHookContext

GENERATED_SCHEMA_DIR = "generated"


POST_TOOL_USE_INPUT_FIXTURE = "post-tool-use.command.input.schema.json"


POST_TOOL_USE_OUTPUT_FIXTURE = "post-tool-use.command.output.schema.json"


PERMISSION_REQUEST_INPUT_FIXTURE = "permission-request.command.input.schema.json"


PERMISSION_REQUEST_OUTPUT_FIXTURE = "permission-request.command.output.schema.json"


POST_COMPACT_INPUT_FIXTURE = "post-compact.command.input.schema.json"


POST_COMPACT_OUTPUT_FIXTURE = "post-compact.command.output.schema.json"


PRE_TOOL_USE_INPUT_FIXTURE = "pre-tool-use.command.input.schema.json"


PRE_TOOL_USE_OUTPUT_FIXTURE = "pre-tool-use.command.output.schema.json"


PRE_COMPACT_INPUT_FIXTURE = "pre-compact.command.input.schema.json"


PRE_COMPACT_OUTPUT_FIXTURE = "pre-compact.command.output.schema.json"


SESSION_START_INPUT_FIXTURE = "session-start.command.input.schema.json"


SESSION_START_OUTPUT_FIXTURE = "session-start.command.output.schema.json"


USER_PROMPT_SUBMIT_INPUT_FIXTURE = "user-prompt-submit.command.input.schema.json"


USER_PROMPT_SUBMIT_OUTPUT_FIXTURE = "user-prompt-submit.command.output.schema.json"


SUBAGENT_START_INPUT_FIXTURE = "subagent-start.command.input.schema.json"


SUBAGENT_START_OUTPUT_FIXTURE = "subagent-start.command.output.schema.json"


SUBAGENT_STOP_INPUT_FIXTURE = "subagent-stop.command.input.schema.json"


SUBAGENT_STOP_OUTPUT_FIXTURE = "subagent-stop.command.output.schema.json"


STOP_INPUT_FIXTURE = "stop.command.input.schema.json"


STOP_OUTPUT_FIXTURE = "stop.command.output.schema.json"


SCHEMA_FIXTURE_NAMES = (
    POST_TOOL_USE_INPUT_FIXTURE,
    POST_TOOL_USE_OUTPUT_FIXTURE,
    PERMISSION_REQUEST_INPUT_FIXTURE,
    PERMISSION_REQUEST_OUTPUT_FIXTURE,
    POST_COMPACT_INPUT_FIXTURE,
    POST_COMPACT_OUTPUT_FIXTURE,
    PRE_COMPACT_INPUT_FIXTURE,
    PRE_COMPACT_OUTPUT_FIXTURE,
    PRE_TOOL_USE_INPUT_FIXTURE,
    PRE_TOOL_USE_OUTPUT_FIXTURE,
    SESSION_START_INPUT_FIXTURE,
    SESSION_START_OUTPUT_FIXTURE,
    USER_PROMPT_SUBMIT_INPUT_FIXTURE,
    USER_PROMPT_SUBMIT_OUTPUT_FIXTURE,
    SUBAGENT_START_INPUT_FIXTURE,
    SUBAGENT_START_OUTPUT_FIXTURE,
    SUBAGENT_STOP_INPUT_FIXTURE,
    SUBAGENT_STOP_OUTPUT_FIXTURE,
    STOP_INPUT_FIXTURE,
    STOP_OUTPUT_FIXTURE,
)


HOOK_EVENT_NAME_WIRE_VALUES = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)


PERMISSION_MODE_SCHEMA_VALUES = (
    "default",
    "acceptEdits",
    "plan",
    "dontAsk",
    "bypassPermissions",
)


SESSION_START_SOURCE_SCHEMA_VALUES = ("startup", "resume", "clear", "compact")


COMPACTION_TRIGGER_SCHEMA_VALUES = ("manual", "auto")


@dataclass(frozen=True)
class SubagentCommandInputFields:
    agent_id: str | None = None
    agent_type: str | None = None

    @classmethod
    def from_context(
        cls,
        context: SubagentHookContext | None,
    ) -> "SubagentCommandInputFields":
        if context is None:
            return cls()
        return cls(context.agent_id, context.agent_type)

    def apply_to(self, payload: dict[str, Any]) -> None:
        if self.agent_id is not None:
            payload["agent_id"] = self.agent_id
        if self.agent_type is not None:
            payload["agent_type"] = self.agent_type


def nullable_string_from_path(path: Path | str | None) -> str | None:
    return None if path is None else str(path)


def nullable_string_from_string(value: str | None) -> str | None:
    return value


def canonicalize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: canonicalize_json(value[key])
            for key in sorted(value)
        }
    if isinstance(value, list):
        return [canonicalize_json(item) for item in value]
    return value


def _string_schema() -> dict[str, str]:
    return {"type": "string"}


def _boolean_schema(default: bool | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "boolean"}
    if default is not None:
        schema["default"] = default
    return schema


def _const_string_schema(value: str) -> dict[str, Any]:
    return {"const": value, "type": "string"}


def _enum_string_schema(values: Sequence[str]) -> dict[str, Any]:
    return {"enum": list(values), "type": "string"}


def _nullable_string_ref() -> dict[str, str]:
    return {"$ref": "#/definitions/NullableString"}


def _base_schema(title: str, properties: Mapping[str, Any], required: Sequence[str]) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "additionalProperties": False,
        "properties": dict(properties),
        "required": list(required),
        "title": title,
        "type": "object",
    }
    if any(value == _nullable_string_ref() for value in properties.values()):
        schema["definitions"] = {"NullableString": {"type": ["string", "null"]}}
    return schema


def _turn_id_schema() -> dict[str, str]:
    return {
        "description": "Codex extension: expose the active turn id to internal turn-scoped hooks.",
        "type": "string",
    }


def _common_input_properties(hook_event_name: str) -> dict[str, Any]:
    return {
        "session_id": _string_schema(),
        "turn_id": _turn_id_schema(),
        "transcript_path": _nullable_string_ref(),
        "cwd": _string_schema(),
        "hook_event_name": _const_string_schema(hook_event_name),
        "model": _string_schema(),
    }


def _with_optional_subagent(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": _string_schema(),
        "agent_type": _string_schema(),
        **properties,
    }


def _input_schema_for_fixture(fixture: str) -> dict[str, Any]:
    permission_mode = {"permission_mode": _enum_string_schema(PERMISSION_MODE_SCHEMA_VALUES)}
    common_required = ["cwd", "hook_event_name", "model", "session_id", "transcript_path", "turn_id"]
    if fixture == PRE_TOOL_USE_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PreToolUse"),
                **permission_mode,
                "tool_name": _string_schema(),
                "tool_input": True,
                "tool_use_id": _string_schema(),
            }
        )
        required = ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "tool_input", "tool_name", "tool_use_id", "transcript_path", "turn_id"]
        return _base_schema("pre-tool-use.command.input", props, required)
    if fixture == PERMISSION_REQUEST_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PermissionRequest"),
                **permission_mode,
                "tool_name": _string_schema(),
                "tool_input": True,
            }
        )
        required = ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "tool_input", "tool_name", "transcript_path", "turn_id"]
        return _base_schema("permission-request.command.input", props, required)
    if fixture == POST_TOOL_USE_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PostToolUse"),
                **permission_mode,
                "tool_name": _string_schema(),
                "tool_input": True,
                "tool_response": True,
                "tool_use_id": _string_schema(),
            }
        )
        required = ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "tool_input", "tool_name", "tool_response", "tool_use_id", "transcript_path", "turn_id"]
        return _base_schema("post-tool-use.command.input", props, required)
    if fixture == PRE_COMPACT_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PreCompact"),
                "trigger": _enum_string_schema(COMPACTION_TRIGGER_SCHEMA_VALUES),
            }
        )
        return _base_schema("pre-compact.command.input", props, [*common_required, "trigger"])
    if fixture == POST_COMPACT_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PostCompact"),
                "trigger": _enum_string_schema(COMPACTION_TRIGGER_SCHEMA_VALUES),
            }
        )
        return _base_schema("post-compact.command.input", props, [*common_required, "trigger"])
    if fixture == SESSION_START_INPUT_FIXTURE:
        props = {
            "session_id": _string_schema(),
            "transcript_path": _nullable_string_ref(),
            "cwd": _string_schema(),
            "hook_event_name": _const_string_schema("SessionStart"),
            "model": _string_schema(),
            **permission_mode,
            "source": _enum_string_schema(SESSION_START_SOURCE_SCHEMA_VALUES),
        }
        return _base_schema("session-start.command.input", props, ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "source", "transcript_path"])
    if fixture == USER_PROMPT_SUBMIT_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("UserPromptSubmit"),
                **permission_mode,
                "prompt": _string_schema(),
            }
        )
        return _base_schema("user-prompt-submit.command.input", props, [*common_required, "permission_mode", "prompt"])
    if fixture == SUBAGENT_START_INPUT_FIXTURE:
        props = {
            **_common_input_properties("SubagentStart"),
            **permission_mode,
            "agent_id": _string_schema(),
            "agent_type": _string_schema(),
        }
        return _base_schema("subagent-start.command.input", props, [*common_required, "permission_mode", "agent_id", "agent_type"])
    if fixture == STOP_INPUT_FIXTURE:
        props = {
            **_common_input_properties("Stop"),
            **permission_mode,
            "stop_hook_active": _boolean_schema(),
            "last_assistant_message": _nullable_string_ref(),
        }
        return _base_schema("stop.command.input", props, [*common_required, "permission_mode", "stop_hook_active", "last_assistant_message"])
    if fixture == SUBAGENT_STOP_INPUT_FIXTURE:
        props = {
            **_common_input_properties("SubagentStop"),
            "agent_transcript_path": _nullable_string_ref(),
            **permission_mode,
            "stop_hook_active": _boolean_schema(),
            "agent_id": _string_schema(),
            "agent_type": _string_schema(),
            "last_assistant_message": _nullable_string_ref(),
        }
        return _base_schema("subagent-stop.command.input", props, [*common_required, "agent_transcript_path", "permission_mode", "stop_hook_active", "agent_id", "agent_type", "last_assistant_message"])
    raise KeyError(f"unknown hook input schema fixture: {fixture}")


def _universal_output_properties() -> dict[str, Any]:
    return {
        "continue": _boolean_schema(True),
        "stopReason": {"default": None, "type": "string"},
        "suppressOutput": _boolean_schema(False),
        "systemMessage": {"default": None, "type": "string"},
    }


def _hook_event_name_wire_definition() -> dict[str, Any]:
    return {"enum": list(HOOK_EVENT_NAME_WIRE_VALUES), "type": "string"}


def _output_schema_for_fixture(fixture: str) -> dict[str, Any]:
    properties = _universal_output_properties()
    definitions: dict[str, Any] = {}
    title_by_fixture = {
        PRE_TOOL_USE_OUTPUT_FIXTURE: "pre-tool-use.command.output",
        POST_TOOL_USE_OUTPUT_FIXTURE: "post-tool-use.command.output",
        PERMISSION_REQUEST_OUTPUT_FIXTURE: "permission-request.command.output",
        PRE_COMPACT_OUTPUT_FIXTURE: "pre-compact.command.output",
        POST_COMPACT_OUTPUT_FIXTURE: "post-compact.command.output",
        SESSION_START_OUTPUT_FIXTURE: "session-start.command.output",
        USER_PROMPT_SUBMIT_OUTPUT_FIXTURE: "user-prompt-submit.command.output",
        SUBAGENT_START_OUTPUT_FIXTURE: "subagent-start.command.output",
        STOP_OUTPUT_FIXTURE: "stop.command.output",
        SUBAGENT_STOP_OUTPUT_FIXTURE: "subagent-stop.command.output",
    }
    if fixture not in title_by_fixture:
        raise KeyError(f"unknown hook output schema fixture: {fixture}")

    if fixture in {PRE_TOOL_USE_OUTPUT_FIXTURE, POST_TOOL_USE_OUTPUT_FIXTURE, USER_PROMPT_SUBMIT_OUTPUT_FIXTURE, STOP_OUTPUT_FIXTURE, SUBAGENT_STOP_OUTPUT_FIXTURE}:
        properties["decision"] = {"default": None, "type": "string"}
        properties["reason"] = {"default": None, "type": "string"}
    if fixture in {PRE_TOOL_USE_OUTPUT_FIXTURE, POST_TOOL_USE_OUTPUT_FIXTURE, PERMISSION_REQUEST_OUTPUT_FIXTURE, SESSION_START_OUTPUT_FIXTURE, USER_PROMPT_SUBMIT_OUTPUT_FIXTURE, SUBAGENT_START_OUTPUT_FIXTURE}:
        definitions["HookEventNameWire"] = _hook_event_name_wire_definition()
        properties["hookSpecificOutput"] = {"default": None}
    if fixture == PERMISSION_REQUEST_OUTPUT_FIXTURE:
        definitions["PermissionRequestBehaviorWire"] = {"enum": ["allow", "deny"], "type": "string"}
        definitions["PermissionRequestDecisionWire"] = {
            "additionalProperties": False,
            "properties": {
                "behavior": {"$ref": "#/definitions/PermissionRequestBehaviorWire"},
                "updatedInput": {"default": None},
                "updatedPermissions": {"default": None},
                "message": {"default": None, "type": "string"},
                "interrupt": _boolean_schema(False),
            },
            "required": ["behavior"],
            "type": "object",
        }
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "additionalProperties": False,
        "properties": properties,
        "title": title_by_fixture[fixture],
        "type": "object",
    }
    if definitions:
        schema["definitions"] = definitions
    return schema


def schema_for_fixture(fixture: str) -> dict[str, Any]:
    if fixture.endswith(".command.input.schema.json"):
        return _input_schema_for_fixture(fixture)
    if fixture.endswith(".command.output.schema.json"):
        return _output_schema_for_fixture(fixture)
    raise KeyError(f"unknown hook schema fixture: {fixture}")


def schema_json(fixture: str) -> str:
    value = canonicalize_json(schema_for_fixture(fixture))
    return json.dumps(value, indent=2, separators=(",", ": ")) + "\n"


def write_schema_fixtures(schema_root: Path | str) -> None:
    generated_dir = Path(schema_root) / GENERATED_SCHEMA_DIR
    if generated_dir.exists():
        for child in generated_dir.iterdir():
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        generated_dir.mkdir(parents=True, exist_ok=True)

    for fixture in SCHEMA_FIXTURE_NAMES:
        (generated_dir / fixture).write_text(schema_json(fixture), encoding="utf-8")
