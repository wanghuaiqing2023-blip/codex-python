"""Python port of ``codex-hooks::engine.schema_loader``."""


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

from ..schema import (
    PERMISSION_REQUEST_INPUT_FIXTURE,
    PERMISSION_REQUEST_OUTPUT_FIXTURE,
    POST_COMPACT_INPUT_FIXTURE,
    POST_COMPACT_OUTPUT_FIXTURE,
    POST_TOOL_USE_INPUT_FIXTURE,
    POST_TOOL_USE_OUTPUT_FIXTURE,
    PRE_COMPACT_INPUT_FIXTURE,
    PRE_COMPACT_OUTPUT_FIXTURE,
    PRE_TOOL_USE_INPUT_FIXTURE,
    PRE_TOOL_USE_OUTPUT_FIXTURE,
    SESSION_START_INPUT_FIXTURE,
    SESSION_START_OUTPUT_FIXTURE,
    STOP_INPUT_FIXTURE,
    STOP_OUTPUT_FIXTURE,
    SUBAGENT_START_INPUT_FIXTURE,
    SUBAGENT_START_OUTPUT_FIXTURE,
    SUBAGENT_STOP_INPUT_FIXTURE,
    SUBAGENT_STOP_OUTPUT_FIXTURE,
    USER_PROMPT_SUBMIT_INPUT_FIXTURE,
    USER_PROMPT_SUBMIT_OUTPUT_FIXTURE,
    schema_json,
)

@dataclass(frozen=True)
class GeneratedHookSchemas:
    post_tool_use_command_input: dict[str, Any]
    post_tool_use_command_output: dict[str, Any]
    permission_request_command_input: dict[str, Any]
    permission_request_command_output: dict[str, Any]
    post_compact_command_input: dict[str, Any]
    post_compact_command_output: dict[str, Any]
    pre_tool_use_command_input: dict[str, Any]
    pre_tool_use_command_output: dict[str, Any]
    pre_compact_command_input: dict[str, Any]
    pre_compact_command_output: dict[str, Any]
    session_start_command_input: dict[str, Any]
    session_start_command_output: dict[str, Any]
    subagent_start_command_input: dict[str, Any]
    subagent_start_command_output: dict[str, Any]
    subagent_stop_command_input: dict[str, Any]
    subagent_stop_command_output: dict[str, Any]
    user_prompt_submit_command_input: dict[str, Any]
    user_prompt_submit_command_output: dict[str, Any]
    stop_command_input: dict[str, Any]
    stop_command_output: dict[str, Any]


_GENERATED_HOOK_SCHEMAS: GeneratedHookSchemas | None = None


def parse_json_schema(name: str, schema: str) -> dict[str, Any]:
    try:
        parsed = json.loads(schema)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated hooks schema {name}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"invalid generated hooks schema {name}: expected object")
    return parsed


def _schema_value(fixture: str) -> dict[str, Any]:
    return parse_json_schema(fixture.removesuffix(".schema.json"), schema_json(fixture))


def generated_hook_schemas() -> GeneratedHookSchemas:
    global _GENERATED_HOOK_SCHEMAS
    if _GENERATED_HOOK_SCHEMAS is None:
        _GENERATED_HOOK_SCHEMAS = GeneratedHookSchemas(
            post_tool_use_command_input=_schema_value(POST_TOOL_USE_INPUT_FIXTURE),
            post_tool_use_command_output=_schema_value(POST_TOOL_USE_OUTPUT_FIXTURE),
            permission_request_command_input=_schema_value(PERMISSION_REQUEST_INPUT_FIXTURE),
            permission_request_command_output=_schema_value(PERMISSION_REQUEST_OUTPUT_FIXTURE),
            post_compact_command_input=_schema_value(POST_COMPACT_INPUT_FIXTURE),
            post_compact_command_output=_schema_value(POST_COMPACT_OUTPUT_FIXTURE),
            pre_tool_use_command_input=_schema_value(PRE_TOOL_USE_INPUT_FIXTURE),
            pre_tool_use_command_output=_schema_value(PRE_TOOL_USE_OUTPUT_FIXTURE),
            pre_compact_command_input=_schema_value(PRE_COMPACT_INPUT_FIXTURE),
            pre_compact_command_output=_schema_value(PRE_COMPACT_OUTPUT_FIXTURE),
            session_start_command_input=_schema_value(SESSION_START_INPUT_FIXTURE),
            session_start_command_output=_schema_value(SESSION_START_OUTPUT_FIXTURE),
            subagent_start_command_input=_schema_value(SUBAGENT_START_INPUT_FIXTURE),
            subagent_start_command_output=_schema_value(SUBAGENT_START_OUTPUT_FIXTURE),
            subagent_stop_command_input=_schema_value(SUBAGENT_STOP_INPUT_FIXTURE),
            subagent_stop_command_output=_schema_value(SUBAGENT_STOP_OUTPUT_FIXTURE),
            user_prompt_submit_command_input=_schema_value(USER_PROMPT_SUBMIT_INPUT_FIXTURE),
            user_prompt_submit_command_output=_schema_value(USER_PROMPT_SUBMIT_OUTPUT_FIXTURE),
            stop_command_input=_schema_value(STOP_INPUT_FIXTURE),
            stop_command_output=_schema_value(STOP_OUTPUT_FIXTURE),
        )
    return _GENERATED_HOOK_SCHEMAS
