"""Tool-call routing helpers ported from Codex core.

This module starts with the pure ``ToolRouter::build_tool_call`` logic from
``codex/codex-rs/core/src/tools/router.rs``.
"""

from __future__ import annotations

import json
import inspect
from dataclasses import dataclass, field
from typing import Any

from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tool_context import FunctionToolOutput, PostToolUseFeedbackOutput, ToolPayload
from pycodex.core.hook_runtime import (
    PostToolUseHookOutcome,
    PreToolUseHookResult,
    post_tool_use_replacement_text,
)
from pycodex.core.tool_lifecycle import ToolCallOutcome, notify_tool_finish, notify_tool_start
from pycodex.core.tool_registry import (
    PostToolUsePayload,
    PreToolUsePayload,
    ToolCallSource,
    ToolInvocation,
    ToolRegistry,
    unsupported_tool_call_message,
    with_updated_hook_input,
)
from pycodex.protocol import ResponseItem, SearchToolCallParams, ToolName, TruncationPolicyConfig

JsonValue = Any


@dataclass(frozen=True)
class ConversationHistory:
    items: tuple[ResponseItem, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.items, (str, bytes)):
            raise TypeError("items must be an iterable of ResponseItem values")
        object.__setattr__(
            self,
            "items",
            tuple(
                item if isinstance(item, ResponseItem) else ResponseItem.from_mapping(item)
                for item in self.items
            ),
        )


@dataclass(frozen=True)
class ToolCall:
    tool_name: ToolName
    call_id: str
    payload: ToolPayload
    turn_id: str = ""
    truncation_policy: TruncationPolicyConfig | None = None
    conversation_history: ConversationHistory = field(default_factory=ConversationHistory)

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, ToolName):
            raise TypeError("tool_name must be ToolName")
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if self.truncation_policy is not None and not isinstance(self.truncation_policy, TruncationPolicyConfig):
            raise TypeError("truncation_policy must be TruncationPolicyConfig or None")
        if not isinstance(self.conversation_history, ConversationHistory):
            raise TypeError("conversation_history must be ConversationHistory")

    def function_arguments(self) -> str:
        if self.payload.type == "function":
            if self.payload.arguments is None:
                raise FunctionCallError.fatal(
                    f"tool {self.tool_name} invoked with malformed function payload"
                )
            return self.payload.arguments
        raise FunctionCallError.fatal(
            f"tool {self.tool_name} invoked with incompatible payload"
        )


