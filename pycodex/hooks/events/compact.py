"""Python port of ``codex-hooks::events.compact``."""


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
from .common import SubagentHookContext, trimmed_non_empty

@dataclass
class PreCompactRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    trigger: str


@dataclass
class PostCompactRequest(PreCompactRequest):
    pass


@dataclass
class StatelessHookOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None


@dataclass
class PreCompactOutcome(StatelessHookOutcome):
    pass


@dataclass(frozen=True)
class CompactHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None


@dataclass(frozen=True)
class ParsedCompactHandler:
    completed: HookCompletedEvent
    data: CompactHandlerData
    completion_order: int = 0


def _compact_command_input_payload(
    request: PreCompactRequest | PostCompactRequest,
    hook_event_name: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": hook_event_name,
        "model": request.model,
        "trigger": request.trigger,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return payload


def pre_compact_command_input_json(request: PreCompactRequest) -> str:
    return json.dumps(
        _compact_command_input_payload(request, "PreCompact"),
        separators=(",", ":"),
    )


def post_compact_command_input_json(request: PostCompactRequest) -> str:
    return json.dumps(
        _compact_command_input_payload(request, "PostCompact"),
        separators=(",", ":"),
    )


_COMPACT_OUTPUT_FIELDS = frozenset(
    {
        "continue",
        "stopReason",
        "suppressOutput",
        "systemMessage",
    }
)


def _parse_compact_json_output(text: str) -> Mapping[str, Any] | None:
    parsed = parse_hook_json_output(text)
    if parsed is None:
        return None
    if set(parsed) - _COMPACT_OUTPUT_FIELDS:
        return None
    continue_processing = parsed.get("continue", True)
    suppress_output = parsed.get("suppressOutput", False)
    if not isinstance(continue_processing, bool):
        return None
    if not isinstance(suppress_output, bool):
        return None
    if parsed.get("stopReason") is not None and not isinstance(parsed.get("stopReason"), str):
        return None
    if parsed.get("systemMessage") is not None and not isinstance(parsed.get("systemMessage"), str):
        return None
    return parsed


def _parse_compact_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
    event_label: str,
) -> ParsedCompactHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None

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
            parsed = _parse_compact_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                if parsed.get("continue", True) is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    stop_text = stop_reason or f"{event_label} hook stopped execution"
                    entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_text))
            elif looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        f"hook returned invalid {event_label} hook JSON output",
                    )
                )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(
            HookOutputEntry(
                HookOutputEntryKind.ERROR,
                "hook process terminated without an exit code",
            )
        )
    else:
        status = HookRunStatus.FAILED
        entries.append(
            HookOutputEntry(
                HookOutputEntryKind.ERROR,
                trimmed_non_empty(stderr) or f"hook exited with code {exit_code}",
            )
        )

    return ParsedCompactHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=completed_summary(handler, run_result, status, entries),
        ),
        data=CompactHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
        ),
    )


def parse_pre_compact_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedCompactHandler:
    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.PRE_COMPACT:
        raise ValueError(f"expected pre compact hook event, got {event_name}")
    return _parse_compact_completed(handler, run_result, turn_id, "PreCompact")


def parse_post_compact_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedCompactHandler:
    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.POST_COMPACT:
        raise ValueError(f"expected post compact hook event, got {event_name}")
    return _parse_compact_completed(handler, run_result, turn_id, "PostCompact")
