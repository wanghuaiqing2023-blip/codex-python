"""Python port of ``codex-hooks::events.post_tool_use``."""


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
    _post_tool_use_invalid_block_reason,
    _post_tool_use_invalid_hook_specific,
    _post_tool_use_invalid_universal,
    looks_like_json,
    parse_hook_json_output,
)
from .common import (
    SubagentHookContext,
    append_additional_context,
    join_text_chunks,
    non_empty_string,
    trimmed_non_empty,
)

@dataclass
class PostToolUseRequest:
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
    tool_response: Any


@dataclass
class PostToolUseOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None
    additional_contexts: list[str]
    feedback_message: str | None


@dataclass(frozen=True)
class PostToolUseHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)
    feedback_messages_for_model: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPostToolUseHandler:
    completed: HookCompletedEvent
    data: PostToolUseHandlerData
    completion_order: int = 0


def post_tool_use_command_input_json(request: PostToolUseRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "PostToolUse",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "tool_name": request.tool_name,
        "tool_input": request.tool_input,
        "tool_response": request.tool_response,
        "tool_use_id": request.tool_use_id,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def parse_post_tool_use_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedPostToolUseHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    additional_contexts_for_model: list[str] = []
    feedback_messages_for_model: list[str] = []

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.POST_TOOL_USE:
        raise ValueError(f"expected post tool use hook event, got {event_name}")

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
                invalid_reason = _post_tool_use_invalid_universal(parsed)
                if invalid_reason is None:
                    invalid_reason = _post_tool_use_invalid_hook_specific(specific_mapping)
                invalid_block_reason = _post_tool_use_invalid_block_reason(parsed)

                additional_context = (
                    specific_mapping.get("additionalContext")
                    if specific_mapping is not None
                    else None
                )
                if (
                    invalid_reason is None
                    and invalid_block_reason is None
                    and isinstance(additional_context, str)
                ):
                    append_additional_context(
                        entries,
                        additional_contexts_for_model,
                        additional_context,
                    )

                if parsed.get("continue", True) is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    stop_text = stop_reason or "PostToolUse hook stopped execution"
                    entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_text))
                    feedback = non_empty_string(parsed.get("reason")) or stop_text
                    feedback_messages_for_model.append(feedback)
                elif invalid_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_reason))
                elif invalid_block_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_block_reason))
                elif parsed.get("decision") == "block":
                    status = HookRunStatus.BLOCKED
                    reason = parsed.get("reason")
                    if isinstance(reason, str):
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
                        feedback_messages_for_model.append(reason)
            elif looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid post-tool-use JSON output",
                    )
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
            feedback_messages_for_model.append(reason)
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    "PostToolUse hook exited with code 2 but did not write feedback to stderr",
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedPostToolUseHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=completed_summary(handler, run_result, status, entries),
        ),
        data=PostToolUseHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            additional_contexts_for_model=additional_contexts_for_model,
            feedback_messages_for_model=feedback_messages_for_model,
        ),
    )


def post_tool_use_feedback_message(results: Sequence[PostToolUseHandlerData]) -> str | None:
    return join_text_chunks(
        [
            feedback
            for result in results
            for feedback in result.feedback_messages_for_model
        ]
    )
