from pycodex.tui.bottom_pane.skills_toggle_view import SEARCH_PLACEHOLDER
from pycodex.tui.bottom_pane.skills_toggle_view import SEARCH_PROMPT_PREFIX
from pycodex.tui.bottom_pane.skills_toggle_view import SkillsToggleItem
from pycodex.tui.bottom_pane.skills_toggle_view import SkillsToggleView
from pycodex.tui.bottom_pane.skills_toggle_view import match_skill
from pycodex.tui.bottom_pane.skills_toggle_view import skills_toggle_hint_line
from pycodex.tui.bottom_pane.skills_toggle_view import truncate_skill_name


def _items():
    return [
        SkillsToggleItem("Repo Scout", "repo_scout", "Summarize the repo layout", True, "/tmp/repo.toml"),
        SkillsToggleItem("Changelog Writer", "changelog_writer", "Draft release notes", False, "/tmp/change.toml"),
        SkillsToggleItem("Bug Hunter", "bug_hunter", "Find likely bugs", False, "/tmp/bug.toml"),
    ]


def test_new_applies_empty_filter_and_initial_selection():
    view = SkillsToggleView.new(_items())

    assert view.filtered_indices == [0, 1, 2]
    assert view.selected_idx == 0
    assert view.visible_len() == 3
    assert view.max_visible_rows(0) == 1


def test_build_rows_uses_selection_enabled_marker_and_truncation():
    item = SkillsToggleItem("Very Long Skill Name That Exceeds Limit", "long_skill", "Long desc", True, "/tmp/long")
    view = SkillsToggleView.new([item])

    rows = view.build_rows()

    assert rows[0].name == f"> [x] {truncate_skill_name(item.name)}"
    assert rows[0].description == "Long desc"
    assert rows[0].selected is True
    assert rows[0].name.endswith(".")


def test_filter_matches_display_name_then_skill_name_and_preserves_selection():
    view = SkillsToggleView.new(_items())
    view.move_down()
    assert view.selected_idx == 1

    view.search_query = "cw"
    view.apply_filter()
    assert view.filtered_indices == [1]
    assert view.selected_idx == 0

    view.search_query = "bughunter"
    view.apply_filter()
    assert view.filtered_indices == [2]
    assert match_skill("repo", "Different", "repo_scout")[0] is None


def test_navigation_page_jump_and_plain_character_search_behavior():
    view = SkillsToggleView.new(_items())

    view.move_up()
    assert view.selected_idx == 2
    view.move_down()
    assert view.selected_idx == 0

    view.handle_key_event("j")
    assert view.search_query == "j"
    assert view.selected_idx is None

    view.handle_key_event("backspace")
    assert view.search_query == ""
    assert view.selected_idx == 0

    view.page_down()
    assert view.selected_idx == 2
    view.jump_top()
    assert view.selected_idx == 0


def test_toggle_selected_sends_set_skill_enabled_event():
    events = []
    view = SkillsToggleView.new(_items(), events)

    view.toggle_selected()

    assert view.items[0].enabled is False
    assert events == [{"type": "SetSkillEnabled", "path": "/tmp/repo.toml", "enabled": False}]


def test_close_is_idempotent_and_triggers_manage_closed_and_reload():
    events = []
    view = SkillsToggleView.new(_items(), events)

    assert view.on_ctrl_c() == "Handled"
    view.close()

    assert view.is_complete()
    assert events == [
        {"type": "ManageSkillsClosed"},
        {"type": "ListSkills", "args": [], "force_reload": True},
    ]


def test_rows_width_height_hint_and_render_empty_state():
    assert SkillsToggleView.rows_width(1) == 0
    assert SkillsToggleView.rows_width(10) == 8
    assert skills_toggle_hint_line() == "Press Space to toggle"

    view = SkillsToggleView.new([])
    assert view.rows_height([]) == 1
    lines = view.render((0, 0, 60, 10))
    assert lines[0].text == "Enable/Disable Skills"
    assert lines[3].text == SEARCH_PLACEHOLDER
    assert lines[4].text == SEARCH_PROMPT_PREFIX
    assert any(line.text == "no matches" for line in lines)


def test_handle_key_event_accept_cancel_and_modified_navigation_semantics():
    events = []
    view = SkillsToggleView.new(_items(), events)

    view.handle_key_event({"key": "down"})
    assert view.selected_idx == 1
    view.handle_key_event({"key": "enter"})
    assert view.items[1].enabled is True
    assert events[-1] == {"type": "SetSkillEnabled", "path": "/tmp/change.toml", "enabled": True}

    view.handle_key_event({"key": "esc"})
    assert view.is_complete()
    assert events[-2:] == [
        {"type": "ManageSkillsClosed"},
        {"type": "ListSkills", "args": [], "force_reload": True},
    ]