class ToolRouter:
    def __init__(
        self,
        model_visible_specs: tuple[JsonValue, ...] = (),
        registry: ToolRegistry | None = None,
    ) -> None:
        if not isinstance(model_visible_specs, tuple):
            raise TypeError("model_visible_specs must be a tuple")
        if registry is not None and not isinstance(registry, ToolRegistry):
            raise TypeError("registry must be ToolRegistry or None")
        self._model_visible_specs = tuple(model_visible_specs)
        self._registry = registry or ToolRegistry.empty()

    @classmethod
    def from_parts(
        cls,
        registry_or_specs: ToolRegistry | tuple[JsonValue, ...] | list[JsonValue],
        model_visible_specs: tuple[JsonValue, ...] | list[JsonValue] | None = None,
    ) -> "ToolRouter":
        if model_visible_specs is None:
            if not isinstance(registry_or_specs, (list, tuple)):
                raise TypeError("ToolRouter.from_parts(specs) requires a list or tuple")
            return cls(tuple(registry_or_specs))  # type: ignore[arg-type]
        if not isinstance(registry_or_specs, ToolRegistry):
            raise TypeError("ToolRouter.from_parts(registry, specs) requires a ToolRegistry")
        if not isinstance(model_visible_specs, (list, tuple)):
            raise TypeError("model_visible_specs must be a list or tuple")
        return cls(tuple(model_visible_specs), registry_or_specs)

    def model_visible_specs(self) -> tuple[JsonValue, ...]:
        return self._model_visible_specs

    def registered_tool_names_for_test(self) -> tuple[ToolName, ...]:
        return self._registry.tool_names_for_test()

    def tool_exposure_for_test(self, name: ToolName) -> Any:
        return self._registry.tool_exposure(name)

    def tool_supports_parallel(self, call: ToolCall) -> bool:
        return self._registry.supports_parallel_tool_calls(call.tool_name) or False

    def tool_waits_for_runtime_cancellation(self, call: ToolCall) -> bool:
        return self._registry.waits_for_runtime_cancellation(call.tool_name) or False

    def create_diff_consumer(self, tool_name: ToolName) -> Any:
        return self._registry.create_diff_consumer(tool_name)

    async def dispatch_tool_call_with_code_mode_result(
        self,
        call: ToolCall,
        *,
        source: ToolCallSource | None = None,
        lifecycle_contributors: Any = (),
        pre_tool_use_hook: Any = None,
        post_tool_use_hook: Any = None,
        terminal_outcome_reached: Any = None,
        **stores: Any,
    ) -> Any:
        return await self.dispatch_tool_call_with_terminal_outcome(
            call,
            source=source,
            lifecycle_contributors=lifecycle_contributors,
            pre_tool_use_hook=pre_tool_use_hook,
            post_tool_use_hook=post_tool_use_hook,
            terminal_outcome_reached=terminal_outcome_reached,
            **stores,
        )

    async def dispatch_tool_call_with_terminal_outcome(
        self,
        call: ToolCall,
        *,
        source: ToolCallSource | None = None,
        lifecycle_contributors: Any = (),
        pre_tool_use_hook: Any = None,
        post_tool_use_hook: Any = None,
        terminal_outcome_reached: Any = None,
        **stores: Any,
    ) -> Any:
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        invocation = ToolInvocation(
            call_id=call.call_id,
            tool_name=call.tool_name,
            source=source or ToolCallSource.direct(),
            payload=call.payload,
        )
        return await dispatch_tool_call_with_terminal_outcome(
            self._registry,
            invocation,
            lifecycle_contributors=lifecycle_contributors,
            pre_tool_use_hook=pre_tool_use_hook,
            post_tool_use_hook=post_tool_use_hook,
            terminal_outcome_reached=terminal_outcome_reached,
            **stores,
        )

    @staticmethod
    def build_tool_call(item: ResponseItem) -> ToolCall | None:
        return build_tool_call(item)


def build_tool_call(item: ResponseItem) -> ToolCall | None:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be ResponseItem")
    if item.type == "function_call":
        return ToolCall(
            tool_name=ToolName.new(item.namespace, item.name or ""),
            call_id=item.call_id or "",
            payload=ToolPayload.function(_function_arguments(item.arguments)),
        )

    if item.type == "tool_search_call":
        if item.call_id is None or item.execution != "client":
            return None
        return ToolCall(
            tool_name=ToolName.plain("tool_search"),
            call_id=item.call_id,
            payload=ToolPayload.tool_search(_search_arguments(item.arguments)),
        )

    if item.type == "custom_tool_call":
        return ToolCall(
            tool_name=ToolName.plain(item.name or ""),
            call_id=item.call_id or "",
            payload=ToolPayload.custom(item.input or ""),
        )

    return None


def _function_arguments(arguments: str | JsonValue | None) -> str:
    if isinstance(arguments, str):
        return arguments
    if arguments is None:
        return ""
    return json.dumps(arguments, separators=(",", ":"))


def _search_arguments(arguments: str | JsonValue | None) -> SearchToolCallParams:
    try:
        if isinstance(arguments, SearchToolCallParams):
            return arguments
        if isinstance(arguments, str):
            decoded = json.loads(arguments)
        elif arguments is None:
            decoded = {}
        else:
            decoded = arguments
        return SearchToolCallParams.from_mapping(decoded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse tool_search arguments: {err}"
        ) from err


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


async def dispatch_tool_call(
    registry: ToolRegistry,
    invocation: ToolInvocation,
    *,
    lifecycle_contributors: Any = (),
    pre_tool_use_hook: Any = None,
    post_tool_use_hook: Any = None,
    **stores: Any,
) -> Any:
    return await dispatch_tool_call_with_terminal_outcome(
        registry,
        invocation,
        lifecycle_contributors=lifecycle_contributors,
        pre_tool_use_hook=pre_tool_use_hook,
        post_tool_use_hook=post_tool_use_hook,
        terminal_outcome_reached=None,
        **stores,
    )


