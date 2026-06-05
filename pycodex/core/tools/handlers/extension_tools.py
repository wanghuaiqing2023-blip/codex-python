"""Extension tool adapter ported from Codex core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import ToolExposure, ToolInvocation
from pycodex.core.tools.router import ConversationHistory, ToolCall
from pycodex.protocol import ResponseItem, ToolName, TruncationPolicyConfig

JsonValue = Any


@dataclass(frozen=True)
class ExtensionTurnContext:
    turn_id: str = ""
    truncation_policy: TruncationPolicyConfig | None = None
    conversation_history: ConversationHistory = field(default_factory=ConversationHistory)

    def __post_init__(self) -> None:
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if self.truncation_policy is None:
            object.__setattr__(self, "truncation_policy", TruncationPolicyConfig.tokens(10_000))
        elif not isinstance(self.truncation_policy, TruncationPolicyConfig):
            raise TypeError("truncation_policy must be TruncationPolicyConfig or None")
        if not isinstance(self.conversation_history, ConversationHistory):
            raise TypeError("conversation_history must be ConversationHistory")

    @classmethod
    def from_items(
        cls,
        *,
        turn_id: str = "",
        truncation_policy: TruncationPolicyConfig | None = None,
        items: Iterable[ResponseItem | JsonValue] = (),
    ) -> "ExtensionTurnContext":
        return cls(turn_id, truncation_policy, ConversationHistory(tuple(items)))


class ExtensionToolAdapter:
    """Adapts an extension executor to the core tool runtime protocol."""

    def __init__(
        self,
        executor: Any,
        *,
        turn_context: ExtensionTurnContext | None = None,
    ) -> None:
        _extension_tool_name(executor)
        self.executor = executor
        self.turn_context = turn_context or ExtensionTurnContext()

    @classmethod
    def new(cls, executor: Any, *, turn_context: ExtensionTurnContext | None = None) -> "ExtensionToolAdapter":
        return cls(executor, turn_context=turn_context)

    def tool_name(self) -> ToolName:
        return _extension_tool_name(self.executor)

    def spec(self) -> JsonValue:
        return _call_or_get(self.executor, "spec", None)

    def exposure(self) -> ToolExposure:
        return ToolExposure.from_value(_call_or_get(self.executor, "exposure", ToolExposure.DIRECT))

    def supports_parallel_tool_calls(self) -> bool:
        value = _call_or_get(self.executor, "supports_parallel_tool_calls", False)
        if not isinstance(value, bool):
            raise TypeError("supports_parallel_tool_calls must return a bool")
        return value

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type == "function"

    def handle(self, invocation_or_payload: ToolInvocation | ToolPayload) -> Any:
        if isinstance(invocation_or_payload, ToolInvocation):
            call = to_extension_call(invocation_or_payload, self.turn_context)
        elif isinstance(invocation_or_payload, ToolPayload):
            call = ToolCall(
                tool_name=self.tool_name(),
                call_id="",
                payload=invocation_or_payload,
                turn_id=self.turn_context.turn_id,
                truncation_policy=self.turn_context.truncation_policy,
                conversation_history=self.turn_context.conversation_history,
            )
        else:
            raise TypeError("invocation must be ToolInvocation or ToolPayload")
        return self.executor.handle(call)


def to_extension_call(invocation: ToolInvocation, turn_context: ExtensionTurnContext) -> ToolCall:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    if not isinstance(turn_context, ExtensionTurnContext):
        raise TypeError("turn_context must be ExtensionTurnContext")
    return ToolCall(
        tool_name=invocation.tool_name,
        call_id=invocation.call_id,
        payload=invocation.payload,
        turn_id=turn_context.turn_id,
        truncation_policy=turn_context.truncation_policy,
        conversation_history=turn_context.conversation_history,
    )


def _extension_tool_name(executor: Any) -> ToolName:
    value = _call_or_get(executor, "tool_name", None)
    if value is None:
        value = _call_or_get(executor, "name", None)
    try:
        return ToolName.from_value(value)
    except TypeError as err:
        raise TypeError("extension executor must expose a ToolName via tool_name() or name") from err


def _call_or_get(target: Any, name: str, default: Any) -> Any:
    value = getattr(target, name, default)
    if callable(value):
        return value()
    return value


__all__ = [
    "ExtensionToolAdapter",
    "ExtensionTurnContext",
    "to_extension_call",
]
