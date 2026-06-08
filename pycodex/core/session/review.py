"""Review session helpers aligned with ``codex-core::session::review``."""

from __future__ import annotations

import copy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from pycodex.core.tasks.review import ReviewTask
from pycodex.features import Feature, Features
from pycodex.protocol import EventMsg, ReviewRequest, UserInput, WebSearchMode


UPSTREAM_SESSION_REVIEW = "codex/codex-rs/core/src/session/review.rs"


async def spawn_review_thread(
    sess: Any,
    config: Any,
    parent_turn_context: Any,
    sub_id: str,
    resolved: Any,
) -> Any:
    """Spawn a review child turn and announce entered-review mode."""

    if not isinstance(sub_id, str):
        raise TypeError("sub_id must be a string")

    review_model = _field(config, "review_model")
    model = review_model or _model_slug(_field(parent_turn_context, "model_info"))
    review_model_info = await _resolve_review_model_info(sess, config, model, parent_turn_context)
    review_features = review_features_for_review(_field(sess, "features", _field(config, "features")))
    per_turn_config = review_config_for_review(config, model, review_features)
    available_models = await _list_available_models(sess)
    goal_tools_supported = bool(not _field(config, "ephemeral", False) and _call_bool(parent_turn_context, "goal_tools_enabled"))

    review_turn_context = build_review_turn_context(
        sess=sess,
        parent_turn_context=parent_turn_context,
        config=per_turn_config,
        sub_id=sub_id,
        model_info=review_model_info,
        features=review_features,
        available_models=available_models,
        goal_tools_supported=goal_tools_supported,
    )

    prompt = _field(resolved, "prompt")
    if not isinstance(prompt, str):
        raise TypeError("resolved.prompt must be a string")
    review_input = [SimpleNamespace(items=(UserInput.text_input(prompt),))]

    metadata_state = _field(review_turn_context, "turn_metadata_state")
    spawn_git_enrichment = getattr(metadata_state, "spawn_git_enrichment_task", None)
    if callable(spawn_git_enrichment):
        spawn_git_enrichment()

    await _maybe_await(_field(sess, "spawn_task")(review_turn_context, review_input, ReviewTask.new()))

    review_request = ReviewRequest(
        target=_field(resolved, "target"),
        user_facing_hint=_field(resolved, "user_facing_hint"),
    )
    await _send_event(sess, review_turn_context, EventMsg.with_payload("entered_review_mode", review_request))
    return review_turn_context


def review_features_for_review(features: Any) -> Any:
    """Return review-turn features with disallowed review tools disabled."""

    review_features = _clone_features(features)
    for feature in (Feature.WEB_SEARCH_REQUEST, Feature.WEB_SEARCH_CACHED, Feature.GOALS):
        disable = getattr(review_features, "disable", None)
        if callable(disable):
            disable(feature)
    return review_features


def review_config_for_review(config: Any, model: str, review_features: Any) -> Any:
    """Build the per-turn config used by the review child turn."""

    if not isinstance(model, str):
        raise TypeError("model must be a string")
    per_turn_config = _clone_config(config)
    _set_field(per_turn_config, "model", model)
    _set_field(per_turn_config, "features", review_features)
    _set_web_search_disabled(per_turn_config)
    return per_turn_config


def build_review_turn_context(
    *,
    sess: Any,
    parent_turn_context: Any,
    config: Any,
    sub_id: str,
    model_info: Any,
    features: Any,
    available_models: Any,
    goal_tools_supported: bool,
) -> Any:
    """Build the child review turn context from the parent turn context."""

    factory = getattr(sess, "build_review_turn_context", None)
    if callable(factory):
        return factory(
            parent_turn_context=parent_turn_context,
            config=config,
            sub_id=sub_id,
            model_info=model_info,
            features=features,
            available_models=available_models,
            goal_tools_supported=goal_tools_supported,
        )

    data = dict(getattr(parent_turn_context, "__dict__", {}))
    data.update(
        {
            "sub_id": sub_id,
            "config": config,
            "model_info": model_info,
            "features": features,
            "available_models": available_models,
            "goal_tools_supported": goal_tools_supported,
            "developer_instructions": None,
            "user_instructions": None,
            "final_output_json_schema": None,
        }
    )
    if "reasoning_effort" not in data:
        data["reasoning_effort"] = _field(config, "model_reasoning_effort")
    if "reasoning_summary" not in data:
        data["reasoning_summary"] = _field(config, "model_reasoning_summary", _field(model_info, "default_reasoning_summary"))
    if "turn_metadata_state" not in data:
        data["turn_metadata_state"] = SimpleNamespace(spawn_git_enrichment_task=lambda: None)
    if "extension_data" not in data:
        data["extension_data"] = SimpleNamespace(turn_id=sub_id)
    return SimpleNamespace(**data)


