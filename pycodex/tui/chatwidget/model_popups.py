"""Model and reasoning popup construction for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/model_popups.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, List, Optional, Tuple, Union

from .._porting import RustTuiModule
from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams
from ..bottom_pane.popup_consts import standard_popup_hint_line

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::model_popups",
    source="codex/codex-rs/tui/src/chatwidget/model_popups.rs",
    status="complete",
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
PLAN_MODE_REASONING_SCOPE_TITLE = "Apply reasoning change"
PLAN_MODE_REASONING_SCOPE_PLAN_ONLY = "Apply to Plan mode override"
PLAN_MODE_REASONING_SCOPE_ALL_MODES = "Apply to global default and Plan mode override"


class ReasoningEffortConfig(str, Enum):
    None_ = "none"
    Minimal = "minimal"
    Low = "low"
    Medium = "medium"
    High = "high"
    XHigh = "xhigh"
    Max = "max"
    Ultra = "ultra"


@dataclass(frozen=True)
class ReasoningEffortPreset:
    effort: ReasoningEffortConfig
    description: str = ""


@dataclass(frozen=True)
class ModelPreset:
    model: str
    description: str = ""
    default_reasoning_effort: ReasoningEffortConfig = ReasoningEffortConfig.Medium
    supported_reasoning_efforts: Tuple[ReasoningEffortPreset, ...] = ()
    is_default: bool = False
    show_in_picker: bool = True


@dataclass(frozen=True)
class ModelPopupEvent:
    kind: str
    model: Optional[str] = None
    effort: Optional[ReasoningEffortConfig] = None
    models: Tuple[ModelPreset, ...] = ()


@dataclass
class ModelPopupContext:
    current_model: str
    model_display_name: Optional[str] = None
    collaboration_modes_enabled: bool = False
    active_mode_kind: str = "chat"
    current_collaboration_model: Optional[str] = None
    current_collaboration_effort: Optional[ReasoningEffortConfig] = None
    effective_reasoning_effort: Optional[ReasoningEffortConfig] = None
    plan_mode_reasoning_effort: Optional[ReasoningEffortConfig] = None
    custom_base_url: Optional[str] = None
    provider_is_openai: bool = True
    session_configured: bool = True
    catalog_error: bool = False
    info_messages: List[str] = field(default_factory=list)
    notifications: List[str] = field(default_factory=list)

    def display_model(self) -> str:
        return self.model_display_name or self.current_model


@dataclass(frozen=True)
class PopupResult:
    view: Optional[SelectionViewParams] = None
    info_message: Optional[str] = None
    events: Tuple[ModelPopupEvent, ...] = ()


def open_model_popup(
    context: ModelPopupContext,
    presets: Iterable[ModelPreset],
) -> PopupResult:
    if not context.session_configured:
        message = "Model selection is disabled until startup completes."
        context.info_messages.append(message)
        return PopupResult(info_message=message)
    if context.catalog_error:
        message = "Models are being updated; please try /model again in a moment."
        context.info_messages.append(message)
        return PopupResult(info_message=message)
    return open_model_popup_with_presets(context, presets)


def open_model_popup_with_presets(
    context: ModelPopupContext,
    presets: Iterable[ModelPreset],
) -> PopupResult:
    visible = [preset for preset in presets if preset.show_in_picker]
    current_label = next(
        (preset.model for preset in visible if preset.model == context.current_model),
        context.display_model(),
    )
    auto_presets = [preset for preset in visible if is_auto_model(preset.model)]
    other_presets = [preset for preset in visible if not is_auto_model(preset.model)]
    if not auto_presets:
        return open_all_models_popup(context, other_presets)

    auto_presets.sort(key=lambda preset: auto_model_order(preset.model))
    items = [
        SelectionItem(
            name=preset.model,
            description=preset.description or None,
            is_current=preset.model == context.current_model,
            is_default=preset.is_default,
            actions=model_selection_actions(
                preset.model,
                preset.default_reasoning_effort,
                should_prompt_plan_mode_reasoning_scope(
                    context,
                    preset.model,
                    preset.default_reasoning_effort,
                ),
            ),
            dismiss_on_select=True,
        )
        for preset in auto_presets
    ]

    if other_presets:
        items.append(
            SelectionItem(
                name="All models",
                description=f"Choose a specific model and reasoning level (current: {current_label})",
                is_current=not any(item.is_current for item in items),
                actions=[ModelPopupEvent(kind="open_all_models_popup", models=tuple(other_presets))],
                dismiss_on_select=True,
            )
        )

    return PopupResult(
        view=SelectionViewParams(
            items=items,
            header=model_menu_header(
                context,
                "Select Model",
                "Pick a quick auto mode or browse all models.",
            ),
            footer_hint=standard_popup_hint_line(),
        )
    )


def open_all_models_popup(
    context: ModelPopupContext,
    presets: Iterable[ModelPreset],
) -> PopupResult:
    preset_list = list(presets)
    if not preset_list:
        return PopupResult(info_message="No additional models are available right now.")

    items = []  # type: List[SelectionItem]
    for preset in preset_list:
        single_supported_effort = len(preset.supported_reasoning_efforts) == 1
        items.append(
            SelectionItem(
                name=preset.model,
                description=preset.description or None,
                is_current=preset.model == context.current_model,
                is_default=preset.is_default,
                actions=[ModelPopupEvent(kind="open_reasoning_popup", model=preset.model)],
                dismiss_on_select=single_supported_effort,
                dismiss_parent_on_child_accept=not single_supported_effort,
            )
        )
    return PopupResult(
        view=SelectionViewParams(
            items=items,
            header=model_menu_header(
                context,
                "Select Model and Effort",
                "Access legacy models by running codex -m <model_name> or in your config.toml",
            ),
            footer_hint=standard_popup_hint_line(),
        )
    )


def open_reasoning_popup(
    context: ModelPopupContext,
    preset: ModelPreset,
) -> PopupResult:
    choices = _reasoning_choices(preset)
    if len(choices) == 1:
        effort = choices[0]
        if should_prompt_plan_mode_reasoning_scope(context, preset.model, effort):
            return PopupResult(events=(ModelPopupEvent("open_plan_reasoning_scope_prompt", preset.model, effort),))
        return PopupResult(events=tuple(apply_model_and_effort(preset.model, effort)))

    default_choice = preset.default_reasoning_effort if preset.default_reasoning_effort in choices else choices[0]
    is_current_model = context.current_model == preset.model
    if is_current_model and context.collaboration_modes_enabled and context.active_mode_kind == "plan":
        highlight_choice = context.plan_mode_reasoning_effort or context.effective_reasoning_effort
    elif is_current_model:
        highlight_choice = context.effective_reasoning_effort
    else:
        highlight_choice = default_choice
    selection_choice = highlight_choice or default_choice
    initial_selected_idx = choices.index(selection_choice) if selection_choice in choices else None

    warn_effort = ReasoningEffortConfig.XHigh if ReasoningEffortConfig.XHigh in choices else (
        ReasoningEffortConfig.High if ReasoningEffortConfig.High in choices else None
    )
    warn_for_model = (
        preset.model.startswith("gpt-5.1-codex")
        or preset.model.startswith("gpt-5.1-codex-max")
        or preset.model.startswith("gpt-5.2")
    )
    descriptions = {option.effort: option.description for option in preset.supported_reasoning_efforts}
    items = []  # type: List[SelectionItem]
    for effort in choices:
        label = reasoning_effort_label(effort)
        if effort == default_choice:
            label += " (default)"
        description = descriptions.get(effort) or None
        selected_description = None
        if warn_for_model and warn_effort == effort:
            warning = f"Warning: {reasoning_effort_label(effort)} reasoning effort can quickly consume Plus plan rate limits."
            selected_description = f"{description}\n{warning}" if description else warning
        should_prompt = should_prompt_plan_mode_reasoning_scope(context, preset.model, effort)
        items.append(
            SelectionItem(
                name=label,
                description=description,
                selected_description=selected_description,
                is_current=is_current_model and effort == highlight_choice,
                actions=model_selection_actions(preset.model, effort, should_prompt),
                dismiss_on_select=True,
            )
        )

    return PopupResult(
        view=SelectionViewParams(
            items=items,
            initial_selected_idx=initial_selected_idx,
            header=f"Select Reasoning Level for {preset.model}",
            footer_hint=standard_popup_hint_line(),
        )
    )


def open_plan_reasoning_scope_prompt(
    context: ModelPopupContext,
    model: str,
    effort: Optional[ReasoningEffortConfig],
) -> PopupResult:
    reasoning_phrase = _reasoning_phrase(effort)
    plan_reasoning_source = _plan_reasoning_source(context)
    plan_only = SelectionItem(
        name=PLAN_MODE_REASONING_SCOPE_PLAN_ONLY,
        description=f"Always use {reasoning_phrase} in Plan mode.",
        actions=[
            ModelPopupEvent("update_model", model, None),
            ModelPopupEvent("update_plan_mode_reasoning_effort", None, effort),
            ModelPopupEvent("persist_plan_mode_reasoning_effort", None, effort),
        ],
        dismiss_on_select=True,
    )
    all_modes = SelectionItem(
        name=PLAN_MODE_REASONING_SCOPE_ALL_MODES,
        description=(
            "Set the global default reasoning level and the Plan mode override. "
            f"This replaces the current {plan_reasoning_source}."
        ),
        actions=[
            ModelPopupEvent("update_model", model, None),
            ModelPopupEvent("update_reasoning_effort", None, effort),
            ModelPopupEvent("update_plan_mode_reasoning_effort", None, effort),
            ModelPopupEvent("persist_plan_mode_reasoning_effort", None, effort),
            ModelPopupEvent("persist_model_selection", model, effort),
        ],
        dismiss_on_select=True,
    )
    context.notifications.append(PLAN_MODE_REASONING_SCOPE_TITLE)
    return PopupResult(
        view=SelectionViewParams(
            title=PLAN_MODE_REASONING_SCOPE_TITLE,
            subtitle=f"Choose where to apply {reasoning_phrase}.",
            footer_hint=standard_popup_hint_line(),
            items=[plan_only, all_modes],
        )
    )


def terminal_model_popup_context_from_runtime(app_runtime: object) -> ModelPopupContext:
    """Build terminal model-popup context from the active app runtime.

    Rust owner: ``chatwidget::model_popups`` owns model picker input state.  The
    terminal runtime supplies an app runtime object, but it should not own the
    model/reasoning resolution rules used to open the popup.
    """

    return ModelPopupContext(
        current_model=terminal_current_model_from_runtime(app_runtime),
        effective_reasoning_effort=terminal_current_reasoning_effort_from_runtime(app_runtime),
    )


@dataclass
class TerminalModelPopupController:
    """Terminal /model popup session state owned by chatwidget::model_popups."""

    app_runtime: object
    dispatch_app_event: Optional[Callable[[Any], Any]] = None
    context: ModelPopupContext | None = None
    presets: Tuple[ModelPreset, ...] = ()

    def open_view(self) -> Any:
        self.context = terminal_model_popup_context_from_runtime(self.app_runtime)
        self.presets = terminal_model_presets_from_runtime(self.app_runtime, self.context.current_model)
        result = open_model_popup(self.context, self.presets)
        for event in result.events:
            self.apply_event(event)
        return result.view

    def handle_events(self, events: Tuple[object, ...]) -> Any:
        return terminal_apply_model_popup_events(
            events,
            context=self.context,
            presets=self.presets,
            dispatch_app_event=self._dispatch_app_event,
        )

    def apply_event(self, event: ModelPopupEvent) -> Any:
        return terminal_apply_model_popup_event(
            event,
            context=self.context,
            presets=self.presets,
            dispatch_app_event=self._dispatch_app_event,
        )

    def _dispatch_app_event(self, event: Any) -> Any:
        dispatcher = self.dispatch_app_event or getattr(self.app_runtime, "handle_app_event", None)
        if not callable(dispatcher):
            return None
        return dispatcher(event)


def terminal_apply_model_popup_events(
    events: Tuple[object, ...],
    *,
    context: ModelPopupContext | None,
    presets: Tuple[ModelPreset, ...],
    dispatch_app_event: Callable[[Any], Any],
) -> Any:
    """Apply terminal model-popup events and return the next view, if any.

    Rust owner: ``chatwidget::model_popups`` wires model popup selection actions
    to ``AppEvent`` updates and follow-up popup views.  The terminal runtime
    owns the loop, but it should not own these model-popup action semantics.
    """

    next_view = None
    for event in events:
        if isinstance(event, ModelPopupEvent):
            candidate = terminal_apply_model_popup_event(
                event,
                context=context,
                presets=presets,
                dispatch_app_event=dispatch_app_event,
            )
            if candidate is not None:
                next_view = candidate
    return next_view


def terminal_apply_model_popup_event(
    event: ModelPopupEvent,
    *,
    context: ModelPopupContext | None,
    presets: Tuple[ModelPreset, ...],
    dispatch_app_event: Callable[[Any], Any],
) -> Any:
    """Apply one terminal model-popup event using Rust-owned popup rules."""

    if context is None:
        return None

    from ..app_event import AppEvent

    if event.kind == "update_model" and event.model is not None:
        dispatch_app_event(AppEvent.update_model(event.model))
        context.current_model = event.model
        return None
    if event.kind == "update_reasoning_effort":
        dispatch_app_event(AppEvent.update_reasoning_effort(event.effort))
        context.effective_reasoning_effort = event.effort
        return None
    if event.kind == "persist_model_selection" and event.model is not None:
        dispatch_app_event(AppEvent.persist_model_selection(event.model, event.effort))
        return None
    if event.kind == "open_all_models_popup":
        return open_all_models_popup(context, event.models).view
    if event.kind == "open_reasoning_popup" and event.model is not None:
        preset = next((candidate for candidate in presets if candidate.model == event.model), None)
        if preset is None:
            return None
        result = open_reasoning_popup(context, preset)
        if result.view is not None:
            return result.view
        return terminal_apply_model_popup_events(
            result.events,
            context=context,
            presets=presets,
            dispatch_app_event=dispatch_app_event,
        )
    if event.kind == "open_plan_reasoning_scope_prompt" and event.model is not None:
        return open_plan_reasoning_scope_prompt(context, event.model, event.effort).view
    return None


def terminal_current_model_from_runtime(app_runtime: object) -> str:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    value = (
        _terminal_runtime_value(session_config, "model")
        or _terminal_runtime_value(runtime, "model")
        or _terminal_runtime_value(app_runtime, "model")
    )
    return str(value or "gpt-5.5")


def terminal_current_reasoning_effort_from_runtime(
    app_runtime: object,
) -> ReasoningEffortConfig | None:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    return terminal_coerce_reasoning_effort(
        _terminal_runtime_value(session_config, "model_reasoning_effort")
        or _terminal_runtime_value(session_config, "reasoning_effort")
        or _terminal_runtime_value(runtime, "model_reasoning_effort")
    )


def terminal_model_presets_from_runtime(
    app_runtime: object,
    current: str,
) -> Tuple[ModelPreset, ...]:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    raw = _terminal_first_value(
        runtime,
        session_config,
        names=("available_models", "model_presets", "models"),
    )
    presets = tuple(terminal_model_preset_from_runtime(item, current) for item in (raw or ()))
    visible = tuple(preset for preset in presets if preset.model)
    if visible:
        return visible

    managed = terminal_model_manager_presets_from_runtime(app_runtime, current)
    if managed:
        return managed

    bundled = terminal_bundled_model_popup_presets(current)
    if bundled:
        return bundled
    return (terminal_fallback_current_model_preset(current),)


def terminal_model_manager_presets_from_runtime(
    app_runtime: object,
    current: str,
) -> Tuple[ModelPreset, ...]:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    services = getattr(session_config, "services", None)
    for source in (
        runtime,
        getattr(services, "models_manager", None),
        getattr(session_config, "models_manager", None),
        getattr(app_runtime, "models_manager", None),
    ):
        if source is None:
            continue
        for method_name in ("list_models", "try_list_models"):
            method = getattr(source, method_name, None)
            if not callable(method):
                continue
            try:
                result = method("online_if_uncached") if method_name == "list_models" else method()
            except TypeError:
                try:
                    result = method()
                except Exception:
                    continue
            except Exception:
                continue
            presets = tuple(terminal_model_preset_from_runtime(item, current) for item in (result or ()))
            visible = tuple(preset for preset in presets if preset.model)
            if visible:
                return visible
    return ()


def terminal_bundled_model_popup_presets(current: str) -> Tuple[ModelPreset, ...]:
    try:
        from pycodex.models_manager import bundled_models_response, model_presets_from_models
        from pycodex.protocol import ModelsResponse
    except Exception:
        return ()
    try:
        response = ModelsResponse.from_mapping(bundled_models_response())
        raw = model_presets_from_models(response.models)
    except Exception:
        return ()
    presets = tuple(terminal_model_preset_from_runtime(item, current) for item in raw)
    return tuple(preset for preset in presets if preset.model)


def terminal_fallback_current_model_preset(current: str) -> ModelPreset:
    effort = ReasoningEffortConfig.Medium
    return ModelPreset(
        model=current,
        default_reasoning_effort=effort,
        supported_reasoning_efforts=(ReasoningEffortPreset(effort, "Balanced reasoning for everyday tasks"),),
        is_default=True,
    )


def terminal_model_preset_from_runtime(value: object, current_model: str) -> ModelPreset:
    if isinstance(value, str):
        effort = ReasoningEffortConfig.Medium
        return ModelPreset(
            model=value,
            default_reasoning_effort=effort,
            supported_reasoning_efforts=(ReasoningEffortPreset(effort),),
            is_default=value == current_model,
        )
    model = (
        _terminal_runtime_value(value, "model")
        or _terminal_runtime_value(value, "id")
        or _terminal_runtime_value(value, "name")
    )
    if model is None:
        return ModelPreset(model="")
    effort = terminal_coerce_reasoning_effort(
        _terminal_runtime_value(value, "default_reasoning_effort")
        or _terminal_runtime_value(value, "reasoning_effort")
        or _terminal_runtime_value(value, "effort")
    ) or ReasoningEffortConfig.Medium
    supported = terminal_coerce_supported_reasoning_efforts(
        _terminal_runtime_value(value, "supported_reasoning_efforts")
        or _terminal_runtime_value(value, "supported_efforts")
        or _terminal_runtime_value(value, "reasoning_efforts")
    )
    if not supported:
        supported = (ReasoningEffortPreset(effort),)
    return ModelPreset(
        model=str(model),
        description=str(_terminal_runtime_value(value, "description") or ""),
        default_reasoning_effort=effort,
        supported_reasoning_efforts=supported,
        is_default=bool(_terminal_runtime_value(value, "is_default")) or str(model) == current_model,
        show_in_picker=bool(_terminal_runtime_value(value, "show_in_picker", True)),
    )


def terminal_coerce_reasoning_effort(value: object | None) -> ReasoningEffortConfig | None:
    if value is None:
        return None
    if isinstance(value, ReasoningEffortConfig):
        return value
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        value = enum_value
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized == "none":
        return ReasoningEffortConfig.None_
    for effort in ReasoningEffortConfig:
        if effort.value == normalized:
            return effort
    return None


def terminal_coerce_supported_reasoning_efforts(
    value: object | None,
) -> Tuple[ReasoningEffortPreset, ...]:
    if not value:
        return ()
    out: list[ReasoningEffortPreset] = []
    for item in value if isinstance(value, (list, tuple)) else (value,):
        effort = terminal_coerce_reasoning_effort(_terminal_runtime_value(item, "effort", item))
        if effort is None:
            continue
        description = str(_terminal_runtime_value(item, "description") or "")
        out.append(ReasoningEffortPreset(effort, description))
    return tuple(out)


def _terminal_first_value(*sources: object, names: Tuple[str, ...]) -> object | None:
    for source in sources:
        if source is None:
            continue
        for name in names:
            value = _terminal_runtime_value(source, name, None)
            if value is not None:
                return value
    return None


def _terminal_runtime_value(source: object, name: str, default: object | None = None) -> object | None:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    value = getattr(source, name, default)
    return value() if callable(value) else value


def model_menu_header(
    context: ModelPopupContext,
    title: str,
    subtitle: str,
) -> Tuple[str, str, Optional[str]]:
    return (title, subtitle, model_menu_warning_line(context))


def model_menu_warning_line(context: ModelPopupContext) -> Optional[str]:
    base_url = custom_openai_base_url(context)
    if base_url is None:
        return None
    return (
        "Warning: OpenAI base URL is overridden to "
        f"{base_url}. Selecting models may not be supported or work properly."
    )


def custom_openai_base_url(context: ModelPopupContext) -> Optional[str]:
    if not context.provider_is_openai or context.custom_base_url is None:
        return None
    trimmed = context.custom_base_url.strip()
    if not trimmed:
        return None
    if trimmed.rstrip("/") == DEFAULT_OPENAI_BASE_URL:
        return None
    return trimmed


def is_auto_model(model: str) -> bool:
    return model.startswith("codex-auto-")


def auto_model_order(model: str) -> int:
    return {
        "codex-auto-fast": 0,
        "codex-auto-balanced": 1,
        "codex-auto-thorough": 2,
    }.get(model, 3)


def model_selection_actions(
    model: str,
    effort: Optional[ReasoningEffortConfig],
    should_prompt_plan_mode_scope: bool,
) -> List[ModelPopupEvent]:
    if should_prompt_plan_mode_scope:
        return [ModelPopupEvent("open_plan_reasoning_scope_prompt", model, effort)]
    return apply_model_and_effort(model, effort)


def should_prompt_plan_mode_reasoning_scope(
    context: ModelPopupContext,
    selected_model: str,
    selected_effort: Optional[ReasoningEffortConfig],
) -> bool:
    if (
        not context.collaboration_modes_enabled
        or context.active_mode_kind != "plan"
        or selected_model != context.current_model
    ):
        return False
    return (
        selected_effort != context.effective_reasoning_effort
        or selected_model != context.current_collaboration_model
        or selected_effort != context.current_collaboration_effort
    )


def reasoning_effort_label(effort: ReasoningEffortConfig) -> str:
    return {
        ReasoningEffortConfig.None_: "None",
        ReasoningEffortConfig.Minimal: "Minimal",
        ReasoningEffortConfig.Low: "Low",
        ReasoningEffortConfig.Medium: "Medium",
        ReasoningEffortConfig.High: "High",
        ReasoningEffortConfig.XHigh: "Extra high",
        ReasoningEffortConfig.Max: "Max",
        ReasoningEffortConfig.Ultra: "Ultra",
    }[effort]


def apply_model_and_effort_without_persist(
    model: str,
    effort: Optional[ReasoningEffortConfig],
) -> List[ModelPopupEvent]:
    return [
        ModelPopupEvent("update_model", model, None),
        ModelPopupEvent("update_reasoning_effort", None, effort),
    ]


def apply_model_and_effort(
    model: str,
    effort: Optional[ReasoningEffortConfig],
) -> List[ModelPopupEvent]:
    return [
        *apply_model_and_effort_without_persist(model, effort),
        ModelPopupEvent("persist_model_selection", model, effort),
    ]


def _reasoning_choices(preset: ModelPreset) -> List[ReasoningEffortConfig]:
    supported = {option.effort for option in preset.supported_reasoning_efforts}
    choices = [effort for effort in ReasoningEffortConfig if effort in supported]
    return choices or [preset.default_reasoning_effort]


def _reasoning_phrase(effort: Optional[ReasoningEffortConfig]) -> str:
    if effort is ReasoningEffortConfig.None_:
        return "no reasoning"
    if effort is None:
        return "the selected reasoning"
    return f"{reasoning_effort_label(effort).lower()} reasoning"


def _plan_reasoning_source(context: ModelPopupContext) -> str:
    if context.plan_mode_reasoning_effort is not None:
        return f"user-chosen Plan override ({reasoning_effort_label(context.plan_mode_reasoning_effort).lower()})"
    if context.current_collaboration_effort is ReasoningEffortConfig.None_:
        return "built-in Plan default (no reasoning)"
    if context.current_collaboration_effort is not None:
        return f"built-in Plan default ({reasoning_effort_label(context.current_collaboration_effort).lower()})"
    return "built-in Plan default"


__all__ = [
    "DEFAULT_OPENAI_BASE_URL",
    "ModelPopupContext",
    "ModelPopupEvent",
    "ModelPreset",
    "PLAN_MODE_REASONING_SCOPE_ALL_MODES",
    "PLAN_MODE_REASONING_SCOPE_PLAN_ONLY",
    "PLAN_MODE_REASONING_SCOPE_TITLE",
    "PopupResult",
    "RUST_MODULE",
    "ReasoningEffortConfig",
    "ReasoningEffortPreset",
    "TerminalModelPopupController",
    "apply_model_and_effort",
    "apply_model_and_effort_without_persist",
    "auto_model_order",
    "custom_openai_base_url",
    "is_auto_model",
    "model_menu_header",
    "model_menu_warning_line",
    "model_selection_actions",
    "open_model_popup",
    "open_all_models_popup",
    "open_model_popup_with_presets",
    "open_plan_reasoning_scope_prompt",
    "open_reasoning_popup",
    "reasoning_effort_label",
    "should_prompt_plan_mode_reasoning_scope",
    "terminal_apply_model_popup_event",
    "terminal_apply_model_popup_events",
    "terminal_bundled_model_popup_presets",
    "terminal_coerce_reasoning_effort",
    "terminal_coerce_supported_reasoning_efforts",
    "terminal_current_model_from_runtime",
    "terminal_current_reasoning_effort_from_runtime",
    "terminal_fallback_current_model_preset",
    "terminal_model_manager_presets_from_runtime",
    "terminal_model_popup_context_from_runtime",
    "terminal_model_preset_from_runtime",
    "terminal_model_presets_from_runtime",
]
