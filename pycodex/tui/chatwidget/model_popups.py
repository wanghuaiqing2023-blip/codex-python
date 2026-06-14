"""Model and reasoning popup construction for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/model_popups.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .._porting import RustTuiModule
from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::model_popups",
    source="codex/codex-rs/tui/src/chatwidget/model_popups.rs",
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


@dataclass(frozen=True)
class ReasoningEffortPreset:
    effort: ReasoningEffortConfig
    description: str = ""


@dataclass(frozen=True)
class ModelPreset:
    model: str
    description: str = ""
    default_reasoning_effort: ReasoningEffortConfig = ReasoningEffortConfig.Medium
    supported_reasoning_efforts: tuple[ReasoningEffortPreset, ...] = ()
    is_default: bool = False
    show_in_picker: bool = True


@dataclass(frozen=True)
class ModelPopupEvent:
    kind: str
    model: str | None = None
    effort: ReasoningEffortConfig | None = None
    models: tuple[ModelPreset, ...] = ()


@dataclass
class ModelPopupContext:
    current_model: str
    model_display_name: str | None = None
    collaboration_modes_enabled: bool = False
    active_mode_kind: str = "chat"
    current_collaboration_model: str | None = None
    current_collaboration_effort: ReasoningEffortConfig | None = None
    effective_reasoning_effort: ReasoningEffortConfig | None = None
    plan_mode_reasoning_effort: ReasoningEffortConfig | None = None
    custom_base_url: str | None = None
    provider_is_openai: bool = True
    info_messages: list[str] = field(default_factory=list)
    notifications: list[str] = field(default_factory=list)

    def display_model(self) -> str:
        return self.model_display_name or self.current_model


@dataclass(frozen=True)
class PopupResult:
    view: SelectionViewParams | None = None
    info_message: str | None = None
    events: tuple[ModelPopupEvent, ...] = ()


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
            footer_hint="standard-popup-hint",
        )
    )


def open_all_models_popup(
    context: ModelPopupContext,
    presets: Iterable[ModelPreset],
) -> PopupResult:
    preset_list = list(presets)
    if not preset_list:
        return PopupResult(info_message="No additional models are available right now.")

    items: list[SelectionItem] = []
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
            footer_hint="standard-popup-hint",
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
    items: list[SelectionItem] = []
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
            footer_hint="standard-popup-hint",
        )
    )


def open_plan_reasoning_scope_prompt(
    context: ModelPopupContext,
    model: str,
    effort: ReasoningEffortConfig | None,
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
            footer_hint="standard-popup-hint",
            items=[plan_only, all_modes],
        )
    )


def model_menu_header(context: ModelPopupContext, title: str, subtitle: str) -> tuple[str, str, str | None]:
    return (title, subtitle, model_menu_warning_line(context))


def model_menu_warning_line(context: ModelPopupContext) -> str | None:
    base_url = custom_openai_base_url(context)
    if base_url is None:
        return None
    return (
        "Warning: OpenAI base URL is overridden to "
        f"{base_url}. Selecting models may not be supported or work properly."
    )


def custom_openai_base_url(context: ModelPopupContext) -> str | None:
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
    effort: ReasoningEffortConfig | None,
    should_prompt_plan_mode_scope: bool,
) -> list[ModelPopupEvent]:
    if should_prompt_plan_mode_scope:
        return [ModelPopupEvent("open_plan_reasoning_scope_prompt", model, effort)]
    return apply_model_and_effort(model, effort)


def should_prompt_plan_mode_reasoning_scope(
    context: ModelPopupContext,
    selected_model: str,
    selected_effort: ReasoningEffortConfig | None,
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
    }[effort]


def apply_model_and_effort_without_persist(
    model: str,
    effort: ReasoningEffortConfig | None,
) -> list[ModelPopupEvent]:
    return [
        ModelPopupEvent("update_model", model, None),
        ModelPopupEvent("update_reasoning_effort", None, effort),
    ]


def apply_model_and_effort(
    model: str,
    effort: ReasoningEffortConfig | None,
) -> list[ModelPopupEvent]:
    return [
        *apply_model_and_effort_without_persist(model, effort),
        ModelPopupEvent("persist_model_selection", model, effort),
    ]


def _reasoning_choices(preset: ModelPreset) -> list[ReasoningEffortConfig]:
    supported = {option.effort for option in preset.supported_reasoning_efforts}
    choices = [effort for effort in ReasoningEffortConfig if effort in supported]
    return choices or [preset.default_reasoning_effort]


def _reasoning_phrase(effort: ReasoningEffortConfig | None) -> str:
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
    "apply_model_and_effort",
    "apply_model_and_effort_without_persist",
    "auto_model_order",
    "custom_openai_base_url",
    "is_auto_model",
    "model_menu_header",
    "model_menu_warning_line",
    "model_selection_actions",
    "open_all_models_popup",
    "open_model_popup_with_presets",
    "open_plan_reasoning_scope_prompt",
    "open_reasoning_popup",
    "reasoning_effort_label",
    "should_prompt_plan_mode_reasoning_scope",
]
