"""Python port of ``codex-hooks::engine.output_parser``."""


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

from ..events.common import non_empty_string


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


def _pre_tool_use_invalid_universal(parsed: Mapping[str, Any]) -> str | None:
    if parsed.get("continue", True) is False:
        return "PreToolUse hook returned unsupported continue:false"
    if parsed.get("stopReason") is not None:
        return "PreToolUse hook returned unsupported stopReason"
    if parsed.get("suppressOutput", False) is True:
        return "PreToolUse hook returned unsupported suppressOutput"
    return None


@dataclass(frozen=True)
class UniversalOutput:
    continue_processing: bool = True
    stop_reason: str | None = None
    suppress_output: bool = False
    system_message: str | None = None


@dataclass(frozen=True)
class SessionStartOutput:
    universal: UniversalOutput
    additional_context: str | None = None


@dataclass(frozen=True)
class PreToolUseOutput:
    universal: UniversalOutput
    block_reason: str | None = None
    additional_context: str | None = None
    updated_input: Any | None = None
    invalid_reason: str | None = None


@dataclass(frozen=True)
class PermissionRequestOutput:
    universal: UniversalOutput
    decision: "PermissionRequestDecision | None" = None
    invalid_reason: str | None = None


@dataclass(frozen=True)
class PostToolUseOutput:
    universal: UniversalOutput
    should_block: bool = False
    reason: str | None = None
    invalid_block_reason: str | None = None
    additional_context: str | None = None
    invalid_reason: str | None = None


@dataclass(frozen=True)
class UserPromptSubmitOutput:
    universal: UniversalOutput
    should_block: bool = False
    reason: str | None = None
    invalid_block_reason: str | None = None
    additional_context: str | None = None


@dataclass(frozen=True)
class StopOutput:
    universal: UniversalOutput
    should_block: bool = False
    reason: str | None = None
    invalid_block_reason: str | None = None


@dataclass(frozen=True)
class PreCompactOutput:
    universal: UniversalOutput
    invalid_reason: str | None = None


@dataclass(frozen=True)
class StatelessHookOutput:
    universal: UniversalOutput
    invalid_reason: str | None = None


_UNIVERSAL_OUTPUT_FIELDS = {"continue", "stopReason", "suppressOutput", "systemMessage"}


_HOOK_EVENT_NAME_WIRE_VALUES = {
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
}


def looks_like_json(stdout: str) -> bool:
    return _looks_like_json(stdout)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _output_parser_trimmed_reason(reason: Any) -> str | None:
    if not isinstance(reason, str):
        return None
    trimmed = reason.strip()
    return trimmed or None


def _invalid_block_message(event_name: str) -> str:
    return f"{event_name} hook returned decision:block without a non-empty reason"


def _wire_object(
    stdout: str,
    allowed_fields: set[str],
    hook_specific_allowed: set[str] | None = None,
    decision_allowed: set[str] | None = None,
    top_level_decisions: set[str] | None = None,
) -> Mapping[str, Any] | None:
    parsed = parse_hook_json_output(stdout.strip())
    if parsed is None:
        return None
    if not set(parsed).issubset(_UNIVERSAL_OUTPUT_FIELDS | allowed_fields):
        return None
    if "continue" in parsed and not isinstance(parsed["continue"], bool):
        return None
    if "suppressOutput" in parsed and not isinstance(parsed["suppressOutput"], bool):
        return None
    if "stopReason" in parsed and parsed["stopReason"] is not None and not isinstance(parsed["stopReason"], str):
        return None
    if (
        "systemMessage" in parsed
        and parsed["systemMessage"] is not None
        and not isinstance(parsed["systemMessage"], str)
    ):
        return None
    if "decision" in parsed:
        decision = parsed["decision"]
        if top_level_decisions is not None and decision is not None and decision not in top_level_decisions:
            return None
    if "reason" in parsed and parsed["reason"] is not None and not isinstance(parsed["reason"], str):
        return None
    specific = parsed.get("hookSpecificOutput")
    if specific is not None:
        if hook_specific_allowed is None or not isinstance(specific, Mapping):
            return None
        if not set(specific).issubset(hook_specific_allowed):
            return None
        hook_event_name = specific.get("hookEventName")
        if hook_event_name not in _HOOK_EVENT_NAME_WIRE_VALUES:
            return None
        if "additionalContext" in specific and specific["additionalContext"] is not None and not isinstance(specific["additionalContext"], str):
            return None
        if "permissionDecision" in specific:
            permission_decision = specific["permissionDecision"]
            if permission_decision is not None and permission_decision not in {"allow", "deny", "ask"}:
                return None
        if (
            "permissionDecisionReason" in specific
            and specific["permissionDecisionReason"] is not None
            and not isinstance(specific["permissionDecisionReason"], str)
        ):
            return None
        decision_value = specific.get("decision")
        if decision_value is not None:
            if not isinstance(decision_value, Mapping):
                return None
            if decision_allowed is None or not set(decision_value).issubset(decision_allowed):
                return None
            behavior = decision_value.get("behavior")
            if behavior not in {"allow", "deny"}:
                return None
            if "message" in decision_value and decision_value["message"] is not None and not isinstance(decision_value["message"], str):
                return None
            if "interrupt" in decision_value and not isinstance(decision_value["interrupt"], bool):
                return None
    return parsed


