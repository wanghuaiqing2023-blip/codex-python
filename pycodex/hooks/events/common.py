"""Python port of ``codex-hooks::events.common``."""


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

@dataclass
class SubagentHookContext:
    agent_id: str
    agent_type: str


def join_text_chunks(chunks: Sequence[str]) -> str | None:
    if not chunks:
        return None
    return "\n\n".join(chunks)


def trimmed_non_empty(text: str) -> str | None:
    trimmed = text.strip()
    if not trimmed:
        return None
    return trimmed


def append_additional_context(
    entries: list[HookOutputEntry],
    additional_contexts_for_model: list[str],
    additional_context: str,
) -> None:
    entries.append(
        HookOutputEntry(
            HookOutputEntryKind.CONTEXT,
            additional_context,
        )
    )
    additional_contexts_for_model.append(additional_context)


def flatten_additional_contexts(
    additional_contexts: Sequence[Sequence[str]],
) -> list[str]:
    return [
        additional_context
        for chunk in additional_contexts
        for additional_context in chunk
    ]


def serialization_failure_hook_events(
    handlers: Sequence[Any],
    turn_id: str | None,
    error_message: str,
) -> list[HookCompletedEvent]:
    events: list[HookCompletedEvent] = []
    for handler in handlers:
        from ..engine.dispatcher import running_summary

        run = running_summary(handler)
        events.append(
            HookCompletedEvent(
                turn_id=turn_id,
                run=replace(
                    run,
                    status=HookRunStatus.FAILED,
                    completed_at=run.started_at,
                    duration_ms=0,
                    entries=(
                        HookOutputEntry(
                            HookOutputEntryKind.ERROR,
                            error_message,
                        ),
                    ),
                ),
            )
        )
    return events


def serialization_failure_hook_events_for_tool_use(
    handlers: Sequence[Any],
    turn_id: str | None,
    error_message: str,
    tool_use_id: str,
) -> list[HookCompletedEvent]:
    return [
        hook_completed_for_tool_use(event, tool_use_id)
        for event in serialization_failure_hook_events(
            handlers,
            turn_id,
            error_message,
        )
    ]


def hook_completed_for_tool_use(
    event: HookCompletedEvent,
    tool_use_id: str,
) -> HookCompletedEvent:
    return replace(event, run=hook_run_for_tool_use(event.run, tool_use_id))


def hook_run_for_tool_use(
    run: HookRunSummary,
    tool_use_id: str,
) -> HookRunSummary:
    return replace(run, id=f"{run.id}:{tool_use_id}")


def matcher_pattern_for_event(
    event_name: HookEventName | str,
    matcher: str | None,
) -> str | None:
    event = HookEventName(event_name)
    if event in {
        HookEventName.PRE_TOOL_USE,
        HookEventName.PERMISSION_REQUEST,
        HookEventName.POST_TOOL_USE,
        HookEventName.SESSION_START,
        HookEventName.SUBAGENT_START,
        HookEventName.SUBAGENT_STOP,
        HookEventName.PRE_COMPACT,
        HookEventName.POST_COMPACT,
    }:
        return matcher
    return None


def _is_match_all_matcher(matcher: str) -> bool:
    return matcher == "" or matcher == "*"


def _is_exact_matcher(matcher: str) -> bool:
    return all(ch.isascii() and (ch.isalnum() or ch in "_|") for ch in matcher)


def validate_matcher_pattern(matcher: str) -> None:
    if _is_match_all_matcher(matcher) or _is_exact_matcher(matcher):
        return None
    re.compile(matcher)
    return None


def matches_matcher(matcher: str | None, input: str | None) -> bool:
    if matcher is None:
        return True
    if _is_match_all_matcher(matcher):
        return True
    if _is_exact_matcher(matcher):
        if input is None:
            return False
        return any(candidate == input for candidate in matcher.split("|"))
    if input is None:
        return False
    try:
        return re.search(matcher, input) is not None
    except re.error:
        return False


def matcher_inputs(tool_name: str, matcher_aliases: Sequence[str]) -> list[str]:
    return [tool_name, *matcher_aliases]


def non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None