async def _resolve_review_model_info(sess: Any, config: Any, model: str, parent_turn_context: Any) -> Any:
    services = _field(sess, "services")
    models_manager = _field(services, "models_manager")
    get_model_info = getattr(models_manager, "get_model_info", None)
    if callable(get_model_info):
        manager_config = None
        to_manager_config = getattr(config, "to_models_manager_config", None)
        if callable(to_manager_config):
            manager_config = to_manager_config()
        return await _maybe_await(get_model_info(model, manager_config))
    return _with_model_slug(_field(parent_turn_context, "model_info"), model)


async def _list_available_models(sess: Any) -> Any:
    services = _field(sess, "services")
    models_manager = _field(services, "models_manager")
    list_models = getattr(models_manager, "list_models", None)
    if not callable(list_models):
        return ()
    try:
        return await _maybe_await(list_models("OnlineIfUncached"))
    except TypeError:
        return await _maybe_await(list_models())


async def _send_event(sess: Any, turn_context: Any, msg: EventMsg) -> None:
    send_event = getattr(sess, "send_event", None)
    if callable(send_event):
        await _maybe_await(send_event(turn_context, msg))
        return
    send_event_raw = getattr(sess, "send_event_raw", None)
    if callable(send_event_raw):
        event_id = _field(turn_context, "sub_id")
        await _maybe_await(send_event_raw(SimpleNamespace(id=event_id, msg=msg)))


def _clone_features(features: Any) -> Any:
    if features is None:
        return Features.with_defaults()
    clone = getattr(features, "clone", None)
    if callable(clone):
        return clone()
    if isinstance(features, Features):
        return Features(features.enabled_features())
    try:
        return copy.deepcopy(features)
    except Exception:
        return features


def _clone_config(config: Any) -> Any:
    if hasattr(config, "__dataclass_fields__"):
        try:
            return replace(config)
        except Exception:
            pass
    clone = getattr(config, "clone", None)
    if callable(clone):
        return clone()
    try:
        return copy.deepcopy(config)
    except Exception:
        return SimpleNamespace(**dict(getattr(config, "__dict__", {})))


def _set_web_search_disabled(config: Any) -> None:
    web_search_mode = _field(config, "web_search_mode")
    setter = getattr(web_search_mode, "set", None)
    if callable(setter):
        setter(WebSearchMode.DISABLED)
        return
    _set_field(config, "web_search_mode", WebSearchMode.DISABLED)


def _with_model_slug(model_info: Any, model: str) -> Any:
    if model_info is None:
        return SimpleNamespace(slug=model, default_reasoning_summary=None, truncation_policy=None)
    if hasattr(model_info, "__dataclass_fields__"):
        try:
            return replace(model_info, slug=model)
        except Exception:
            pass
    data = dict(getattr(model_info, "__dict__", {}))
    data["slug"] = model
    return SimpleNamespace(**data)


def _model_slug(model_info: Any) -> str:
    slug = _field(model_info, "slug")
    if not isinstance(slug, str):
        raise TypeError("parent turn model_info.slug must be a string")
    return slug


def _field(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _set_field(target: Any, name: str, value: Any) -> None:
    if isinstance(target, dict):
        target[name] = value
    else:
        setattr(target, name, value)


def _call_bool(source: Any, name: str) -> bool:
    value = getattr(source, name, None)
    if callable(value):
        return bool(value())
    return bool(value)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "UPSTREAM_SESSION_REVIEW",
    "build_review_turn_context",
    "review_config_for_review",
    "review_features_for_review",
    "spawn_review_thread",
]
