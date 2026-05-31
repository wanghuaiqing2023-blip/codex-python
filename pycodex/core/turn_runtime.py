"""Session-like turn runtime request construction.

This module is a small executable skeleton for the core user-turn path. It
does not perform network I/O; it advances a session-like object through the
same transport-independent steps the Rust session takes before sampling:
create turn context, record contextual updates, record user input, collect
history/tools/base instructions, and build a Responses API request.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.core.client import ModelClient
from pycodex.core.codex_thread import SessionSettingsUpdate
from pycodex.core.features import Feature
from pycodex.core.original_image_detail import can_request_original_image_detail
from pycodex.core.spec_plan import build_environment_tool_router_from_turn_context
from pycodex.core.tool_parallel import ToolCallRuntime
from pycodex.core.tool_router import ToolRouter
from pycodex.core.turn_request import TurnResponsesRequestPlan, build_turn_responses_request
from pycodex.protocol import BaseInstructions, ContentItem, Op, ResponseInputItem, ResponseItem, ThreadSettingsOverrides, UserInput


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
    raw_results: tuple[Any, ...] = ()
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
    thread_settings: Any = None,
    responsesapi_client_metadata: Mapping[str, str] | None = None,
    additional_context: Mapping[str, Any] | None = None,
    environments: Sequence[Any] | None = None,
    output_schema: Any = None,
    apply_output_schema_update: bool = False,
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
    output_schema_strict: bool = True,
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
    output_schema_strict: bool = True,
    max_tool_followups: int = 8,
) -> UserTurnSamplingResult:
    """Build a request, run an injected sampler, and record response items."""

    if sampler is None or not callable(sampler):
        raise TypeError("sampler must be callable")
    max_tool_followups = _validate_max_tool_followups(max_tool_followups)
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
    sampling_request = UserTurnSamplingRequest(
        session=sess,
        turn_context=prepared.turn_context,
        request_plan=prepared.request_plan,
    )
    raw_result = await _maybe_await(sampler(sampling_request))
    response_items = _response_items_from_sampling_result(raw_result)
    if response_items:
        await _maybe_await(sess.record_conversation_items(prepared.turn_context, response_items))
    all_response_items = list(response_items)
    all_tool_response_items: list[ResponseItem] = []
    request_plans = [prepared.request_plan]
    raw_results = [raw_result]
    tool_response_items = await _handle_response_tool_calls(
        sess,
        prepared.turn_context,
        prepared.router,
        response_items,
    )
    followups = 0
    while True:
        if tool_response_items:
            await _maybe_await(sess.record_conversation_items(prepared.turn_context, tool_response_items))
            all_tool_response_items.extend(tool_response_items)
        if not tool_response_items or followups >= max_tool_followups:
            break
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
        raw_result = await _maybe_await(sampler(followup_request))
        raw_results.append(raw_result)
        response_items = _response_items_from_sampling_result(raw_result)
        if response_items:
            await _maybe_await(sess.record_conversation_items(prepared.turn_context, response_items))
            all_response_items.extend(response_items)
        tool_response_items = await _handle_response_tool_calls(
            sess,
            prepared.turn_context,
            prepared.router,
            response_items,
        )
        followups += 1
    return UserTurnSamplingResult(
        request_plan=prepared.request_plan,
        response_items=tuple(all_response_items),
        tool_response_items=tuple(all_tool_response_items),
        request_plans=tuple(request_plans),
        raw_results=tuple(raw_results),
        raw_result=raw_result,
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
    output_schema_strict: bool = True,
    max_tool_followups: int = 8,
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
    router: Any
    model_info: Any
    effort: Any
    summary: Any
    service_tier: str | None
    output_schema: Any
    output_schema_strict: bool
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
    thread_settings: Any = None,
    responsesapi_client_metadata: Mapping[str, str] | None = None,
    additional_context: Mapping[str, Any] | None = None,
    environments: Sequence[Any] | None = None,
    output_schema: Any = None,
    apply_output_schema_update: bool = False,
    output_schema_strict: bool = True,
) -> _PreparedUserTurnRequest:
    user_input = _user_inputs(input)
    await _apply_thread_settings_overrides(sess, thread_settings)
    await _apply_turn_environments(sess, environments)
    if apply_output_schema_update:
        await _apply_final_output_json_schema(sess, output_schema)
    turn_context = await _maybe_await(sess.new_default_turn())
    _apply_responsesapi_client_metadata(turn_context, responsesapi_client_metadata)
    await _maybe_await(sess.record_context_updates_and_set_reference_context_item(turn_context))

    additional_context_items = _additional_context_response_items(sess, additional_context)
    if additional_context_items:
        await _maybe_await(sess.record_conversation_items(turn_context, additional_context_items))

    if user_input:
        input_item = ResponseInputItem.from_user_inputs(user_input)
        response_item = ResponseItem.from_response_input_item(input_item)
        await _maybe_await(sess.record_conversation_items(turn_context, (response_item,)))

    history = await _maybe_await(sess.clone_history())
    effective_model_info = getattr(turn_context, "model_info", None) or model_info
    input_modalities = getattr(effective_model_info, "input_modalities", None)
    prompt_input = history.for_prompt(input_modalities) if hasattr(history, "for_prompt") else list(history)

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
        has_current_user_input=bool(user_input),
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
    prompt_input = history.for_prompt(input_modalities) if hasattr(history, "for_prompt") else list(history)
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


def _validate_max_tool_followups(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("max_tool_followups must be an integer")
    if value < 0:
        raise ValueError("max_tool_followups must be >= 0")
    return value


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
            items.append(ResponseItem.message("user", (ContentItem.input_text(f"<external_{key}>{context_value}</external_{key}>"),)))
        elif kind == "application":
            items.append(ResponseItem.message("developer", (ContentItem.input_text(f"<{key}>{context_value}</{key}>"),)))
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


async def _handle_response_tool_calls(
    sess: Any,
    turn_context: Any,
    router: Any,
    response_items: Sequence[ResponseItem],
) -> tuple[ResponseItem, ...]:
    if not isinstance(router, ToolRouter):
        return ()
    runtime = ToolCallRuntime(router)
    tool_outputs: list[ResponseItem] = []
    for item in response_items:
        call = ToolRouter.build_tool_call(item)
        if call is None:
            continue
        response_input_item = await runtime.handle_tool_call(
            call,
            session=sess,
            turn=turn_context,
        )
        tool_outputs.append(ResponseItem.from_response_input_item(response_input_item))
    return tuple(tool_outputs)


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
