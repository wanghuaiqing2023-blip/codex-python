"""Shared multi-agent helper logic ported from Codex core."""

from __future__ import annotations

import json
import copy
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


def build_agent_spawn_config(base_instructions: Any, turn: Any) -> Any:
    config = build_agent_shared_config(turn)
    _set_config_value(config, "base_instructions", _base_instruction_text(base_instructions))
    return config


def build_agent_resume_config(turn: Any, child_depth: int) -> Any:
    config = build_agent_shared_config(turn)
    apply_spawn_agent_overrides(config, child_depth)
    _set_config_value(config, "base_instructions", None)
    return config


def build_agent_shared_config(turn: Any) -> Any:
    base_config = getattr(turn, "config", None)
    if base_config is None:
        raise TypeError("turn.config is required")
    config = copy.deepcopy(base_config)
    model_info = getattr(turn, "model_info", None)
    provider = getattr(turn, "provider", None)
    model_slug = getattr(model_info, "slug", None)
    if model_slug is not None:
        _set_config_value(config, "model", model_slug)
    provider_info = getattr(provider, "info", None)
    if callable(provider_info):
        _set_config_value(config, "model_provider", provider_info())
    elif provider is not None:
        _set_config_value(config, "model_provider", provider)
    reasoning_effort = getattr(turn, "reasoning_effort", None)
    if reasoning_effort is None:
        reasoning_effort = getattr(model_info, "default_reasoning_level", None)
    _set_config_value(config, "model_reasoning_effort", reasoning_effort)
    if hasattr(turn, "reasoning_summary"):
        _set_config_value(config, "model_reasoning_summary", getattr(turn, "reasoning_summary"))
    if hasattr(turn, "developer_instructions"):
        _set_config_value(config, "developer_instructions", getattr(turn, "developer_instructions"))
    if hasattr(turn, "compact_prompt"):
        _set_config_value(config, "compact_prompt", getattr(turn, "compact_prompt"))
    apply_spawn_agent_runtime_overrides(config, turn)
    return config


def apply_spawn_agent_runtime_overrides(config: Any, turn: Any) -> None:
    permissions = _config_permissions(config)
    approval_policy = getattr(turn, "approval_policy", None)
    if approval_policy is not None:
        _set_nested_permission_value(permissions, "approval_policy", _approval_policy_value(approval_policy))
    if hasattr(turn, "shell_environment_policy"):
        _set_nested_permission_value(permissions, "shell_environment_policy", getattr(turn, "shell_environment_policy"))
    if hasattr(turn, "codex_linux_sandbox_exe"):
        _set_config_value(config, "codex_linux_sandbox_exe", getattr(turn, "codex_linux_sandbox_exe"))
    if hasattr(turn, "cwd"):
        _set_config_value(config, "cwd", getattr(turn, "cwd"))
    permission_profile = _turn_permission_profile(turn)
    if permission_profile is not None:
        setter = getattr(permissions, "set_permission_profile", None)
        if callable(setter):
            try:
                setter(permission_profile)
            except Exception as err:
                raise FunctionCallError.respond_to_model(f"permission_profile is invalid: {err}") from err
        else:
            _set_nested_permission_value(permissions, "permission_profile", permission_profile)


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


def apply_requested_spawn_agent_model_overrides(
    session: Any,
    turn: Any,
    config: Any,
    requested_model: str | None = None,
    requested_reasoning_effort: ReasoningEffort | str | None = None,
) -> None:
    if requested_model is None and requested_reasoning_effort is None:
        return
    if requested_model is not None:
        models_manager = _models_manager(session)
        available_models = _call_maybe_await(getattr(models_manager, "list_models"), "offline")
        selected_model_name = find_spawn_agent_model_name(available_models, requested_model)
        model_info = _model_info(models_manager, selected_model_name, config)
        _set_config_value(config, "model", selected_model_name)
        if requested_reasoning_effort is not None:
            validate_spawn_agent_reasoning_effort(
                selected_model_name,
                getattr(model_info, "supported_reasoning_levels", ()),
                requested_reasoning_effort,
            )
            _set_config_value(config, "model_reasoning_effort", requested_reasoning_effort)
        else:
            _set_config_value(config, "model_reasoning_effort", getattr(model_info, "default_reasoning_level", None))
        return

    model_info = getattr(turn, "model_info", None)
    model = getattr(model_info, "slug", _get_config_value(config, "model"))
    validate_spawn_agent_reasoning_effort(
        str(model),
        getattr(model_info, "supported_reasoning_levels", ()),
        requested_reasoning_effort,
    )
    _set_config_value(config, "model_reasoning_effort", requested_reasoning_effort)


