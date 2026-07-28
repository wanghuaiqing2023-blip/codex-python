"""Python port of ``codex-hooks::events.session_start``."""


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
from .common import append_additional_context

class SessionStartSource(str, Enum):
    STARTUP = "startup"
    RESUME = "resume"
    CLEAR = "clear"
    COMPACT = "compact"

    def as_str(self) -> str:
        return self.value


@dataclass(frozen=True)
class StartHookTarget:
    event_name: HookEventName
    source: SessionStartSource | None = None
    turn_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None

    @classmethod
    def SessionStart(cls, source: SessionStartSource) -> "StartHookTarget":
        return cls(HookEventName.SESSION_START, source=source)

    @classmethod
    def SubagentStart(cls, turn_id: str, agent_id: str, agent_type: str) -> "StartHookTarget":
        return cls(HookEventName.SUBAGENT_START, turn_id=turn_id, agent_id=agent_id, agent_type=agent_type)

    def matcher_input(self) -> str:
        if self.event_name == HookEventName.SESSION_START:
            if self.source is None:
                raise ValueError("SessionStart target requires source")
            return self.source.as_str()
        if self.event_name == HookEventName.SUBAGENT_START:
            if self.agent_type is None:
                raise ValueError("SubagentStart target requires agent_type")
            return self.agent_type
        raise ValueError(f"unsupported start hook event: {self.event_name}")


@dataclass
class SessionStartRequest:
    session_id: ThreadId | str
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    target: StartHookTarget


@dataclass
class SessionStartOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None
    additional_contexts: list[str]


@dataclass(frozen=True)
class SessionStartHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedSessionStartHandler:
    completed: HookCompletedEvent
    data: SessionStartHandlerData
    completion_order: int = 0


def session_start_command_input_json(request: SessionStartRequest) -> tuple[str, str | None]:
    if request.target.event_name == HookEventName.SESSION_START:
        payload = {
            "session_id": str(request.session_id),
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "cwd": str(request.cwd),
            "hook_event_name": "SessionStart",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "source": request.target.matcher_input(),
        }
        return json.dumps(payload, separators=(",", ":")), None
    if request.target.event_name == HookEventName.SUBAGENT_START:
        if request.target.turn_id is None or request.target.agent_id is None or request.target.agent_type is None:
            raise ValueError("SubagentStart target requires turn_id, agent_id, and agent_type")
        payload = {
            "session_id": str(request.session_id),
            "turn_id": request.target.turn_id,
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "cwd": str(request.cwd),
            "hook_event_name": "SubagentStart",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "agent_id": request.target.agent_id,
            "agent_type": request.target.agent_type,
        }
        return json.dumps(payload, separators=(",", ":")), request.target.turn_id
    raise ValueError(f"unsupported start hook event: {request.target.event_name}")


def parse_session_start_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedSessionStartHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    additional_contexts_for_model: list[str] = []
    event_name = HookEventName(_field(handler, "event_name"))
    if event_name not in {HookEventName.SESSION_START, HookEventName.SUBAGENT_START}:
        raise ValueError(f"expected start hook event, got {event_name}")

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
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
                additional_context = (
                    specific.get("additionalContext")
                    if isinstance(specific, Mapping)
                    else None
                )
                if isinstance(additional_context, str):
                    append_additional_context(
                        entries,
                        additional_contexts_for_model,
                        additional_context,
                    )
                continue_processing = parsed.get("continue", True)
                if event_name == HookEventName.SESSION_START and continue_processing is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    if stop_reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_reason))
            elif looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        (
                            "hook returned invalid session start JSON output"
                            if event_name == HookEventName.SESSION_START
                            else "hook returned invalid subagent start JSON output"
                        ),
                    )
                )
            else:
                append_additional_context(
                    entries,
                    additional_contexts_for_model,
                    trimmed_stdout,
                )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedSessionStartHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=completed_summary(handler, run_result, status, entries),
        ),
        data=SessionStartHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            additional_contexts_for_model=additional_contexts_for_model,
        ),
    )
