import os
from types import SimpleNamespace

from pycodex.tui.bottom_pane.list_selection_view import ListSelectionView
from pycodex.tui.bottom_pane.terminal_action import TerminalBottomPaneState
from pycodex.tui.chatwidget.model_popups import (
    PLAN_MODE_REASONING_SCOPE_ALL_MODES,
    PLAN_MODE_REASONING_SCOPE_PLAN_ONLY,
    PLAN_MODE_REASONING_SCOPE_TITLE,
    ModelPopupContext,
    ModelPopupEvent,
    ModelPreset,
    ReasoningEffortConfig,
    ReasoningEffortPreset,
    TerminalModelPopupController,
    auto_model_order,
    custom_openai_base_url,
    open_model_popup,
    open_model_popup_with_presets,
    open_plan_reasoning_scope_prompt,
    open_reasoning_popup,
    reasoning_effort_label,
    should_prompt_plan_mode_reasoning_scope,
    terminal_apply_model_popup_event,
    terminal_apply_model_popup_events,
    terminal_coerce_reasoning_effort,
    terminal_model_popup_context_from_runtime,
    terminal_model_preset_from_runtime,
    terminal_model_presets_from_runtime,
)
from pycodex.tui.chatwidget.rendering import terminal_bottom_pane_frame, terminal_bottom_pane_frame_buffer
from pycodex.tui.ratatui_bridge import Color as RatatuiColor


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


def test_all_models_item_is_current_when_current_model_is_not_auto() -> None:
    # Rust parity: open_model_popup_with_presets marks "All models" current when
    # none of the quick auto items match the active model.
    context = ModelPopupContext(current_model="legacy-model")
    result = open_model_popup_with_presets(
        context,
        [
            _preset("codex-auto-fast"),
            _preset("legacy-model"),
        ],
    )

    assert result.view is not None
    all_models = result.view.items[-1]
    assert all_models.name == "All models"
    assert all_models.is_current
    assert all_models.description == (
        "Choose a specific model and reasoning level (current: legacy-model)"
    )


def test_open_model_popup_guards_startup_and_catalog_refresh_errors() -> None:
    # Rust parity: open_model_popup startup and model-catalog error branches.
    startup = ModelPopupContext(current_model="x", session_configured=False)
    startup_result = open_model_popup(startup, [_preset("codex-auto-fast")])
    assert startup_result.info_message == "Model selection is disabled until startup completes."
    assert startup.info_messages == [startup_result.info_message]

    refreshing = ModelPopupContext(current_model="x", catalog_error=True)
    refreshing_result = open_model_popup(refreshing, [_preset("codex-auto-fast")])
    assert refreshing_result.info_message == "Models are being updated; please try /model again in a moment."
    assert refreshing.info_messages == [refreshing_result.info_message]


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


def test_all_models_popup_dismiss_flags_depend_on_supported_effort_count() -> None:
    # Rust parity: open_all_models_popup dismisses immediately only when the model has
    # one supported reasoning effort; multi-effort models keep the parent for child accept.
    context = ModelPopupContext(current_model="other")
    result = open_model_popup_with_presets(
        context,
        [
            ModelPreset(
                model="single",
                supported_reasoning_efforts=(
                    ReasoningEffortPreset(ReasoningEffortConfig.Low, "low"),
                ),
            ),
            ModelPreset(
                model="multi",
                supported_reasoning_efforts=(
                    ReasoningEffortPreset(ReasoningEffortConfig.Low, "low"),
                    ReasoningEffortPreset(ReasoningEffortConfig.High, "high"),
                ),
            ),
        ],
    )

    assert result.view is not None
    assert [(item.name, item.dismiss_on_select, item.dismiss_parent_on_child_accept) for item in result.view.items] == [
        ("single", True, False),
        ("multi", False, True),
    ]


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


def test_terminal_model_popup_context_reads_runtime_model_and_reasoning() -> None:
    # Rust owner: chatwidget::model_popups owns the model picker context used
    # when /model opens from the terminal product path.
    runtime = SimpleNamespace(
        session_config=SimpleNamespace(
            model="gpt-5.4",
            model_reasoning_effort="low",
        )
    )
    app_runtime = SimpleNamespace(active_thread_runtime=runtime)

    context = terminal_model_popup_context_from_runtime(app_runtime)

    assert context.current_model == "gpt-5.4"
    assert context.effective_reasoning_effort is ReasoningEffortConfig.Low


