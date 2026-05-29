"""Session-like turn runtime request construction.

This module is a small executable skeleton for the core user-turn path. It
does not perform network I/O; it advances a session-like object through the
same transport-independent steps the Rust session takes before sampling:
create turn context, record contextual updates, record user input, collect
history/tools/base instructions, and build a Responses API request.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.core.client import ModelClient
from pycodex.core.turn_request import TurnResponsesRequestPlan, build_turn_responses_request
from pycodex.protocol import BaseInstructions, ResponseInputItem, ResponseItem, UserInput


BuiltToolsFn = Callable[[Any, Any], Any | Awaitable[Any]]
SamplerFn = Callable[["UserTurnSamplingRequest"], Any | Awaitable[Any]]


@dataclass(frozen=True)
class UserTurnSamplingRequest:
    """Arguments passed to an injected sampler for one user turn."""

    session: Any
    turn_context: Any
    request_plan: TurnResponsesRequestPlan


@dataclass(frozen=True)
class UserTurnSamplingResult:
    """Completed sampling result after response items are recorded."""

    request_plan: TurnResponsesRequestPlan
    response_items: tuple[ResponseItem, ...]
    raw_result: Any = None


async def build_user_turn_responses_request_from_session(
    sess: Any,
    input: Sequence[UserInput],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    built_tools: BuiltToolsFn | None = None,
    effort: Any = None,
    summary: Any = None,
    service_tier: str | None = None,
    output_schema: Any = None,
    output_schema_strict: bool = True,
) -> TurnResponsesRequestPlan:
    """Build a model request for a user turn from a session-like object."""

    prepared = await _prepare_user_turn_request_from_session(
        sess,
        input,
        model_client,
        provider,
        model_info,
        built_tools=built_tools,
        effort=effort,
        summary=summary,
        service_tier=service_tier,
        output_schema=output_schema,
        output_schema_strict=output_schema_strict,
    )
    return prepared.request_plan


async def run_user_turn_sampling_from_session(
    sess: Any,
    input: Sequence[UserInput],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    sampler: SamplerFn,
    *,
    built_tools: BuiltToolsFn | None = None,
    effort: Any = None,
    summary: Any = None,
    service_tier: str | None = None,
    output_schema: Any = None,
    output_schema_strict: bool = True,
) -> UserTurnSamplingResult:
    """Build a request, run an injected sampler, and record response items."""

    if sampler is None or not callable(sampler):
        raise TypeError("sampler must be callable")
    prepared = await _prepare_user_turn_request_from_session(
        sess,
        input,
        model_client,
        provider,
        model_info,
        built_tools=built_tools,
        effort=effort,
        summary=summary,
        service_tier=service_tier,
        output_schema=output_schema,
        output_schema_strict=output_schema_strict,
    )
    sampling_request = UserTurnSamplingRequest(
        session=sess,
        turn_context=prepared.turn_context,
        request_plan=prepared.request_plan,
    )
    raw_result = await _maybe_await(sampler(sampling_request))
    response_items = _response_items_from_sampling_result(raw_result)
    if response_items:
        await _maybe_await(sess.record_conversation_items(prepared.turn_context, response_items))
    return UserTurnSamplingResult(
        request_plan=prepared.request_plan,
        response_items=response_items,
        raw_result=raw_result,
    )


@dataclass(frozen=True)
class _PreparedUserTurnRequest:
    turn_context: Any
    request_plan: TurnResponsesRequestPlan


async def _prepare_user_turn_request_from_session(
    sess: Any,
    input: Sequence[UserInput],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    built_tools: BuiltToolsFn | None = None,
    effort: Any = None,
    summary: Any = None,
    service_tier: str | None = None,
    output_schema: Any = None,
    output_schema_strict: bool = True,
) -> _PreparedUserTurnRequest:
    user_input = _user_inputs(input)
    turn_context = await _maybe_await(sess.new_default_turn())
    await _maybe_await(sess.record_context_updates_and_set_reference_context_item(turn_context))

    if user_input:
        input_item = ResponseInputItem.from_user_inputs(user_input)
        response_item = ResponseItem.from_response_input_item(input_item)
        await _maybe_await(sess.record_conversation_items(turn_context, (response_item,)))

    history = await _maybe_await(sess.clone_history())
    input_modalities = getattr(getattr(turn_context, "model_info", None), "input_modalities", None)
    prompt_input = history.for_prompt(input_modalities) if hasattr(history, "for_prompt") else list(history)

    built_tools_fn = built_tools or _default_built_tools
    router = await _maybe_await(built_tools_fn(sess, turn_context))
    base_instructions = await _maybe_await(sess.get_base_instructions())
    if not isinstance(base_instructions, BaseInstructions):
        base_instructions = BaseInstructions(str(getattr(base_instructions, "text", base_instructions)))

    request_plan = build_turn_responses_request(
        model_client,
        provider,
        model_info,
        prompt_input,
        router,
        turn_context,
        base_instructions,
        has_current_user_input=bool(user_input),
        effort=effort,
        summary=summary,
        service_tier=service_tier,
        output_schema=output_schema,
        output_schema_strict=output_schema_strict,
    )
    return _PreparedUserTurnRequest(turn_context=turn_context, request_plan=request_plan)


def _user_inputs(value: Sequence[UserInput]) -> tuple[UserInput, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("input must be a sequence of UserInput")
    return tuple(item if isinstance(item, UserInput) else UserInput.from_mapping(item) for item in value)


def _response_items_from_sampling_result(value: Any) -> tuple[ResponseItem, ...]:
    raw_items = getattr(value, "response_items", value)
    if raw_items is None:
        return ()
    if isinstance(raw_items, ResponseItem):
        return (raw_items,)
    if isinstance(raw_items, dict):
        return (ResponseItem.from_mapping(raw_items),)
    if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
        raise TypeError("sampler result must be a ResponseItem, mapping, sequence, or expose response_items")
    items: list[ResponseItem] = []
    for item in raw_items:
        if isinstance(item, ResponseItem):
            items.append(item)
        elif isinstance(item, dict):
            items.append(ResponseItem.from_mapping(item))
        else:
            raise TypeError("sampler response_items entries must be ResponseItem or mapping")
    return tuple(items)


async def _default_built_tools(_sess: Any, _turn_context: Any) -> Any:
    return None


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable) or inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "BuiltToolsFn",
    "SamplerFn",
    "UserTurnSamplingRequest",
    "UserTurnSamplingResult",
    "build_user_turn_responses_request_from_session",
    "run_user_turn_sampling_from_session",
]
