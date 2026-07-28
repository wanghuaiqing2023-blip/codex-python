"""Python port of ``codex-hooks::events.user_prompt_submit``."""


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
from ..engine.output_parser import looks_like_json, parse_hook_json_output
from .common import (
    SubagentHookContext,
    append_additional_context,
    non_empty_string,
    trimmed_non_empty,
)

@dataclass
class UserPromptSubmitRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    prompt: str


@dataclass
class UserPromptSubmitOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None
    additional_contexts: list[str]


@dataclass(frozen=True)
class UserPromptSubmitHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedUserPromptSubmitHandler:
    completed: HookCompletedEvent
    data: UserPromptSubmitHandlerData
    completion_order: int = 0


def user_prompt_submit_command_input_json(request: UserPromptSubmitRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "UserPromptSubmit",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "prompt": request.prompt,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def parse_user_prompt_submit_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedUserPromptSubmitHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    additional_contexts_for_model: list[str] = []

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.USER_PROMPT_SUBMIT:
        raise ValueError(f"expected user prompt submit hook event, got {event_name}")

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

                decision = parsed.get("decision")
                reason = non_empty_string(parsed.get("reason"))
                invalid_block_reason = None
                should_block = False
                if decision == "block":
                    if reason is None:
                        invalid_block_reason = (
                            "UserPromptSubmit hook returned decision:block without a non-empty reason"
                        )
                    else:
                        should_block = True

                specific = parsed.get("hookSpecificOutput")
                additional_context = (
                    specific.get("additionalContext")
                    if isinstance(specific, Mapping)
                    else None
                )
                if invalid_block_reason is None and isinstance(additional_context, str):
                    append_additional_context(
                        entries,
                        additional_contexts_for_model,
                        additional_context,
                    )

                continue_processing = parsed.get("continue", True)
                if continue_processing is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    if stop_reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_reason))
                elif invalid_block_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_block_reason))
                elif should_block:
                    status = HookRunStatus.BLOCKED
                    should_stop = True
                    stop_reason = reason
                    if reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
            elif looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid user prompt submit JSON output",
                    )
                )
            else:
                append_additional_context(
                    entries,
                    additional_contexts_for_model,
                    trimmed_stdout,
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            status = HookRunStatus.BLOCKED
            should_stop = True
            stop_reason = reason
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    (
                        "UserPromptSubmit hook exited with code 2 but did not write a blocking "
                        "reason to stderr"
                    ),
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedUserPromptSubmitHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=completed_summary(handler, run_result, status, entries),
        ),
        data=UserPromptSubmitHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            additional_contexts_for_model=additional_contexts_for_model,
        ),
    )