def test_terminal_model_presets_from_runtime_prefers_available_models() -> None:
    # Rust owner: chatwidget::model_popups owns model popup preset inputs; the
    # terminal runtime should not construct these rows itself.
    runtime = SimpleNamespace(
        session_config=SimpleNamespace(
            available_models=(
                SimpleNamespace(
                    model="gpt-5.4",
                    description="Strong model",
                    default_reasoning_effort="high",
                    supported_reasoning_efforts=(
                        SimpleNamespace(effort="low", description="Fast"),
                        SimpleNamespace(effort="high", description="Deep"),
                    ),
                ),
            )
        )
    )
    app_runtime = SimpleNamespace(active_thread_runtime=runtime)

    presets = terminal_model_presets_from_runtime(app_runtime, "gpt-5.4")

    assert len(presets) == 1
    assert presets[0].model == "gpt-5.4"
    assert presets[0].description == "Strong model"
    assert presets[0].default_reasoning_effort is ReasoningEffortConfig.High
    assert [item.effort for item in presets[0].supported_reasoning_efforts] == [
        ReasoningEffortConfig.Low,
        ReasoningEffortConfig.High,
    ]
    assert presets[0].is_default


def test_terminal_model_preset_from_runtime_handles_string_and_reasoning_aliases() -> None:
    # Rust owner: chatwidget::model_popups normalizes runtime catalog data into
    # ModelPreset values before the ListSelectionView is created.
    assert terminal_coerce_reasoning_effort("extra-high") is None
    assert terminal_coerce_reasoning_effort("xhigh") is ReasoningEffortConfig.XHigh

    preset = terminal_model_preset_from_runtime("gpt-test", "gpt-test")

    assert preset.model == "gpt-test"
    assert preset.default_reasoning_effort is ReasoningEffortConfig.Medium
    assert preset.supported_reasoning_efforts[0].effort is ReasoningEffortConfig.Medium
    assert preset.is_default


def test_terminal_apply_model_popup_events_dispatches_model_and_effort_app_events() -> None:
    # Rust owner: chatwidget::model_popups::model_selection_actions sends
    # UpdateModel, UpdateReasoningEffort, and PersistModelSelection.
    context = ModelPopupContext(current_model="old", effective_reasoning_effort=ReasoningEffortConfig.High)
    dispatched = []

    terminal_apply_model_popup_events(
        (
            ModelPopupEvent("update_model", "gpt-5.4", None),
            ModelPopupEvent("update_reasoning_effort", None, ReasoningEffortConfig.Low),
            ModelPopupEvent("persist_model_selection", "gpt-5.4", ReasoningEffortConfig.Low),
        ),
        context=context,
        presets=(),
        dispatch_app_event=dispatched.append,
    )

    assert [event.kind for event in dispatched] == [
        "UpdateModel",
        "UpdateReasoningEffort",
        "PersistModelSelection",
    ]
    assert context.current_model == "gpt-5.4"
    assert context.effective_reasoning_effort is ReasoningEffortConfig.Low


def test_terminal_apply_model_popup_event_opens_reasoning_view_from_presets() -> None:
    # Rust owner: chatwidget::model_popups::open_all_models_popup sends
    # OpenReasoningPopup, which opens the reasoning picker for multi-effort
    # models rather than applying a single special runtime branch.
    context = ModelPopupContext(current_model="old")
    preset = ModelPreset(
        model="gpt-5.4",
        supported_reasoning_efforts=(
            ReasoningEffortPreset(ReasoningEffortConfig.Low, "Fast"),
            ReasoningEffortPreset(ReasoningEffortConfig.High, "Deep"),
        ),
    )

    view = terminal_apply_model_popup_event(
        ModelPopupEvent("open_reasoning_popup", "gpt-5.4", None),
        context=context,
        presets=(preset,),
        dispatch_app_event=lambda event: None,
    )

    assert view is not None
    assert view.header == "Select Reasoning Level for gpt-5.4"
    assert [item.name for item in view.items] == ["Low (default)", "High"]


def test_terminal_model_popup_controller_owns_runtime_session_state() -> None:
    # Rust owner: chatwidget::model_popups owns the /model popup session state
    # and applies selection actions; codex-tui::tui only schedules the view.
    runtime = SimpleNamespace(
        session_config=SimpleNamespace(
            model="gpt-5.4",
            model_reasoning_effort="low",
            available_models=(
                SimpleNamespace(
                    model="gpt-5.4",
                    description="Strong model",
                    default_reasoning_effort="medium",
                    supported_reasoning_efforts=(
                        SimpleNamespace(effort="low", description="Fast"),
                        SimpleNamespace(effort="medium", description="Balanced"),
                    ),
                ),
            ),
        )
    )
    dispatched = []
    app_runtime = SimpleNamespace(active_thread_runtime=runtime, handle_app_event=dispatched.append)
    controller = TerminalModelPopupController(app_runtime)

    model_view = controller.open_view()
    assert model_view is not None
    assert model_view.header[0] == "Select Model and Effort"

    reasoning_view = controller.handle_events(tuple(model_view.items[0].actions))
    assert reasoning_view is not None
    assert reasoning_view.header == "Select Reasoning Level for gpt-5.4"

    controller.handle_events(tuple(reasoning_view.items[1].actions))

    assert [event.kind for event in dispatched] == [
        "UpdateModel",
        "UpdateReasoningEffort",
        "PersistModelSelection",
    ]
    assert controller.context is not None
    assert controller.context.current_model == "gpt-5.4"
    assert controller.context.effective_reasoning_effort is ReasoningEffortConfig.Medium


