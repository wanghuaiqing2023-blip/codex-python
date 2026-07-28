"""Python port of ``codex-hooks::engine``."""


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

def _handler_event_name_label(event_name: HookEventName | str) -> str:
    return HookEventName(event_name).value.replace("_", "-")


@dataclass(frozen=True)
class CommandShell:
    program: str
    args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfiguredHandler:
    event_name: HookEventName
    matcher: str | None
    command: str
    timeout_sec: int
    status_message: str | None
    source_path: Path
    source: HookSource
    display_order: int
    env: Mapping[str, str] = field(default_factory=dict)

    def run_id(self) -> str:
        return f"{_handler_event_name_label(self.event_name)}:{self.display_order}:{self.source_path}"


@dataclass
class HookListEntry:
    key: str
    event_name: HookEventName
    handler_type: HookHandlerType
    matcher: str | None
    command: str | None
    timeout_sec: int
    status_message: str | None
    source_path: Path
    source: HookSource
    plugin_id: str | None
    display_order: int
    enabled: bool
    is_managed: bool
    current_hash: str
    trust_status: HookTrustStatus

from ..declarations import _field
from ..events.common import (
    flatten_additional_contexts,
    hook_completed_for_tool_use,
    hook_run_for_tool_use,
    matcher_inputs,
)
from ..events.compact import (
    PostCompactRequest,
    PreCompactOutcome,
    PreCompactRequest,
    StatelessHookOutcome,
    parse_post_compact_completed,
    parse_pre_compact_completed,
    post_compact_command_input_json,
    pre_compact_command_input_json,
)
from ..events.permission_request import (
    PermissionRequestOutcome,
    PermissionRequestRequest,
    parse_permission_request_completed,
    permission_request_command_input_json,
    resolve_permission_request_decision,
)
from ..events.post_tool_use import (
    PostToolUseOutcome,
    PostToolUseRequest,
    parse_post_tool_use_completed,
    post_tool_use_command_input_json,
    post_tool_use_feedback_message,
)
from ..events.pre_tool_use import (
    PreToolUseOutcome,
    PreToolUseRequest,
    latest_pre_tool_use_updated_input,
    parse_pre_tool_use_completed,
    pre_tool_use_command_input_json,
)
from ..events.session_start import (
    SessionStartOutcome,
    SessionStartRequest,
    parse_session_start_completed,
    session_start_command_input_json,
)
from ..events.stop import (
    StopOutcome,
    StopRequest,
    aggregate_stop_results,
    parse_stop_completed,
    stop_command_input_json,
)
from ..events.user_prompt_submit import (
    UserPromptSubmitOutcome,
    UserPromptSubmitRequest,
    parse_user_prompt_submit_completed,
    user_prompt_submit_command_input_json,
)
from ..output_spill import HookOutputSpiller
from .discovery import discover_handlers
from .dispatcher import (
    execute_handlers,
    running_summary,
    select_handlers,
    select_handlers_for_matcher_inputs,
)
from .schema_loader import generated_hook_schemas

@dataclass(frozen=True)
class _CommandShell:
    program: str
    args: list[str]


