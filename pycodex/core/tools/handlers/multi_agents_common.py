"""Shared multi-agent helper logic ported from Codex core."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.features import Feature
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import (
    AgentPath,
    AgentStatus,
    CollabAgentRef,
    CollabAgentStatusEntry,
    CodexErr,
    ReasoningEffort,
    ResponseInputItem,
    SessionSource,
    SubAgentSource,
    ThreadId,
    UserInput,
)

JsonValue = Any

MIN_WAIT_TIMEOUT_MS = 1_000
DEFAULT_WAIT_TIMEOUT_MS = 30_000
MAX_WAIT_TIMEOUT_MS = 600_000


def function_arguments(payload: ToolPayload) -> str:
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    if payload.type == "function":
        return payload.arguments or ""
    raise FunctionCallError.respond_to_model("collab handler received unsupported payload")


def tool_output_json_text(value: JsonValue, tool_name: str) -> str:
    if not isinstance(tool_name, str):
        raise TypeError("tool_name must be a string")
    try:
        return json.dumps(_to_json_value(value), separators=(",", ":"))
    except (TypeError, ValueError) as err:
        return json.dumps(f"failed to serialize {tool_name} result: {err}")


def tool_output_response_item(
    call_id: str,
    payload: ToolPayload,
    value: JsonValue,
    success: bool | None,
    tool_name: str,
) -> ResponseInputItem:
    if not isinstance(call_id, str):
        raise TypeError("call_id must be a string")
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    if success is not None and not isinstance(success, bool):
        raise TypeError("success must be a bool or None")
    return FunctionToolOutput.from_text(
        tool_output_json_text(value, tool_name),
        success,
    ).to_response_item(call_id, payload)


def tool_output_code_mode_result(value: JsonValue, tool_name: str) -> JsonValue:
    if not isinstance(tool_name, str):
        raise TypeError("tool_name must be a string")
    try:
        return _to_json_value(value)
    except (TypeError, ValueError) as err:
        return f"failed to serialize {tool_name} result: {err}"


def build_wait_agent_statuses(
    statuses: Mapping[ThreadId, AgentStatus],
    receiver_agents: Iterable[CollabAgentRef],
) -> tuple[CollabAgentStatusEntry, ...]:
    if not isinstance(statuses, Mapping):
        raise TypeError("statuses must be a mapping")
    receiver_tuple = _receiver_agents_tuple(receiver_agents)
    if not statuses:
        return ()

    entries: list[CollabAgentStatusEntry] = []
    seen: set[ThreadId] = set()
    for receiver_agent in receiver_tuple:
        seen.add(receiver_agent.thread_id)
        status = statuses.get(receiver_agent.thread_id)
        if status is not None:
            entries.append(
                CollabAgentStatusEntry(
                    thread_id=receiver_agent.thread_id,
                    agent_nickname=receiver_agent.agent_nickname,
                    agent_role=receiver_agent.agent_role,
                    status=_agent_status(status),
                )
            )

    extras = [
        CollabAgentStatusEntry(
            thread_id=_thread_id(thread_id),
            agent_nickname=None,
            agent_role=None,
            status=_agent_status(status),
        )
        for thread_id, status in statuses.items()
        if thread_id not in seen
    ]
    extras.sort(key=lambda entry: str(entry.thread_id))
    return tuple(entries + extras)


def collab_spawn_error(error: CodexErr | Exception) -> FunctionCallError:
    if isinstance(error, CodexErr):
        if error.kind == "unsupported_operation" and error.message == "thread manager dropped":
            return FunctionCallError.respond_to_model("collab manager unavailable")
        if error.kind == "unsupported_operation":
            return FunctionCallError.respond_to_model(error.message or "")
    return FunctionCallError.respond_to_model(f"collab spawn failed: {error}")


def collab_agent_error(agent_id: ThreadId | str, error: CodexErr | Exception) -> FunctionCallError:
    parsed_agent_id = agent_id if isinstance(agent_id, ThreadId) else ThreadId.from_string(str(agent_id))
    if isinstance(error, CodexErr):
        if error.kind == "thread_not_found":
            missing_id = error.message or str(parsed_agent_id)
            return FunctionCallError.respond_to_model(f"agent with id {missing_id} not found")
        if error.kind == "internal_agent_died":
            return FunctionCallError.respond_to_model(f"agent with id {parsed_agent_id} is closed")
        if error.kind == "unsupported_operation":
            return FunctionCallError.respond_to_model("collab manager unavailable")
    return FunctionCallError.respond_to_model(f"collab tool failed: {error}")


def thread_spawn_source(
    parent_thread_id: ThreadId | str,
    parent_session_source: SessionSource,
    depth: int,
    agent_role: str | None = None,
    task_name: str | None = None,
) -> SessionSource:
    if not isinstance(parent_session_source, SessionSource):
        raise TypeError("parent_session_source must be SessionSource")
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise TypeError("depth must be an integer")
    if agent_role is not None and not isinstance(agent_role, str):
        raise TypeError("agent_role must be a string or None")
    if task_name is not None and not isinstance(task_name, str):
        raise TypeError("task_name must be a string or None")
    parent_id = parent_thread_id if isinstance(parent_thread_id, ThreadId) else ThreadId.from_string(str(parent_thread_id))
    agent_path = None
    if task_name is not None:
        parent_agent_path = parent_session_source.get_agent_path() or AgentPath.root()
        try:
            agent_path = parent_agent_path.join(task_name)
        except ValueError as err:
            raise FunctionCallError.respond_to_model(str(err)) from err
    return SessionSource.subagent(
        SubAgentSource.thread_spawn(
            parent_thread_id=parent_id,
            depth=depth,
            agent_path=agent_path,
            agent_nickname=None,
            agent_role=agent_role,
        )
    )


def parse_collab_input(
    message: str | None,
    items: Iterable[UserInput | Mapping[str, JsonValue]] | None,
) -> tuple[UserInput, ...]:
    if message is not None and not isinstance(message, str):
        raise TypeError("message must be a string or None")
    if message is not None and items is not None:
        raise FunctionCallError.respond_to_model("Provide either message or items, but not both")
    if message is None and items is None:
        raise FunctionCallError.respond_to_model("Provide one of: message or items")
    if message is not None:
        if message.strip() == "":
            raise FunctionCallError.respond_to_model("Empty message can't be sent to an agent")
        return (UserInput.text_input(message),)

    item_tuple = _user_input_tuple(items)
    if not item_tuple:
        raise FunctionCallError.respond_to_model("Items can't be empty")
    return item_tuple


def reject_full_fork_spawn_overrides(
    agent_type: str | None,
    model: str | None,
    reasoning_effort: str | None,
) -> None:
    if agent_type is not None and not isinstance(agent_type, str):
        raise TypeError("agent_type must be a string or None")
    if model is not None and not isinstance(model, str):
        raise TypeError("model must be a string or None")
    if reasoning_effort is not None and not isinstance(reasoning_effort, str):
        raise TypeError("reasoning_effort must be a string or None")
    if agent_type is not None or model is not None or reasoning_effort is not None:
        raise FunctionCallError.respond_to_model(
            "not supported: "
            "Full-history forked agents inherit the parent agent type, model, and reasoning effort; "
            "omit agent_type, model, and reasoning_effort, or spawn without a full-history fork."
        )


def find_spawn_agent_model_name(available_models: Iterable[Any], requested_model: str) -> str:
    if not isinstance(requested_model, str):
        raise TypeError("requested_model must be a string")
    models = tuple(available_models)
    for model in models:
        model_name = getattr(model, "model", None)
        if model_name == requested_model:
            return model_name
    available = ", ".join(str(getattr(model, "model", "")) for model in models)
    raise FunctionCallError.respond_to_model(
        f"Unknown model `{requested_model}` for spawn_agent. Available models: {available}"
    )


def validate_spawn_agent_reasoning_effort(
    model: str,
    supported_reasoning_levels: Iterable[Any],
    requested_reasoning_effort: ReasoningEffort | str,
) -> None:
    if not isinstance(model, str):
        raise TypeError("model must be a string")
    requested = (
        requested_reasoning_effort
        if isinstance(requested_reasoning_effort, ReasoningEffort)
        else ReasoningEffort.parse(str(requested_reasoning_effort))
    )
    presets = tuple(supported_reasoning_levels)
    for preset in presets:
        if _reasoning_preset_effort(preset) == requested:
            return
    supported = ", ".join(str(_reasoning_preset_effort(preset).value) for preset in presets)
    raise FunctionCallError.respond_to_model(
        f"Reasoning effort `{requested.value}` is not supported for model `{model}`. Supported reasoning efforts: {supported}"
    )


def select_spawn_agent_service_tier(
    model: str,
    model_info: Any,
    config_service_tier: str | None = None,
    requested_service_tier: str | None = None,
    parent_service_tier: str | None = None,
) -> str | None:
    if not isinstance(model, str):
        raise TypeError("model must be a string")
    for label, value in {
        "config_service_tier": config_service_tier,
        "requested_service_tier": requested_service_tier,
        "parent_service_tier": parent_service_tier,
    }.items():
        if value is not None and not isinstance(value, str):
            raise TypeError(f"{label} must be a string or None")
    candidates = (config_service_tier, requested_service_tier, parent_service_tier)
    if all(candidate is None for candidate in candidates):
        return None
    if requested_service_tier is not None and not _supports_service_tier(model_info, requested_service_tier):
        supported_service_tiers = _supported_service_tier_text(model_info)
        raise FunctionCallError.respond_to_model(
            f"Service tier `{requested_service_tier}` is not supported for model `{model}`. Supported service tiers: {supported_service_tiers}"
        )
    for candidate in candidates:
        if candidate is not None and _supports_service_tier(model_info, candidate):
            return candidate
    return None


def apply_spawn_agent_overrides(config: Any, child_depth: int) -> None:
    if isinstance(child_depth, bool) or not isinstance(child_depth, int):
        raise TypeError("child_depth must be an integer")
    agent_max_depth = _config_agent_max_depth(config)
    features = _config_features(config)
    if child_depth >= agent_max_depth and not _feature_enabled(features, Feature.MULTI_AGENT_V2):
        _disable_feature(features, Feature.SPAWN_CSV)
        _disable_feature(features, Feature.COLLAB)


def _receiver_agents_tuple(values: Iterable[CollabAgentRef]) -> tuple[CollabAgentRef, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError("receiver_agents must be an iterable of CollabAgentRef values")
    result: list[CollabAgentRef] = []
    for value in values:
        if isinstance(value, CollabAgentRef):
            result.append(value)
        else:
            result.append(CollabAgentRef.from_mapping(value))
    return tuple(result)


def _user_input_tuple(
    values: Iterable[UserInput | Mapping[str, JsonValue]] | None,
) -> tuple[UserInput, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError("items must be an iterable of UserInput values")
    result: list[UserInput] = []
    for value in values:
        if isinstance(value, UserInput):
            result.append(value)
        else:
            result.append(UserInput.from_mapping(value))
    return tuple(result)


def _thread_id(value: ThreadId) -> ThreadId:
    if not isinstance(value, ThreadId):
        raise TypeError("statuses keys must be ThreadId")
    return value


def _agent_status(value: AgentStatus) -> AgentStatus:
    if isinstance(value, AgentStatus):
        return value
    return AgentStatus.from_mapping(value)


def _reasoning_preset_effort(preset: Any) -> ReasoningEffort:
    effort = getattr(preset, "effort", None)
    if effort is None and isinstance(preset, Mapping):
        effort = preset.get("effort")
    if isinstance(effort, ReasoningEffort):
        return effort
    return ReasoningEffort.parse(str(effort))


def _supports_service_tier(model_info: Any, service_tier: str) -> bool:
    supports = getattr(model_info, "supports_service_tier", None)
    if callable(supports):
        return bool(supports(service_tier))
    tiers = getattr(model_info, "service_tiers", ())
    if isinstance(model_info, Mapping):
        tiers = model_info.get("service_tiers", ())
    return any(_service_tier_id(tier) == service_tier for tier in tiers)


def _supported_service_tier_text(model_info: Any) -> str:
    tiers = getattr(model_info, "service_tiers", ())
    if isinstance(model_info, Mapping):
        tiers = model_info.get("service_tiers", ())
    ids = [tier_id for tier in tiers if (tier_id := _service_tier_id(tier))]
    return "none" if not ids else ", ".join(ids)


def _service_tier_id(tier: Any) -> str | None:
    if isinstance(tier, str):
        return tier
    if isinstance(tier, Mapping):
        value = tier.get("id")
    else:
        value = getattr(tier, "id", None)
    return value if isinstance(value, str) else None


def _config_agent_max_depth(config: Any) -> int:
    value = config.get("agent_max_depth") if isinstance(config, Mapping) else getattr(config, "agent_max_depth", None)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("config.agent_max_depth must be an integer")
    return value


def _config_features(config: Any) -> Any:
    if isinstance(config, Mapping):
        features = config.get("features")
    else:
        features = getattr(config, "features", None)
    if features is None:
        raise TypeError("config.features is required")
    return features


def _feature_enabled(features: Any, feature: Feature) -> bool:
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        return bool(enabled(feature))
    if isinstance(features, Mapping):
        return bool(
            features.get(feature)
            or features.get(feature.value)
            or features.get(feature.key())
        )
    if isinstance(features, set):
        return feature in features or feature.value in features or feature.key() in features
    raise TypeError("features must expose enabled(), be a mapping, or be a set")


def _disable_feature(features: Any, feature: Feature) -> None:
    disable = getattr(features, "disable", None)
    if callable(disable):
        disable(feature)
        return
    if isinstance(features, dict):
        for key in (feature, feature.value, feature.key()):
            if key in features:
                features[key] = False
        return
    if isinstance(features, set):
        features.discard(feature)
        features.discard(feature.value)
        features.discard(feature.key())
        return
    raise TypeError("features must expose disable(), be a dict, or be a set")


def _to_json_value(value: JsonValue) -> JsonValue:
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    return value
