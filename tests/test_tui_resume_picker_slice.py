from __future__ import annotations

from dataclasses import dataclass

from pycodex.tui.resume_picker import (
    PICKER_LIST_HORIZONTAL_INSET,
    ProviderFilter,
    SessionFilterMode,
    SessionListDensity,
    SessionPickerAction,
    SessionTarget,
    ToolbarControl,
    from_,
    list_viewport_width,
    local_picker_cwd_filter,
    normalize_pasted_query,
    picker_cwd_filter,
    picker_provider_filter,
    raw_reasoning_visibility,
    sort_key_label,
)


@dataclass
class Config:
    model_provider_id: str = "openai"
    show_raw_agent_reasoning: bool = False


def test_session_target_display_label_prefers_path_then_thread_id() -> None:
    assert SessionTarget("/tmp/session.jsonl", "thread-1").display_label() == "/tmp/session.jsonl"
    assert SessionTarget(None, "thread-1").display_label() == "thread thread-1"


def test_session_picker_action_labels_and_selection() -> None:
    assert SessionPickerAction.RESUME.title() == "Resume a previous session"
    assert SessionPickerAction.RESUME.action_label() == "resume"
    assert SessionPickerAction.FORK.title() == "Fork a previous session"
    selection = SessionPickerAction.FORK.selection("/tmp/a.jsonl", "tid")
    assert selection.kind == "Fork"
    assert selection.target == SessionTarget("/tmp/a.jsonl", "tid")


def test_filter_mode_show_all_and_toggle_semantics() -> None:
    assert SessionFilterMode.from_show_all(False, "/repo") is SessionFilterMode.CWD
    assert SessionFilterMode.from_show_all(True, "/repo") is SessionFilterMode.ALL
    assert SessionFilterMode.from_show_all(False, None) is SessionFilterMode.ALL
    assert SessionFilterMode.CWD.toggle("/repo") is SessionFilterMode.ALL
    assert SessionFilterMode.ALL.toggle("/repo") is SessionFilterMode.CWD
    assert SessionFilterMode.ALL.toggle(None) is SessionFilterMode.ALL


def test_toolbar_and_density_toggle() -> None:
    assert ToolbarControl.FILTER.next() is ToolbarControl.SORT
    assert ToolbarControl.SORT.previous() is ToolbarControl.FILTER
    assert SessionListDensity.COMFORTABLE.toggle() is SessionListDensity.DENSE
    assert from_("dense") is SessionListDensity.DENSE


def test_picker_filter_helpers() -> None:
    assert raw_reasoning_visibility(Config(show_raw_agent_reasoning=True)) == "Visible"
    assert raw_reasoning_visibility(Config(show_raw_agent_reasoning=False)) == "Hidden"
    assert local_picker_cwd_filter("/repo", False) == "/repo"
    assert local_picker_cwd_filter("/repo", True) is None
    assert picker_provider_filter(Config("openai"), False) == ProviderFilter.match_default("openai")
    assert picker_provider_filter(Config("openai"), True) == ProviderFilter.any()
    assert picker_cwd_filter("/local", False, False, None) == "/local"
    assert picker_cwd_filter("/local", False, True, "/remote") == "/remote"
    assert picker_cwd_filter("/local", True, True, "/remote") is None


def test_query_sort_and_viewport_helpers() -> None:
    assert normalize_pasted_query("  alpha\n\tbeta\r\n gamma  ") == "alpha beta gamma"
    assert normalize_pasted_query("  \n\t  ") is None
    assert sort_key_label("CreatedAt") == "Created"
    assert sort_key_label("UpdatedAt") == "Updated"
    assert list_viewport_width(80) == 80 - (PICKER_LIST_HORIZONTAL_INSET * 2)
    assert list_viewport_width(4) == 0
