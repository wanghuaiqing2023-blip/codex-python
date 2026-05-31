"""Context update helpers ported from ``core/src/context_manager/updates.rs``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pycodex.core.features import Feature
from pycodex.core.context import (
    CollaborationModeInstructions,
    EnvironmentContext,
    EnvironmentContextEnvironment,
    ModelSwitchInstructions,
    NetworkContext,
    PersonalitySpecInstructions,
    RealtimeEndInstructions,
    RealtimeStartInstructions,
    RealtimeStartWithInstructions,
)
from pycodex.core.permissions_instructions import PermissionsInstructions
from pycodex.protocol import ContentItem, ResponseItem


def build_environment_update_item(
    previous: Any | None,
    next_context: Any,
    shell: Any,
) -> ResponseItem | None:
    if not _call_or_get(_call_or_get(next_context, "config"), "include_environment_context"):
        return None
    if previous is None:
        return None
    shell_name = _shell_name(shell)
    previous_context = EnvironmentContext.from_turn_context_item(previous, shell_name)
    next_environment_context = _environment_context_from_next_context(next_context, shell_name)
    if previous_context.equals_except_shell(next_environment_context):
        return None
    return EnvironmentContext.diff_from_turn_context_item(
        previous,
        next_environment_context,
    ).into_response_item()


def build_permissions_update_item(
    previous: Any | None,
    next_context: Any,
    exec_policy: Any = None,
) -> str | None:
    """Build the permissions-instructions update for a turn context change.

    Mirrors the focused Rust logic in ``build_permissions_update_item``:
    no update is emitted for the first context, and feature-only changes do not
    trigger a permissions update unless the permission profile or approval
    policy also changed.
    """

    config = _call_or_get(next_context, "config")
    if not _call_or_get(config, "include_permissions_instructions"):
        return None
    if previous is None:
        return None
    previous_permission_profile = _call_or_get(previous, "permission_profile")
    next_permission_profile = _call_or_get(next_context, "permission_profile")
    previous_approval_policy = _approval_policy_value(_call_or_get(previous, "approval_policy"))
    next_approval_policy = _approval_policy_value(_call_or_get(next_context, "approval_policy"))
    if (
        previous_permission_profile == next_permission_profile
        and previous_approval_policy == next_approval_policy
    ):
        return None

    features = _call_or_get(next_context, "features")
    return PermissionsInstructions.from_permission_profile(
        next_permission_profile,
        next_approval_policy,
        _call_or_get(config, "approvals_reviewer"),
        exec_policy,
        Path(_call_or_get(next_context, "cwd")),
        _feature_enabled(features, Feature.EXEC_PERMISSION_APPROVALS),
        _feature_enabled(features, Feature.REQUEST_PERMISSIONS_TOOL),
    ).render()


def build_collaboration_mode_update_item(
    previous: Any | None,
    next_context: Any,
) -> str | None:
    if not _call_or_get(_call_or_get(next_context, "config"), "include_collaboration_mode_instructions"):
        return None
    if previous is None:
        return None
    next_collaboration_mode = _call_or_get(next_context, "collaboration_mode")
    if _call_or_get(previous, "collaboration_mode") == next_collaboration_mode:
        return None
    instructions = CollaborationModeInstructions.from_collaboration_mode(next_collaboration_mode)
    return instructions.render() if instructions is not None else None


def build_realtime_update_item(
    previous: Any | None,
    previous_turn_settings: Any | None,
    next_context: Any,
) -> str | None:
    previous_realtime_active = None if previous is None else _call_or_get(previous, "realtime_active")
    next_realtime_active = _call_or_get(next_context, "realtime_active")
    if not isinstance(next_realtime_active, bool):
        raise TypeError("next_context.realtime_active must be a bool")

    if previous_realtime_active is True and next_realtime_active is False:
        return RealtimeEndInstructions.new("inactive").render()
    if (previous_realtime_active is False and next_realtime_active is True) or (
        previous_realtime_active is None and next_realtime_active is True
    ):
        instructions = _call_or_get(_call_or_get(next_context, "config"), "experimental_realtime_start_instructions")
        if instructions is not None:
            return RealtimeStartWithInstructions.new(str(instructions)).render()
        return RealtimeStartInstructions().render()
    if (previous_realtime_active is True and next_realtime_active is True) or (
        previous_realtime_active is False and next_realtime_active is False
    ):
        return None
    if previous_realtime_active is None and next_realtime_active is False:
        settings_active = (
            None
            if previous_turn_settings is None
            else _call_or_get(previous_turn_settings, "realtime_active")
        )
        return RealtimeEndInstructions.new("inactive").render() if settings_active is True else None
    return None


def build_initial_realtime_item(
    previous: Any | None,
    previous_turn_settings: Any | None,
    next_context: Any,
) -> str | None:
    return build_realtime_update_item(previous, previous_turn_settings, next_context)


def build_personality_update_item(
    previous: Any | None,
    next_context: Any,
    personality_feature_enabled: bool,
) -> str | None:
    if not isinstance(personality_feature_enabled, bool):
        raise TypeError("personality_feature_enabled must be a bool")
    if not personality_feature_enabled or previous is None:
        return None
    model_info = _call_or_get(next_context, "model_info")
    if _call_or_get(model_info, "slug") != _call_or_get(previous, "model"):
        return None
    personality = _call_or_get(next_context, "personality")
    if personality is None or personality == _call_or_get(previous, "personality"):
        return None
    message = personality_message_for(model_info, personality)
    return PersonalitySpecInstructions.new(message).render() if message is not None else None


def personality_message_for(model_info: Any, personality: Any) -> str | None:
    model_messages = _call_or_get(model_info, "model_messages")
    if model_messages is None:
        return None
    getter = getattr(model_messages, "get_personality_message", None)
    if not callable(getter):
        return None
    message = getter(personality)
    if not isinstance(message, str) or message == "":
        return None
    return message


def build_model_instructions_update_item(
    previous_turn_settings: Any | None,
    next_context: Any,
) -> str | None:
    if previous_turn_settings is None:
        return None
    model_info = _call_or_get(next_context, "model_info")
    if _call_or_get(previous_turn_settings, "model") == _call_or_get(model_info, "slug"):
        return None
    getter = getattr(model_info, "get_model_instructions", None)
    if not callable(getter):
        return None
    model_instructions = getter(_call_or_get(next_context, "personality"))
    if not isinstance(model_instructions, str) or model_instructions == "":
        return None
    return ModelSwitchInstructions.new(model_instructions).render()


def build_developer_update_item(text_sections: list[str] | tuple[str, ...]) -> ResponseItem | None:
    return build_text_message("developer", text_sections)


def build_contextual_user_message(text_sections: list[str] | tuple[str, ...]) -> ResponseItem | None:
    return build_text_message("user", text_sections)


def build_text_message(role: str, text_sections: list[str] | tuple[str, ...]) -> ResponseItem | None:
    if not isinstance(role, str):
        raise TypeError("role must be a string")
    if isinstance(text_sections, (str, bytes)) or not isinstance(text_sections, (list, tuple)):
        raise TypeError("text_sections must be a list or tuple of strings")
    if not text_sections:
        return None
    if any(not isinstance(text, str) for text in text_sections):
        raise TypeError("text_sections must contain strings")
    return ResponseItem.message(
        role,
        tuple(ContentItem.input_text(text) for text in text_sections),
    )


def build_settings_update_items(
    previous: Any | None,
    previous_turn_settings: Any | None,
    next_context: Any,
    *,
    exec_policy: Any = None,
    personality_feature_enabled: bool,
    shell: Any = None,
    contextual_user_message: ResponseItem | None = None,
) -> list[ResponseItem]:
    if not isinstance(personality_feature_enabled, bool):
        raise TypeError("personality_feature_enabled must be a bool")
    if contextual_user_message is not None and not isinstance(contextual_user_message, ResponseItem):
        raise TypeError("contextual_user_message must be ResponseItem or None")
    if shell is not None and contextual_user_message is None:
        contextual_user_message = build_environment_update_item(previous, next_context, shell)
    developer_update_sections = [
        build_model_instructions_update_item(previous_turn_settings, next_context),
        build_permissions_update_item(previous, next_context, exec_policy),
        build_collaboration_mode_update_item(previous, next_context),
        build_realtime_update_item(previous, previous_turn_settings, next_context),
        build_personality_update_item(previous, next_context, personality_feature_enabled),
    ]
    items: list[ResponseItem] = []
    developer_message = build_developer_update_item(
        [section for section in developer_update_sections if section is not None]
    )
    if developer_message is not None:
        items.append(developer_message)
    if contextual_user_message is not None:
        items.append(contextual_user_message)
    return items


def _approval_policy_value(value: Any) -> Any:
    method = getattr(value, "value", None)
    return method() if callable(method) else value


def _environment_context_from_next_context(next_context: Any, shell_name: str) -> EnvironmentContext:
    explicit = getattr(next_context, "environment_context", None)
    if isinstance(explicit, EnvironmentContext):
        return explicit
    return EnvironmentContext.new(
        _environment_context_environments(next_context, shell_name),
        current_date=_call_or_get_default(next_context, "current_date", None),
        timezone=_call_or_get_default(next_context, "timezone", None),
        network=_network_context_from_next_context(next_context),
    )


def _environment_context_environments(next_context: Any, shell_name: str) -> tuple[EnvironmentContextEnvironment, ...]:
    environments = _call_or_get_default(next_context, "environments", None)
    if environments is None:
        return (EnvironmentContextEnvironment.legacy(_call_or_get(next_context, "cwd"), shell_name),)
    candidates = getattr(environments, "turn_environments", environments)
    if candidates is None:
        return (EnvironmentContextEnvironment.legacy(_call_or_get(next_context, "cwd"), shell_name),)
    items = tuple(candidates)
    if not items:
        return ()
    result: list[EnvironmentContextEnvironment] = []
    for item in items:
        cwd = getattr(item, "cwd", _call_or_get(next_context, "cwd"))
        item_shell = getattr(item, "shell", None) or shell_name
        environment_id = getattr(item, "environment_id", None)
        if environment_id is None:
            environment_id = getattr(item, "id", "")
        result.append(EnvironmentContextEnvironment(str(environment_id), Path(cwd), str(item_shell)))
    return tuple(result)


def _network_context_from_next_context(next_context: Any) -> NetworkContext | None:
    network = _call_or_get_default(next_context, "network", None)
    if network is None:
        return None
    if isinstance(network, NetworkContext):
        return network
    return NetworkContext(
        allowed_domains=tuple(_call_or_get_default(network, "allowed_domains", ())),
        denied_domains=tuple(_call_or_get_default(network, "denied_domains", ())),
    )


def _shell_name(shell: Any) -> str:
    name = getattr(shell, "name", None)
    value = name() if callable(name) else name
    return str(value if value is not None else shell)


def _feature_enabled(features: Any, feature: Feature) -> bool:
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        value = enabled(feature)
        if not isinstance(value, bool):
            raise TypeError("features.enabled() must return a bool")
        return value
    if isinstance(features, dict):
        return bool(features.get(feature, features.get(feature.value, False)))
    return feature in features


def _call_or_get(value: Any, name: str) -> Any:
    attr = getattr(value, name)
    return attr() if callable(attr) else attr


def _call_or_get_default(value: Any, name: str, default: Any) -> Any:
    attr = getattr(value, name, default)
    return attr() if callable(attr) else attr


__all__ = [
    "build_collaboration_mode_update_item",
    "build_contextual_user_message",
    "build_developer_update_item",
    "build_environment_update_item",
    "build_initial_realtime_item",
    "build_model_instructions_update_item",
    "build_personality_update_item",
    "build_permissions_update_item",
    "build_realtime_update_item",
    "build_settings_update_items",
    "build_text_message",
    "personality_message_for",
]