def test_model_picker_view_projects_through_chatwidget_rendering_buffer() -> None:
    # Rust owners: chatwidget::model_popups builds the /model picker,
    # bottom_pane::list_selection_view owns current-row terminal projection,
    # and chatwidget::rendering/custom_terminal consume the frame Buffer.  The
    # terminal runtime must not hand-render the model picker.
    result = open_model_popup_with_presets(
        ModelPopupContext(current_model="gpt-5.4"),
        [
            ModelPreset(
                model="gpt-5.4",
                description="Strong model",
                supported_reasoning_efforts=(
                    ReasoningEffortPreset(ReasoningEffortConfig.Low, "Fast"),
                    ReasoningEffortPreset(ReasoningEffortConfig.High, "Deep"),
                ),
            ),
            ModelPreset(
                model="gpt-5.4-mini",
                description="Small model",
                supported_reasoning_efforts=(
                    ReasoningEffortPreset(ReasoningEffortConfig.Medium, "Balanced"),
                ),
            ),
        ],
    )

    assert result.view is not None
    view = ListSelectionView.new(result.view, app_event_tx=[])
    popup_lines = tuple(view.terminal_lines(width=100))
    frame = terminal_bottom_pane_frame(
        os.terminal_size((100, 16)),
        TerminalBottomPaneState(
            draft="",
            footer_text="gpt-5.4 high",
            popup_lines=popup_lines,
        ),
    )
    buffer = terminal_bottom_pane_frame_buffer(os.terminal_size((100, 16)), frame)

    selected_writes = [write for write in frame.writes if write.selected]
    assert selected_writes
    assert selected_writes[0].text.startswith("> 1. * gpt-5.4")
    assert "Select Model and Effort" in buffer.plain()
    assert "Access legacy models" in buffer.plain()
    assert "2.   gpt-5.4-mini" in buffer.plain()
    assert buffer.cell(0, selected_writes[0].row - 1).style.fg == RatatuiColor.LightBlue


def test_reasoning_popup_view_projects_through_chatwidget_rendering_buffer() -> None:
    # Rust owners: chatwidget::model_popups builds the reasoning picker,
    # bottom_pane::list_selection_view owns selected-row terminal projection,
    # and chatwidget::rendering/custom_terminal consume the frame Buffer.  The
    # terminal runtime must not special-case this UI path.
    preset = ModelPreset(
        model="gpt-5.4",
        default_reasoning_effort=ReasoningEffortConfig.Medium,
        supported_reasoning_efforts=(
            ReasoningEffortPreset(ReasoningEffortConfig.Low, "Fast"),
            ReasoningEffortPreset(ReasoningEffortConfig.Medium, "Balanced"),
            ReasoningEffortPreset(ReasoningEffortConfig.High, "Deep"),
        ),
    )
    result = open_reasoning_popup(
        ModelPopupContext(
            current_model="gpt-5.4",
            effective_reasoning_effort=ReasoningEffortConfig.Low,
        ),
        preset,
    )

    assert result.view is not None
    view = ListSelectionView.new(result.view, app_event_tx=[])
    popup_lines = tuple(view.terminal_lines(width=100))
    frame = terminal_bottom_pane_frame(
        os.terminal_size((100, 16)),
        TerminalBottomPaneState(
            draft="",
            footer_text="gpt-5.4 low",
            popup_lines=popup_lines,
        ),
    )
    buffer = terminal_bottom_pane_frame_buffer(os.terminal_size((100, 16)), frame)

    plain = buffer.plain_lines()
    assert "Select Reasoning Level for gpt-5.4" in plain[1]
    assert "> 1. * Low" in plain[2]
    assert "2.   Medium (default)" in plain[3]
    assert "3.   High" in plain[4]
    assert buffer.cell(0, frame.writes[2].row - 1).style.fg == RatatuiColor.LightBlue
