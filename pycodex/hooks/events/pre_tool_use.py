"""Python port of ``codex-hooks::events.pre_tool_use``."""


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

from ..declarations import _field
from ..engine.dispatcher import completed_summary
from ..engine.output_parser import (
    _pre_tool_use_invalid_universal,
    _pre_tool_use_unsupported_hook_specific,
    _pre_tool_use_unsupported_legacy_decision,
    looks_like_json,
    parse_hook_json_output,
)
from .common import (
    SubagentHookContext,
    append_additional_context,
    non_empty_string,
    trimmed_non_empty,
)

@dataclass
class PreToolUseRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    tool_name: str
    matcher_aliases: Sequence[str]
    run_id_suffix: str | None
    tool_use_id: str
    tool_input: Any


@dataclass
class PreToolUseOutcome:
    hook_events: list[HookCompletedEvent]
    should_block: bool
    block_reason: str | None
    additional_contexts: list[str]
    updated_input: Any | None


@dataclass(frozen=True)
class PreToolUseHandlerData:
    should_block: bool = False
    block_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)
    updated_input: Any | None = None


@dataclass(frozen=True)
class ParsedPreToolUseHandler:
    completed: HookCompletedEvent
    data: PreToolUseHandlerData
    completion_order: int = 0


def pre_tool_use_command_input_json(request: PreToolUseRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "PreToolUse",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "tool_name": request.tool_name,
        "tool_input": request.tool_input,
        "tool_use_id": request.tool_use_id,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def parse_pre_tool_use_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedPreToolUseHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_block = False
    block_reason = None
    additional_contexts_for_model: list[str] = []
    updated_input = None

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.PRE_TOOL_USE:
        raise ValueError(f"expected pre tool use hook event, got {event_name}")

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    stderr = str(_field(run_result, "stderr", ""))

    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = parse_hook_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                specific = parsed.get("hookSpecificOutput")
                specific_mapping = specific if isinstance(specific, Mapping) else None
                use_hook_specific_decision = (
                    specific_mapping is not None
                    and (
                        specific_mapping.get("permissionDecision") is not None
                        or specific_mapping.get("permissionDecisionReason") is not None
                        or specific_mapping.get("updatedInput") is not None
                    )
                )
                invalid_reason = _pre_tool_use_invalid_universal(parsed)
                if invalid_reason is None:
                    if use_hook_specific_decision and specific_mapping is not None:
                        invalid_reason = _pre_tool_use_unsupported_hook_specific(specific_mapping)
                    else:
                        invalid_reason = _pre_tool_use_unsupported_legacy_decision(
                            parsed.get("decision"),
                            parsed.get("reason"),
                        )

                if invalid_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_reason))
                else:
                    additional_context = (
                        specific_mapping.get("additionalContext")
                        if specific_mapping is not None
                        else None
                    )
                    if isinstance(additional_context, str):
                        append_additional_context(
                            entries,
                            additional_contexts_for_model,
                            additional_context,
                        )

                    if use_hook_specific_decision and specific_mapping is not None:
                        if specific_mapping.get("permissionDecision") == "deny":
                            block_reason = non_empty_string(
                                specific_mapping.get("permissionDecisionReason")
                            )
                        elif specific_mapping.get("permissionDecision") == "allow":
                            updated_input = specific_mapping.get("updatedInput")
                    elif parsed.get("decision") == "block":
                        block_reason = non_empty_string(parsed.get("reason"))

                    if block_reason is not None:
                        status = HookRunStatus.BLOCKED
                        should_block = True
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, block_reason))
                        updated_input = None
            elif looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid pre-tool-use JSON output",
                    )
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            status = HookRunStatus.BLOCKED
            should_block = True
            block_reason = reason
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    "PreToolUse hook exited with code 2 but did not write a blocking reason to stderr",
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedPreToolUseHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=completed_summary(handler, run_result, status, entries),
        ),
        data=PreToolUseHandlerData(
            should_block=should_block,
            block_reason=block_reason,
            additional_contexts_for_model=additional_contexts_for_model,
            updated_input=updated_input,
        ),
    )


def latest_pre_tool_use_updated_input(
    results: Sequence[ParsedPreToolUseHandler],
) -> Any | None:
    candidates = [
        (result.completion_order, result.data.updated_input)
        for result in results
        if result.data.updated_input is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[0])[1]