def _universal_output(parsed: Mapping[str, Any]) -> UniversalOutput:
    return UniversalOutput(
        continue_processing=parsed.get("continue", True),
        stop_reason=_string_or_none(parsed.get("stopReason")),
        suppress_output=parsed.get("suppressOutput", False),
        system_message=_string_or_none(parsed.get("systemMessage")),
    )


def parse_session_start(stdout: str) -> SessionStartOutput | None:
    parsed = _wire_object(
        stdout,
        {"hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "additionalContext"},
    )
    if parsed is None:
        return None
    specific = parsed.get("hookSpecificOutput")
    additional_context = specific.get("additionalContext") if isinstance(specific, Mapping) else None
    return SessionStartOutput(_universal_output(parsed), _string_or_none(additional_context))


def parse_subagent_start(stdout: str) -> SessionStartOutput | None:
    return parse_session_start(stdout)


def parse_pre_tool_use(stdout: str) -> PreToolUseOutput | None:
    parsed = _wire_object(
        stdout,
        {"decision", "reason", "hookSpecificOutput"},
        hook_specific_allowed={
            "hookEventName",
            "permissionDecision",
            "permissionDecisionReason",
            "updatedInput",
            "additionalContext",
        },
        top_level_decisions={"approve", "block"},
    )
    if parsed is None:
        return None
    universal = _universal_output(parsed)
    specific = parsed.get("hookSpecificOutput")
    specific_mapping = specific if isinstance(specific, Mapping) else None
    additional_context = specific_mapping.get("additionalContext") if specific_mapping is not None else None
    use_hook_specific_decision = specific_mapping is not None and (
        specific_mapping.get("permissionDecision") is not None
        or specific_mapping.get("permissionDecisionReason") is not None
        or specific_mapping.get("updatedInput") is not None
    )
    invalid_reason = _pre_tool_use_invalid_universal(parsed)
    if invalid_reason is None:
        if use_hook_specific_decision and specific_mapping is not None:
            invalid_reason = _pre_tool_use_unsupported_hook_specific(specific_mapping)
        else:
            invalid_reason = _pre_tool_use_unsupported_legacy_decision(
                parsed.get("decision"),
                parsed.get("reason"),
            )
    block_reason = None
    updated_input = None
    if invalid_reason is None:
        if use_hook_specific_decision and specific_mapping is not None:
            if specific_mapping.get("permissionDecision") == "deny":
                block_reason = _output_parser_trimmed_reason(specific_mapping.get("permissionDecisionReason"))
            elif specific_mapping.get("permissionDecision") == "allow":
                updated_input = specific_mapping.get("updatedInput")
        elif parsed.get("decision") == "block":
            block_reason = _output_parser_trimmed_reason(parsed.get("reason"))
    return PreToolUseOutput(
        universal=universal,
        block_reason=block_reason,
        additional_context=_string_or_none(additional_context),
        updated_input=updated_input,
        invalid_reason=invalid_reason,
    )


def parse_permission_request(stdout: str) -> PermissionRequestOutput | None:
    parsed = _wire_object(
        stdout,
        {"hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "decision"},
        decision_allowed={"behavior", "updatedInput", "updatedPermissions", "message", "interrupt"},
    )
    if parsed is None:
        return None
    universal = _universal_output(parsed)
    specific = parsed.get("hookSpecificOutput")
    decision_mapping = None
    if isinstance(specific, Mapping):
        raw_decision = specific.get("decision")
        decision_mapping = raw_decision if isinstance(raw_decision, Mapping) else None
    invalid_reason = _permission_request_invalid_universal(parsed)
    if invalid_reason is None:
        invalid_reason = _permission_request_invalid_decision(decision_mapping)
    decision = _permission_request_decision(decision_mapping) if invalid_reason is None and decision_mapping is not None else None
    return PermissionRequestOutput(universal, decision, invalid_reason)


def parse_post_tool_use(stdout: str) -> PostToolUseOutput | None:
    parsed = _wire_object(
        stdout,
        {"decision", "reason", "hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "additionalContext", "updatedMCPToolOutput"},
        top_level_decisions={"block"},
    )
    if parsed is None:
        return None
    universal = _universal_output(parsed)
    invalid_reason = _post_tool_use_invalid_universal(parsed)
    specific = parsed.get("hookSpecificOutput")
    specific_mapping = specific if isinstance(specific, Mapping) else None
    if invalid_reason is None and specific_mapping is not None and specific_mapping.get("updatedMCPToolOutput") is not None:
        invalid_reason = "PostToolUse hook returned unsupported updatedMCPToolOutput"
    should_block_candidate = parsed.get("decision") == "block"
    invalid_block_reason = None
    if should_block_candidate and _output_parser_trimmed_reason(parsed.get("reason")) is None:
        invalid_block_reason = _invalid_block_message("PostToolUse")
    elif not should_block_candidate and universal.continue_processing and parsed.get("reason") is not None:
        invalid_block_reason = "PostToolUse hook returned reason without decision"
    additional_context = specific_mapping.get("additionalContext") if specific_mapping is not None else None
    return PostToolUseOutput(
        universal=universal,
        should_block=should_block_candidate and invalid_reason is None and invalid_block_reason is None,
        reason=_string_or_none(parsed.get("reason")),
        invalid_block_reason=invalid_block_reason,
        additional_context=_string_or_none(additional_context),
        invalid_reason=invalid_reason,
    )


def parse_pre_compact(stdout: str) -> PreCompactOutput | None:
    parsed = _wire_object(stdout, set())
    return None if parsed is None else PreCompactOutput(_universal_output(parsed))


def parse_post_compact(stdout: str) -> StatelessHookOutput | None:
    parsed = _wire_object(stdout, set())
    return None if parsed is None else StatelessHookOutput(_universal_output(parsed))


def parse_user_prompt_submit(stdout: str) -> UserPromptSubmitOutput | None:
    parsed = _wire_object(
        stdout,
        {"decision", "reason", "hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "additionalContext"},
        top_level_decisions={"block"},
    )
    if parsed is None:
        return None
    should_block_candidate = parsed.get("decision") == "block"
    invalid_block_reason = (
        _invalid_block_message("UserPromptSubmit")
        if should_block_candidate and _output_parser_trimmed_reason(parsed.get("reason")) is None
        else None
    )
    specific = parsed.get("hookSpecificOutput")
    additional_context = specific.get("additionalContext") if isinstance(specific, Mapping) else None
    return UserPromptSubmitOutput(
        universal=_universal_output(parsed),
        should_block=should_block_candidate and invalid_block_reason is None,
        reason=_string_or_none(parsed.get("reason")),
        invalid_block_reason=invalid_block_reason,
        additional_context=_string_or_none(additional_context),
    )


def _stop_output(parsed: Mapping[str, Any], event_name: str) -> StopOutput:
    should_block_candidate = parsed.get("decision") == "block"
    invalid_block_reason = (
        _invalid_block_message(event_name)
        if should_block_candidate and _output_parser_trimmed_reason(parsed.get("reason")) is None
        else None
    )
    return StopOutput(
        universal=_universal_output(parsed),
        should_block=should_block_candidate and invalid_block_reason is None,
        reason=_string_or_none(parsed.get("reason")),
        invalid_block_reason=invalid_block_reason,
    )


def parse_stop(stdout: str) -> StopOutput | None:
    parsed = _wire_object(stdout, {"decision", "reason"}, top_level_decisions={"block"})
    return None if parsed is None else _stop_output(parsed, "Stop")


def parse_subagent_stop(stdout: str) -> StopOutput | None:
    parsed = _wire_object(stdout, {"decision", "reason"}, top_level_decisions={"block"})
    return None if parsed is None else _stop_output(parsed, "SubagentStop")


def _pre_tool_use_unsupported_hook_specific(specific: Mapping[str, Any]) -> str | None:
    permission_decision = specific.get("permissionDecision")
    permission_reason = specific.get("permissionDecisionReason")
    has_updated_input = specific.get("updatedInput") is not None

    if has_updated_input and permission_decision != "allow":
        return "PreToolUse hook returned updatedInput without permissionDecision:allow"
    if permission_decision == "allow":
        if not has_updated_input:
            return "PreToolUse hook returned unsupported permissionDecision:allow"
    elif permission_decision == "ask":
        return "PreToolUse hook returned unsupported permissionDecision:ask"
    elif permission_decision == "deny":
        if non_empty_string(permission_reason) is None:
            return (
                "PreToolUse hook returned permissionDecision:deny without a non-empty "
                "permissionDecisionReason"
            )
    elif permission_decision is None:
        if permission_reason is not None:
            return "PreToolUse hook returned permissionDecisionReason without permissionDecision"
    return None


def _pre_tool_use_unsupported_legacy_decision(
    decision: Any,
    reason: Any,
) -> str | None:
    if decision == "approve":
        return "PreToolUse hook returned unsupported decision:approve"
    if decision == "block":
        if non_empty_string(reason) is None:
            return "PreToolUse hook returned decision:block without a non-empty reason"
    elif decision is None:
        if reason is not None:
            return "PreToolUse hook returned reason without decision"
    return None


def _permission_request_invalid_universal(parsed: Mapping[str, Any]) -> str | None:
    if parsed.get("continue", True) is False:
        return "PermissionRequest hook returned unsupported continue:false"
    if parsed.get("stopReason") is not None:
        return "PermissionRequest hook returned unsupported stopReason"
    if parsed.get("suppressOutput", False) is True:
        return "PermissionRequest hook returned unsupported suppressOutput"
    return None


def _permission_request_invalid_decision(decision: Mapping[str, Any] | None) -> str | None:
    if decision is None:
        return None
    if decision.get("updatedInput") is not None:
        return "PermissionRequest hook returned unsupported updatedInput"
    if decision.get("updatedPermissions") is not None:
        return "PermissionRequest hook returned unsupported updatedPermissions"
    if decision.get("interrupt", False) is True:
        return "PermissionRequest hook returned unsupported interrupt:true"
    return None


def _permission_request_decision(decision: Mapping[str, Any]) -> PermissionRequestDecision | None:
    behavior = decision.get("behavior")
    if behavior == "allow":
        return PermissionRequestDecision.Allow()
    if behavior == "deny":
        message = non_empty_string(decision.get("message")) or "PermissionRequest hook denied approval"
        return PermissionRequestDecision.Deny(message)
    return None


def _post_tool_use_invalid_universal(parsed: Mapping[str, Any]) -> str | None:
    if parsed.get("suppressOutput", False) is True:
        return "PostToolUse hook returned unsupported suppressOutput"
    return None


def _post_tool_use_invalid_hook_specific(specific: Mapping[str, Any] | None) -> str | None:
    if specific is not None and specific.get("updatedMCPToolOutput") is not None:
        return "PostToolUse hook returned unsupported updatedMCPToolOutput"
    return None


def _post_tool_use_invalid_block_reason(parsed: Mapping[str, Any]) -> str | None:
    should_block = parsed.get("decision") == "block"
    reason = parsed.get("reason")
    if should_block and non_empty_string(reason) is None:
        return "PostToolUse hook returned decision:block without a non-empty reason"
    if not should_block and parsed.get("continue", True) is True and reason is not None:
        return "PostToolUse hook returned reason without decision"
    return None


def looks_like_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def parse_hook_json_output(text: str) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return parsed
    return None
