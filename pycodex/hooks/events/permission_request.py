"""Python port of ``codex-hooks::events.permission_request``."""


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
    _permission_request_decision,
    _permission_request_invalid_decision,
    _permission_request_invalid_universal,
    looks_like_json,
    parse_hook_json_output,
)
from .common import SubagentHookContext, non_empty_string, trimmed_non_empty

class PermissionRequestDecisionKind(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionRequestDecision:
    kind: PermissionRequestDecisionKind
    message: str | None = None

    @classmethod
    def Allow(cls) -> "PermissionRequestDecision":
        return cls(PermissionRequestDecisionKind.ALLOW)

    @classmethod
    def Deny(cls, message: str) -> "PermissionRequestDecision":
        return cls(PermissionRequestDecisionKind.DENY, message)


@dataclass
class PermissionRequestRequest:
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
    tool_input: Any


@dataclass
class PermissionRequestOutcome:
    hook_events: list[HookCompletedEvent]
    decision: PermissionRequestDecision | None


@dataclass(frozen=True)
class PermissionRequestHandlerData:
    decision: PermissionRequestDecision | None = None


@dataclass(frozen=True)
class ParsedPermissionRequestHandler:
    completed: HookCompletedEvent
    data: PermissionRequestHandlerData
    completion_order: int = 0


def permission_request_command_input_json(request: PermissionRequestRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "PermissionRequest",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "tool_name": request.tool_name,
        "tool_input": request.tool_input,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def parse_permission_request_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedPermissionRequestHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    decision = None

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.PERMISSION_REQUEST:
        raise ValueError(f"expected permission request hook event, got {event_name}")

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
                raw_decision = (
                    specific_mapping.get("decision")
                    if specific_mapping is not None
                    else None
                )
                decision_mapping = raw_decision if isinstance(raw_decision, Mapping) else None
                invalid_reason = _permission_request_invalid_universal(parsed)
                if invalid_reason is None:
                    invalid_reason = _permission_request_invalid_decision(decision_mapping)

                if invalid_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_reason))
                elif decision_mapping is not None:
                    parsed_decision = _permission_request_decision(decision_mapping)
                    if (
                        parsed_decision is not None
                        and parsed_decision.kind.value == PermissionRequestDecisionKind.ALLOW.value
                    ):
                        decision = PermissionRequestDecision.Allow()
                    elif (
                        parsed_decision is not None
                        and parsed_decision.kind.value == PermissionRequestDecisionKind.DENY.value
                    ):
                        status = HookRunStatus.BLOCKED
                        message = parsed_decision.message or "PermissionRequest hook denied approval"
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, message))
                        decision = PermissionRequestDecision.Deny(message)
            elif looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid permission-request JSON output",
                    )
                )
    elif exit_code == 2:
        message = trimmed_non_empty(stderr)
        if message is not None:
            status = HookRunStatus.BLOCKED
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, message))
            decision = PermissionRequestDecision.Deny(message)
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    (
                        "PermissionRequest hook exited with code 2 but did not write a "
                        "denial reason to stderr"
                    ),
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedPermissionRequestHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=completed_summary(handler, run_result, status, entries),
        ),
        data=PermissionRequestHandlerData(decision=decision),
    )


def resolve_permission_request_decision(
    decisions: Sequence[PermissionRequestDecision],
) -> PermissionRequestDecision | None:
    resolved_allow = None
    for decision in decisions:
        if decision.kind == PermissionRequestDecisionKind.ALLOW:
            resolved_allow = PermissionRequestDecision.Allow()
        elif decision.kind == PermissionRequestDecisionKind.DENY:
            return PermissionRequestDecision.Deny(decision.message or "")
    return resolved_allow
