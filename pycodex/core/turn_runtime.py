"""Session-like turn runtime request construction.

This module is a small executable skeleton for the core user-turn path. It
does not perform network I/O; it advances a session-like object through the
same transport-independent steps the Rust session takes before sampling:
create turn context, record contextual updates, record user input, collect
history/tools/base instructions, and build a Responses API request.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pycodex.core.client import ModelClient, SamplingRequestRuntimeHookAdapter, SamplingRuntimeEventApplicationState
from pycodex.core.codex_thread import SessionSettingsUpdate
from pycodex.core.compact_remote import normalize_history_for_prompt
from pycodex.core.features import Feature
from pycodex.core.hook_runtime import HookRuntimeOutcome, additional_context_messages
from pycodex.core.string_utils import truncate_middle_with_token_budget
from pycodex.core.original_image_detail import can_request_original_image_detail
from pycodex.core.responses_retry import (
    ResponsesStreamRequest,
    RetryableResponseStreamAction,
    response_stream_retry_decision,
)
from pycodex.core.spec_plan import build_environment_tool_router_from_turn_context
from pycodex.core.tool_parallel import ToolCallRuntime
from pycodex.core.tool_router import FunctionCallError, ToolRouter
from pycodex.core.stream_events_utils import AssistantMessageStreamParsers, OutputItemResult, SamplingOutputState
from pycodex.core.stream_events_utils import get_last_assistant_message_from_turn
from pycodex.core.stream_events_utils import handle_non_tool_response_item
from pycodex.core.stream_events_utils import last_assistant_message_from_item
from pycodex.core.stream_events_utils import sampling_stream_event_apply_plan
from pycodex.core.stream_events_utils import sampling_stream_event_dispatch_plan
from pycodex.core.turn_timing import ResponseEvent as TimingResponseEvent
from pycodex.core.turn_request import TurnResponsesRequestPlan, build_turn_responses_request
from pycodex.protocol import BaseInstructions, CodexErr, CodexErrorInfo, ContentItem, ErrorEvent, EventMsg, StreamErrorEvent
from pycodex.protocol import FunctionCallOutputContentItem, FunctionCallOutputPayload
from pycodex.protocol import HookPromptFragment, Op, ResponseInputItem, ResponseItem
from pycodex.protocol import TurnCompleteEvent, TurnDiffEvent, TurnItem, TurnStartedEvent, UserMessageItem
from pycodex.protocol import ThreadSettingsOverrides, TokenUsage, UsageLimitReachedError, UserInput, WarningEvent
from pycodex.protocol import build_hook_prompt_message


MAX_ADDITIONAL_CONTEXT_TOKENS = 1000
DEFAULT_STREAM_MAX_RETRIES = 5
MAX_STREAM_MAX_RETRIES = 100
TURN_TTFM_DURATION_METRIC = "codex.turn.ttfm.duration_ms"
_LAST_AGENT_MESSAGE_UNSET = object()


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
    tool_response_items: tuple[ResponseItem, ...] = ()
    request_plans: tuple[TurnResponsesRequestPlan, ...] = ()
    raw_tool_output_items: tuple[Any, ...] = ()
    raw_results: tuple[Any, ...] = ()
    raw_result: Any = None
    session_events: tuple[Any, ...] = ()
    stream_events: tuple[Any, ...] = ()
    stream_event_dispatch_plans: tuple[Any, ...] = ()
    stream_event_apply_plans: tuple[Any, ...] = ()
    stream_runtime_state_summary: dict[str, Any] | None = None
    last_agent_message: str | None = None
    turn_status: str = "completed"


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
    thread_settings: Any = None,
    responsesapi_client_metadata: Mapping[str, str] | None = None,
    additional_context: Mapping[str, Any] | None = None,
    environments: Sequence[Any] | None = None,
    output_schema: Any = None,
    apply_output_schema_update: bool = False,
    output_schema_strict: bool | None = None,
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
        thread_settings=thread_settings,
        responsesapi_client_metadata=responsesapi_client_metadata,
        additional_context=additional_context,
        environments=environments,
        output_schema=output_schema,
        apply_output_schema_update=apply_output_schema_update or output_schema is not None,
        output_schema_strict=output_schema_strict,
    )
    return prepared.request_plan


async def build_user_input_op_responses_request_from_session(
    sess: Any,
    op: Op | dict[str, Any],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    built_tools: BuiltToolsFn | None = None,
    effort: Any = None,
    summary: Any = None,
    service_tier: str | None = None,
    output_schema_strict: bool | None = None,
) -> TurnResponsesRequestPlan:
    """Build a model request from a protocol ``Op.user_input`` value."""

    fields = _user_input_op_fields(op)
    return await build_user_turn_responses_request_from_session(
        sess,
        fields.get("items", ()),
        model_client,
        provider,
        model_info,
        built_tools=built_tools,
        effort=effort,
        summary=summary,
        service_tier=service_tier,
        thread_settings=fields.get("thread_settings"),
        responsesapi_client_metadata=fields.get("responsesapi_client_metadata"),
        additional_context=fields.get("additional_context"),
        environments=fields.get("environments"),
        output_schema=fields.get("final_output_json_schema"),
        apply_output_schema_update=True,
        output_schema_strict=output_schema_strict,
    )


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
    thread_settings: Any = None,
    responsesapi_client_metadata: Mapping[str, str] | None = None,
    additional_context: Mapping[str, Any] | None = None,
    environments: Sequence[Any] | None = None,
    output_schema: Any = None,
    apply_output_schema_update: bool = False,
    output_schema_strict: bool | None = None,
    max_tool_followups: int | None = None,
    emit_user_prompt_turn_item: bool = True,
    emit_response_item_turn_item: bool = True,
) -> UserTurnSamplingResult:
    """Build a request, run an injected sampler, and record response items."""

    if sampler is None or not callable(sampler):
        raise TypeError("sampler must be callable")
    max_tool_followups = _validate_max_tool_followups(max_tool_followups)
    try:
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
            thread_settings=thread_settings,
            responsesapi_client_metadata=responsesapi_client_metadata,
            additional_context=additional_context,
            environments=environments,
            output_schema=output_schema,
            apply_output_schema_update=apply_output_schema_update or output_schema is not None,
            output_schema_strict=output_schema_strict,
            run_pre_sampling_compact=True,
            run_user_prompt_submit_hooks=True,
            emit_turn_started_lifecycle=True,
        )
    except _PreSamplingCompactError as exc:
        prepared = _PreparedUserTurnRequest(
            turn_context=exc.turn_context,
            user_input=(),
            router=None,
            model_info=model_info,
            effort=effort,
            summary=summary,
            service_tier=service_tier,
            output_schema=output_schema,
            output_schema_strict=output_schema_strict,
            request_plan=TurnResponsesRequestPlan(prompt=None, request={}),
        )
        await _handle_auto_compact_error(sess, exc.turn_context, exc.error)
        return await _completed_user_turn_sampling_result(
            prepared,
            (),
            (),
            (),
            (),
            None,
            sess,
            (),
            (),
            (),
            SamplingRuntimeEventApplicationState(),
            last_agent_message_override=None,
        )
    except _UserInputBlocked as exc:
        prepared = _PreparedUserTurnRequest(
            turn_context=exc.turn_context,
            user_input=(),
            router=None,
            model_info=model_info,
            effort=effort,
            summary=summary,
            service_tier=service_tier,
            output_schema=output_schema,
            output_schema_strict=output_schema_strict,
            request_plan=TurnResponsesRequestPlan(prompt=None, request={}),
        )
        return await _completed_user_turn_sampling_result(
            prepared,
            (),
            (),
            (),
            (),
            None,
            sess,
            (),
            (),
            (),
            SamplingRuntimeEventApplicationState(),
            last_agent_message_override=None,
        )
    request_plans = [prepared.request_plan]
    user_input_to_emit = prepared.user_input
    sampling_request = UserTurnSamplingRequest(
        session=sess,
        turn_context=prepared.turn_context,
        request_plan=prepared.request_plan,
    )
    user_input_emitted = False
    while True:
        try:
            raw_result = await _sample_with_retry(sess, prepared.turn_context, provider, sampler, sampling_request)
            break
        except CodexErr as exc:
            if exc.kind == "turn_aborted":
                return _user_turn_sampling_result(
                    prepared,
                    (),
                    (),
                    request_plans,
                    (),
                    None,
                    sess,
                    (),
                    (),
                    (),
                    SamplingRuntimeEventApplicationState(),
                    turn_status="interrupted",
                )
            if exc.kind == "invalid_image_request":
                if await _recover_invalid_image_request(sess, prepared.turn_context, exc):
                    retry_plan = await _build_follow_up_request_from_session(
                        sess,
                        prepared,
                        model_client,
                        provider,
                    )
                    request_plans.append(retry_plan)
                    sampling_request = UserTurnSamplingRequest(
                        session=sess,
                        turn_context=prepared.turn_context,
                        request_plan=retry_plan,
                    )
                    continue
                return await _completed_user_turn_sampling_result(
                    prepared,
                    (),
                    (),
                    request_plans,
                    (),
                    None,
                    sess,
                    (),
                    (),
                    (),
                    SamplingRuntimeEventApplicationState(),
                )
            await _handle_terminal_sampling_error(sess, prepared.turn_context, exc)
            return await _completed_user_turn_sampling_result(
                prepared,
                (),
                (),
                request_plans,
                (),
                None,
                sess,
                (),
                (),
                (),
                SamplingRuntimeEventApplicationState(),
                last_agent_message_override=None,
            )
    await _record_sampling_token_usage(sess, prepared.turn_context, raw_result)
    if not user_input_emitted and user_input_to_emit and emit_user_prompt_turn_item:
        await _emit_user_prompt_turn_item(sess, prepared.turn_context, user_input_to_emit)
        user_input_emitted = True
    stream_runtime_state = SamplingRuntimeEventApplicationState()
    response_items = _response_items_from_sampling_result(raw_result)
    if response_items:
        await _record_response_items(
            sess,
            prepared.turn_context,
            response_items,
            emit_turn_item=emit_response_item_turn_item,
        )
    await _record_response_items_turn_ttfm(sess, prepared.turn_context, response_items)
    _update_stream_runtime_last_agent_message_from_response_items(stream_runtime_state, response_items)
    all_response_items = list(response_items)
    all_tool_response_items: list[ResponseItem] = []
    raw_results = [raw_result]
    all_stream_events = list(_stream_events_from_sampling_result(raw_result))
    await _record_stream_events_turn_ttft(sess, prepared.turn_context, all_stream_events)
    all_stream_event_dispatch_plans = list(
        _sampling_stream_event_dispatch_plans_from_result(
            raw_result,
            prepared.router,
            turn_context=prepared.turn_context,
            thread_id=str(getattr(model_client.state, "thread_id", "")),
            turn_id=_turn_context_turn_id(prepared.turn_context),
        )
    )
    stream_event_apply_plans = list(
        _sampling_stream_event_apply_plans_from_result(
            raw_result,
        all_stream_event_dispatch_plans,
        stream_runtime_state,
        turn_context=prepared.turn_context,
        has_pending_mailbox_items=await _has_pending_mailbox_items(sess) if all_stream_events else False,
    )
    )
    emitted_stream_event_cursor = await _emit_stream_runtime_events(
        sess,
        prepared.turn_context,
        stream_runtime_state,
        0,
    )
    await _apply_stream_runtime_session_side_effects(
        sess,
        prepared.turn_context,
        stream_runtime_state,
        raw_result,
    )
    try:
        await _apply_stream_runtime_loop_tail(
            sess,
            prepared.turn_context,
            stream_event_apply_plans,
        )
    except CodexErr as exc:
        if exc.kind == "turn_aborted":
            return _user_turn_sampling_result(
                prepared,
                all_response_items,
                all_tool_response_items,
                request_plans,
                raw_results,
                raw_result,
                sess,
                all_stream_events,
                all_stream_event_dispatch_plans,
                stream_event_apply_plans,
                stream_runtime_state,
                turn_status="interrupted",
            )
        raise
    stream_response_items = _stream_non_tool_response_items(
        all_stream_events,
        skip_items=response_items,
    )
    if stream_response_items:
        await _maybe_await(sess.record_conversation_items(prepared.turn_context, stream_response_items))
        await _record_response_items_turn_ttfm(sess, prepared.turn_context, stream_response_items)
        _update_stream_runtime_last_agent_message_from_response_items(stream_runtime_state, stream_response_items)
        all_response_items.extend(stream_response_items)
    stream_tool_response_items = await _handle_stream_response_tool_calls(
        sess,
        prepared.turn_context,
        prepared.router,
        all_stream_events,
        skip_call_ids=_tool_call_ids(response_items),
    )
    tool_response_items = stream_tool_response_items + await _handle_response_tool_calls(
        sess,
        prepared.turn_context,
        prepared.router,
        response_items,
    )
    needs_model_followup = (
        _sampling_result_needs_followup(raw_result)
        or _stream_completed_end_turn_needs_followup(all_stream_events)
        or _stream_apply_plans_need_followup(stream_event_apply_plans)
    )
    tool_followups = 0
    stop_hook_active = False
    while True:
        has_tool_response_items = bool(tool_response_items)
        if tool_response_items:
            await _maybe_await(sess.record_conversation_items(prepared.turn_context, tool_response_items))
            all_tool_response_items.extend(tool_response_items)
        tool_followup_limit_reached = (
            max_tool_followups is not None
            and has_tool_response_items
            and tool_followups >= max_tool_followups
        )
        can_drain_pending_input = not needs_model_followup and (
            not has_tool_response_items or tool_followup_limit_reached
        )
        checked_pending_compact = False
        if can_drain_pending_input and await _has_pending_input(sess):
            checked_pending_compact = True
            compact_result = await _maybe_run_mid_turn_auto_compact_result(sess, prepared.turn_context)
            if not compact_result.success:
                return await _completed_user_turn_sampling_result(
                    prepared,
                    all_response_items,
                    all_tool_response_items,
                    request_plans,
                    raw_results,
                    raw_result,
                    sess,
                    all_stream_events,
                    all_stream_event_dispatch_plans,
                    stream_event_apply_plans,
                    stream_runtime_state,
                    last_agent_message_override=None,
                )
            if compact_result.compacted:
                continue
        pending_input_result = (
            await _drain_and_record_pending_inputs(sess, prepared.turn_context)
            if can_drain_pending_input
            else _PendingInputRecordResult(())
        )
        pending_input_items = pending_input_result.recorded_items
        if pending_input_result.blocked_without_accepted_user_input:
            break
        if tool_followup_limit_reached and not needs_model_followup and not pending_input_items:
            break
        if not tool_response_items and not needs_model_followup and not pending_input_items:
            stop_outcome = await _run_turn_stop_hook(
                sess,
                prepared.turn_context,
                stop_hook_active,
                _last_agent_message_from_sampling(
                    stream_runtime_state,
                    all_response_items,
                    stream_event_apply_plans,
                    all_stream_events,
                ),
            )
            if _stop_outcome_should_block(stop_outcome):
                hook_prompt_message = _stop_outcome_hook_prompt_message(stop_outcome)
                if hook_prompt_message is not None:
                    await _maybe_await(sess.record_conversation_items(prepared.turn_context, (hook_prompt_message,)))
                    stop_hook_active = True
                    needs_model_followup = True
                    continue
                else:
                    await _send_warning_event(
                        sess,
                        prepared.turn_context,
                        "Stop hook requested continuation without a prompt; ignoring the block.",
                    )
                    if _stop_outcome_should_stop(stop_outcome):
                        break
            elif _stop_outcome_should_stop(stop_outcome):
                break
            if await _run_legacy_after_agent_hook(
                sess,
                prepared.turn_context,
                request_plans[-1].request.get("input", ()),
                _last_agent_message_from_sampling(
                    stream_runtime_state,
                    all_response_items,
                    stream_event_apply_plans,
                    all_stream_events,
                ),
            ):
                return await _completed_user_turn_sampling_result(
                    prepared,
                    all_response_items,
                    all_tool_response_items,
                    request_plans,
                    raw_results,
                    raw_result,
                    sess,
                    all_stream_events,
                    all_stream_event_dispatch_plans,
                    stream_event_apply_plans,
                    stream_runtime_state,
                    last_agent_message_override=None,
                )
            break
        compact_continue = (
            True
            if checked_pending_compact
            else await _maybe_run_mid_turn_auto_compact(sess, prepared.turn_context)
        )
        if not compact_continue:
            return await _completed_user_turn_sampling_result(
                prepared,
                all_response_items,
                all_tool_response_items,
                request_plans,
                raw_results,
                raw_result,
                sess,
                all_stream_events,
                all_stream_event_dispatch_plans,
                stream_event_apply_plans,
                stream_runtime_state,
                last_agent_message_override=None,
            )
        followup_plan = await _build_follow_up_request_from_session(
            sess,
            prepared,
            model_client,
            provider,
        )
        request_plans.append(followup_plan)
        followup_request = UserTurnSamplingRequest(
            session=sess,
            turn_context=prepared.turn_context,
            request_plan=followup_plan,
        )
        while True:
            try:
                raw_result = await _sample_with_retry(sess, prepared.turn_context, provider, sampler, followup_request)
                break
            except CodexErr as exc:
                if exc.kind == "turn_aborted":
                    return _user_turn_sampling_result(
                        prepared,
                        all_response_items,
                        all_tool_response_items,
                        request_plans,
                        raw_results,
                        raw_result,
                        sess,
                        all_stream_events,
                        all_stream_event_dispatch_plans,
                        stream_event_apply_plans,
                        stream_runtime_state,
                        turn_status="interrupted",
                    )
                if exc.kind == "invalid_image_request":
                    if await _recover_invalid_image_request(sess, prepared.turn_context, exc):
                        followup_plan = await _build_follow_up_request_from_session(
                            sess,
                            prepared,
                            model_client,
                            provider,
                        )
                        request_plans.append(followup_plan)
                        followup_request = UserTurnSamplingRequest(
                            session=sess,
                            turn_context=prepared.turn_context,
                            request_plan=followup_plan,
                        )
                        continue
                    return await _completed_user_turn_sampling_result(
                        prepared,
                        all_response_items,
                        all_tool_response_items,
                        request_plans,
                        raw_results,
                        raw_result,
                        sess,
                        all_stream_events,
                        all_stream_event_dispatch_plans,
                        stream_event_apply_plans,
                        stream_runtime_state,
                    )
                await _handle_terminal_sampling_error(sess, prepared.turn_context, exc)
                return await _completed_user_turn_sampling_result(
                    prepared,
                    all_response_items,
                    all_tool_response_items,
                    request_plans,
                    raw_results,
                    raw_result,
                    sess,
                    all_stream_events,
                    all_stream_event_dispatch_plans,
                    stream_event_apply_plans,
                    stream_runtime_state,
                    last_agent_message_override=None,
                )
        await _record_sampling_token_usage(sess, prepared.turn_context, raw_result)
        raw_results.append(raw_result)
        followup_stream_events = _stream_events_from_sampling_result(raw_result)
        await _record_stream_events_turn_ttft(sess, prepared.turn_context, followup_stream_events)
        followup_dispatch_plans = _sampling_stream_event_dispatch_plans_from_result(
            raw_result,
            prepared.router,
            turn_context=prepared.turn_context,
            thread_id=str(getattr(model_client.state, "thread_id", "")),
            turn_id=_turn_context_turn_id(prepared.turn_context),
        )
        all_stream_events.extend(followup_stream_events)
        all_stream_event_dispatch_plans.extend(followup_dispatch_plans)
        followup_apply_plans = _sampling_stream_event_apply_plans_from_result(
            raw_result,
            followup_dispatch_plans,
            stream_runtime_state,
            turn_context=prepared.turn_context,
            has_pending_mailbox_items=await _has_pending_mailbox_items(sess) if followup_stream_events else False,
        )
        stream_event_apply_plans.extend(followup_apply_plans)
        emitted_stream_event_cursor = await _emit_stream_runtime_events(
            sess,
            prepared.turn_context,
            stream_runtime_state,
            emitted_stream_event_cursor,
        )
        await _apply_stream_runtime_session_side_effects(
            sess,
            prepared.turn_context,
            stream_runtime_state,
            raw_result,
        )
        try:
            await _apply_stream_runtime_loop_tail(
                sess,
                prepared.turn_context,
                followup_apply_plans,
            )
        except CodexErr as exc:
            if exc.kind == "turn_aborted":
                return _user_turn_sampling_result(
                    prepared,
                    all_response_items,
                    all_tool_response_items,
                    request_plans,
                    raw_results,
                    raw_result,
                    sess,
                    all_stream_events,
                    all_stream_event_dispatch_plans,
                    stream_event_apply_plans,
                    stream_runtime_state,
                    turn_status="interrupted",
                )
            raise
        response_items = _response_items_from_sampling_result(raw_result)
        if response_items:
            await _record_response_items(
                sess,
                prepared.turn_context,
                response_items,
                emit_turn_item=emit_response_item_turn_item,
            )
            await _record_response_items_turn_ttfm(sess, prepared.turn_context, response_items)
            _update_stream_runtime_last_agent_message_from_response_items(stream_runtime_state, response_items)
            all_response_items.extend(response_items)
        stream_response_items = _stream_non_tool_response_items(
            followup_stream_events,
            skip_items=response_items,
        )
        if stream_response_items:
            await _maybe_await(sess.record_conversation_items(prepared.turn_context, stream_response_items))
            await _record_response_items_turn_ttfm(sess, prepared.turn_context, stream_response_items)
            _update_stream_runtime_last_agent_message_from_response_items(stream_runtime_state, stream_response_items)
            all_response_items.extend(stream_response_items)
        stream_tool_response_items = await _handle_stream_response_tool_calls(
            sess,
            prepared.turn_context,
            prepared.router,
            followup_stream_events,
            skip_call_ids=_tool_call_ids(response_items),
        )
        tool_response_items = stream_tool_response_items + await _handle_response_tool_calls(
            sess,
            prepared.turn_context,
            prepared.router,
            response_items,
        )
        needs_model_followup = (
            _sampling_result_needs_followup(raw_result)
            or _stream_completed_end_turn_needs_followup(followup_stream_events)
            or _stream_apply_plans_need_followup(followup_apply_plans)
        )
        if has_tool_response_items:
            tool_followups += 1
    return await _completed_user_turn_sampling_result(
        prepared,
        all_response_items,
        all_tool_response_items,
        request_plans,
        raw_results,
        raw_result,
        sess,
        all_stream_events,
        all_stream_event_dispatch_plans,
        stream_event_apply_plans,
        stream_runtime_state,
    )


def _user_turn_sampling_result(
    prepared: _PreparedUserTurn,
    all_response_items: Sequence[ResponseItem],
    all_tool_response_items: Sequence[ResponseItem],
    request_plans: Sequence[TurnResponsesRequestPlan],
    raw_results: Sequence[Any],
    raw_result: Any,
    sess: Any,
    all_stream_events: Sequence[Any],
    all_stream_event_dispatch_plans: Sequence[Any],
    stream_event_apply_plans: Sequence[Any],
    stream_runtime_state: SamplingRuntimeEventApplicationState,
    turn_status: str = "completed",
    last_agent_message_override: str | None | object = _LAST_AGENT_MESSAGE_UNSET,
) -> UserTurnSamplingResult:
    last_agent_message = (
        _last_agent_message_from_sampling(
            stream_runtime_state,
            all_response_items,
            stream_event_apply_plans,
            all_stream_events,
        )
        if last_agent_message_override is _LAST_AGENT_MESSAGE_UNSET
        else last_agent_message_override
    )
    return UserTurnSamplingResult(
        request_plan=prepared.request_plan,
        response_items=tuple(all_response_items),
        tool_response_items=tuple(all_tool_response_items),
        request_plans=tuple(request_plans),
        raw_results=tuple(raw_results),
        raw_result=raw_result,
        session_events=tuple(getattr(sess, "emitted_events", ()) or ()),
        stream_events=tuple(all_stream_events),
        stream_event_dispatch_plans=tuple(all_stream_event_dispatch_plans),
        stream_event_apply_plans=tuple(stream_event_apply_plans),
        stream_runtime_state_summary=stream_runtime_state.snapshot() if stream_event_apply_plans else None,
        last_agent_message=last_agent_message,
        turn_status=turn_status,
    )


async def _completed_user_turn_sampling_result(
    prepared: _PreparedUserTurn,
    all_response_items: Sequence[ResponseItem],
    all_tool_response_items: Sequence[ResponseItem],
    request_plans: Sequence[TurnResponsesRequestPlan],
    raw_results: Sequence[Any],
    raw_result: Any,
    sess: Any,
    all_stream_events: Sequence[Any],
    all_stream_event_dispatch_plans: Sequence[Any],
    stream_event_apply_plans: Sequence[Any],
    stream_runtime_state: SamplingRuntimeEventApplicationState,
    last_agent_message_override: str | None | object = _LAST_AGENT_MESSAGE_UNSET,
) -> UserTurnSamplingResult:
    last_agent_message = (
        _last_agent_message_from_sampling(
            stream_runtime_state,
            all_response_items,
            stream_event_apply_plans,
            all_stream_events,
        )
        if last_agent_message_override is _LAST_AGENT_MESSAGE_UNSET
        else last_agent_message_override
    )
    await _emit_turn_complete_lifecycle(sess, prepared.turn_context, last_agent_message)
    return _user_turn_sampling_result(
        prepared,
        all_response_items,
        all_tool_response_items,
        request_plans,
        raw_results,
        raw_result,
        sess,
        all_stream_events,
        all_stream_event_dispatch_plans,
        stream_event_apply_plans,
        stream_runtime_state,
        last_agent_message_override=last_agent_message,
    )


async def run_user_input_op_sampling_from_session(
    sess: Any,
    op: Op | dict[str, Any],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    sampler: SamplerFn,
    *,
    built_tools: BuiltToolsFn | None = None,
    effort: Any = None,
    summary: Any = None,
    service_tier: str | None = None,
    output_schema_strict: bool | None = None,
    max_tool_followups: int | None = None,
) -> UserTurnSamplingResult:
    """Run one protocol ``Op.user_input`` through the session-like runtime."""

    fields = _user_input_op_fields(op)
    return await run_user_turn_sampling_from_session(
        sess,
        fields.get("items", ()),
        model_client,
        provider,
        model_info,
        sampler,
        built_tools=built_tools,
        effort=effort,
        summary=summary,
        service_tier=service_tier,
        thread_settings=fields.get("thread_settings"),
        responsesapi_client_metadata=fields.get("responsesapi_client_metadata"),
        additional_context=fields.get("additional_context"),
        environments=fields.get("environments"),
        output_schema=fields.get("final_output_json_schema"),
        apply_output_schema_update=True,
        output_schema_strict=output_schema_strict,
        max_tool_followups=max_tool_followups,
    )


@dataclass(frozen=True)
class _PreparedUserTurnRequest:
    turn_context: Any
    user_input: tuple[UserInput, ...]
    router: Any
    model_info: Any
    effort: Any
    summary: Any
    service_tier: str | None
    output_schema: Any
    output_schema_strict: bool | None
    request_plan: TurnResponsesRequestPlan


class _PreSamplingCompactError(Exception):
    def __init__(self, turn_context: Any, error: CodexErr) -> None:
        super().__init__(str(error))
        self.turn_context = turn_context
        self.error = error


class _UserInputBlocked(Exception):
    def __init__(self, turn_context: Any) -> None:
        super().__init__("user input blocked")
        self.turn_context = turn_context


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
    thread_settings: Any = None,
    responsesapi_client_metadata: Mapping[str, str] | None = None,
    additional_context: Mapping[str, Any] | None = None,
    environments: Sequence[Any] | None = None,
    output_schema: Any = None,
    apply_output_schema_update: bool = False,
    output_schema_strict: bool | None = None,
    run_pre_sampling_compact: bool = False,
    run_user_prompt_submit_hooks: bool = False,
    emit_turn_started_lifecycle: bool = False,
) -> _PreparedUserTurnRequest:
    user_input = _user_inputs(input)
    await _apply_thread_settings_overrides(sess, thread_settings)
    await _apply_turn_environments(sess, environments)
    if apply_output_schema_update:
        await _apply_final_output_json_schema(sess, output_schema)
    turn_context = await _maybe_await(sess.new_default_turn())
    _apply_responsesapi_client_metadata(turn_context, responsesapi_client_metadata)
    if emit_turn_started_lifecycle:
        await _emit_turn_started_lifecycle(sess, turn_context)
    if run_pre_sampling_compact:
        try:
            await _maybe_run_pre_sampling_auto_compact(sess, turn_context)
        except CodexErr as exc:
            raise _PreSamplingCompactError(turn_context, exc) from exc
    await _maybe_await(sess.record_context_updates_and_set_reference_context_item(turn_context))

    additional_context_items = _additional_context_response_items(sess, additional_context)
    if additional_context_items:
        await _maybe_await(sess.record_conversation_items(turn_context, additional_context_items))

    if user_input and run_user_prompt_submit_hooks:
        if await _record_user_input_with_submit_hook(
            sess,
            turn_context,
            user_input,
            emit_turn_item=False,
        ):
            raise _UserInputBlocked(turn_context)
    elif user_input:
        await _record_user_inputs(sess, turn_context, user_input, emit_turn_item=False)

    pre_sampling_pending_input = _PendingInputRecordResult(())
    if not user_input and run_user_prompt_submit_hooks:
        pre_sampling_pending_input = await _drain_and_record_pending_inputs(sess, turn_context)
        if pre_sampling_pending_input.blocked_without_accepted_user_input:
            raise _UserInputBlocked(turn_context)

    history = await _maybe_await(sess.clone_history())
    effective_model_info = getattr(turn_context, "model_info", None) or model_info
    input_modalities = getattr(effective_model_info, "input_modalities", None)
    prompt_input = _history_for_prompt(history, input_modalities)

    built_tools_fn = built_tools or _default_built_tools
    router = await _maybe_await(built_tools_fn(sess, turn_context))
    base_instructions = await _maybe_await(sess.get_base_instructions())
    if not isinstance(base_instructions, BaseInstructions):
        base_instructions = BaseInstructions(str(getattr(base_instructions, "text", base_instructions)))

    effective_effort = effort if effort is not None else _turn_setting(
        turn_context,
        "model_reasoning_effort",
        "reasoning_effort",
    )
    effective_summary = summary if summary is not None else _turn_setting(
        turn_context,
        "model_reasoning_summary",
        "reasoning_summary",
    )
    effective_service_tier = service_tier if service_tier is not None else _turn_setting(
        turn_context,
        "service_tier",
        "service_tier",
    )
    request_plan = build_turn_responses_request(
        model_client,
        provider,
        effective_model_info,
        prompt_input,
        router,
        turn_context,
        base_instructions,
        has_current_user_input=bool(user_input) or pre_sampling_pending_input.accepted_user_input,
        effort=effective_effort,
        summary=effective_summary,
        service_tier=effective_service_tier,
        output_schema=output_schema if apply_output_schema_update else getattr(turn_context, "final_output_json_schema", output_schema),
        output_schema_strict=output_schema_strict,
    )
    request_output_schema = output_schema if apply_output_schema_update else getattr(
        turn_context,
        "final_output_json_schema",
        output_schema,
    )
    return _PreparedUserTurnRequest(
        turn_context=turn_context,
        user_input=user_input,
        router=router,
        model_info=effective_model_info,
        effort=effective_effort,
        summary=effective_summary,
        service_tier=effective_service_tier,
        output_schema=request_output_schema,
        output_schema_strict=output_schema_strict,
        request_plan=request_plan,
    )


async def _build_follow_up_request_from_session(
    sess: Any,
    prepared: _PreparedUserTurnRequest,
    model_client: ModelClient,
    provider: Any,
) -> TurnResponsesRequestPlan:
    history = await _maybe_await(sess.clone_history())
    input_modalities = getattr(prepared.model_info, "input_modalities", None)
    prompt_input = _history_for_prompt(history, input_modalities)
    base_instructions = await _maybe_await(sess.get_base_instructions())
    if not isinstance(base_instructions, BaseInstructions):
        base_instructions = BaseInstructions(str(getattr(base_instructions, "text", base_instructions)))
    return build_turn_responses_request(
        model_client,
        provider,
        prepared.model_info,
        prompt_input,
        prepared.router,
        prepared.turn_context,
        base_instructions,
        has_current_user_input=False,
        effort=prepared.effort,
        summary=prepared.summary,
        service_tier=prepared.service_tier,
        output_schema=prepared.output_schema,
        output_schema_strict=prepared.output_schema_strict,
    )


def _user_inputs(value: Sequence[UserInput]) -> tuple[UserInput, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("input must be a sequence of UserInput")
    return tuple(item if isinstance(item, UserInput) else UserInput.from_mapping(item) for item in value)


def _history_for_prompt(history: Any, input_modalities: Any) -> tuple[ResponseItem, ...]:
    prompt_items = history.for_prompt(input_modalities) if hasattr(history, "for_prompt") else list(history)
    return normalize_history_for_prompt(prompt_items, input_modalities)


async def _record_user_input_with_submit_hook(
    sess: Any,
    turn_context: Any,
    user_input: tuple[UserInput, ...],
    *,
    emit_turn_item: bool = True,
) -> bool:
    outcome = await _run_user_prompt_submit_hook(sess, turn_context, user_input)
    if outcome is None:
        await _record_user_inputs(sess, turn_context, user_input, emit_turn_item=emit_turn_item)
        return False

    additional_items = additional_context_messages(outcome.additional_contexts)
    if outcome.should_stop:
        if additional_items:
            await _maybe_await(sess.record_conversation_items(turn_context, additional_items))
        return True

    await _record_user_inputs(sess, turn_context, user_input, emit_turn_item=emit_turn_item)
    if additional_items:
        await _maybe_await(sess.record_conversation_items(turn_context, additional_items))
    return False


async def _record_user_inputs(
    sess: Any,
    turn_context: Any,
    user_input: tuple[UserInput, ...],
    *,
    emit_turn_item: bool = True,
) -> ResponseItem:
    response_item = ResponseItem.from_response_input_item(ResponseInputItem.from_user_inputs(user_input))
    recorder = getattr(sess, "record_user_prompt_and_emit_turn_item", None)
    if callable(recorder) and emit_turn_item:
        await _maybe_await(recorder(turn_context, user_input))
        return response_item
    await _maybe_await(sess.record_conversation_items(turn_context, (response_item,)))
    return response_item


async def _emit_user_prompt_turn_item(
    sess: Any,
    turn_context: Any,
    user_input: tuple[UserInput, ...],
) -> None:
    started = getattr(sess, "emit_turn_item_started", None)
    completed = getattr(sess, "emit_turn_item_completed", None)
    if callable(started) and callable(completed):
        turn_item = TurnItem.user_message(UserMessageItem.new(user_input))
        await _maybe_await(started(turn_context, turn_item))
        await _maybe_await(completed(turn_context, turn_item))
        return
    # The user prompt is already recorded before sampling begins, so we only emit
    # lifecycle events here when possible.


async def _record_response_items(
    sess: Any,
    turn_context: Any,
    response_items: tuple[ResponseItem, ...],
    *,
    emit_turn_item: bool = True,
) -> None:
    recorder = getattr(sess, "record_response_item_and_emit_turn_item", None)
    if not callable(recorder) or not emit_turn_item:
        await _maybe_await(sess.record_conversation_items(turn_context, response_items))
        return
    for item in response_items:
        await _maybe_await(recorder(turn_context, item))


async def _run_user_prompt_submit_hook(
    sess: Any,
    turn_context: Any,
    user_input: tuple[UserInput, ...],
) -> HookRuntimeOutcome | None:
    hook = (
        getattr(sess, "run_user_prompt_submit_hook", None)
        or getattr(sess, "run_user_prompt_submit", None)
        or getattr(sess, "user_prompt_submit_hook", None)
        or getattr(turn_context, "run_user_prompt_submit_hook", None)
    )
    if not callable(hook):
        return None
    prompt = _user_prompt_submit_prompt(user_input)
    raw_outcome = await _call_user_prompt_submit_hook(hook, sess, turn_context, user_input, prompt)
    return _user_prompt_submit_outcome(raw_outcome)


async def _call_user_prompt_submit_hook(
    hook: Any,
    sess: Any,
    turn_context: Any,
    user_input: tuple[UserInput, ...],
    prompt: str,
) -> Any:
    try:
        signature = inspect.signature(hook)
    except (TypeError, ValueError):
        return await _maybe_await(hook(turn_context, user_input, prompt))
    parameters = tuple(signature.parameters.values())
    if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return await _maybe_await(hook(sess, turn_context, user_input, prompt))
    required = [
        parameter
        for parameter in parameters
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]
    if len(required) >= 4:
        return await _maybe_await(hook(sess, turn_context, user_input, prompt))
    by_name = {parameter.name: parameter for parameter in parameters}
    if (
        "turn_context" in by_name
        and "user_input" in by_name
        and "prompt" in by_name
    ):
        try:
            return await _maybe_await(
                hook(
                    turn_context=turn_context,
                    user_input=user_input,
                    prompt=prompt,
                )
            )
        except TypeError:
            if len(required) == 3:
                return await _maybe_await(hook(turn_context, user_input, prompt))
            pass
    if (
        "user_input" in by_name
        and "prompt" in by_name
        and len(required) == 2
    ):
        try:
            return await _maybe_await(hook(user_input=user_input, prompt=prompt))
        except TypeError:
            pass
    if "prompt" in by_name:
        try:
            return await _maybe_await(hook(prompt=prompt))
        except TypeError:
            pass
    if len(required) == 3:
        return await _maybe_await(hook(turn_context, user_input, prompt))
    if len(required) == 2:
        return await _maybe_await(hook(turn_context, prompt))
    if len(required) == 1:
        return await _maybe_await(hook(prompt))
    return await _maybe_await(hook())


def _user_prompt_submit_outcome(value: Any) -> HookRuntimeOutcome:
    if value is None:
        return HookRuntimeOutcome()
    if isinstance(value, HookRuntimeOutcome):
        return value
    if isinstance(value, bool):
        return HookRuntimeOutcome(should_stop=value)
    if isinstance(value, Mapping):
        should_stop = value.get("should_stop", value.get("shouldStop", False))
        additional_contexts = value.get("additional_contexts", value.get("additionalContexts", ()))
        return HookRuntimeOutcome(bool(should_stop), tuple(additional_contexts or ()))
    should_stop = getattr(value, "should_stop", getattr(value, "shouldStop", False))
    additional_contexts = getattr(value, "additional_contexts", getattr(value, "additionalContexts", ()))
    return HookRuntimeOutcome(bool(should_stop), tuple(additional_contexts or ()))


def _user_prompt_submit_prompt(user_input: tuple[UserInput, ...]) -> str:
    input_item = ResponseInputItem.from_user_inputs(user_input)
    text_parts = [
        content.text
        for content in input_item.content
        if getattr(content, "type", None) == "input_text" and content.text is not None
    ]
    return "\n".join(text_parts)


def _validate_max_tool_followups(value: int | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("max_tool_followups must be an integer or None")
    if value < 0:
        raise ValueError("max_tool_followups must be >= 0")
    return value


@dataclass(frozen=True)
class _PendingInputRecordResult:
    recorded_items: tuple[ResponseItem, ...]
    blocked_without_accepted_user_input: bool = False
    accepted_user_input: bool = False


@dataclass(frozen=True)
class _PendingUserInput:
    items: tuple[UserInput, ...]


@dataclass(frozen=True)
class _PendingResponseItem:
    item: ResponseItem


async def _drain_and_record_pending_inputs(sess: Any, turn_context: Any) -> _PendingInputRecordResult:
    pending = await _drain_pending_input(sess)
    return await _record_pending_inputs_with_hooks(sess, turn_context, pending)


async def _drain_pending_input(sess: Any) -> Any:
    input_queue = getattr(sess, "input_queue", None)
    if input_queue is None:
        return ()
    get_pending_input = getattr(input_queue, "get_pending_input", None)
    if not callable(get_pending_input):
        return ()
    return await _call_input_queue_method(get_pending_input, sess)


async def _record_pending_inputs_with_hooks(
    sess: Any,
    turn_context: Any,
    pending: Any,
) -> _PendingInputRecordResult:
    blocked_input = False
    accepted_user_input = False
    recorded_items: list[ResponseItem] = []

    for pending_item in _pending_input_turn_items(pending):
        if isinstance(pending_item, _PendingUserInput):
            outcome = await _run_user_prompt_submit_hook(sess, turn_context, pending_item.items)
            if outcome is None:
                outcome = HookRuntimeOutcome()
            additional_items = additional_context_messages(outcome.additional_contexts)
            if outcome.should_stop:
                blocked_input = True
                if additional_items:
                    await _maybe_await(sess.record_conversation_items(turn_context, additional_items))
                    recorded_items.extend(additional_items)
                continue
            if pending_item.items:
                accepted_user_input = True
            response_item = await _record_user_inputs(sess, turn_context, pending_item.items)
            recorded_items.append(response_item)
            if additional_items:
                await _maybe_await(sess.record_conversation_items(turn_context, additional_items))
                recorded_items.extend(additional_items)
            continue

        items = (pending_item.item,)
        await _maybe_await(sess.record_conversation_items(turn_context, items))
        recorded_items.extend(items)

    return _PendingInputRecordResult(
        tuple(recorded_items),
        blocked_without_accepted_user_input=blocked_input and not accepted_user_input,
        accepted_user_input=accepted_user_input,
    )


async def _drain_pending_input_response_items(sess: Any, turn_context: Any) -> tuple[ResponseItem, ...]:
    pending = await _drain_pending_input(sess)
    return _pending_input_response_items(pending)


async def _call_input_queue_method(method: Callable[..., Any], sess: Any) -> Any:
    active_turn = getattr(sess, "active_turn", None)
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        try:
            return await _maybe_await(method(active_turn))
        except TypeError:
            return await _maybe_await(method())
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    accepts_positional = any(
        parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
        for parameter in signature.parameters.values()
    )
    accepts_kw_only_active_turn = any(
        parameter.kind == inspect.Parameter.KEYWORD_ONLY
        and parameter.name == "active_turn"
        and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )
    accepts_kw_active_turn_optional = any(
        parameter.kind == inspect.Parameter.KEYWORD_ONLY
        and parameter.name == "active_turn"
        for parameter in signature.parameters.values()
    )
    if active_turn is not None and accepts_positional:
        return await _maybe_await(method(active_turn))
    if active_turn is not None and accepts_kw_only_active_turn:
        return await _maybe_await(method(active_turn=active_turn))
    if active_turn is not None and accepts_kw_active_turn_optional:
        try:
            return await _maybe_await(method(active_turn=active_turn))
        except TypeError:
            pass
    if required:
        return await _maybe_await(method(active_turn))
    return await _maybe_await(method())


def _pending_input_response_items(pending: Any) -> tuple[ResponseItem, ...]:
    return tuple(
        item.item
        if isinstance(item, _PendingResponseItem)
        else ResponseItem.from_response_input_item(ResponseInputItem.from_user_inputs(item.items))
        for item in _pending_input_turn_items(pending)
    )


def _pending_input_turn_items(pending: Any) -> tuple[_PendingUserInput | _PendingResponseItem, ...]:
    if pending is None:
        return ()
    if isinstance(pending, (str, bytes)) or not isinstance(pending, Sequence):
        raise TypeError("pending input must be a sequence")
    pending_items: list[_PendingUserInput | _PendingResponseItem] = []
    user_inputs: list[UserInput] = []

    def flush_user_inputs() -> None:
        if not user_inputs:
            return
        pending_items.append(_PendingUserInput(tuple(user_inputs)))
        user_inputs.clear()

    for item in pending:
        if isinstance(item, UserInput):
            user_inputs.append(item)
            continue
        user_input = _pending_user_input(item)
        if user_input is not None:
            user_inputs.extend(user_input)
            continue
        flush_user_inputs()
        response_item = _pending_response_item(item)
        if response_item is not None:
            pending_items.append(_PendingResponseItem(response_item))
    flush_user_inputs()
    return tuple(pending_items)


def _pending_user_input(value: Any) -> tuple[UserInput, ...] | None:
    if isinstance(value, Mapping):
        pending_type = value.get("type")
        if pending_type in {"user_input", "UserInput"}:
            raw_items = value.get("items", value.get("input", value.get("content", ())))
            return _user_inputs(_sequence_value(raw_items))
        if pending_type in {"text", "image", "local_image", "skill", "mention"}:
            return (UserInput.from_mapping(value),)
        return None
    user_input = getattr(value, "user_input", None)
    if user_input is None:
        return None
    if isinstance(user_input, UserInput):
        return (user_input,)
    if isinstance(user_input, Mapping):
        return (UserInput.from_mapping(user_input),)
    return _user_inputs(tuple(user_input))


def _pending_response_item(value: Any) -> ResponseItem | None:
    if isinstance(value, ResponseItem):
        return value
    if isinstance(value, ResponseInputItem):
        return ResponseItem.from_response_input_item(value)
    if isinstance(value, Mapping):
        pending_type = value.get("type")
        if pending_type in {"response_item", "ResponseItem"}:
            response_item = value.get("item", value.get("response_item"))
            if response_item is None:
                return None
            return response_item if isinstance(response_item, ResponseItem) else ResponseItem.from_mapping(response_item)
        return ResponseItem.from_mapping(value)
    response_item = getattr(value, "response_item", None)
    if response_item is not None:
        return response_item if isinstance(response_item, ResponseItem) else ResponseItem.from_mapping(response_item)
    return None


def _sequence_value(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _user_input_op_fields(value: Op | dict[str, Any]) -> dict[str, Any]:
    op = value if isinstance(value, Op) else Op.from_mapping(value)
    if op.type != "user_input":
        raise TypeError("op must be user_input")
    return dict(op.fields or {})


def _apply_responsesapi_client_metadata(turn_context: Any, value: Mapping[str, str] | None) -> None:
    if value is None:
        return
    target = getattr(turn_context, "turn_metadata_state", turn_context)
    setter = getattr(target, "set_responsesapi_client_metadata", None)
    if callable(setter):
        setter(value)


def _additional_context_response_items(sess: Any, value: Mapping[str, Any] | None) -> tuple[ResponseItem, ...]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise TypeError("additional_context must be a mapping")
    normalized = _normalize_additional_context(value)
    previous = getattr(sess, "_additional_context_values", {})
    items: list[ResponseItem] = []
    for key in sorted(normalized):
        kind, context_value = normalized[key]
        if previous.get(key) == (kind, context_value):
            continue
        if kind == "untrusted":
            items.append(
                ResponseItem.message(
                    "user",
                    (ContentItem.input_text(f"<external_{key}>{context_value}</external_{key}>"),),
                )
            )
        elif kind == "application":
            items.append(
                ResponseItem.message(
                    "developer",
                    (ContentItem.input_text(f"<{key}>{context_value}</{key}>"),),
                )
            )
        else:
            raise ValueError(f"unknown additional_context kind: {kind}")
    try:
        setattr(sess, "_additional_context_values", normalized)
    except Exception:
        pass
    return tuple(items)


def _normalize_additional_context(value: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    normalized: dict[str, tuple[str, str]] = {}
    for key, entry in value.items():
        if not isinstance(key, str):
            raise TypeError("additional_context keys must be strings")
        if not isinstance(entry, Mapping):
            raise TypeError("additional_context entries must be mappings")
        kind = entry.get("kind")
        context_value = entry.get("value")
        if not isinstance(kind, str):
            raise TypeError("additional_context entry kind must be a string")
        if not isinstance(context_value, str):
            raise TypeError("additional_context entry value must be a string")
        context_value = truncate_middle_with_token_budget(context_value, MAX_ADDITIONAL_CONTEXT_TOKENS)[0]
        normalized[key] = (kind, context_value)
    return normalized


async def _apply_thread_settings_overrides(sess: Any, value: Any) -> None:
    if value is None:
        return
    thread_settings = value if isinstance(value, ThreadSettingsOverrides) else ThreadSettingsOverrides.from_mapping(value)
    if thread_settings == ThreadSettingsOverrides.default():
        return
    applier = getattr(sess, "apply_thread_settings_overrides", None)
    if callable(applier):
        await _maybe_await(applier(thread_settings))
        return
    updater = getattr(sess, "thread_settings_update", None)
    update_settings = getattr(sess, "update_settings", None)
    if callable(updater) and callable(update_settings):
        updates = await _maybe_await(updater(thread_settings))
        await _maybe_await(update_settings(updates))
        return
    raise TypeError("session must support thread settings overrides")


async def _apply_turn_environments(sess: Any, value: Sequence[Any] | None) -> None:
    if value is None:
        return
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("environments must be a sequence")
    update_settings = getattr(sess, "update_settings", None)
    if callable(update_settings):
        await _maybe_await(update_settings(SessionSettingsUpdate(environments=tuple(value))))
        return
    try:
        setattr(sess, "environments", tuple(value))
    except Exception as exc:
        raise TypeError("session must support turn environments") from exc


async def _apply_final_output_json_schema(sess: Any, value: Any) -> None:
    update_settings = getattr(sess, "update_settings", None)
    if callable(update_settings):
        await _maybe_await(update_settings(SessionSettingsUpdate(final_output_json_schema=value)))
        return
    try:
        setattr(sess, "final_output_json_schema", value)
    except Exception as exc:
        raise TypeError("session must support final output JSON schema updates") from exc


def _turn_setting(turn_context: Any, config_name: str, fallback_name: str) -> Any:
    config = getattr(turn_context, "config", None)
    value = None if config is None else getattr(config, config_name, None)
    if value is not None:
        return value
    return getattr(turn_context, fallback_name, None)


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


def _stream_events_from_sampling_result(value: Any) -> tuple[Any, ...]:
    raw_events = getattr(value, "stream_events", ())
    if raw_events is None:
        return ()
    if isinstance(raw_events, Mapping):
        return (raw_events,)
    if isinstance(raw_events, (str, bytes)) or not isinstance(raw_events, Sequence):
        raise TypeError("sampler stream_events must be a mapping or sequence")
    return tuple(raw_events)


async def _record_stream_events_turn_ttft(
    sess: Any,
    turn_context: Any,
    stream_events: Sequence[Any],
) -> None:
    timing_state = getattr(turn_context, "turn_timing_state", None) or getattr(sess, "turn_timing_state", None)
    recorder = getattr(timing_state, "record_ttft_for_response_event", None)
    if not callable(recorder):
        return
    for event in stream_events:
        timing_event = _timing_response_event_from_stream_event(event)
        if timing_event is None:
            continue
        recorded = await _maybe_await(recorder(timing_event))
        if recorded is None:
            continue
        await _sync_turn_timing_first_token_ms(turn_context, timing_state)
        return


async def _sync_turn_timing_first_token_ms(turn_context: Any, timing_state: Any) -> None:
    getter = getattr(timing_state, "time_to_first_token_ms", None)
    if not callable(getter):
        return
    value = await _maybe_await(getter())
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            setattr(turn_context, "time_to_first_token_ms", value)
        except Exception:
            pass


def _timing_response_event_from_stream_event(event: Any) -> TimingResponseEvent | None:
    if not isinstance(event, Mapping):
        return None
    event_type = event.get("type")
    if not isinstance(event_type, str):
        return None
    normalized_type = _STREAM_EVENT_TIMING_ALIASES.get(event_type, event_type)
    if normalized_type == "output_item_done":
        item = event.get("item")
        if isinstance(item, ResponseItem):
            return TimingResponseEvent.output_item_done(item)
        return None
    if normalized_type == "output_item_added":
        item = event.get("item")
        if isinstance(item, ResponseItem):
            return TimingResponseEvent.output_item_added(item)
        return None
    if normalized_type == "output_text_delta":
        return TimingResponseEvent.output_text_delta()
    if normalized_type == "reasoning_summary_delta":
        return TimingResponseEvent.reasoning_summary_delta()
    if normalized_type == "reasoning_content_delta":
        return TimingResponseEvent.reasoning_content_delta()
    if normalized_type == "created":
        return TimingResponseEvent.created()
    if normalized_type == "server_model":
        return TimingResponseEvent.server_model()
    if normalized_type == "model_verifications":
        return TimingResponseEvent.model_verifications()
    if normalized_type == "server_reasoning_included":
        return TimingResponseEvent.server_reasoning_included()
    if normalized_type == "tool_call_input_delta":
        return TimingResponseEvent.tool_call_input_delta()
    if normalized_type == "completed":
        return TimingResponseEvent.completed()
    if normalized_type == "reasoning_summary_part_added":
        return TimingResponseEvent.reasoning_summary_part_added()
    if normalized_type == "rate_limits":
        return TimingResponseEvent.rate_limits()
    if normalized_type == "models_etag":
        return TimingResponseEvent.models_etag()
    return None


_STREAM_EVENT_TIMING_ALIASES = {
    "response.created": "created",
    "response.output_item.done": "output_item_done",
    "response.output_item.added": "output_item_added",
    "response.output_text.delta": "output_text_delta",
    "response.function_call_arguments.delta": "tool_call_input_delta",
    "response.custom_tool_call_input.delta": "tool_call_input_delta",
    "response.reasoning_summary_text.delta": "reasoning_summary_delta",
    "response.reasoning_summary_part.added": "reasoning_summary_part_added",
    "response.reasoning_text.delta": "reasoning_content_delta",
    "response.completed": "completed",
}


def _sampling_stream_event_dispatch_plans_from_result(
    raw_result: Any,
    router: Any,
    *,
    turn_context: Any = None,
    thread_id: str = "",
    turn_id: str = "",
) -> tuple[Any, ...]:
    stream_events = _stream_events_from_sampling_result(raw_result)
    if not stream_events:
        return ()
    tool_runtime = ToolCallRuntime(router) if isinstance(router, ToolRouter) else router
    state = SamplingOutputState()
    active_item = None
    active_item_is_streaming_to_client = False
    active_tool_argument_diff_consumer = None
    plan_mode = _turn_context_plan_mode(turn_context)
    assistant_message_stream_parsers = AssistantMessageStreamParsers(plan_mode=plan_mode)
    plans: list[Any] = []
    for event in stream_events:
        if not isinstance(event, Mapping):
            raise TypeError("sampler stream_events entries must be mappings")
        event_type = event.get("type")
        if not isinstance(event_type, str):
            raise TypeError("sampler stream event must include string type")
        payload = _sampling_stream_event_payload(event)
        dispatch_plan = sampling_stream_event_dispatch_plan(
            event_type,
            payload,
            state=state,
            active_item=active_item,
            active_item_is_streaming_to_client=active_item_is_streaming_to_client,
            active_tool_argument_diff_consumer=active_tool_argument_diff_consumer,
            assistant_message_stream_parsers=assistant_message_stream_parsers,
            plan_mode=plan_mode,
            tool_runtime=tool_runtime,
            call_id=event.get("call_id") if isinstance(event.get("call_id"), str) else None,
            thread_id=thread_id,
            turn_id=turn_id,
            summary_index=_int_event_field(event, "summary_index"),
            content_index=_int_event_field(event, "content_index"),
            response_id=_sampling_stream_completed_response_id(event),
            token_usage=_sampling_stream_completed_token_usage(event),
            end_turn=_sampling_stream_completed_end_turn(event),
            turn_context=turn_context,
        )
        plans.append(dispatch_plan)
        added_plan = getattr(dispatch_plan, "output_item_added_plan", None)
        if added_plan is not None:
            if getattr(added_plan, "reset_tool_argument_diff_consumer", False):
                active_tool_argument_diff_consumer = None
            elif getattr(added_plan, "active_tool_argument_diff_consumer", None) is not None:
                active_tool_argument_diff_consumer = added_plan.active_tool_argument_diff_consumer
            active_item = getattr(added_plan, "active_item", None)
            active_item_is_streaming_to_client = bool(
                getattr(added_plan, "active_item_is_streaming_to_client", False)
            )
        if getattr(dispatch_plan, "output_item_done_transition_plan", None) is not None:
            item = event.get("item")
            if isinstance(item, ResponseItem):
                state = SamplingOutputState(
                    needs_follow_up=state.needs_follow_up or item.type in _TOOL_RESPONSE_ITEM_TYPES,
                    last_agent_message=state.last_agent_message,
                    in_flight=state.in_flight,
                )
            active_tool_argument_diff_consumer = None
            active_item = None
            active_item_is_streaming_to_client = False
    return tuple(plans)


def _turn_context_turn_id(turn_context: Any) -> str:
    for name in ("turn_id", "sub_id"):
        value = getattr(turn_context, name, None)
        if value is not None:
            return str(value)
    return ""


def _turn_context_model_context_window(turn_context: Any) -> int | None:
    for name in ("model_context_window", "context_window"):
        value = getattr(turn_context, name, None)
        if callable(value):
            value = value()
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    model_info = getattr(turn_context, "model_info", None)
    for name in ("context_window", "model_context_window"):
        value = getattr(model_info, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _turn_context_collaboration_mode_kind(turn_context: Any) -> Any:
    collaboration_mode = getattr(turn_context, "collaboration_mode", None)
    mode = getattr(collaboration_mode, "mode", collaboration_mode)
    value = getattr(mode, "value", mode)
    return value if value is not None else "default"


def _optional_str_attr(value: Any, name: str) -> str | None:
    attr = getattr(value, name, None)
    return attr if isinstance(attr, str) else None


def _optional_int_attr(value: Any, name: str) -> int | None:
    attr = getattr(value, name, None)
    return attr if isinstance(attr, int) and not isinstance(attr, bool) else None


def _turn_context_plan_mode(turn_context: Any) -> bool:
    collaboration_mode = getattr(turn_context, "collaboration_mode", None)
    mode = getattr(collaboration_mode, "mode", collaboration_mode)
    value = getattr(mode, "value", mode)
    return str(value).lower() == "plan"


async def _sample_with_retry(
    sess: Any,
    turn_context: Any,
    provider: Any,
    sampler: SamplerFn,
    sampling_request: UserTurnSamplingRequest,
) -> Any:
    retries = 0
    max_retries = _provider_stream_max_retries(provider)
    while True:
        try:
            return await _maybe_await(sampler(sampling_request))
        except CodexErr as err:
            if not err.is_retryable():
                raise
            decision = response_stream_retry_decision(
                retries=retries,
                max_retries=max_retries,
                err=err,
                request=ResponsesStreamRequest.SAMPLING,
                fallback_transport_available=_sampling_fallback_transport_available(sess),
                responses_websocket_enabled=_responses_websocket_enabled(sess),
            )
            if decision.action is RetryableResponseStreamAction.RETRY:
                await _emit_sampling_retry_decision(sess, turn_context, decision)
                retries = decision.retries
                if decision.delay is not None:
                    await _sleep_for_sampling_retry(sess, decision.delay.total_seconds())
                continue
            if decision.action is RetryableResponseStreamAction.FALLBACK_TRANSPORT:
                if _activate_sampling_fallback_transport(sess, turn_context):
                    await _emit_sampling_retry_decision(sess, turn_context, decision)
                    retries = decision.retries
                    continue
            raise decision.error or err


def _provider_stream_max_retries(provider: Any) -> int:
    configured = _provider_stream_max_retries_value(provider)
    if configured is None:
        return DEFAULT_STREAM_MAX_RETRIES
    if isinstance(configured, bool) or not isinstance(configured, int):
        raise TypeError("stream_max_retries must be an integer")
    if configured < 0:
        raise ValueError("stream_max_retries must be non-negative")
    return min(configured, MAX_STREAM_MAX_RETRIES)


def _provider_stream_max_retries_value(provider: Any) -> Any:
    info = _provider_info(provider)
    for source in (info, provider):
        if source is None:
            continue
        value = _stream_max_retries_value(source)
        if value is not None:
            return value
    return None


def _provider_info(provider: Any) -> Any:
    if isinstance(provider, Mapping):
        value = provider.get("info")
        return value() if callable(value) else value
    value = getattr(provider, "info", None)
    return value() if callable(value) else value


def _stream_max_retries_value(source: Any) -> Any:
    if isinstance(source, Mapping):
        value = source.get("stream_max_retries")
        return value() if callable(value) else value
    value = getattr(source, "stream_max_retries", None)
    return value() if callable(value) else value


def _responses_websocket_enabled(sess: Any) -> bool:
    services = getattr(sess, "services", None)
    model_client = getattr(services, "model_client", None)
    enabled = getattr(model_client, "responses_websocket_enabled", None)
    if callable(enabled):
        return bool(enabled())
    if enabled is not None:
        return bool(enabled)
    return False


def _sampling_fallback_transport_available(sess: Any) -> bool:
    services = getattr(sess, "services", None)
    model_client = getattr(services, "model_client", None)
    fallback = getattr(model_client, "force_http_fallback", None)
    return callable(fallback) and _responses_websocket_enabled(sess)


def _activate_sampling_fallback_transport(sess: Any, turn_context: Any) -> bool:
    services = getattr(sess, "services", None)
    model_client = getattr(services, "model_client", None)
    fallback = getattr(model_client, "force_http_fallback", None)
    if not callable(fallback):
        return False
    session_telemetry = getattr(turn_context, "session_telemetry", None)
    model_info = getattr(turn_context, "model_info", None)
    return bool(fallback(session_telemetry, model_info))


async def _emit_sampling_retry_decision(sess: Any, turn_context: Any, decision: Any) -> None:
    warning_message = getattr(decision, "warning_message", None)
    if isinstance(warning_message, str) and warning_message:
        await _send_warning_event(sess, turn_context, warning_message)

    notify_message = getattr(decision, "notify_message", None)
    error = getattr(decision, "error", None)
    if not isinstance(notify_message, str) or not notify_message or not isinstance(error, CodexErr):
        return

    notifier = getattr(sess, "notify_stream_error", None)
    if callable(notifier):
        await _maybe_await(notifier(turn_context, notify_message, error))
        return

    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(
            sender(
                turn_context,
                EventMsg.with_payload(
                    "stream_error",
                    StreamErrorEvent(
                        message=notify_message,
                        codex_error_info=CodexErrorInfo.response_stream_disconnected(error.http_status_code_value()),
                        additional_details=str(error),
                    ),
                ),
            )
        )


async def _sleep_for_sampling_retry(sess: Any, seconds: float) -> None:
    sleeper = getattr(sess, "sleep_for_sampling_retry", None) or getattr(sess, "sleep_for_retry", None)
    if callable(sleeper):
        await _maybe_await(sleeper(seconds))
        return
    await asyncio.sleep(seconds)


async def _has_pending_mailbox_items(sess: Any) -> bool:
    input_queue = getattr(sess, "input_queue", None)
    for source in (input_queue, sess):
        if source is None:
            continue
        checker = getattr(source, "has_pending_mailbox_items", None)
        if callable(checker):
            return bool(await _maybe_await(checker()))
    return False


async def _has_pending_input(sess: Any) -> bool:
    input_queue = getattr(sess, "input_queue", None)
    if input_queue is None:
        return False
    checker = getattr(input_queue, "has_pending_input", None)
    if not callable(checker):
        return False
    return bool(await _call_input_queue_method(checker, sess))


async def _emit_stream_runtime_events(
    sess: Any,
    turn_context: Any,
    runtime_state: SamplingRuntimeEventApplicationState,
    cursor: int,
) -> int:
    sender = getattr(sess, "send_event", None)
    events = tuple(getattr(runtime_state, "emitted_stream_events", ()) or ())
    if not callable(sender):
        return len(events)
    for event in events[cursor:]:
        if event is None:
            continue
        await _record_stream_runtime_event_turn_ttfm(sess, turn_context, event)
        await _maybe_await(sender(turn_context, event))
    return len(events)


async def _apply_stream_runtime_session_side_effects(
    sess: Any,
    turn_context: Any,
    runtime_state: SamplingRuntimeEventApplicationState,
    raw_result: Any,
) -> None:
    await _apply_stream_metadata_event_side_effects(sess, turn_context, runtime_state)
    metadata_events = tuple(getattr(runtime_state, "metadata_events", ()) or ())

    if getattr(runtime_state, "server_reasoning_included", None) is not None and (
        _first_metadata_attr(raw_result, "server_reasoning_included") is None
        or _metadata_events_include_type(metadata_events, "server_reasoning_included")
    ):
        handler = getattr(sess, "set_server_reasoning_included", None)
        if callable(handler):
            await _maybe_await(handler(runtime_state.server_reasoning_included))
        runtime_state.server_reasoning_included = None

    if getattr(runtime_state, "models_etag_to_refresh", None) is not None and (
        _first_metadata_attr(raw_result, "models_etag") is None
        or _metadata_events_include_type(metadata_events, "models_etag")
    ):
        for name in ("refresh_models_etag", "record_models_etag"):
            handler = getattr(sess, name, None)
            if callable(handler):
                await _maybe_await(handler(runtime_state.models_etag_to_refresh))
                break
        runtime_state.models_etag_to_refresh = None

    if getattr(runtime_state, "rate_limits_to_record", None) is not None and (
        not _rate_limits_from_sampling_result(raw_result) or _metadata_events_include_type(metadata_events, "rate_limits")
    ):
        recorder = getattr(sess, "record_rate_limits_info", None)
        if callable(recorder):
            await _maybe_await(recorder(runtime_state.rate_limits_to_record))
        runtime_state.rate_limits_to_record = None

    if getattr(runtime_state, "token_usage_to_record", None) is not None and (
        _token_usage_from_sampling_result(raw_result) is None
    ):
        token_usage = _coerce_stream_token_usage(runtime_state.token_usage_to_record)
        recorder = getattr(sess, "record_token_usage_info", None)
        if callable(recorder) and token_usage is not None:
            await _maybe_await(recorder(turn_context, token_usage))
        runtime_state.token_usage_to_record = None


async def _apply_stream_metadata_event_side_effects(
    sess: Any,
    turn_context: Any,
    runtime_state: SamplingRuntimeEventApplicationState,
) -> None:
    metadata_events = tuple(getattr(runtime_state, "metadata_events", ()) or ())
    cursor = getattr(turn_context, "_stream_metadata_events_applied_count", 0)
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        cursor = 0

    for record in metadata_events[cursor:]:
        if not isinstance(record, Mapping):
            continue
        server_model = record.get("server_model_to_check")
        if isinstance(server_model, str) and not bool(getattr(turn_context, "server_model_warning_emitted", False)):
            handler = getattr(sess, "maybe_warn_on_server_model_mismatch", None)
            if callable(handler) and await _maybe_await(handler(turn_context, server_model)):
                try:
                    object.__setattr__(turn_context, "server_model_warning_emitted", True)
                except Exception:
                    pass

        model_verification = record.get("model_verification_to_emit")
        if model_verification is not None and not bool(getattr(turn_context, "model_verification_emitted", False)):
            handler = getattr(sess, "emit_model_verification", None)
            if callable(handler):
                await _maybe_await(handler(turn_context, model_verification))
                try:
                    object.__setattr__(turn_context, "model_verification_emitted", True)
                except Exception:
                    pass

    try:
        object.__setattr__(turn_context, "_stream_metadata_events_applied_count", len(metadata_events))
    except Exception:
        pass


def _coerce_stream_token_usage(value: Any) -> TokenUsage | None:
    if isinstance(value, TokenUsage):
        return None if value.is_zero() else value
    if isinstance(value, Mapping):
        return _token_usage_from_sampling_result({"token_usage": value})
    return None


async def _apply_stream_runtime_loop_tail(
    sess: Any,
    turn_context: Any,
    apply_plans: Sequence[Any],
) -> None:
    tail = _stream_runtime_loop_tail_from_apply_plans(apply_plans)
    completed_response_id = tail["completed_response_id"]
    if isinstance(completed_response_id, str) and _feature_enabled(
        _session_or_turn_features(sess, turn_context),
        Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED,
    ):
        sender = getattr(sess, "send_response_processed", None)
        if callable(sender):
            await _maybe_await(sender(completed_response_id))

    drainer = getattr(sess, "drain_in_flight", None)
    if callable(drainer):
        await _maybe_await(drainer())

    if tail["should_emit_token_count"]:
        sender = getattr(sess, "send_token_count_event", None)
        if callable(sender):
            await _maybe_await(sender(turn_context))

    if _cancellation_requested(turn_context):
        raise CodexErr.simple("turn_aborted")

    if tail["should_emit_turn_diff"]:
        unified_diff = await _stream_runtime_unified_diff(sess, turn_context)
        if unified_diff is not None:
            sender = getattr(sess, "send_event", None)
            if callable(sender):
                await _maybe_await(sender(turn_context, EventMsg.with_payload("turn_diff", TurnDiffEvent(unified_diff))))


def _stream_runtime_loop_tail_from_apply_plans(apply_plans: Sequence[Any]) -> dict[str, Any]:
    completed_response_id = None
    should_emit_token_count = False
    should_emit_turn_diff = False
    for plan in apply_plans:
        completed = getattr(plan, "completed_event_apply_plan", None)
        if completed is not None:
            value = getattr(completed, "completed_response_id_after", None)
            if isinstance(value, str):
                completed_response_id = value
            should_emit_token_count = should_emit_token_count or bool(
                getattr(completed, "should_emit_token_count", False)
            )
            should_emit_turn_diff = should_emit_turn_diff or bool(
                getattr(completed, "should_emit_turn_diff", False)
            )
        metadata = getattr(plan, "metadata_event_apply_plan", None)
        if metadata is not None:
            should_emit_token_count = should_emit_token_count or bool(
                getattr(metadata, "should_emit_token_count", False)
            )
    return {
        "completed_response_id": completed_response_id,
        "should_emit_token_count": should_emit_token_count,
        "should_emit_turn_diff": should_emit_turn_diff,
    }


def _stream_completed_end_turn_needs_followup(stream_events: Sequence[Any]) -> bool:
    for event in stream_events:
        if (
            isinstance(event, Mapping)
            and _is_completed_sampling_stream_event_type(event.get("type"))
            and _sampling_stream_completed_end_turn(event) is False
        ):
            return True
    return False


def _stream_apply_plans_need_followup(apply_plans: Sequence[Any]) -> bool:
    for plan in apply_plans:
        done = getattr(plan, "output_item_done_apply_plan", None)
        if done is None:
            continue
        mailbox_preemption = getattr(done, "mailbox_preemption_plan", None)
        if mailbox_preemption is not None and bool(getattr(mailbox_preemption, "needs_follow_up", False)):
            return True
    return False


def _update_stream_runtime_last_agent_message_from_response_items(
    runtime_state: SamplingRuntimeEventApplicationState,
    response_items: Sequence[ResponseItem],
) -> None:
    last_agent_message = get_last_assistant_message_from_turn(tuple(response_items))
    if last_agent_message is not None:
        runtime_state.result_last_agent_message = last_agent_message


def _last_agent_message_from_sampling(
    runtime_state: SamplingRuntimeEventApplicationState,
    response_items: Sequence[ResponseItem],
    apply_plans: Sequence[Any],
    stream_events: Sequence[Any],
) -> str | None:
    last_agent_message = getattr(runtime_state, "result_last_agent_message", None)
    if isinstance(last_agent_message, str):
        return last_agent_message
    for plan in reversed(tuple(apply_plans)):
        completed = getattr(plan, "completed_event_apply_plan", None)
        if completed is not None:
            value = getattr(completed, "result_last_agent_message", None)
            if isinstance(value, str):
                return value
        done = getattr(plan, "output_item_done_apply_plan", None)
        if done is None:
            continue
        for name in ("mailbox_preemption_plan", "state_after_output_result"):
            state = getattr(done, name, None)
            value = getattr(state, "last_agent_message", None)
            if isinstance(value, str):
                return value
    for event in reversed(tuple(stream_events)):
        if not isinstance(event, Mapping) or event.get("type") != "output_item_done":
            continue
        item = event.get("item")
        if isinstance(item, ResponseItem):
            value = get_last_assistant_message_from_turn((item,))
            if value is not None:
                return value
    return get_last_assistant_message_from_turn(tuple(response_items)) if response_items else None


def _session_or_turn_features(sess: Any, turn_context: Any) -> Any:
    features = getattr(sess, "features", None)
    if features is not None:
        return features
    return getattr(turn_context, "features", None)


def _cancellation_requested(turn_context: Any) -> bool:
    token = getattr(turn_context, "cancellation_token", None)
    if token is None:
        return bool(getattr(turn_context, "cancelled", False))
    checker = getattr(token, "is_cancelled", None)
    if callable(checker):
        return bool(checker())
    return bool(token)


async def _stream_runtime_unified_diff(sess: Any, turn_context: Any) -> str | None:
    for name in ("get_unified_diff", "get_turn_diff", "turn_diff"):
        reader = getattr(sess, name, None)
        if callable(reader):
            value = await _maybe_await(_call_with_optional_turn_context(reader, turn_context))
            return value if isinstance(value, str) and value else None
        if isinstance(reader, str) and reader:
            return reader
    tracker = getattr(sess, "turn_diff_tracker", None) or getattr(turn_context, "turn_diff_tracker", None)
    reader = getattr(tracker, "get_unified_diff", None)
    if callable(reader):
        value = await _maybe_await(reader())
        return value if isinstance(value, str) and value else None
    return None


def _call_with_optional_turn_context(callback: Any, turn_context: Any) -> Any:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback()
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]
    if required:
        return callback(turn_context)
    return callback()


def _sampling_stream_event_apply_plans_from_result(
    raw_result: Any,
    dispatch_plans: Sequence[Any],
    runtime_state: SamplingRuntimeEventApplicationState,
    *,
    turn_context: Any = None,
    has_pending_mailbox_items: bool = False,
) -> tuple[Any, ...]:
    stream_events = _stream_events_from_sampling_result(raw_result)
    if not stream_events:
        return ()
    if len(stream_events) != len(dispatch_plans):
        raise ValueError("stream event and dispatch plan counts differ")
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=runtime_state)
    output_state = SamplingOutputState()
    plan_mode = _turn_context_plan_mode(turn_context)
    turn_id = _turn_context_turn_id(turn_context)
    runtime_state.plan_item_id = f"{turn_id}-plan" if turn_id else "plan"
    assistant_message_stream_parsers = AssistantMessageStreamParsers(plan_mode=plan_mode)
    apply_plans: list[Any] = []
    for event, dispatch_plan in zip(stream_events, dispatch_plans, strict=True):
        if not isinstance(event, Mapping):
            raise TypeError("sampler stream_events entries must be mappings")
        item = event.get("item") if event.get("type") == "output_item_done" else None
        output_item_done_item = item if isinstance(item, ResponseItem) else None
        output_item_done_result = (
            _stream_event_output_result_for_item(output_item_done_item, plan_mode=plan_mode)
            if output_item_done_item is not None
            else None
        )
        apply_plan = sampling_stream_event_apply_plan(
            dispatch_plan,
            plan_mode=plan_mode,
            state=output_state,
            output_item_done_item=output_item_done_item,
            output_item_done_result=output_item_done_result,
            has_pending_mailbox_items=has_pending_mailbox_items,
            assistant_message_stream_parsers=assistant_message_stream_parsers,
            plan_item_id=runtime_state.plan_item_id,
            plan_item_started=runtime_state.plan_item_started,
            plan_item_completed=runtime_state.plan_item_completed,
            pending_agent_message_items={
                item.id(): item
                for item in runtime_state.pending_agent_message_items
                if isinstance(item, TurnItem)
            },
            started_agent_message_item_ids=runtime_state.started_agent_message_item_ids,
            leading_whitespace_by_item=dict(runtime_state.leading_whitespace_by_item),
        )
        apply_plans.append(apply_plan)
        adapter.apply_event_plan({"type": "apply_event_plan", "plan": apply_plan})
        state_after = getattr(getattr(apply_plan, "output_item_done_apply_plan", None), "state_after_output_result", None)
        if isinstance(state_after, SamplingOutputState):
            output_state = state_after
    return tuple(apply_plans)


def _stream_event_output_result_for_item(item: ResponseItem, *, plan_mode: bool) -> OutputItemResult:
    return OutputItemResult(
        needs_follow_up=item.type in _TOOL_RESPONSE_ITEM_TYPES,
        last_agent_message=last_assistant_message_from_item(item, plan_mode),
    )


_TOOL_RESPONSE_ITEM_TYPES = {
    "function_call",
    "custom_tool_call",
    "local_shell_call",
    "tool_search_call",
}


def _sampling_stream_event_payload(event: Mapping[str, Any]) -> Any:
    event_type = event.get("type")
    if event_type in {"output_item_added", "output_item_done"}:
        return event.get("item")
    if event_type in {
        "server_model",
        "model_verifications",
        "server_reasoning_included",
        "rate_limits",
        "models_etag",
    }:
        return event.get(event_type)
    if _is_completed_sampling_stream_event_type(event_type):
        return {
            "response_id": _sampling_stream_completed_response_id(event),
            "token_usage": _sampling_stream_completed_token_usage(event),
            "end_turn": _sampling_stream_completed_end_turn(event),
        }
    return event


def _is_completed_sampling_stream_event_type(event_type: Any) -> bool:
    return event_type in {"completed", "response.completed"}


def _sampling_stream_completed_response(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    response = event.get("response")
    return response if isinstance(response, Mapping) else None


def _sampling_stream_completed_response_id(event: Mapping[str, Any]) -> str | None:
    value = event.get("response_id")
    if isinstance(value, str):
        return value
    response = _sampling_stream_completed_response(event)
    if response is None:
        return None
    value = response.get("id")
    return value if isinstance(value, str) else None


def _sampling_stream_completed_token_usage(event: Mapping[str, Any]) -> Any:
    usage = event.get("token_usage")
    if usage is not None:
        return usage
    usage = event.get("usage")
    if usage is not None:
        return usage
    response = _sampling_stream_completed_response(event)
    if response is None:
        return None
    return response.get("usage")


def _sampling_stream_completed_end_turn(event: Mapping[str, Any]) -> bool | None:
    value = event.get("end_turn")
    if isinstance(value, bool):
        return value
    response = _sampling_stream_completed_response(event)
    if response is None:
        return None
    value = response.get("end_turn")
    return value if isinstance(value, bool) else None


def _int_event_field(event: Mapping[str, Any], name: str) -> int | None:
    value = event.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sampling_result_needs_followup(value: Any) -> bool:
    current = value
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        end_turn = getattr(current, "end_turn", None)
        if isinstance(end_turn, bool):
            return end_turn is False
        if isinstance(current, Mapping):
            end_turn = current.get("end_turn")
            return end_turn is False if isinstance(end_turn, bool) else False
        current = getattr(current, "raw_result", None)
    return False


async def _recover_invalid_image_request(sess: Any, turn_context: Any, error: CodexErr) -> bool:
    if error.kind != "invalid_image_request":
        return False
    if await _replace_last_turn_images(sess, "Invalid image"):
        return True
    await _emit_turn_error_lifecycle(sess, turn_context, CodexErrorInfo.bad_request())
    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(
            sender(
                turn_context,
                EventMsg.with_payload(
                    "error",
                    ErrorEvent(
                        "Invalid image in your last message. Please remove it and try again.",
                        CodexErrorInfo.bad_request(),
                    ),
                ),
            )
        )
    return False


async def _replace_last_turn_images(sess: Any, placeholder: str) -> bool:
    replacer = getattr(sess, "replace_last_turn_images", None)
    if callable(replacer):
        return bool(await _maybe_await(replacer(placeholder)))
    history = getattr(sess, "history", None)
    history_replacer = getattr(history, "replace_last_turn_images", None)
    if callable(history_replacer):
        return bool(await _maybe_await(history_replacer(placeholder)))
    state = getattr(sess, "state", None)
    state_history = getattr(state, "history", None)
    state_history_replacer = getattr(state_history, "replace_last_turn_images", None)
    if callable(state_history_replacer):
        return bool(await _maybe_await(state_history_replacer(placeholder)))
    items = getattr(history, "items", history)
    if isinstance(items, list):
        return _replace_last_turn_images_in_items(items, placeholder)
    return False


def _replace_last_turn_images_in_items(items: list[Any], placeholder: str) -> bool:
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if _is_function_call_output_item(item):
            replaced_item = _function_output_item_with_replaced_images(item, placeholder)
            if replaced_item is None:
                return False
            items[index] = replaced_item
            return True
        if _is_user_turn_boundary(item):
            return False
    return False


def _is_function_call_output_item(item: Any) -> bool:
    if isinstance(item, ResponseItem):
        return item.type == "function_call_output"
    if isinstance(item, Mapping):
        return item.get("type") == "function_call_output"
    return getattr(item, "type", None) == "function_call_output"


def _is_user_turn_boundary(item: Any) -> bool:
    role = item.get("role") if isinstance(item, Mapping) else getattr(item, "role", None)
    item_type = item.get("type") if isinstance(item, Mapping) else getattr(item, "type", None)
    return item_type == "message" and role == "user"


def _function_output_item_with_replaced_images(item: Any, placeholder: str) -> ResponseItem | dict[str, Any] | None:
    if isinstance(item, ResponseItem):
        output = item.output
        try:
            payload = output if isinstance(output, FunctionCallOutputPayload) else FunctionCallOutputPayload.from_value(output)
        except (TypeError, ValueError):
            return None
        replaced_output = _function_output_payload_with_replaced_images(payload, placeholder)
        if replaced_output is None:
            return None
        return replace(item, output=replaced_output)
    if isinstance(item, Mapping):
        try:
            response_item = ResponseItem.from_mapping(item)
        except (TypeError, ValueError, KeyError):
            return None
        replaced = _function_output_item_with_replaced_images(response_item, placeholder)
        return replaced.to_mapping() if isinstance(replaced, ResponseItem) else None
    return None


def _function_output_payload_with_replaced_images(
    payload: FunctionCallOutputPayload,
    placeholder: str,
) -> FunctionCallOutputPayload | None:
    body = payload.body
    if body.type != "content_items":
        return None
    content_items = []
    replaced = False
    for content_item in body.content_items:
        if content_item.type == "input_image":
            content_items.append(FunctionCallOutputContentItem.input_text(placeholder))
            replaced = True
        else:
            content_items.append(content_item)
    if not replaced:
        return None
    return FunctionCallOutputPayload.from_content_items(tuple(content_items), success=payload.success)


async def _handle_terminal_sampling_error(sess: Any, turn_context: Any, error: CodexErr) -> None:
    if error.kind == "turn_aborted":
        return
    if error.kind == "context_window_exceeded":
        handler = getattr(sess, "set_total_tokens_full", None)
        if callable(handler):
            await _maybe_await(handler(turn_context))
    elif error.kind == "usage_limit_reached" and isinstance(error.payload, UsageLimitReachedError):
        rate_limits = error.payload.rate_limits
        handler = getattr(sess, "update_rate_limits", None)
        if rate_limits is not None and callable(handler):
            await _maybe_await(handler(turn_context, rate_limits))
    error_info = error.to_codex_protocol_error()
    await _emit_turn_error_lifecycle(sess, turn_context, error_info)
    if error_info == CodexErrorInfo.usage_limit_exceeded():
        await _apply_usage_limit_goal_runtime(sess, turn_context)
    await _send_terminal_error_event(sess, turn_context, error)


async def _apply_usage_limit_goal_runtime(sess: Any, turn_context: Any) -> None:
    apply = sess.get("goal_runtime_apply") if isinstance(sess, Mapping) else getattr(sess, "goal_runtime_apply", None)
    if not callable(apply):
        return
    try:
        await _maybe_await(
            apply(
                {
                    "type": "usage_limit_reached",
                    "turn_context": turn_context,
                }
            )
        )
    except Exception:
        return


async def _maybe_run_mid_turn_auto_compact(sess: Any, turn_context: Any) -> bool:
    result = await _maybe_run_mid_turn_auto_compact_result(sess, turn_context)
    return result.success


@dataclass(frozen=True)
class _AutoCompactResult:
    success: bool = True
    compacted: bool = False


async def _maybe_run_mid_turn_auto_compact_result(sess: Any, turn_context: Any) -> _AutoCompactResult:
    try:
        compacted = await _run_auto_compact_if_needed(
            sess,
            turn_context,
            initial_context_injection="before_last_user_message",
            reason="context_limit",
            phase="mid_turn",
        )
    except CodexErr as exc:
        await _handle_auto_compact_error(sess, turn_context, exc)
        return _AutoCompactResult(success=False)
    return _AutoCompactResult(success=True, compacted=compacted)


async def _maybe_run_pre_sampling_auto_compact(sess: Any, turn_context: Any) -> None:
    previous_model_compact = _mapping_or_attr(sess, "maybe_run_previous_model_inline_compact")
    if not callable(previous_model_compact):
        previous_model_compact = _mapping_or_attr(sess, "run_previous_model_inline_compact")
    if callable(previous_model_compact):
        await _call_auto_compact(
            previous_model_compact,
            turn_context,
            initial_context_injection="do_not_inject",
            reason="model_downshift",
            phase="pre_turn",
        )
    await _run_auto_compact_if_needed(
        sess,
        turn_context,
        initial_context_injection="do_not_inject",
        reason="context_limit",
        phase="pre_turn",
    )


async def _run_auto_compact_if_needed(
    sess: Any,
    turn_context: Any,
    *,
    initial_context_injection: str,
    reason: str,
    phase: str,
) -> bool:
    status_provider = _mapping_or_attr(sess, "auto_compact_token_status")
    if not callable(status_provider):
        status_provider = _mapping_or_attr(sess, "get_auto_compact_token_status")
    if not callable(status_provider):
        return
    status = await _call_optional_turn_context(status_provider, turn_context)
    if not _auto_compact_token_limit_reached(status):
        return False
    compact = _mapping_or_attr(sess, "run_auto_compact")
    if not callable(compact):
        compact = _mapping_or_attr(sess, "auto_compact")
    if not callable(compact):
        return False
    await _call_auto_compact(
        compact,
        turn_context,
        initial_context_injection=initial_context_injection,
        reason=reason,
        phase=phase,
    )
    return True


async def _handle_auto_compact_error(sess: Any, turn_context: Any, error: CodexErr) -> None:
    error_info = error.to_codex_protocol_error()
    await _emit_turn_error_lifecycle(sess, turn_context, error_info)
    if error_info == CodexErrorInfo.usage_limit_exceeded():
        await _apply_usage_limit_goal_runtime(sess, turn_context)


def _auto_compact_token_limit_reached(status: Any) -> bool:
    if isinstance(status, bool):
        return status
    if isinstance(status, Mapping):
        return bool(status.get("token_limit_reached", False))
    return bool(getattr(status, "token_limit_reached", False))


async def _call_auto_compact(
    compact: Callable[..., Any],
    turn_context: Any,
    *,
    initial_context_injection: str,
    reason: str,
    phase: str,
) -> Any:
    try:
        return await _maybe_await(
            compact(
                turn_context,
                initial_context_injection=initial_context_injection,
                reason=reason,
                phase=phase,
            )
        )
    except TypeError:
        return await _call_optional_turn_context(compact, turn_context)


async def _call_optional_turn_context(callback: Callable[..., Any], turn_context: Any) -> Any:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        try:
            return await _maybe_await(callback(turn_context))
        except TypeError:
            return await _maybe_await(callback())
    accepts_positional = any(
        parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
        for parameter in signature.parameters.values()
    )
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if accepts_positional:
        return await _maybe_await(callback(turn_context))
    if required:
        return await _maybe_await(callback(turn_context))
    return await _maybe_await(callback())


def _mapping_or_attr(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


async def _emit_turn_error_lifecycle(sess: Any, turn_context: Any, error_info: CodexErrorInfo) -> None:
    handler = getattr(sess, "emit_turn_error_lifecycle", None)
    if callable(handler):
        await _maybe_await(handler(turn_context, error_info))


async def _send_terminal_error_event(sess: Any, turn_context: Any, error: CodexErr) -> None:
    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(sender(turn_context, EventMsg.with_payload("error", error.to_error_event())))


async def _emit_turn_started_lifecycle(sess: Any, turn_context: Any) -> None:
    await _mark_turn_timing_started(sess, turn_context)
    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(
            sender(
                turn_context,
                EventMsg.with_payload(
                    "task_started",
                    TurnStartedEvent(
                        turn_id=_turn_context_turn_id(turn_context),
                        trace_id=_optional_str_attr(turn_context, "trace_id"),
                        started_at=_optional_int_attr(turn_context, "started_at"),
                        model_context_window=_turn_context_model_context_window(turn_context),
                        collaboration_mode_kind=_turn_context_collaboration_mode_kind(turn_context),
                    ),
                ),
            )
        )
    setter = getattr(sess, "set_server_reasoning_included", None)
    if callable(setter):
        await _maybe_await(setter(False))


async def _emit_turn_complete_lifecycle(
    sess: Any,
    turn_context: Any,
    last_agent_message: str | None,
) -> None:
    await _mark_turn_timing_completed(sess, turn_context)
    flusher = getattr(sess, "flush_rollout", None)
    if callable(flusher):
        try:
            await _maybe_await(flusher())
        except Exception as exc:
            await _send_warning_event(
                sess,
                turn_context,
                f"Failed to save the conversation transcript; Codex will continue retrying. Error: {exc}",
            )
    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(
            sender(
                turn_context,
                EventMsg.with_payload(
                    "task_complete",
                    TurnCompleteEvent(
                        turn_id=_turn_context_turn_id(turn_context),
                        last_agent_message=last_agent_message,
                        completed_at=_optional_int_attr(turn_context, "completed_at"),
                        duration_ms=_optional_int_attr(turn_context, "duration_ms"),
                        time_to_first_token_ms=_optional_int_attr(turn_context, "time_to_first_token_ms"),
                    ),
                ),
            )
        )


async def _mark_turn_timing_started(sess: Any, turn_context: Any) -> None:
    timing_state = _turn_timing_state(sess, turn_context)
    marker = getattr(timing_state, "mark_turn_started", None)
    if not callable(marker):
        return
    started_at = await _call_timing_marker(marker)
    if isinstance(started_at, int) and not isinstance(started_at, bool):
        _set_optional_int_attr(turn_context, "started_at", started_at)


async def _mark_turn_timing_completed(sess: Any, turn_context: Any) -> None:
    timing_state = _turn_timing_state(sess, turn_context)
    completed = getattr(timing_state, "completed_at_and_duration_ms", None)
    if callable(completed):
        value = await _maybe_await(completed())
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
            completed_at, duration_ms = value[0], value[1]
            if isinstance(completed_at, int) and not isinstance(completed_at, bool):
                _set_optional_int_attr(turn_context, "completed_at", completed_at)
            if isinstance(duration_ms, int) and not isinstance(duration_ms, bool):
                _set_optional_int_attr(turn_context, "duration_ms", duration_ms)
    await _sync_turn_timing_first_token_ms(turn_context, timing_state)


async def _record_response_items_turn_ttfm(
    sess: Any,
    turn_context: Any,
    response_items: Sequence[ResponseItem],
) -> None:
    for item in response_items:
        if not isinstance(item, ResponseItem):
            continue
        turn_item = handle_non_tool_response_item(item, _turn_context_plan_mode(turn_context))
        if turn_item is None:
            continue
        await _record_turn_item_ttfm(sess, turn_context, turn_item)


async def _record_stream_runtime_event_turn_ttfm(sess: Any, turn_context: Any, event: Any) -> None:
    if _field_or_mapping_value(event, "type", None) != "item_completed":
        return
    item = _field_or_mapping_value(event, "item", None)
    if isinstance(item, TurnItem):
        turn_item = item
    elif isinstance(item, Mapping):
        try:
            turn_item = TurnItem.from_mapping(item)
        except Exception:
            return
    else:
        return
    await _record_turn_item_ttfm(sess, turn_context, turn_item)


async def _record_turn_item_ttfm(sess: Any, turn_context: Any, item: TurnItem) -> None:
    timing_state = _turn_timing_state(sess, turn_context)
    recorder = getattr(timing_state, "record_ttfm_for_turn_item", None)
    if not callable(recorder):
        return
    duration = await _maybe_await(recorder(item))
    if duration is None:
        return
    await _record_turn_ttfm_duration_metric(sess, turn_context, duration)


async def _record_turn_ttfm_duration_metric(sess: Any, turn_context: Any, duration: Any) -> None:
    telemetry = _session_telemetry(sess, turn_context)
    recorder = getattr(telemetry, "record_duration", None)
    if not callable(recorder):
        return
    await _maybe_await(recorder(TURN_TTFM_DURATION_METRIC, duration, ()))


def _session_telemetry(sess: Any, turn_context: Any) -> Any:
    telemetry = getattr(turn_context, "session_telemetry", None)
    if telemetry is not None:
        return telemetry
    telemetry = getattr(sess, "session_telemetry", None)
    if telemetry is not None:
        return telemetry
    services = getattr(sess, "services", None)
    return getattr(services, "session_telemetry", None)


def _turn_timing_state(sess: Any, turn_context: Any) -> Any:
    return getattr(turn_context, "turn_timing_state", None) or getattr(sess, "turn_timing_state", None)


async def _call_timing_marker(marker: Callable[..., Any]) -> Any:
    try:
        signature = inspect.signature(marker)
    except (TypeError, ValueError):
        return await _maybe_await(marker())
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]
    if required:
        return None
    return await _maybe_await(marker())


def _set_optional_int_attr(target: Any, name: str, value: int) -> None:
    try:
        setattr(target, name, value)
    except Exception:
        pass


async def _send_warning_event(sess: Any, turn_context: Any, message: str) -> None:
    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(sender(turn_context, EventMsg.with_payload("warning", WarningEvent(message))))


async def _send_error_event(sess: Any, turn_context: Any, message: str) -> None:
    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(sender(turn_context, EventMsg.with_payload("error", ErrorEvent(message))))


async def _run_turn_stop_hook(
    sess: Any,
    turn_context: Any,
    stop_hook_active: bool,
    last_agent_message: str | None,
) -> Any:
    hook = (
        getattr(sess, "run_turn_stop_hook", None)
        or getattr(sess, "run_stop_hook", None)
        or getattr(turn_context, "run_turn_stop_hook", None)
    )
    if not callable(hook):
        return None
    try:
        signature = inspect.signature(hook)
    except (TypeError, ValueError):
        return await _maybe_await(hook(turn_context, stop_hook_active, last_agent_message))
    params = tuple(signature.parameters.values())
    required = [
        parameter
        for parameter in params
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]
    by_name = {parameter.name: parameter for parameter in params}
    if len(required) >= 4 or any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in params
    ):
        return await _maybe_await(hook(sess, turn_context, stop_hook_active, last_agent_message))
    has_canonical_stop_kw = (
        "turn_context" in by_name
        and "stop_hook_active" in by_name
        and "last_agent_message" in by_name
    )
    if has_canonical_stop_kw:
        try:
            return await _maybe_await(
                hook(
                    turn_context=turn_context,
                    stop_hook_active=stop_hook_active,
                    last_agent_message=last_agent_message,
                )
            )
        except TypeError:
            pass
    if len(required) == 3:
        return await _maybe_await(hook(turn_context, stop_hook_active, last_agent_message))
    if (
        "stop_hook_active" in by_name
        and "last_agent_message" in by_name
        and len(required) == 2
    ):
        try:
            return await _maybe_await(
                hook(
                    stop_hook_active=stop_hook_active,
                    last_agent_message=last_agent_message,
                )
            )
        except TypeError:
            return await _maybe_await(hook(stop_hook_active, last_agent_message))
    if "last_agent_message" in by_name:
        return await _maybe_await(hook(last_agent_message=last_agent_message))
    if len(required) == 2:
        return await _maybe_await(hook(stop_hook_active, last_agent_message))
    if len(required) == 1:
        return await _maybe_await(hook(last_agent_message))
    return await _maybe_await(hook())


async def _run_legacy_after_agent_hook(
    sess: Any,
    turn_context: Any,
    request_input: Any,
    last_agent_message: str | None,
) -> bool:
    hook = (
        getattr(sess, "run_legacy_after_agent_hook", None)
        or getattr(sess, "run_after_agent_hook", None)
        or getattr(sess, "after_agent_hook", None)
        or getattr(turn_context, "run_legacy_after_agent_hook", None)
    )
    if not callable(hook):
        return False
    input_messages = _after_agent_input_messages(request_input)
    raw_outcome = await _call_after_agent_hook(
        hook,
        sess,
        turn_context,
        input_messages,
        last_agent_message,
    )
    outcome = _after_agent_outcome(raw_outcome)
    if not outcome["should_abort"]:
        return False
    hook_name = outcome["hook_name"]
    error = outcome["error"]
    await _send_error_event(
        sess,
        turn_context,
        f"after_agent hook '{hook_name}' failed and aborted turn completion: {error}",
    )
    return True


async def _call_after_agent_hook(
    hook: Any,
    sess: Any,
    turn_context: Any,
    input_messages: tuple[str, ...],
    last_agent_message: str | None,
) -> Any:
    try:
        signature = inspect.signature(hook)
    except (TypeError, ValueError):
        return await _maybe_await(hook(turn_context, input_messages, last_agent_message))
    params = tuple(signature.parameters.values())
    required = [
        parameter
        for parameter in params
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]
    by_name = {parameter.name: parameter for parameter in params}
    if len(required) >= 4 or any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in params
    ):
        return await _maybe_await(hook(sess, turn_context, input_messages, last_agent_message))
    has_canonical_after_kw = (
        "turn_context" in by_name
        and "input_messages" in by_name
        and "last_agent_message" in by_name
    )
    if has_canonical_after_kw:
        try:
            return await _maybe_await(
                hook(
                    turn_context=turn_context,
                    input_messages=input_messages,
                    last_agent_message=last_agent_message,
                )
            )
        except TypeError:
            pass
    if len(required) == 3:
        return await _maybe_await(hook(turn_context, input_messages, last_agent_message))
    if (
        "input_messages" in by_name
        and "last_agent_message" in by_name
        and len(required) == 2
    ):
        try:
            return await _maybe_await(
                hook(
                    input_messages=input_messages,
                    last_agent_message=last_agent_message,
                )
            )
        except TypeError:
            return await _maybe_await(hook(input_messages, last_agent_message))
    if "last_agent_message" in by_name:
        return await _maybe_await(hook(last_agent_message=last_agent_message))
    if len(required) == 2:
        return await _maybe_await(hook(input_messages, last_agent_message))
    if len(required) == 1:
        return await _maybe_await(hook(last_agent_message))
    return await _maybe_await(hook())


def _after_agent_outcome(value: Any) -> dict[str, Any]:
    if value is None or value is False:
        return {"should_abort": False, "hook_name": "after_agent", "error": ""}
    if value is True:
        return {"should_abort": True, "hook_name": "after_agent", "error": "hook failed"}
    result = _field_or_mapping_value(value, "result", None)
    should_abort = bool(
        _field_or_mapping_value(value, "should_abort", False)
        or _field_or_mapping_value(value, "abort", False)
        or str(result).lower() in {"failed_abort", "abort"}
    )
    hook_name = _field_or_mapping_value(value, "hook_name", "after_agent")
    error = _field_or_mapping_value(value, "error", _field_or_mapping_value(value, "message", "hook failed"))
    if not isinstance(hook_name, str):
        hook_name = "after_agent"
    if not isinstance(error, str):
        error = str(error)
    return {"should_abort": should_abort, "hook_name": hook_name, "error": error}


def _after_agent_input_messages(request_input: Any) -> tuple[str, ...]:
    if isinstance(request_input, (str, bytes)) or not isinstance(request_input, Sequence):
        return ()
    messages: list[str] = []
    for item in request_input:
        role = _field_or_mapping_value(item, "role", None)
        if role != "user":
            continue
        text = _message_text(item)
        if text:
            messages.append(text)
    return tuple(messages)


def _message_text(item: Any) -> str:
    content = _field_or_mapping_value(item, "content", ())
    if isinstance(content, str):
        return content
    if isinstance(content, (str, bytes)) or not isinstance(content, Sequence):
        return ""
    parts: list[str] = []
    for part in content:
        text = _field_or_mapping_value(part, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _field_or_mapping_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _stop_outcome_should_block(outcome: Any) -> bool:
    return bool(_stop_outcome_field(outcome, "should_block", False))


def _stop_outcome_should_stop(outcome: Any) -> bool:
    return bool(_stop_outcome_field(outcome, "should_stop", False))


def _stop_outcome_hook_prompt_message(outcome: Any) -> ResponseItem | None:
    fragments = _stop_outcome_continuation_fragments(outcome)
    if not fragments:
        return None
    return build_hook_prompt_message(fragments)


def _stop_outcome_continuation_fragments(outcome: Any) -> tuple[HookPromptFragment, ...]:
    raw_fragments = _stop_outcome_field(outcome, "continuation_fragments", ())
    if raw_fragments is None:
        return ()
    if isinstance(raw_fragments, HookPromptFragment):
        return (raw_fragments,)
    if isinstance(raw_fragments, Mapping):
        if "text" in raw_fragments or "hook_run_id" in raw_fragments or "hookRunId" in raw_fragments:
            raw_fragments = (raw_fragments,)
        else:
            raw_fragments = raw_fragments.values()
    if isinstance(raw_fragments, (str, bytes)) or not isinstance(raw_fragments, Sequence):
        raise TypeError("stop hook continuation_fragments must be HookPromptFragment entries")
    fragments: list[HookPromptFragment] = []
    for fragment in raw_fragments:
        if isinstance(fragment, HookPromptFragment):
            fragments.append(fragment)
            continue
        if isinstance(fragment, Mapping):
            text = fragment.get("text")
            hook_run_id = fragment.get("hook_run_id", fragment.get("hookRunId"))
            fragments.append(HookPromptFragment(text, hook_run_id))
            continue
        raise TypeError("stop hook continuation_fragments entries must be HookPromptFragment or mapping")
    return tuple(fragments)


def _stop_outcome_field(outcome: Any, name: str, default: Any = None) -> Any:
    if outcome is None:
        return default
    if isinstance(outcome, Mapping):
        return outcome.get(name, default)
    return getattr(outcome, name, default)


async def _record_sampling_token_usage(sess: Any, turn_context: Any, raw_result: Any) -> None:
    stream_events = _stream_events_from_sampling_result(raw_result)
    await _apply_sampling_metadata(
        sess,
        turn_context,
        raw_result,
        skip_server_model=_stream_events_include_type(stream_events, "server_model"),
        skip_model_verifications=_stream_events_include_type(stream_events, "model_verifications"),
        skip_server_reasoning_included=_stream_events_include_type(stream_events, "server_reasoning_included"),
        skip_models_etag=_stream_events_include_type(stream_events, "models_etag"),
    )
    rate_limit_recorder = getattr(sess, "record_rate_limits_info", None)
    if callable(rate_limit_recorder) and not _stream_events_include_type(stream_events, "rate_limits"):
        for snapshot in _rate_limits_from_sampling_result(raw_result):
            await _maybe_await(rate_limit_recorder(snapshot))
    usage = _token_usage_from_sampling_result(raw_result)
    if usage is None:
        return
    recorder = getattr(sess, "record_token_usage_info", None)
    if callable(recorder):
        await _maybe_await(recorder(turn_context, usage))
    if stream_events:
        return
    sender = getattr(sess, "send_token_count_event", None)
    if callable(sender):
        await _maybe_await(sender(turn_context))


async def _apply_sampling_metadata(
    sess: Any,
    turn_context: Any,
    raw_result: Any,
    *,
    skip_server_model: bool = False,
    skip_model_verifications: bool = False,
    skip_server_reasoning_included: bool = False,
    skip_models_etag: bool = False,
) -> None:
    if not skip_server_model:
        server_models = _metadata_tuple(raw_result, "server_models")
        if not server_models:
            server_model = _first_metadata_attr(raw_result, "server_model")
            server_models = (server_model,) if isinstance(server_model, str) else ()
        for server_model in server_models:
            if not isinstance(server_model, str):
                continue
            warned = bool(getattr(turn_context, "server_model_warning_emitted", False))
            if not warned:
                handler = getattr(sess, "maybe_warn_on_server_model_mismatch", None)
                if callable(handler) and await _maybe_await(handler(turn_context, server_model)):
                    try:
                        object.__setattr__(turn_context, "server_model_warning_emitted", True)
                    except Exception:
                        pass

    if not skip_model_verifications:
        model_verifications = _metadata_tuple(raw_result, "model_verifications")
        if model_verifications:
            emitted = bool(getattr(turn_context, "model_verification_emitted", False))
            if not emitted:
                handler = getattr(sess, "emit_model_verification", None)
                if callable(handler):
                    await _maybe_await(handler(turn_context, model_verifications))
                    try:
                        object.__setattr__(turn_context, "model_verification_emitted", True)
                    except Exception:
                        pass

    server_reasoning_included = _first_metadata_attr(raw_result, "server_reasoning_included")
    if not skip_server_reasoning_included and isinstance(server_reasoning_included, bool):
        handler = getattr(sess, "set_server_reasoning_included", None)
        if callable(handler):
            await _maybe_await(handler(server_reasoning_included))

    models_etag = _first_metadata_attr(raw_result, "models_etag")
    if not skip_models_etag and isinstance(models_etag, str):
        for name in ("refresh_models_etag", "record_models_etag"):
            handler = getattr(sess, name, None)
            if callable(handler):
                await _maybe_await(handler(models_etag))
                break


def _stream_events_include_type(stream_events: Sequence[Any], event_type: str) -> bool:
    for event in stream_events:
        if isinstance(event, Mapping) and event.get("type") == event_type:
            return True
    return False


def _metadata_events_include_type(metadata_events: Sequence[Any], event_type: str) -> bool:
    for event in metadata_events:
        if isinstance(event, Mapping) and event.get("event_type") == event_type:
            return True
    return False


def _token_usage_from_sampling_result(raw_result: Any) -> TokenUsage | None:
    payload = getattr(raw_result, "raw_result", raw_result)
    while payload is not None and not isinstance(payload, Mapping):
        nested = getattr(payload, "raw_result", None)
        if nested is None or nested is payload:
            break
        payload = nested
    if not isinstance(payload, Mapping):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        usage = payload.get("token_usage")
    if not isinstance(usage, Mapping):
        usage = payload.get("tokenUsage")
    if not isinstance(usage, Mapping):
        return None
    input_details = _mapping_field(usage, "input_tokens_details", "inputTokensDetails")
    output_details = _mapping_field(usage, "output_tokens_details", "outputTokensDetails")
    token_usage = TokenUsage(
        input_tokens=_int_field(usage, "input_tokens", "inputTokens"),
        cached_input_tokens=_int_field(input_details, "cached_tokens", "cachedTokens"),
        output_tokens=_int_field(usage, "output_tokens", "outputTokens"),
        reasoning_output_tokens=_int_field(output_details, "reasoning_tokens", "reasoningTokens"),
        total_tokens=_int_field(usage, "total_tokens", "totalTokens"),
    )
    if token_usage.total_tokens == 0:
        token_usage = TokenUsage(
            input_tokens=token_usage.input_tokens,
            cached_input_tokens=token_usage.cached_input_tokens,
            output_tokens=token_usage.output_tokens,
            reasoning_output_tokens=token_usage.reasoning_output_tokens,
            total_tokens=token_usage.input_tokens + token_usage.output_tokens,
        )
    return None if token_usage.is_zero() else token_usage


def _first_metadata_attr(raw_result: Any, name: str) -> Any:
    seen: set[int] = set()
    current = raw_result
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        value = getattr(current, name, None)
        if value is not None:
            return value
        current = getattr(current, "raw_result", None)
    return None


def _metadata_tuple(raw_result: Any, name: str) -> tuple[Any, ...]:
    seen: set[int] = set()
    values: list[Any] = []
    current = raw_result
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        raw = getattr(current, name, None)
        if raw is not None:
            if isinstance(raw, tuple):
                for item in raw:
                    if item not in values:
                        values.append(item)
            elif isinstance(raw, list):
                for item in raw:
                    if item not in values:
                        values.append(item)
            elif raw not in values:
                values.append(raw)
        current = getattr(current, "raw_result", None)
    return tuple(values)


def _rate_limits_from_sampling_result(raw_result: Any) -> tuple[Any, ...]:
    seen: set[int] = set()
    snapshots: list[Any] = []
    current = raw_result
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for snapshot in tuple(getattr(current, "rate_limits", ()) or ()):
            if snapshot not in snapshots:
                snapshots.append(snapshot)
        current = getattr(current, "raw_result", None)
    return tuple(snapshots)


def _mapping_field(value: Any, *names: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    for name in names:
        item = value.get(name)
        if isinstance(item, Mapping):
            return item
    return {}


def _int_field(value: Any, *names: str) -> int:
    if not isinstance(value, Mapping):
        return 0
    for name in names:
        item = value.get(name)
        if isinstance(item, bool):
            return 0
        if isinstance(item, int):
            return item
        if isinstance(item, float) and item.is_integer():
            return int(item)
    return 0


async def _handle_response_tool_calls(
    sess: Any,
    turn_context: Any,
    router: Any,
    response_items: Sequence[ResponseItem],
) -> tuple[ResponseItem, ...]:
    return await _handle_tool_call_items(
        sess,
        turn_context,
        router,
        response_items,
        record_tool_call_items=False,
    )


def _stream_non_tool_response_items(
    stream_events: Sequence[Any],
    *,
    skip_items: Sequence[ResponseItem],
) -> tuple[ResponseItem, ...]:
    if not stream_events:
        return ()
    items: list[ResponseItem] = []
    for event in stream_events:
        if not isinstance(event, Mapping) or event.get("type") != "output_item_done":
            continue
        item = event.get("item")
        if not isinstance(item, ResponseItem) or _response_item_already_recorded(item, skip_items):
            continue
        try:
            call = ToolRouter.build_tool_call(item)
        except FunctionCallError:
            continue
        if call is not None:
            continue
        items.append(item)
    return tuple(items)


def _response_item_already_recorded(item: ResponseItem, recorded: Sequence[ResponseItem]) -> bool:
    for existing in recorded:
        if existing == item:
            return True
        if item.id is not None and existing.type == item.type and existing.id == item.id:
            return True
        if item.call_id is not None and existing.type == item.type and existing.call_id == item.call_id:
            return True
    return False


async def _handle_stream_response_tool_calls(
    sess: Any,
    turn_context: Any,
    router: Any,
    stream_events: Sequence[Any],
    *,
    skip_call_ids: set[str],
) -> tuple[ResponseItem, ...]:
    if not stream_events:
        return ()
    items: list[ResponseItem] = []
    for event in stream_events:
        if not isinstance(event, Mapping) or event.get("type") != "output_item_done":
            continue
        item = event.get("item")
        if not isinstance(item, ResponseItem):
            continue
        call_id = getattr(item, "call_id", None)
        if isinstance(call_id, str) and call_id in skip_call_ids:
            continue
        items.append(item)
    if not items:
        return ()
    return await _handle_tool_call_items(
        sess,
        turn_context,
        router,
        items,
        record_tool_call_items=True,
    )


async def _handle_tool_call_items(
    sess: Any,
    turn_context: Any,
    router: Any,
    response_items: Sequence[ResponseItem],
    *,
    record_tool_call_items: bool,
) -> tuple[ResponseItem, ...]:
    if not isinstance(router, ToolRouter):
        return ()
    runtime = ToolCallRuntime(router)
    tool_outputs: list[ResponseItem | None] = []
    pending: list[tuple[int, Any]] = []
    for item in response_items:
        try:
            call = ToolRouter.build_tool_call(item)
        except FunctionCallError as exc:
            if exc.is_model_response:
                if record_tool_call_items:
                    await _maybe_await(sess.record_conversation_items(turn_context, (item,)))
                response_input_item = ResponseInputItem.function_call_output("", exc.message)
                tool_outputs.append(ResponseItem.from_response_input_item(response_input_item))
                continue
            raise CodexErr.fatal(exc.message) from exc
        if call is None:
            continue
        if record_tool_call_items:
            await _maybe_await(sess.record_conversation_items(turn_context, (item,)))
        output_index = len(tool_outputs)
        tool_outputs.append(None)
        pending.append(
            (
                output_index,
                asyncio.create_task(
                    runtime.handle_tool_call(
                        call,
                        session=sess,
                        turn=turn_context,
                    )
                ),
            )
        )
    for output_index, task in pending:
        try:
            response_input_item = await task
        except RuntimeError as exc:
            for _, pending_task in pending:
                if pending_task is not task:
                    pending_task.cancel()
            await _drain_cancelled_tool_tasks(pending)
            raise CodexErr.fatal(str(exc)) from exc
        tool_outputs[output_index] = ResponseItem.from_response_input_item(response_input_item)
    return tuple(item for item in tool_outputs if item is not None)


def _tool_call_ids(response_items: Sequence[ResponseItem]) -> set[str]:
    call_ids: set[str] = set()
    for item in response_items:
        try:
            call = ToolRouter.build_tool_call(item)
        except FunctionCallError:
            continue
        if call is not None:
            call_ids.add(call.call_id)
    return call_ids


async def _drain_cancelled_tool_tasks(tasks: Sequence[tuple[int, Any]]) -> None:
    for _index, task in tasks:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def _default_built_tools(_sess: Any, _turn_context: Any) -> Any:
    model_info = getattr(_turn_context, "model_info", None)
    config = getattr(_turn_context, "config", None)
    permissions = getattr(config, "permissions", None)
    return build_environment_tool_router_from_turn_context(
        _turn_context,
        apply_patch_tool_type=getattr(model_info, "apply_patch_tool_type", None),
        allow_login_shell=bool(getattr(permissions, "allow_login_shell", False)),
        exec_permission_approvals_enabled=_feature_enabled(
            getattr(_turn_context, "features", None),
            Feature.EXEC_PERMISSION_APPROVALS,
        ),
        request_permissions_tool_enabled=_feature_enabled(
            getattr(_turn_context, "features", None),
            Feature.REQUEST_PERMISSIONS_TOOL,
        ),
        can_request_original_image_detail=_can_request_original_image_detail(model_info),
    )


def _feature_enabled(features: Any, feature: Feature | str) -> bool:
    if features is None:
        return False
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        return bool(enabled(feature))
    if isinstance(features, Mapping):
        keys = [feature]
        if isinstance(feature, Feature):
            keys.extend((feature.value, feature.key()))
        for key in keys:
            if key in features:
                return bool(features[key])
        return False
    try:
        return feature in features
    except TypeError:
        return False


def _can_request_original_image_detail(model_info: Any) -> bool:
    if model_info is None:
        return False
    try:
        return can_request_original_image_detail(model_info)
    except TypeError:
        return bool(getattr(model_info, "supports_image_detail_original", False))


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable) or inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "BuiltToolsFn",
    "SamplerFn",
    "UserTurnSamplingRequest",
    "UserTurnSamplingResult",
    "build_user_input_op_responses_request_from_session",
    "build_user_turn_responses_request_from_session",
    "run_user_input_op_sampling_from_session",
    "run_user_turn_sampling_from_session",
]