async def dispatch_tool_call_with_terminal_outcome(
    registry: ToolRegistry,
    invocation: ToolInvocation,
    *,
    lifecycle_contributors: Any = (),
    pre_tool_use_hook: Any = None,
    post_tool_use_hook: Any = None,
    terminal_outcome_reached: Any = None,
    **stores: Any,
) -> Any:
    if not isinstance(registry, ToolRegistry):
        raise TypeError("registry must be ToolRegistry")
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    tool = registry.tool(invocation.tool_name)
    if tool is None:
        raise FunctionCallError.respond_to_model(
            unsupported_tool_call_message(invocation.payload, invocation.tool_name)
        )
    if not (registry.matches_kind(invocation.tool_name, invocation.payload) or False):
        raise FunctionCallError.fatal(
            f"tool {invocation.tool_name} invoked with incompatible payload"
        )

    await notify_tool_start(lifecycle_contributors, invocation, **stores)
    try:
        invocation = await _apply_pre_tool_use_hook(
            tool,
            invocation,
            pre_tool_use_hook,
            lifecycle_contributors=lifecycle_contributors,
            terminal_outcome_reached=terminal_outcome_reached,
            **stores,
        )
    except FunctionCallError:
        raise
    handler_executed = False
    try:
        handler_executed = True
        output = await _handle_tool(tool, invocation)
    except FunctionCallError as err:
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(handler_executed),
            **stores,
        )
        raise err
    except Exception as err:
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(handler_executed),
            **stores,
        )
        raise FunctionCallError.fatal(str(err)) from err

    from pycodex.core.tool_parallel import ToolCallResult

    result = ToolCallResult(
        call_id=invocation.call_id,
        payload=invocation.payload,
        result=output,
        post_tool_use_payload=_tool_post_tool_use_payload(tool, invocation, output),
    )
    result = await _apply_post_tool_use_hook(result, post_tool_use_hook)
    await notify_tool_finish_if_unclaimed(
        lifecycle_contributors,
        invocation,
        terminal_outcome_reached,
        ToolCallOutcome.completed(_success_for_logging(result.result)),
        **stores,
    )
    return result


async def _apply_pre_tool_use_hook(
    tool: Any,
    invocation: ToolInvocation,
    pre_tool_use_hook: Any,
    *,
    lifecycle_contributors: Any,
    terminal_outcome_reached: Any,
    **stores: Any,
) -> ToolInvocation:
    if pre_tool_use_hook is None:
        return invocation
    hook_payload = _tool_pre_tool_use_payload(tool, invocation)
    if hook_payload is None:
        return invocation
    raw_result = pre_tool_use_hook(hook_payload, invocation)
    if inspect.isawaitable(raw_result):
        raw_result = await raw_result
    result = _coerce_pre_tool_use_result(raw_result)
    if result.type == "blocked":
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.blocked(),
            **stores,
        )
        raise FunctionCallError.respond_to_model(result.message or "")
    if result.updated_input is None:
        return invocation
    try:
        return with_updated_hook_input(invocation, result.updated_input)
    except FunctionCallError:
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise
    except Exception as err:
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise FunctionCallError.fatal(str(err)) from err


async def _apply_post_tool_use_hook(result: Any, post_tool_use_hook: Any) -> Any:
    if post_tool_use_hook is None or result.post_tool_use_payload is None:
        return result
    raw_outcome = post_tool_use_hook(result.post_tool_use_payload, result)
    if inspect.isawaitable(raw_outcome):
        raw_outcome = await raw_outcome
    outcome = _coerce_post_tool_use_outcome(raw_outcome)
    return apply_post_tool_use_feedback(result, post_tool_use_replacement_text(outcome))


