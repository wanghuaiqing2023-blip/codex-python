from pycodex.tui.chatwidget.model_popups import (
    PLAN_MODE_REASONING_SCOPE_ALL_MODES,
    PLAN_MODE_REASONING_SCOPE_PLAN_ONLY,
    PLAN_MODE_REASONING_SCOPE_TITLE,
    ModelPopupContext,
    ModelPreset,
    ReasoningEffortConfig,
    ReasoningEffortPreset,
    auto_model_order,
    custom_openai_base_url,
    open_model_popup_with_presets,
    open_plan_reasoning_scope_prompt,
    open_reasoning_popup,
    reasoning_effort_label,
    should_prompt_plan_mode_reasoning_scope,
)


def _preset(model: str, *, show: bool = True, effort: ReasoningEffortConfig = ReasoningEffortConfig.Medium) -> ModelPreset:
    return ModelPreset(
        model=model,
        description=f"{model} description",
        default_reasoning_effort=effort,
        supported_reasoning_efforts=(ReasoningEffortPreset(effort=effort, description=effort.value),),
        show_in_picker=show,
    )


def test_model_popup_filters_hidden_models_and_sorts_auto_models() -> None:
    # Rust parity: open_model_popup_with_presets filters show_in_picker and sorts auto presets.
    context = ModelPopupContext(current_model="codex-auto-balanced")
    result = open_model_popup_with_presets(
        context,
        [
            _preset("test-hidden-model", show=False),
            _preset("codex-auto-thorough"),
            _preset("legacy-model"),
            _preset("codex-auto-fast"),
            _preset("codex-auto-balanced"),
        ],
    )

    assert result.view is not None
    assert [item.name for item in result.view.items] == [
        "codex-auto-fast",
        "codex-auto-balanced",
        "codex-auto-thorough",
        "All models",
    ]
    assert result.view.items[1].is_current
    assert result.view.items[-1].actions[0].kind == "open_all_models_popup"
    assert [preset.model for preset in result.view.items[-1].actions[0].models] == ["legacy-model"]


def test_all_models_popup_empty_returns_info_message() -> None:
    # Rust parity: open_all_models_popup empty branch.
    result = open_model_popup_with_presets(ModelPopupContext(current_model="x"), [_preset("hidden", show=False)])
    assert result.view is None
    assert result.info_message == "No additional models are available right now."


def test_reasoning_popup_single_supported_effort_applies_immediately() -> None:
    # Rust parity: open_reasoning_popup single choice applies model/effort without showing a popup.
    preset = _preset("gpt-5.4", effort=ReasoningEffortConfig.High)
    result = open_reasoning_popup(ModelPopupContext(current_model="other"), preset)
    assert result.view is None
    assert [event.kind for event in result.events] == [
        "update_model",
        "update_reasoning_effort",
        "persist_model_selection",
    ]
    assert result.events[-1].model == "gpt-5.4"
    assert result.events[-1].effort is ReasoningEffortConfig.High


def test_reasoning_popup_multiple_choices_marks_default_current_and_warning() -> None:
    # Rust parity: open_reasoning_popup labels default and warns for high gpt-5.2 effort.
    preset = ModelPreset(
        model="gpt-5.2",
        default_reasoning_effort=ReasoningEffortConfig.Medium,
        supported_reasoning_efforts=(
            ReasoningEffortPreset(ReasoningEffortConfig.Medium, "medium"),
            ReasoningEffortPreset(ReasoningEffortConfig.High, "high"),
        ),
    )
    result = open_reasoning_popup(
        ModelPopupContext(current_model="gpt-5.2", effective_reasoning_effort=ReasoningEffortConfig.Medium),
        preset,
    )

    assert result.view is not None
    assert [item.name for item in result.view.items] == ["Medium (default)", "High"]
    assert result.view.initial_selected_idx == 0
    assert result.view.items[0].is_current
    assert "Plus plan rate limits" in (result.view.items[1].selected_description or "")


def test_plan_mode_reasoning_scope_prompt_gate_matches_rust_noop_rules() -> None:
    # Rust parity: should_prompt_plan_mode_reasoning_scope Plan-mode no-op and changed-global cases.
    context = ModelPopupContext(
        current_model="gpt-5.4",
        collaboration_modes_enabled=True,
        active_mode_kind="plan",
        current_collaboration_model="gpt-5.4",
        current_collaboration_effort=ReasoningEffortConfig.Medium,
        effective_reasoning_effort=ReasoningEffortConfig.Medium,
    )
    assert not should_prompt_plan_mode_reasoning_scope(context, "gpt-5.4", ReasoningEffortConfig.Medium)
    assert should_prompt_plan_mode_reasoning_scope(context, "gpt-5.4", ReasoningEffortConfig.High)


def test_plan_reasoning_scope_prompt_builds_two_action_paths_and_notifies() -> None:
    # Rust parity: open_plan_reasoning_scope_prompt item names/actions and notification title.
    context = ModelPopupContext(
        current_model="gpt-5.4",
        plan_mode_reasoning_effort=ReasoningEffortConfig.Low,
    )
    result = open_plan_reasoning_scope_prompt(context, "gpt-5.4", ReasoningEffortConfig.High)

    assert result.view is not None
    assert result.view.title == PLAN_MODE_REASONING_SCOPE_TITLE
    assert [item.name for item in result.view.items] == [
        PLAN_MODE_REASONING_SCOPE_PLAN_ONLY,
        PLAN_MODE_REASONING_SCOPE_ALL_MODES,
    ]
    assert [event.kind for event in result.view.items[0].actions] == [
        "update_model",
        "update_plan_mode_reasoning_effort",
        "persist_plan_mode_reasoning_effort",
    ]
    assert [event.kind for event in result.view.items[1].actions] == [
        "update_model",
        "update_reasoning_effort",
        "update_plan_mode_reasoning_effort",
        "persist_plan_mode_reasoning_effort",
        "persist_model_selection",
    ]
    assert context.notifications == [PLAN_MODE_REASONING_SCOPE_TITLE]


def test_small_helpers_match_rust_literals() -> None:
    # Rust parity: is_auto_model/auto_model_order/custom_openai_base_url/reasoning_effort_label.
    assert auto_model_order("codex-auto-fast") == 0
    assert auto_model_order("codex-auto-balanced") == 1
    assert auto_model_order("codex-auto-thorough") == 2
    assert auto_model_order("codex-auto-weird") == 3
    assert reasoning_effort_label(ReasoningEffortConfig.XHigh) == "Extra high"
    assert custom_openai_base_url(ModelPopupContext(current_model="x", custom_base_url=" https://example.test/ ")) == "https://example.test/"
    assert custom_openai_base_url(ModelPopupContext(current_model="x", custom_base_url="https://api.openai.com/v1/")) is None
