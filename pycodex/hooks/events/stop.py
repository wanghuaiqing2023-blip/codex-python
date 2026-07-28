"""Python port of ``codex-hooks::events.stop``."""


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
from ..engine.output_parser import parse_hook_json_output
from .common import join_text_chunks, non_empty_string, trimmed_non_empty

@dataclass(frozen=True)
class StopHookTarget:
    event_name: HookEventName
    agent_id: str | None = None
    agent_type: str | None = None
    agent_transcript_path: Path | None = None

    @classmethod
    def Stop(cls) -> "StopHookTarget":
        return cls(HookEventName.STOP)

    @classmethod
    def SubagentStop(cls, agent_id: str, agent_type: str, agent_transcript_path: Path | None) -> "StopHookTarget":
        return cls(HookEventName.SUBAGENT_STOP, agent_id, agent_type, agent_transcript_path)

    def matcher_input(self) -> str | None:
        if self.event_name == HookEventName.STOP:
            return None
        if self.event_name == HookEventName.SUBAGENT_STOP:
            return self.agent_type
        raise ValueError(f"expected stop hook event, got {self.event_name}")


@dataclass
class StopRequest:
    session_id: ThreadId | str
    turn_id: str
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    stop_hook_active: bool
    last_assistant_message: str | None
    target: StopHookTarget


@dataclass
class StopOutcome:
    hook_events: list[HookCompletedEvent] = field(default_factory=list)
    should_stop: bool = False
    stop_reason: str | None = None
    should_block: bool = False
    block_reason: str | None = None
    continuation_fragments: list[HookPromptFragment] = field(default_factory=list)


@dataclass(frozen=True)
class StopHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    should_block: bool = False
    block_reason: str | None = None
    continuation_fragments: list[HookPromptFragment] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedStopHandler:
    completed: HookCompletedEvent
    data: StopHandlerData
    completion_order: int = 0


def stop_command_input_json(request: StopRequest) -> str:
    if request.target.event_name == HookEventName.STOP:
        payload: dict[str, Any] = {
            "session_id": str(request.session_id),
            "turn_id": request.turn_id,
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "cwd": str(request.cwd),
            "hook_event_name": "Stop",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "stop_hook_active": request.stop_hook_active,
            "last_assistant_message": request.last_assistant_message,
        }
    elif request.target.event_name == HookEventName.SUBAGENT_STOP:
        payload = {
            "session_id": str(request.session_id),
            "turn_id": request.turn_id,
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "agent_transcript_path": (
                str(request.target.agent_transcript_path)
                if request.target.agent_transcript_path is not None
                else None
            ),
            "cwd": str(request.cwd),
            "hook_event_name": "SubagentStop",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "stop_hook_active": request.stop_hook_active,
            "agent_id": request.target.agent_id,
            "agent_type": request.target.agent_type,
            "last_assistant_message": request.last_assistant_message,
        }
    else:
        raise ValueError(f"expected stop hook event, got {request.target.event_name}")
    return json.dumps(payload, separators=(",", ":"))


def _stop_hook_label(event_name: HookEventName) -> str:
    if event_name == HookEventName.STOP:
        return "Stop"
    if event_name == HookEventName.SUBAGENT_STOP:
        return "SubagentStop"
    raise ValueError(f"expected stop hook event, got {event_name}")


def _stop_invalid_json_message(event_name: HookEventName) -> str:
    if event_name == HookEventName.STOP:
        return "hook returned invalid stop hook JSON output"
    if event_name == HookEventName.SUBAGENT_STOP:
        return "hook returned invalid subagent stop hook JSON output"
    raise ValueError(f"expected stop hook event, got {event_name}")


def parse_stop_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedStopHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    should_block = False
    block_reason = None
    continuation_prompt = None

    event_name = HookEventName(_field(handler, "event_name"))
    label = _stop_hook_label(event_name)
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
                parsed_should_block = False
                if decision == "block":
                    if reason is None:
                        invalid_block_reason = (
                            f"{label} hook returned decision:block without a non-empty reason"
                        )
                    else:
                        parsed_should_block = True

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
                elif parsed_should_block:
                    status = HookRunStatus.BLOCKED
                    should_block = True
                    block_reason = reason
                    continuation_prompt = reason
                    if reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
            else:
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        _stop_invalid_json_message(event_name),
                    )
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            status = HookRunStatus.BLOCKED
            should_block = True
            block_reason = reason
            continuation_prompt = reason
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    f"{label} hook exited with code 2 but did not write a continuation prompt to stderr",
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    completed = HookCompletedEvent(
        turn_id=turn_id,
        run=completed_summary(handler, run_result, status, entries),
    )
    continuation_fragments = (
        [HookPromptFragment.from_single_hook(continuation_prompt, completed.run.id)]
        if continuation_prompt is not None
        else []
    )
    return ParsedStopHandler(
        completed=completed,
        data=StopHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            should_block=should_block,
            block_reason=block_reason,
            continuation_fragments=continuation_fragments,
        ),
    )


def aggregate_stop_results(results: Sequence[StopHandlerData]) -> StopHandlerData:
    should_stop = any(result.should_stop for result in results)
    stop_reason = next((result.stop_reason for result in results if result.stop_reason is not None), None)
    should_block = (not should_stop) and any(result.should_block for result in results)
    block_reason = (
        join_text_chunks([result.block_reason for result in results if result.block_reason is not None])
        if should_block
        else None
    )
    continuation_fragments = (
        [
            fragment
            for result in results
            if result.should_block
            for fragment in result.continuation_fragments
        ]
        if should_block
        else []
    )
    return StopHandlerData(
        should_stop=should_stop,
        stop_reason=stop_reason,
        should_block=should_block,
        block_reason=block_reason,
        continuation_fragments=continuation_fragments,
    )
