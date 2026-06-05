"""Pure hook-runtime outcome helpers ported from Codex core.

Rust ``core/src/hook_runtime.rs`` owns hook process dispatch and event emission.
This stdlib slice keeps the observable outcome shaping: pre-tool-use block vs
continue decisions, post-tool-use replacement text rules, compact hook
outcomes, and additional-context developer messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.core.context import HookAdditionalContext
from pycodex.core.tools.hook_names import HookToolName
from pycodex.protocol import ResponseItem

JsonValue = Any


@dataclass(frozen=True)
class HookRequestContext:
    session_id: str
    turn_id: str
    cwd: str
    transcript_path: str | None
    model: str
    permission_mode: str
    subagent: JsonValue | None = None

    def __post_init__(self) -> None:
        for field_name in ("session_id", "turn_id", "cwd", "model", "permission_mode"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
        if self.transcript_path is not None and not isinstance(self.transcript_path, str):
            raise TypeError("transcript_path must be a string or None")


@dataclass(frozen=True)
class PreToolUseRequest:
    session_id: str
    turn_id: str
    subagent: JsonValue | None
    cwd: str
    transcript_path: str | None
    model: str
    permission_mode: str
    tool_name: str
    matcher_aliases: tuple[str, ...]
    tool_use_id: str
    tool_input: JsonValue

    def __post_init__(self) -> None:
        _validate_request_base(self)
        object.__setattr__(self, "matcher_aliases", _string_tuple(self.matcher_aliases, "matcher_aliases"))
        for field_name in ("tool_name", "tool_use_id"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")


@dataclass(frozen=True)
class PostToolUseRequest:
    session_id: str
    turn_id: str
    subagent: JsonValue | None
    cwd: str
    transcript_path: str | None
    model: str
    permission_mode: str
    tool_name: str
    matcher_aliases: tuple[str, ...]
    tool_use_id: str
    tool_input: JsonValue
    tool_response: JsonValue

    def __post_init__(self) -> None:
        _validate_request_base(self)
        object.__setattr__(self, "matcher_aliases", _string_tuple(self.matcher_aliases, "matcher_aliases"))
        for field_name in ("tool_name", "tool_use_id"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")


@dataclass(frozen=True)
class PermissionRequestRequest:
    session_id: str
    turn_id: str
    subagent: JsonValue | None
    cwd: str
    transcript_path: str | None
    model: str
    permission_mode: str
    tool_name: str
    matcher_aliases: tuple[str, ...]
    run_id_suffix: str
    tool_input: JsonValue

    def __post_init__(self) -> None:
        _validate_request_base(self)
        object.__setattr__(self, "matcher_aliases", _string_tuple(self.matcher_aliases, "matcher_aliases"))
        for field_name in ("tool_name", "run_id_suffix"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")


@dataclass(frozen=True)
class SessionStartTarget:
    type: str
    source: str | None = None
    turn_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None

    @classmethod
    def session_start(cls, source: str) -> "SessionStartTarget":
        return cls("session_start", source=source)

    @classmethod
    def subagent_start(cls, *, turn_id: str, agent_id: str, agent_type: str) -> "SessionStartTarget":
        return cls("subagent_start", turn_id=turn_id, agent_id=agent_id, agent_type=agent_type)

    def __post_init__(self) -> None:
        if self.type == "session_start":
            if not isinstance(self.source, str):
                raise TypeError("session_start target requires source")
            if self.turn_id is not None or self.agent_id is not None or self.agent_type is not None:
                raise ValueError("session_start target must not include subagent fields")
            return
        if self.type == "subagent_start":
            for field_name in ("turn_id", "agent_id", "agent_type"):
                if not isinstance(getattr(self, field_name), str):
                    raise TypeError(f"subagent_start target requires {field_name}")
            if self.source is not None:
                raise ValueError("subagent_start target must not include source")
            return
        raise ValueError(f"unknown session-start target type: {self.type}")


@dataclass(frozen=True)
class StopTarget:
    type: str
    agent_id: str | None = None
    agent_type: str | None = None
    agent_transcript_path: str | None = None

    @classmethod
    def stop(cls) -> "StopTarget":
        return cls("stop")

    @classmethod
    def subagent_stop(
        cls,
        *,
        agent_id: str,
        agent_type: str,
        agent_transcript_path: str | None = None,
    ) -> "StopTarget":
        return cls(
            "subagent_stop",
            agent_id=agent_id,
            agent_type=agent_type,
            agent_transcript_path=agent_transcript_path,
        )

    def __post_init__(self) -> None:
        if self.type == "stop":
            if self.agent_id is not None or self.agent_type is not None or self.agent_transcript_path is not None:
                raise ValueError("stop target must not include subagent fields")
            return
        if self.type == "subagent_stop":
            for field_name in ("agent_id", "agent_type"):
                if not isinstance(getattr(self, field_name), str):
                    raise TypeError(f"subagent_stop target requires {field_name}")
            if self.agent_transcript_path is not None and not isinstance(self.agent_transcript_path, str):
                raise TypeError("agent_transcript_path must be a string or None")
            return
        raise ValueError(f"unknown stop target type: {self.type}")


@dataclass(frozen=True)
class SessionStartRequest:
    session_id: str
    cwd: str
    transcript_path: str | None
    model: str
    permission_mode: str
    target: SessionStartTarget

    def __post_init__(self) -> None:
        for field_name in ("session_id", "cwd", "model", "permission_mode"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        if self.transcript_path is not None and not isinstance(self.transcript_path, str):
            raise TypeError("transcript_path must be a string or None")
        if not isinstance(self.target, SessionStartTarget):
            raise TypeError("target must be SessionStartTarget")


@dataclass(frozen=True)
class UserPromptSubmitRequest:
    session_id: str
    turn_id: str
    subagent: JsonValue | None
    cwd: str
    transcript_path: str | None
    model: str
    permission_mode: str
    prompt: str

    def __post_init__(self) -> None:
        _validate_request_base(self)
        if not isinstance(self.prompt, str):
            raise TypeError("prompt must be a string")


@dataclass(frozen=True)
class StopRequest:
    session_id: str
    turn_id: str
    cwd: str
    transcript_path: str | None
    model: str
    permission_mode: str
    stop_hook_active: bool
    last_assistant_message: str | None
    target: StopTarget

    def __post_init__(self) -> None:
        _validate_request_base(self)
        if not isinstance(self.stop_hook_active, bool):
            raise TypeError("stop_hook_active must be a bool")
        if self.last_assistant_message is not None and not isinstance(self.last_assistant_message, str):
            raise TypeError("last_assistant_message must be a string or None")
        if not isinstance(self.target, StopTarget):
            raise TypeError("target must be StopTarget")


@dataclass(frozen=True)
class PreCompactRequest:
    session_id: str
    turn_id: str
    subagent: JsonValue | None
    cwd: str
    transcript_path: str | None
    model: str
    trigger: str

    def __post_init__(self) -> None:
        _validate_compact_request(self)


@dataclass(frozen=True)
class PostCompactRequest:
    session_id: str
    turn_id: str
    subagent: JsonValue | None
    cwd: str
    transcript_path: str | None
    model: str
    trigger: str

    def __post_init__(self) -> None:
        _validate_compact_request(self)


@dataclass(frozen=True)
class HookRuntimeOutcome:
    should_stop: bool = False
    additional_contexts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.should_stop, bool):
            raise TypeError("should_stop must be a bool")
        object.__setattr__(self, "additional_contexts", _string_tuple(self.additional_contexts, "additional_contexts"))


@dataclass(frozen=True)
class PreToolUseHookResult:
    type: str
    updated_input: JsonValue | None = None
    message: str | None = None

    @classmethod
    def continue_(cls, updated_input: JsonValue | None = None) -> "PreToolUseHookResult":
        return cls("continue", updated_input=updated_input)

    @classmethod
    def blocked(cls, message: str) -> "PreToolUseHookResult":
        return cls("blocked", message=message)

    def __post_init__(self) -> None:
        if self.type == "continue":
            if self.message is not None:
                raise ValueError("continue result must not include message")
            return
        if self.type == "blocked":
            if not isinstance(self.message, str):
                raise TypeError("blocked result requires message")
            if self.updated_input is not None:
                raise ValueError("blocked result must not include updated_input")
            return
        raise ValueError(f"unknown pre-tool-use hook result type: {self.type}")


@dataclass(frozen=True)
class PostToolUseHookOutcome:
    should_stop: bool = False
    feedback_message: str | None = None
    stop_reason: str | None = None
    additional_contexts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.should_stop, bool):
            raise TypeError("should_stop must be a bool")
        if self.feedback_message is not None and not isinstance(self.feedback_message, str):
            raise TypeError("feedback_message must be a string or None")
        if self.stop_reason is not None and not isinstance(self.stop_reason, str):
            raise TypeError("stop_reason must be a string or None")
        object.__setattr__(self, "additional_contexts", _string_tuple(self.additional_contexts, "additional_contexts"))


@dataclass(frozen=True)
class PreCompactHookOutcome:
    type: str
    reason: str | None = None

    @classmethod
    def continue_(cls) -> "PreCompactHookOutcome":
        return cls("continue")

    @classmethod
    def stopped(cls, reason: str | None = None) -> "PreCompactHookOutcome":
        return cls("stopped", reason)

    def __post_init__(self) -> None:
        if self.type == "continue":
            if self.reason is not None:
                raise ValueError("continue compact outcome must not include reason")
            return
        if self.type == "stopped":
            if self.reason is not None and not isinstance(self.reason, str):
                raise TypeError("reason must be a string or None")
            return
        raise ValueError(f"unknown pre-compact hook outcome type: {self.type}")


@dataclass(frozen=True)
class PostCompactHookOutcome:
    type: str

    @classmethod
    def continue_(cls) -> "PostCompactHookOutcome":
        return cls("continue")

    @classmethod
    def stopped(cls) -> "PostCompactHookOutcome":
        return cls("stopped")

    def __post_init__(self) -> None:
        if self.type not in {"continue", "stopped"}:
            raise ValueError(f"unknown post-compact hook outcome type: {self.type}")


def pre_tool_use_result_from_outcome(
    outcome: Any,
    *,
    tool_name: HookToolName,
    tool_input: JsonValue,
) -> PreToolUseHookResult:
    if not isinstance(tool_name, HookToolName):
        raise TypeError("tool_name must be HookToolName")
    should_block = bool(_field(outcome, "should_block", False))
    block_reason = _field(outcome, "block_reason", None)
    updated_input = _field(outcome, "updated_input", None)
    if not should_block:
        return PreToolUseHookResult.continue_(updated_input)
    if block_reason is None:
        return PreToolUseHookResult.continue_(None)
    if not isinstance(block_reason, str):
        raise TypeError("block_reason must be a string or None")
    return PreToolUseHookResult.blocked(
        blocked_pre_tool_use_message(
            tool_name=tool_name,
            tool_input=tool_input,
            reason=block_reason,
        )
    )


def build_pre_tool_use_request(
    context: HookRequestContext,
    *,
    tool_use_id: str,
    tool_name: HookToolName,
    tool_input: JsonValue,
) -> PreToolUseRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    if not isinstance(tool_name, HookToolName):
        raise TypeError("tool_name must be HookToolName")
    if not isinstance(tool_use_id, str):
        raise TypeError("tool_use_id must be a string")
    return PreToolUseRequest(
        session_id=context.session_id,
        turn_id=context.turn_id,
        subagent=context.subagent,
        cwd=context.cwd,
        transcript_path=context.transcript_path,
        model=context.model,
        permission_mode=context.permission_mode,
        tool_name=tool_name.name,
        matcher_aliases=tool_name.matcher_aliases,
        tool_use_id=tool_use_id,
        tool_input=tool_input,
    )


def build_post_tool_use_request(
    context: HookRequestContext,
    *,
    tool_use_id: str,
    tool_name: HookToolName | str,
    matcher_aliases: tuple[str, ...] | list[str] = (),
    tool_input: JsonValue,
    tool_response: JsonValue,
) -> PostToolUseRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    if isinstance(tool_name, HookToolName):
        name = tool_name.name
        aliases = tool_name.matcher_aliases if matcher_aliases == () else matcher_aliases
    elif isinstance(tool_name, str):
        name = tool_name
        aliases = matcher_aliases
    else:
        raise TypeError("tool_name must be HookToolName or string")
    if not isinstance(tool_use_id, str):
        raise TypeError("tool_use_id must be a string")
    return PostToolUseRequest(
        session_id=context.session_id,
        turn_id=context.turn_id,
        subagent=context.subagent,
        cwd=context.cwd,
        transcript_path=context.transcript_path,
        model=context.model,
        permission_mode=context.permission_mode,
        tool_name=name,
        matcher_aliases=_string_tuple(aliases, "matcher_aliases"),
        tool_use_id=tool_use_id,
        tool_input=tool_input,
        tool_response=tool_response,
    )


def build_permission_request_request(
    context: HookRequestContext,
    *,
    run_id_suffix: str,
    tool_name: HookToolName,
    tool_input: JsonValue,
) -> PermissionRequestRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    if not isinstance(tool_name, HookToolName):
        raise TypeError("tool_name must be HookToolName")
    if not isinstance(run_id_suffix, str):
        raise TypeError("run_id_suffix must be a string")
    return PermissionRequestRequest(
        session_id=context.session_id,
        turn_id=context.turn_id,
        subagent=context.subagent,
        cwd=context.cwd,
        transcript_path=context.transcript_path,
        model=context.model,
        permission_mode=context.permission_mode,
        tool_name=tool_name.name,
        matcher_aliases=tool_name.matcher_aliases,
        run_id_suffix=run_id_suffix,
        tool_input=tool_input,
    )


def hook_permission_mode(approval_policy: Any) -> str:
    value = approval_policy
    if hasattr(value, "value"):
        candidate = value.value
        value = candidate() if callable(candidate) else candidate
    if isinstance(value, str) and value.lower() == "never":
        return "bypassPermissions"
    return "default"


def build_session_start_request(
    context: HookRequestContext,
    *,
    target: SessionStartTarget,
) -> SessionStartRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    if not isinstance(target, SessionStartTarget):
        raise TypeError("target must be SessionStartTarget")
    return SessionStartRequest(
        session_id=context.session_id,
        cwd=context.cwd,
        transcript_path=context.transcript_path,
        model=context.model,
        permission_mode=context.permission_mode,
        target=target,
    )


def build_user_prompt_submit_request(
    context: HookRequestContext,
    *,
    prompt: str,
) -> UserPromptSubmitRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    return UserPromptSubmitRequest(
        session_id=context.session_id,
        turn_id=context.turn_id,
        subagent=context.subagent,
        cwd=context.cwd,
        transcript_path=context.transcript_path,
        model=context.model,
        permission_mode=context.permission_mode,
        prompt=prompt,
    )


def build_stop_request(
    context: HookRequestContext,
    *,
    stop_hook_active: bool,
    last_assistant_message: str | None,
    target: StopTarget,
    transcript_path: str | None = None,
) -> StopRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    if not isinstance(target, StopTarget):
        raise TypeError("target must be StopTarget")
    return StopRequest(
        session_id=context.session_id,
        turn_id=context.turn_id,
        cwd=context.cwd,
        transcript_path=context.transcript_path if transcript_path is None else transcript_path,
        model=context.model,
        permission_mode=context.permission_mode,
        stop_hook_active=stop_hook_active,
        last_assistant_message=last_assistant_message,
        target=target,
    )


def build_pre_compact_request(
    context: HookRequestContext,
    *,
    trigger: str,
) -> PreCompactRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    trigger = compaction_trigger_label(trigger)
    return PreCompactRequest(
        session_id=context.session_id,
        turn_id=context.turn_id,
        subagent=context.subagent,
        cwd=context.cwd,
        transcript_path=context.transcript_path,
        model=context.model,
        trigger=trigger,
    )


def build_post_compact_request(
    context: HookRequestContext,
    *,
    trigger: str,
) -> PostCompactRequest:
    if not isinstance(context, HookRequestContext):
        raise TypeError("context must be HookRequestContext")
    trigger = compaction_trigger_label(trigger)
    return PostCompactRequest(
        session_id=context.session_id,
        turn_id=context.turn_id,
        subagent=context.subagent,
        cwd=context.cwd,
        transcript_path=context.transcript_path,
        model=context.model,
        trigger=trigger,
    )


def compaction_trigger_label(trigger: Any) -> str:
    value = trigger
    if hasattr(value, "value"):
        candidate = value.value
        value = candidate() if callable(candidate) else candidate
    if not isinstance(value, str):
        raise TypeError("trigger must be a string")
    lowered = value.lower()
    if lowered in {"manual", "auto"}:
        return lowered
    raise ValueError(f"unknown compaction trigger: {value}")


def blocked_pre_tool_use_message(
    *,
    tool_name: HookToolName,
    tool_input: JsonValue,
    reason: str,
) -> str:
    if not isinstance(tool_name, HookToolName):
        raise TypeError("tool_name must be HookToolName")
    if not isinstance(reason, str):
        raise TypeError("reason must be a string")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if tool_name.name in {"Bash", "apply_patch"} and isinstance(command, str):
        return f"Command blocked by PreToolUse hook: {reason}. Command: {command}"
    return f"Tool call blocked by PreToolUse hook: {reason}. Tool: {tool_name.name}"


def post_tool_use_replacement_text(outcome: PostToolUseHookOutcome) -> str | None:
    if not isinstance(outcome, PostToolUseHookOutcome):
        raise TypeError("outcome must be PostToolUseHookOutcome")
    if outcome.should_stop:
        return (
            outcome.feedback_message
            or outcome.stop_reason
            or "PostToolUse hook stopped execution"
        )
    return outcome.feedback_message


def pre_compact_outcome_from_hook(should_stop: bool, reason: str | None = None) -> PreCompactHookOutcome:
    if not isinstance(should_stop, bool):
        raise TypeError("should_stop must be a bool")
    return PreCompactHookOutcome.stopped(reason) if should_stop else PreCompactHookOutcome.continue_()


def post_compact_outcome_from_hook(should_stop: bool) -> PostCompactHookOutcome:
    if not isinstance(should_stop, bool):
        raise TypeError("should_stop must be a bool")
    return PostCompactHookOutcome.stopped() if should_stop else PostCompactHookOutcome.continue_()


def additional_context_messages(additional_contexts: tuple[str, ...] | list[str]) -> tuple[ResponseItem, ...]:
    return tuple(HookAdditionalContext.new(text).into_response_item() for text in _string_tuple(additional_contexts, "additional_contexts"))


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _validate_request_base(value: Any) -> None:
    for field_name in ("session_id", "turn_id", "cwd", "model", "permission_mode"):
        if not isinstance(getattr(value, field_name), str):
            raise TypeError(f"{field_name} must be a string")
    transcript_path = getattr(value, "transcript_path")
    if transcript_path is not None and not isinstance(transcript_path, str):
        raise TypeError("transcript_path must be a string or None")


def _validate_compact_request(value: Any) -> None:
    for field_name in ("session_id", "turn_id", "cwd", "model", "trigger"):
        if not isinstance(getattr(value, field_name), str):
            raise TypeError(f"{field_name} must be a string")
    transcript_path = getattr(value, "transcript_path")
    if transcript_path is not None and not isinstance(transcript_path, str):
        raise TypeError("transcript_path must be a string or None")


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be a tuple or list of strings")
    output = tuple(value)
    if not all(isinstance(item, str) for item in output):
        raise TypeError(f"{field_name} must contain only strings")
    return output


__all__ = [
    "HookRequestContext",
    "HookRuntimeOutcome",
    "PermissionRequestRequest",
    "PostCompactHookOutcome",
    "PostCompactRequest",
    "PostToolUseHookOutcome",
    "PostToolUseRequest",
    "PreCompactHookOutcome",
    "PreCompactRequest",
    "PreToolUseRequest",
    "PreToolUseHookResult",
    "SessionStartRequest",
    "SessionStartTarget",
    "StopRequest",
    "StopTarget",
    "UserPromptSubmitRequest",
    "additional_context_messages",
    "blocked_pre_tool_use_message",
    "build_permission_request_request",
    "build_post_compact_request",
    "build_post_tool_use_request",
    "build_pre_compact_request",
    "build_pre_tool_use_request",
    "build_session_start_request",
    "build_stop_request",
    "build_user_prompt_submit_request",
    "compaction_trigger_label",
    "hook_permission_mode",
    "post_compact_outcome_from_hook",
    "post_tool_use_replacement_text",
    "pre_compact_outcome_from_hook",
    "pre_tool_use_result_from_outcome",
]
