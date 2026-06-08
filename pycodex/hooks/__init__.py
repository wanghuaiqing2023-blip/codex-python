"""Python port of source-verified ``codex-hooks`` public interfaces.

Rust reference:
- ``codex/codex-rs/hooks/src/lib.rs``
- ``codex/codex-rs/hooks/src/types.rs``
- ``codex/codex-rs/hooks/src/registry.rs``
- ``codex/codex-rs/hooks/src/events/*.rs``
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    HookCompletedEvent,
    HookEventName,
    HookHandlerType,
    HookPromptFragment,
    HookSource,
    HookTrustStatus,
    ThreadId,
)

HOOK_EVENT_NAMES = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)

HOOK_EVENT_NAMES_WITH_MATCHERS = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "SubagentStart",
    "SubagentStop",
)


def hook_event_key_label(event_name: HookEventName | str) -> str:
    return HookEventName(event_name).value


def hook_key(key_source: str, event_name: HookEventName | str, group_index: int, handler_index: int) -> str:
    return f"{key_source}:{hook_event_key_label(event_name)}:{group_index}:{handler_index}"


@dataclass(frozen=True)
class PluginHookDeclaration:
    key: str
    event_name: HookEventName


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _plugin_key(plugin_id: Any) -> str:
    if hasattr(plugin_id, "as_key"):
        return str(plugin_id.as_key())
    return str(plugin_id)


def plugin_hook_declarations(hook_sources: Sequence[Any]) -> list[PluginHookDeclaration]:
    declarations: list[PluginHookDeclaration] = []
    for source in hook_sources:
        key_source = f"{_plugin_key(_field(source, 'plugin_id'))}:{_field(source, 'source_relative_path', '')}"
        hooks = _field(source, "hooks", {})
        if hasattr(hooks, "into_matcher_groups"):
            groups_by_event = hooks.into_matcher_groups()
        elif isinstance(hooks, Mapping):
            groups_by_event = hooks.items()
        else:
            groups_by_event = ()
        for event_name, groups in groups_by_event:
            event = HookEventName(event_name)
            for group_index, group in enumerate(groups):
                handlers = _field(group, "hooks", ())
                for handler_index, _handler in enumerate(handlers):
                    declarations.append(
                        PluginHookDeclaration(
                            hook_key(key_source, event, group_index, handler_index),
                            event,
                        )
                    )
    return declarations


@dataclass
class SubagentHookContext:
    agent_id: str
    agent_type: str


class HookResultKind(str, Enum):
    SUCCESS = "success"
    FAILED_CONTINUE = "failed_continue"
    FAILED_ABORT = "failed_abort"


@dataclass(frozen=True)
class HookResult:
    kind: HookResultKind
    error: Exception | str | None = None

    @classmethod
    def Success(cls) -> "HookResult":
        return cls(HookResultKind.SUCCESS)

    @classmethod
    def FailedContinue(cls, error: Exception | str) -> "HookResult":
        return cls(HookResultKind.FAILED_CONTINUE, error)

    @classmethod
    def FailedAbort(cls, error: Exception | str) -> "HookResult":
        return cls(HookResultKind.FAILED_ABORT, error)

    def should_abort_operation(self) -> bool:
        return self.kind == HookResultKind.FAILED_ABORT


@dataclass
class HookResponse:
    hook_name: str
    result: HookResult


HookFunc = Callable[["HookPayload"], Awaitable[HookResult] | HookResult]


async def _default_hook_func(_payload: "HookPayload") -> HookResult:
    return HookResult.Success()


@dataclass
class Hook:
    name: str = "default"
    func: HookFunc = _default_hook_func

    async def execute(self, payload: "HookPayload") -> HookResponse:
        result = self.func(payload)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[assignment]
        if not isinstance(result, HookResult):
            raise TypeError("hook func must return HookResult")
        return HookResponse(self.name, result)


@dataclass
class HookEventAfterAgent:
    thread_id: ThreadId | str
    turn_id: str
    input_messages: list[str]
    last_assistant_message: str | None


@dataclass
class HookEvent:
    after_agent: HookEventAfterAgent

    @classmethod
    def AfterAgent(cls, event: HookEventAfterAgent) -> "HookEvent":
        return cls(event)

    def to_mapping(self) -> dict[str, Any]:
        event = self.after_agent
        return {
            "event_type": "after_agent",
            "thread_id": str(event.thread_id),
            "turn_id": event.turn_id,
            "input_messages": list(event.input_messages),
            "last_assistant_message": event.last_assistant_message,
        }


@dataclass
class HookPayload:
    session_id: ThreadId | str
    cwd: Path
    client: str | None
    triggered_at: datetime
    hook_event: HookEvent

    def to_mapping(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "cwd": str(self.cwd),
            "client": self.client,
            "triggered_at": self.triggered_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            **self.hook_event.to_mapping(),
        }


def legacy_notify_json(payload: HookPayload) -> str:
    event = payload.hook_event.after_agent
    return json.dumps(
        {
            "type": "agent-turn-complete",
            "thread-id": str(event.thread_id),
            "turn-id": event.turn_id,
            "cwd": str(payload.cwd),
            **({"client": payload.client} if payload.client is not None else {}),
            "input-messages": list(event.input_messages),
            "last-assistant-message": event.last_assistant_message,
        },
        separators=(",", ":"),
    )


def command_from_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv or not argv[0]:
        return None
    return list(argv)


def notify_hook(argv: Sequence[str]) -> Hook:
    async def run(payload: HookPayload) -> HookResult:
        command = command_from_argv(argv)
        if command is None:
            return HookResult.Success()
        try:
            subprocess.Popen(
                [*command, legacy_notify_json(payload)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            return HookResult.FailedContinue(exc)
        return HookResult.Success()

    return Hook("legacy_notify", run)


@dataclass
class PreToolUseRequest:
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


@dataclass
class PreToolUseOutcome:
    hook_events: list[HookCompletedEvent]
    should_block: bool
    block_reason: str | None
    additional_contexts: list[str]
    updated_input: Any | None


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
    tool_input: Any
    tool_response: Any


@dataclass
class PostToolUseOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None
    additional_contexts: list[str]
    feedback_message: str | None


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

    @classmethod
    def new(cls, config: HooksConfig) -> "Hooks":
        return cls(config)

    def startup_warnings(self) -> list[str]:
        if not self.config.feature_enabled:
            return []
        return list(self.config.plugin_hook_load_warnings)

    async def dispatch(self, hook_payload: HookPayload) -> list[HookResponse]:
        outcomes: list[HookResponse] = []
        for hook in self.after_agent:
            outcome = await hook.execute(hook_payload)
            outcomes.append(outcome)
            if outcome.result.should_abort_operation():
                break
        return outcomes

    def preview_session_start(self, request: SessionStartRequest) -> list[Any]:
        return []

    def preview_pre_tool_use(self, request: PreToolUseRequest) -> list[Any]:
        return []

    def preview_permission_request(self, request: PermissionRequestRequest) -> list[Any]:
        return []

    def preview_post_tool_use(self, request: PostToolUseRequest) -> list[Any]:
        return []

    def preview_pre_compact(self, request: PreCompactRequest) -> list[Any]:
        return []

    def preview_post_compact(self, request: PostCompactRequest) -> list[Any]:
        return []

    def preview_user_prompt_submit(self, request: UserPromptSubmitRequest) -> list[Any]:
        return []

    def preview_stop(self, request: StopRequest) -> list[Any]:
        return []

    async def run_session_start(self, request: SessionStartRequest, turn_id: str | None) -> SessionStartOutcome:
        return SessionStartOutcome([], False, None, [])

    async def run_pre_tool_use(self, request: PreToolUseRequest) -> PreToolUseOutcome:
        return PreToolUseOutcome([], False, None, [], None)

    async def run_permission_request(self, request: PermissionRequestRequest) -> PermissionRequestOutcome:
        return PermissionRequestOutcome([], None)

    async def run_post_tool_use(self, request: PostToolUseRequest) -> PostToolUseOutcome:
        return PostToolUseOutcome([], False, None, [], None)

    async def run_pre_compact(self, request: PreCompactRequest) -> PreCompactOutcome:
        return PreCompactOutcome([], False, None)

    async def run_post_compact(self, request: PostCompactRequest) -> StatelessHookOutcome:
        return StatelessHookOutcome([], False, None)

    async def run_user_prompt_submit(self, request: UserPromptSubmitRequest) -> UserPromptSubmitOutcome:
        return UserPromptSubmitOutcome([], False, None, [])

    async def run_stop(self, request: StopRequest) -> StopOutcome:
        return StopOutcome()


def list_hooks(config: HooksConfig) -> HookListOutcome:
    if not config.feature_enabled:
        return HookListOutcome()
    return HookListOutcome(warnings=list(config.plugin_hook_load_warnings))


def hook_states_from_stack(config_layer_stack: Any | None) -> dict[str, Any]:
    if config_layer_stack is None:
        return {}
    if hasattr(config_layer_stack, "get_layers"):
        layers = config_layer_stack.get_layers("lowest_precedence_first", True)
    elif isinstance(config_layer_stack, Sequence):
        layers = config_layer_stack
    else:
        return {}

    states: dict[str, dict[str, Any]] = {}
    for layer in layers:
        name = _field(layer, "name")
        name_text = str(name).lower()
        if "user" not in name_text and "session" not in name_text:
            continue
        config = _field(layer, "config", {})
        hooks = _field(config, "hooks", {}) if not isinstance(config, Mapping) else config.get("hooks", {})
        state_by_key = _field(hooks, "state", {}) if not isinstance(hooks, Mapping) else hooks.get("state", {})
        if not isinstance(state_by_key, Mapping):
            continue
        for key, state in state_by_key.items():
            key = str(key).strip()
            if not key:
                continue
            if not isinstance(state, Mapping):
                continue
            effective = states.setdefault(key, {})
            if isinstance(state.get("enabled"), bool):
                effective["enabled"] = state["enabled"]
            if isinstance(state.get("trusted_hash"), str):
                effective["trusted_hash"] = state["trusted_hash"]
    return states


def write_schema_fixtures(*_args: Any, **_kwargs: Any) -> None:
    return None


__all__ = [name for name in globals() if not name.startswith("_")]