def apply_spawn_agent_service_tier(
    session: Any,
    config: Any,
    parent_service_tier: str | None = None,
    requested_service_tier: str | None = None,
) -> None:
    candidates = (
        _get_config_value(config, "service_tier"),
        requested_service_tier,
        parent_service_tier,
    )
    if all(candidate is None for candidate in candidates):
        _set_config_value(config, "service_tier", None)
        return
    model = _get_config_value(config, "model")
    if model is None:
        raise FunctionCallError.respond_to_model(
            "spawn_agent could not resolve the child model for service tier validation"
        )
    model_info = _model_info(_models_manager(session), str(model), config)
    selected = select_spawn_agent_service_tier(
        str(model),
        model_info,
        config_service_tier=candidates[0],
        requested_service_tier=requested_service_tier,
        parent_service_tier=parent_service_tier,
    )
    _set_config_value(config, "service_tier", selected)


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


def _base_instruction_text(base_instructions: Any) -> str | None:
    if base_instructions is None:
        return None
    if isinstance(base_instructions, str):
        return base_instructions
    if isinstance(base_instructions, Mapping):
        value = base_instructions.get("text")
    else:
        value = getattr(base_instructions, "text", None)
    if value is None or isinstance(value, str):
        return value
    raise TypeError("base_instructions.text must be a string or None")


def _get_config_value(config: Any, key: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _set_config_value(config: Any, key: str, value: Any) -> None:
    if isinstance(config, dict):
        config[key] = value
        return
    setattr(config, key, value)


def _config_permissions(config: Any) -> Any:
    permissions = _get_config_value(config, "permissions")
    if permissions is None:
        if isinstance(config, dict):
            permissions = {}
            config["permissions"] = permissions
        else:
            permissions = type("Permissions", (), {})()
            setattr(config, "permissions", permissions)
    return permissions


def _set_nested_permission_value(permissions: Any, key: str, value: Any) -> None:
    if key == "approval_policy":
        target = permissions.get(key) if isinstance(permissions, Mapping) else getattr(permissions, key, None)
        setter = getattr(target, "set", None)
        if callable(setter):
            try:
                setter(value)
            except Exception as err:
                raise FunctionCallError.respond_to_model(f"approval_policy is invalid: {err}") from err
            return
    if isinstance(permissions, dict):
        permissions[key] = value
    else:
        setattr(permissions, key, value)


def _approval_policy_value(approval_policy: Any) -> Any:
    value = getattr(approval_policy, "value", None)
    if callable(value):
        return value()
    if value is not None:
        return value
    return approval_policy


def _turn_permission_profile(turn: Any) -> Any:
    value = getattr(turn, "permission_profile", None)
    if callable(value):
        return value()
    return value


def _models_manager(session: Any) -> Any:
    services = getattr(session, "services", None)
    manager = getattr(services, "models_manager", None)
    if manager is None:
        manager = getattr(session, "models_manager", None)
    if manager is None:
        raise FunctionCallError.respond_to_model("models manager is unavailable for spawn_agent")
    return manager


def _model_info(models_manager: Any, model: str, config: Any) -> Any:
    getter = getattr(models_manager, "get_model_info", None)
    if not callable(getter):
        raise FunctionCallError.respond_to_model("models manager cannot resolve model info for spawn_agent")
    manager_config = config
    to_manager_config = getattr(config, "to_models_manager_config", None)
    if callable(to_manager_config):
        manager_config = to_manager_config()
    try:
        return _call_maybe_await(getter, model, manager_config)
    except TypeError:
        return _call_maybe_await(getter, model)


def _call_maybe_await(callable_obj: Any, *args: Any) -> Any:
    if not callable(callable_obj):
        raise TypeError("expected callable")
    value = callable_obj(*args)
    import inspect
    if not inspect.isawaitable(value):
        return value
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)

    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["value"] = asyncio.run(value)
        except BaseException as err:
            result["error"] = err

    import threading

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


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
