"""Python port of ``codex-hooks::registry``."""


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

from .engine import HookListEntry, _ClaudeHooksEngine, _CommandShell
from .events.compact import PostCompactRequest, PreCompactOutcome, PreCompactRequest, StatelessHookOutcome
from .events.permission_request import PermissionRequestOutcome, PermissionRequestRequest
from .events.post_tool_use import PostToolUseOutcome, PostToolUseRequest
from .events.pre_tool_use import PreToolUseOutcome, PreToolUseRequest
from .events.session_start import SessionStartOutcome, SessionStartRequest
from .events.stop import StopOutcome, StopRequest
from .events.user_prompt_submit import UserPromptSubmitOutcome, UserPromptSubmitRequest
from .legacy_notify import notify_hook
from .types import HookPayload, HookResponse

def command_from_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv or not argv[0]:
        return None
    return list(argv)


@dataclass
class HooksConfig:
    legacy_notify_argv: list[str] | None = None
    feature_enabled: bool = False
    bypass_hook_trust: bool = False
    config_layer_stack: Any | None = None
    plugin_hook_sources: list[Any] = field(default_factory=list)
    plugin_hook_load_warnings: list[str] = field(default_factory=list)
    shell_program: str | None = None
    shell_args: list[str] = field(default_factory=list)


@dataclass
class HookListOutcome:
    hooks: list[HookListEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Hooks:
    def __init__(self, config: HooksConfig | None = None) -> None:
        self.config = config or HooksConfig()
        self.after_agent = []
        if self.config.legacy_notify_argv and self.config.legacy_notify_argv[0]:
            self.after_agent.append(notify_hook(self.config.legacy_notify_argv))
        self.engine = _ClaudeHooksEngine.new(
            self.config.feature_enabled,
            self.config.bypass_hook_trust,
            self.config.config_layer_stack,
            self.config.plugin_hook_sources,
            self.config.plugin_hook_load_warnings,
            _CommandShell(
                self.config.shell_program or "",
                list(self.config.shell_args),
            ),
        )

    @classmethod
    def new(cls, config: HooksConfig) -> "Hooks":
        return cls(config)

    def startup_warnings(self) -> list[str]:
        return self.engine.warnings()

    async def dispatch(self, hook_payload: HookPayload) -> list[HookResponse]:
        outcomes: list[HookResponse] = []
        for hook in self.after_agent:
            outcome = await hook.execute(hook_payload)
            outcomes.append(outcome)
            if outcome.result.should_abort_operation():
                break
        return outcomes

    def preview_session_start(self, request: SessionStartRequest) -> list[Any]:
        return self.engine.preview_session_start(request)

    def preview_pre_tool_use(self, request: PreToolUseRequest) -> list[Any]:
        return self.engine.preview_pre_tool_use(request)

    def preview_permission_request(self, request: PermissionRequestRequest) -> list[Any]:
        return self.engine.preview_permission_request(request)

    def preview_post_tool_use(self, request: PostToolUseRequest) -> list[Any]:
        return self.engine.preview_post_tool_use(request)

    def preview_pre_compact(self, request: PreCompactRequest) -> list[Any]:
        return self.engine.preview_pre_compact(request)

    def preview_post_compact(self, request: PostCompactRequest) -> list[Any]:
        return self.engine.preview_post_compact(request)

    def preview_user_prompt_submit(self, request: UserPromptSubmitRequest) -> list[Any]:
        return self.engine.preview_user_prompt_submit(request)

    def preview_stop(self, request: StopRequest) -> list[Any]:
        return self.engine.preview_stop(request)

    async def run_session_start(self, request: SessionStartRequest, turn_id: str | None) -> SessionStartOutcome:
        return await self.engine.run_session_start(request, turn_id)

    async def run_pre_tool_use(self, request: PreToolUseRequest) -> PreToolUseOutcome:
        return await self.engine.run_pre_tool_use(request)

    async def run_permission_request(self, request: PermissionRequestRequest) -> PermissionRequestOutcome:
        return await self.engine.run_permission_request(request)

    async def run_post_tool_use(self, request: PostToolUseRequest) -> PostToolUseOutcome:
        return await self.engine.run_post_tool_use(request)

    async def run_pre_compact(self, request: PreCompactRequest) -> PreCompactOutcome:
        return await self.engine.run_pre_compact(request)

    async def run_post_compact(self, request: PostCompactRequest) -> StatelessHookOutcome:
        return await self.engine.run_post_compact(request)

    async def run_user_prompt_submit(self, request: UserPromptSubmitRequest) -> UserPromptSubmitOutcome:
        return await self.engine.run_user_prompt_submit(request)

    async def run_stop(self, request: StopRequest) -> StopOutcome:
        return await self.engine.run_stop(request)


def _discover_handlers(config: HooksConfig) -> HookListOutcome:
    discovered = discover_handlers(
        config.config_layer_stack,
        config.plugin_hook_sources,
        config.plugin_hook_load_warnings,
        config.bypass_hook_trust,
    )
    return HookListOutcome(discovered.hook_entries, discovered.warnings)


def list_hooks(config: HooksConfig) -> HookListOutcome:
    if not config.feature_enabled:
        return HookListOutcome()
    return _discover_handlers(config)
