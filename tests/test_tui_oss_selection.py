import asyncio

from pycodex.tui.oss_selection import (
    LMSTUDIO_OSS_PROVIDER_ID,
    OLLAMA_OSS_PROVIDER_ID,
    OSS_SELECT_OPTIONS,
    OssProviderSelection,
    OssSelectionWidget,
    ProviderStatus,
    check_lmstudio_status,
    check_ollama_status,
    ctrl_h_l_move_provider_selection,
    get_status_symbol_and_color,
    run_oss_selection_widget,
    render_ref,
    select_oss_provider,
)


def run(coro):
    return asyncio.run(coro)


def test_ctrl_h_l_move_provider_selection_matches_rust():
    widget = OssSelectionWidget.new(ProviderStatus.UNKNOWN, ProviderStatus.UNKNOWN)

    assert widget.selected_option == 0
    widget.handle_key_event({"code": "l", "modifiers": {"CONTROL"}})
    assert widget.selected_option == 1
    widget.handle_key_event({"code": "h", "modifiers": {"CONTROL"}})
    assert widget.selected_option == 0
    assert ctrl_h_l_move_provider_selection() == (0, 1, 0)


def test_arrow_navigation_wraps_and_release_events_are_ignored():
    widget = OssSelectionWidget.new("unknown", "unknown")

    widget.handle_key_event("left")
    assert widget.selected_option == 1
    widget.handle_key_event({"code": "right", "kind": "release"})
    assert widget.selected_option == 1
    widget.handle_key_event({"code": "right", "kind": "repeat"})
    assert widget.selected_option == 1
    widget.handle_key_event("right")
    assert widget.selected_option == 0


def test_enter_escape_cancel_and_letter_shortcuts_select_expected_provider():
    enter_widget = OssSelectionWidget.new("unknown", "unknown")
    enter_widget.handle_key_event("right")
    assert enter_widget.handle_key_event("enter") == OLLAMA_OSS_PROVIDER_ID
    assert enter_widget.is_complete()

    escape_widget = OssSelectionWidget.new("unknown", "unknown")
    assert escape_widget.handle_key_event("esc") == LMSTUDIO_OSS_PROVIDER_ID

    cancel_widget = OssSelectionWidget.new("unknown", "unknown")
    assert cancel_widget.handle_key_event({"code": "c", "modifiers": {"CONTROL"}}) == "__CANCELLED__"

    letter_widget = OssSelectionWidget.new("unknown", "unknown")
    assert letter_widget.handle_key_event("O") == OLLAMA_OSS_PROVIDER_ID


def test_options_and_desired_height_match_source_shape():
    widget = OssSelectionWidget.new(ProviderStatus.RUNNING, ProviderStatus.NOT_RUNNING)

    assert [option.provider_id for option in OSS_SELECT_OPTIONS] == [LMSTUDIO_OSS_PROVIDER_ID, OLLAMA_OSS_PROVIDER_ID]
    assert widget.get_confirmation_prompt_height(80) == len(widget.confirmation_prompt_lines())
    assert widget.desired_height(80) == len(widget.confirmation_prompt_lines()) + len(widget.select_options)
    rendered = render_ref(widget)
    assert "? Select an open-source provider" in rendered
    assert "Select provider?" in rendered
    assert "Local LM Studio server (default port 1234)" in rendered[-1]


def test_status_symbol_and_color_semantics():
    assert get_status_symbol_and_color(ProviderStatus.RUNNING) == ("*", "green")
    assert get_status_symbol_and_color(ProviderStatus.NOT_RUNNING) == ("x", "red")
    assert get_status_symbol_and_color(ProviderStatus.UNKNOWN) == ("?", "yellow")


def test_select_oss_provider_autoselects_when_only_one_provider_runs():
    assert run(select_oss_provider(lmstudio_status="running", ollama_status="not_running")) == OssProviderSelection(
        LMSTUDIO_OSS_PROVIDER_ID,
        manually_selected=False,
    )
    assert run(select_oss_provider(lmstudio_status="not_running", ollama_status="running")) == OssProviderSelection(
        OLLAMA_OSS_PROVIDER_ID,
        manually_selected=False,
    )


def test_select_oss_provider_manual_ui_uses_semantic_event_loop_and_marks_manual_selection():
    async def runner(widget):
        widget.handle_key_event("o")
        return widget.selection

    assert run(select_oss_provider(lmstudio_status="unknown", ollama_status="unknown")) == OssProviderSelection(
        LMSTUDIO_OSS_PROVIDER_ID,
        manually_selected=True,
    )
    assert run(
        select_oss_provider(
            lmstudio_status="unknown",
            ollama_status="unknown",
            selection_events=["right", "enter"],
        )
    ) == OssProviderSelection(
        OLLAMA_OSS_PROVIDER_ID,
        manually_selected=True,
    )
    assert run(select_oss_provider(lmstudio_status="unknown", ollama_status="unknown", selection_runner=runner)) == OssProviderSelection(
        OLLAMA_OSS_PROVIDER_ID,
        manually_selected=True,
    )

    widget = OssSelectionWidget.new("unknown", "unknown")
    assert run_oss_selection_widget(widget, ["o"]) == OLLAMA_OSS_PROVIDER_ID


def test_status_helpers_map_port_probe_results(monkeypatch):
    import pycodex.tui.oss_selection as mod

    async def true_probe(port):
        return True

    async def false_probe(port):
        return False

    async def raising_probe(port):
        raise OSError("boom")

    monkeypatch.setattr(mod, "check_port_status", true_probe)
    assert run(check_lmstudio_status()) is ProviderStatus.RUNNING
    monkeypatch.setattr(mod, "check_port_status", false_probe)
    assert run(check_ollama_status()) is ProviderStatus.NOT_RUNNING
    monkeypatch.setattr(mod, "check_port_status", raising_probe)
    assert run(check_lmstudio_status()) is ProviderStatus.UNKNOWN