class _ClaudeHooksEngine:
    def __init__(
        self,
        handlers: Sequence[ConfiguredHandler] = (),
        warnings: Sequence[str] = (),
        shell: _CommandShell | CommandShell | None = None,
        output_spiller: HookOutputSpiller | None = None,
    ) -> None:
        self.handlers = list(handlers)
        self._warnings = list(warnings)
        raw_shell = shell or _CommandShell("", [])
        self.shell = CommandShell(
            program=str(_field(raw_shell, "program", "")),
            args=list(_field(raw_shell, "args", [])),
        )
        self.output_spiller = output_spiller or HookOutputSpiller.new()

    @classmethod
    def new(
        cls,
        enabled: bool,
        bypass_hook_trust: bool,
        config_layer_stack: Any | None,
        plugin_hook_sources: Sequence[Any],
        plugin_hook_load_warnings: Sequence[str],
        _shell: _CommandShell,
    ) -> "_ClaudeHooksEngine":
        if not enabled:
            return cls(shell=_shell)
        generated_hook_schemas()
        discovered = discover_handlers(
            config_layer_stack,
            plugin_hook_sources,
            plugin_hook_load_warnings,
            bypass_hook_trust,
        )
        return cls(discovered.handlers, discovered.warnings, shell=_shell)

    def warnings(self) -> list[str]:
        return list(self._warnings)

    def preview_session_start(self, request: SessionStartRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                request.target.event_name,
                request.target.matcher_input(),
            )
        ]

    def preview_pre_tool_use(self, request: PreToolUseRequest) -> list[HookRunSummary]:
        return [
            hook_run_for_tool_use(running_summary(handler), request.tool_use_id)
            for handler in select_handlers_for_matcher_inputs(
                self.handlers,
                HookEventName.PRE_TOOL_USE,
                matcher_inputs(request.tool_name, request.matcher_aliases),
            )
        ]

    def preview_permission_request(self, request: PermissionRequestRequest) -> list[HookRunSummary]:
        summaries = [
            running_summary(handler)
            for handler in select_handlers_for_matcher_inputs(
                self.handlers,
                HookEventName.PERMISSION_REQUEST,
                matcher_inputs(request.tool_name, request.matcher_aliases),
            )
        ]
        if request.run_id_suffix is None:
            return summaries
        return [hook_run_for_tool_use(summary, request.run_id_suffix) for summary in summaries]

    def preview_post_tool_use(self, request: PostToolUseRequest) -> list[HookRunSummary]:
        return [
            hook_run_for_tool_use(running_summary(handler), request.tool_use_id)
            for handler in select_handlers_for_matcher_inputs(
                self.handlers,
                HookEventName.POST_TOOL_USE,
                matcher_inputs(request.tool_name, request.matcher_aliases),
            )
        ]

    def preview_pre_compact(self, request: PreCompactRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                HookEventName.PRE_COMPACT,
                request.trigger,
            )
        ]

    def preview_post_compact(self, request: PostCompactRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                HookEventName.POST_COMPACT,
                request.trigger,
            )
        ]

    def preview_user_prompt_submit(self, _request: UserPromptSubmitRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(self.handlers, HookEventName.USER_PROMPT_SUBMIT, None)
        ]

    def preview_stop(self, request: StopRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                request.target.event_name,
                request.target.matcher_input(),
            )
        ]

    async def run_session_start(
        self,
        request: SessionStartRequest,
        turn_id: str | None,
    ) -> SessionStartOutcome:
        matched = select_handlers(
            self.handlers,
            request.target.event_name,
            request.target.matcher_input(),
        )
        if not matched:
            return SessionStartOutcome([], False, None, [])
        input_json, target_turn_id = session_start_command_input_json(request)
        run_turn_id = target_turn_id if target_turn_id is not None else turn_id
        results = await execute_handlers(
            self.shell,
            matched,
            input_json,
            request.cwd,
            run_turn_id,
            parse_session_start_completed,
        )
        additional_contexts = flatten_additional_contexts(
            [result.data.additional_contexts_for_model for result in results]
        )
        return SessionStartOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
        )

    async def run_pre_tool_use(self, request: PreToolUseRequest) -> PreToolUseOutcome:
        matched = select_handlers_for_matcher_inputs(
            self.handlers,
            HookEventName.PRE_TOOL_USE,
            matcher_inputs(request.tool_name, request.matcher_aliases),
        )
        if not matched:
            return PreToolUseOutcome([], False, None, [], None)
        results = await execute_handlers(
            self.shell,
            matched,
            pre_tool_use_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_pre_tool_use_completed,
        )
        data = [result.data for result in results]
        additional_contexts = flatten_additional_contexts(
            [item.additional_contexts_for_model for item in data]
        )
        return PreToolUseOutcome(
            [hook_completed_for_tool_use(result.completed, request.tool_use_id) for result in results],
            any(item.should_block for item in data),
            next((item.block_reason for item in data if item.block_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
            latest_pre_tool_use_updated_input(results),
        )

    async def run_permission_request(
        self,
        request: PermissionRequestRequest,
    ) -> PermissionRequestOutcome:
        matched = select_handlers_for_matcher_inputs(
            self.handlers,
            HookEventName.PERMISSION_REQUEST,
            matcher_inputs(request.tool_name, request.matcher_aliases),
        )
        if not matched:
            return PermissionRequestOutcome([], None)
        results = await execute_handlers(
            self.shell,
            matched,
            permission_request_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_permission_request_completed,
        )
        hook_events = [result.completed for result in results]
        if request.run_id_suffix is not None:
            hook_events = [
                hook_completed_for_tool_use(event, request.run_id_suffix)
                for event in hook_events
            ]
        return PermissionRequestOutcome(
            hook_events,
            resolve_permission_request_decision(
                [result.data.decision for result in results if result.data.decision is not None]
            ),
        )

    async def run_post_tool_use(self, request: PostToolUseRequest) -> PostToolUseOutcome:
        matched = select_handlers_for_matcher_inputs(
            self.handlers,
            HookEventName.POST_TOOL_USE,
            matcher_inputs(request.tool_name, request.matcher_aliases),
        )
        if not matched:
            return PostToolUseOutcome([], False, None, [], None)
        results = await execute_handlers(
            self.shell,
            matched,
            post_tool_use_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_post_tool_use_completed,
        )
        data = [result.data for result in results]
        additional_contexts = flatten_additional_contexts(
            [item.additional_contexts_for_model for item in data]
        )
        feedback = post_tool_use_feedback_message(data)
        return PostToolUseOutcome(
            [hook_completed_for_tool_use(result.completed, request.tool_use_id) for result in results],
            any(item.should_stop for item in data),
            next((item.stop_reason for item in data if item.stop_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
            (
                await self.output_spiller.maybe_spill_text(request.session_id, feedback)
                if feedback is not None
                else None
            ),
        )

    async def run_pre_compact(self, request: PreCompactRequest) -> PreCompactOutcome:
        matched = select_handlers(self.handlers, HookEventName.PRE_COMPACT, request.trigger)
        if not matched:
            return PreCompactOutcome([], False, None)
        results = await execute_handlers(
            self.shell,
            matched,
            pre_compact_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_pre_compact_completed,
        )
        return PreCompactOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
        )

    async def run_post_compact(self, request: PostCompactRequest) -> StatelessHookOutcome:
        matched = select_handlers(self.handlers, HookEventName.POST_COMPACT, request.trigger)
        if not matched:
            return StatelessHookOutcome([], False, None)
        results = await execute_handlers(
            self.shell,
            matched,
            post_compact_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_post_compact_completed,
        )
        return StatelessHookOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
        )

    async def run_user_prompt_submit(
        self,
        request: UserPromptSubmitRequest,
    ) -> UserPromptSubmitOutcome:
        matched = select_handlers(self.handlers, HookEventName.USER_PROMPT_SUBMIT, None)
        if not matched:
            return UserPromptSubmitOutcome([], False, None, [])
        results = await execute_handlers(
            self.shell,
            matched,
            user_prompt_submit_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_user_prompt_submit_completed,
        )
        additional_contexts = flatten_additional_contexts(
            [result.data.additional_contexts_for_model for result in results]
        )
        return UserPromptSubmitOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
        )

    async def run_stop(self, request: StopRequest) -> StopOutcome:
        matched = select_handlers(
            self.handlers,
            request.target.event_name,
            request.target.matcher_input(),
        )
        if not matched:
            return StopOutcome()
        results = await execute_handlers(
            self.shell,
            matched,
            stop_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_stop_completed,
        )
        aggregate = aggregate_stop_results([result.data for result in results])
        return StopOutcome(
            hook_events=[result.completed for result in results],
            should_stop=aggregate.should_stop,
            stop_reason=aggregate.stop_reason,
            should_block=aggregate.should_block,
            block_reason=aggregate.block_reason,
            continuation_fragments=await self.output_spiller.maybe_spill_prompt_fragments(
                request.session_id,
                aggregate.continuation_fragments,
            ),
        )
