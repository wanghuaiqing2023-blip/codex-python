"""Python port of the public ``codex-hooks`` crate surface."""

from __future__ import annotations

from pycodex.protocol import HookEventName

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
    return HookEventName(event_name).value.replace("-", "_").lower()


def hook_key(
    key_source: str,
    event_name: HookEventName | str,
    group_index: int,
    handler_index: int,
) -> str:
    return f"{key_source}:{hook_event_key_label(event_name)}:{group_index}:{handler_index}"


from .config_rules import hook_states_from_stack
from .declarations import PluginHookDeclaration, plugin_hook_declarations
from .engine import HookListEntry
from .events.common import SubagentHookContext
from .events.compact import (
    PostCompactRequest,
    PreCompactOutcome,
    PreCompactRequest,
    StatelessHookOutcome,
)
from .events.permission_request import (
    PermissionRequestDecision,
    PermissionRequestOutcome,
    PermissionRequestRequest,
)
from .events.post_tool_use import PostToolUseOutcome, PostToolUseRequest
from .events.pre_tool_use import PreToolUseOutcome, PreToolUseRequest
from .events.session_start import (
    SessionStartOutcome,
    SessionStartRequest,
    SessionStartSource,
    StartHookTarget,
)
from .events.stop import StopHookTarget, StopOutcome, StopRequest
from .events.user_prompt_submit import (
    UserPromptSubmitOutcome,
    UserPromptSubmitRequest,
)
from .legacy_notify import legacy_notify_json, notify_hook
from .registry import (
    HookListOutcome,
    Hooks,
    HooksConfig,
    command_from_argv,
    list_hooks,
)
from .schema import write_schema_fixtures
from .types import (
    Hook,
    HookEvent,
    HookEventAfterAgent,
    HookPayload,
    HookResponse,
    HookResult,
)

__all__ = [
    "HOOK_EVENT_NAMES",
    "HOOK_EVENT_NAMES_WITH_MATCHERS",
    "Hook",
    "HookEvent",
    "HookEventAfterAgent",
    "HookListEntry",
    "HookListOutcome",
    "HookPayload",
    "HookResponse",
    "HookResult",
    "Hooks",
    "HooksConfig",
    "PluginHookDeclaration",
    "PostCompactRequest",
    "PostToolUseOutcome",
    "PostToolUseRequest",
    "PreCompactOutcome",
    "PreCompactRequest",
    "PreToolUseOutcome",
    "PreToolUseRequest",
    "PermissionRequestDecision",
    "PermissionRequestOutcome",
    "PermissionRequestRequest",
    "SessionStartOutcome",
    "SessionStartRequest",
    "SessionStartSource",
    "StartHookTarget",
    "StatelessHookOutcome",
    "StopHookTarget",
    "StopOutcome",
    "StopRequest",
    "SubagentHookContext",
    "UserPromptSubmitOutcome",
    "UserPromptSubmitRequest",
    "command_from_argv",
    "hook_event_key_label",
    "hook_key",
    "hook_states_from_stack",
    "legacy_notify_json",
    "list_hooks",
    "notify_hook",
    "plugin_hook_declarations",
    "write_schema_fixtures",
]