def apply_post_tool_use_feedback(result: Any, replacement_text: str | None) -> Any:
    if replacement_text is None:
        return result
    if not isinstance(replacement_text, str):
        raise TypeError("replacement_text must be a string or None")
    from pycodex.core.tool_parallel import ToolCallResult

    if not isinstance(result, ToolCallResult):
        raise TypeError("result must be ToolCallResult")
    return ToolCallResult(
        call_id=result.call_id,
        payload=result.payload,
        result=PostToolUseFeedbackOutput(
            original=result.result,
            model_visible=FunctionToolOutput.from_text(replacement_text, None),
        ),
        post_tool_use_payload=result.post_tool_use_payload,
    )


def _coerce_pre_tool_use_result(value: Any) -> PreToolUseHookResult:
    if isinstance(value, PreToolUseHookResult):
        return value
    if isinstance(value, dict):
        result_type = value.get("type")
        if result_type == "continue":
            return PreToolUseHookResult.continue_(value.get("updated_input"))
        if result_type == "blocked":
            return PreToolUseHookResult.blocked(value.get("message", ""))
    raise TypeError("pre_tool_use_hook must return PreToolUseHookResult")


def _coerce_post_tool_use_outcome(value: Any) -> PostToolUseHookOutcome:
    if isinstance(value, PostToolUseHookOutcome):
        return value
    if isinstance(value, dict):
        return PostToolUseHookOutcome(
            should_stop=bool(value.get("should_stop", False)),
            feedback_message=value.get("feedback_message"),
            stop_reason=value.get("stop_reason"),
            additional_contexts=tuple(value.get("additional_contexts", ())),
        )
    raise TypeError("post_tool_use_hook must return PostToolUseHookOutcome")


def _tool_pre_tool_use_payload(tool: Any, invocation: ToolInvocation) -> Any:
    method = getattr(tool, "pre_tool_use_payload", None)
    if method is None:
        from pycodex.core.tool_registry import pre_tool_use_payload

        value = pre_tool_use_payload(invocation)
    else:
        value = method(invocation)
    if value is not None and not isinstance(value, PreToolUsePayload):
        raise TypeError("pre_tool_use_payload must return PreToolUsePayload or None")
    return value


def _tool_post_tool_use_payload(tool: Any, invocation: ToolInvocation, output: Any) -> Any:
    method = getattr(tool, "post_tool_use_payload", None)
    if method is None:
        from pycodex.core.tool_registry import post_tool_use_payload

        value = post_tool_use_payload(invocation, output)
    else:
        value = method(invocation, output)
    if value is not None and not isinstance(value, PostToolUsePayload):
        raise TypeError("post_tool_use_payload must return PostToolUsePayload or None")
    return value


async def notify_tool_finish_if_unclaimed(
    lifecycle_contributors: Any,
    invocation: ToolInvocation,
    terminal_outcome_reached: Any,
    outcome: ToolCallOutcome,
    **stores: Any,
) -> bool:
    if terminal_outcome_reached is not None:
        swap = getattr(terminal_outcome_reached, "swap", None)
        if swap is None:
            raise TypeError("terminal_outcome_reached must expose swap(bool)")
        if swap(True):
            return False
    await notify_tool_finish(lifecycle_contributors, invocation, outcome, **stores)
    return True


async def _handle_tool(tool: Any, invocation: ToolInvocation) -> Any:
    handle = getattr(tool, "handle", None)
    if handle is None:
        raise FunctionCallError.fatal(f"tool {invocation.tool_name} has no handle method")
    result = handle(invocation)
    if inspect.isawaitable(result):
        result = await result
    return result


def _success_for_logging(output: Any) -> bool:
    method = getattr(output, "success_for_logging", None)
    if method is None:
        return True
    value = method()
    if not isinstance(value, bool):
        raise TypeError("success_for_logging must return a bool")
    return value


__all__ = [
    "ConversationHistory",
    "FunctionCallError",
    "ToolCall",
    "ToolRouter",
    "build_tool_call",
    "dispatch_tool_call",
    "dispatch_tool_call_with_terminal_outcome",
    "apply_post_tool_use_feedback",
    "notify_tool_finish_if_unclaimed",
]
