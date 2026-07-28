"""Python port of ``codex-hooks::engine.dispatcher``."""


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
from ..events.common import matcher_inputs, matches_matcher
from . import CommandShell, ConfiguredHandler, _handler_event_name_label
from .command_runner import CommandRunResult, run_command

@dataclass
class ParsedHandler:
    completed: HookCompletedEvent
    data: Any
    completion_order: int = 0


def scope_for_event(event_name: HookEventName | str) -> HookScope:
    event = HookEventName(event_name)
    if event in {HookEventName.SESSION_START, HookEventName.SUBAGENT_START}:
        return HookScope.THREAD
    return HookScope.TURN


def _running_summary(handler: Any) -> HookRunSummary:
    event_name = HookEventName(_field(handler, "event_name"))
    raw_source_path = _field(handler, "source_path", "")
    source_path = raw_source_path if hasattr(raw_source_path, "__fspath__") else Path(str(raw_source_path))
    display_order = int(_field(handler, "display_order", 0))
    run_id = f"{_handler_event_name_label(event_name)}:{display_order}:{source_path}"
    return HookRunSummary(
        id=run_id,
        event_name=event_name,
        handler_type=HookHandlerType.COMMAND,
        execution_mode=HookExecutionMode.SYNC,
        scope=scope_for_event(event_name),
        source_path=source_path,
        source=HookSource(_field(handler, "source", HookSource.UNKNOWN)),
        display_order=display_order,
        status=HookRunStatus.RUNNING,
        status_message=_field(handler, "status_message"),
        started_at=int(_field(handler, "started_at", 0)),
    )


def running_summary(handler: Any) -> HookRunSummary:
    return _running_summary(handler)


def select_handlers(
    handlers: Sequence[ConfiguredHandler],
    event_name: HookEventName | str,
    matcher_input: str | None,
) -> list[ConfiguredHandler]:
    matcher_inputs = [] if matcher_input is None else [matcher_input]
    return select_handlers_for_matcher_inputs(handlers, event_name, matcher_inputs)


def select_handlers_for_matcher_inputs(
    handlers: Sequence[ConfiguredHandler],
    event_name: HookEventName | str,
    matcher_inputs: Sequence[str],
) -> list[ConfiguredHandler]:
    event = HookEventName(event_name)
    selected: list[ConfiguredHandler] = []
    for handler in handlers:
        if HookEventName(handler.event_name) != event:
            continue
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
            if not matcher_inputs:
                if not matches_matcher(handler.matcher, None):
                    continue
            elif not any(matches_matcher(handler.matcher, matcher_input) for matcher_input in matcher_inputs):
                continue
        selected.append(handler)
    return selected


def completed_summary(
    handler: Any,
    run_result: Any,
    status: HookRunStatus,
    entries: Sequence[HookOutputEntry],
) -> HookRunSummary:
    event_name = HookEventName(_field(handler, "event_name"))
    raw_source_path = _field(handler, "source_path", "")
    source_path = raw_source_path if hasattr(raw_source_path, "__fspath__") else Path(str(raw_source_path))
    display_order = int(_field(handler, "display_order", 0))
    return HookRunSummary(
        id=f"{_handler_event_name_label(event_name)}:{display_order}:{source_path}",
        event_name=event_name,
        handler_type=HookHandlerType.COMMAND,
        execution_mode=HookExecutionMode.SYNC,
        scope=scope_for_event(event_name),
        source_path=source_path,
        source=HookSource(_field(handler, "source", HookSource.UNKNOWN)),
        display_order=display_order,
        status=status,
        status_message=_field(handler, "status_message"),
        started_at=int(_field(run_result, "started_at")),
        completed_at=int(_field(run_result, "completed_at")),
        duration_ms=int(_field(run_result, "duration_ms")),
        entries=tuple(entries),
    )


async def execute_handlers(
    shell: CommandShell,
    handlers: Sequence[ConfiguredHandler],
    input_json: str,
    cwd: Path,
    turn_id: str | None,
    parse: Callable[[ConfiguredHandler, CommandRunResult, str | None], ParsedHandler],
    run_command_func: Callable[
        [CommandShell, ConfiguredHandler, str, Path],
        Awaitable[CommandRunResult],
    ]
    | None = None,
) -> list[ParsedHandler]:
    if run_command_func is None:
        run_command_func = run_command

    async def run_one(configured_order: int, handler: ConfiguredHandler) -> tuple[int, ParsedHandler]:
        result = await run_command_func(shell, handler, input_json, cwd)
        return configured_order, parse(handler, result, turn_id)

    tasks = [
        asyncio.create_task(run_one(configured_order, handler))
        for configured_order, handler in enumerate(handlers)
    ]
    completed: list[tuple[int, ParsedHandler]] = []
    completion_order = 0
    for task in asyncio.as_completed(tasks):
        configured_order, parsed = await task
        object.__setattr__(parsed, "completion_order", completion_order)
        completion_order += 1
        completed.append((configured_order, parsed))
    completed.sort(key=lambda item: item[0])
    return [parsed for _, parsed in completed]
