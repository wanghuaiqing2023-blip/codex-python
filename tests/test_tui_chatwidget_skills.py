from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.skills import (
    AppInfo,
    ProtocolSkillMetadata,
    SkillMetadata,
    SkillsListEntry,
    ToolMentions,
    app_id_from_path,
    collect_tool_mentions,
    enabled_skills_for_mentions,
    extract_tool_mentions_from_text,
    find_app_mentions,
    find_skill_mentions_with_tool_mentions,
    handle_manage_skills_closed,
    is_skill_path,
    normalize_skill_path,
    open_manage_skills_popup,
    open_skills_list,
    open_skills_menu,
    parse_linked_tool_mention,
    protocol_skill_to_core,
    set_skills_from_response,
    skills_for_cwd,
    update_skill_enabled,
)


def test_collect_tool_mentions_parses_plain_and_linked_mentions_skipping_env_vars() -> None:
    mention_paths = {"docs": "skill:///skills/docs/SKILL.md", "drive": "app://google_drive"}

    mentions = collect_tool_mentions("$docs $PATH [$drive](app://google_drive) [$other](skill://x)", mention_paths)

    assert mentions.names == {"docs", "other"}
    assert mentions.linked_paths == {
        "drive": "app://google_drive",
        "other": "skill://x",
        "docs": "skill:///skills/docs/SKILL.md",
    }


def test_linked_tool_mention_parser_and_path_helpers_match_rust_rules() -> None:
    text = "[$skill-name]   ( skill://abc/SKILL.md )"

    assert parse_linked_tool_mention(text, 0) == ("skill-name", "skill://abc/SKILL.md", len(text))
    assert is_skill_path("skill://abc")
    assert not is_skill_path("app://abc")
    assert normalize_skill_path("skill://abc") == "abc"
    assert app_id_from_path("app://linear") == "linear"
    assert app_id_from_path("skill://linear") is None


def test_find_skill_mentions_prefers_bound_paths_then_names_and_dedupes() -> None:
    skills = [
        SkillMetadata(name="docs", path_to_skills_md="/skills/docs/SKILL.md"),
        SkillMetadata(name="docs", path_to_skills_md="/skills/docs2/SKILL.md"),
        SkillMetadata(name="code", path_to_skills_md="/skills/code/SKILL.md"),
    ]
    mentions = ToolMentions(
        names={"docs", "code"},
        linked_paths={"alias": "skill:///skills/code/SKILL.md"},
    )

    found = find_skill_mentions_with_tool_mentions(mentions, skills)

    assert [skill.path_to_skills_md for skill in found] == [
        "/skills/code/SKILL.md",
        "/skills/docs/SKILL.md",
    ]


def test_find_app_mentions_requires_accessible_enabled_apps_for_slugs_and_bound_paths() -> None:
    apps = [
        AppInfo("google_drive", "Google Drive"),
        AppInfo("arabica_uae", "% Arabica UAE", is_accessible=False),
        AppInfo("linear", "Linear", is_enabled=False),
    ]

    mentions = collect_tool_mentions("$google-drive $arabica-uae $linear", {})
    assert find_app_mentions(mentions, apps, set()) == [apps[0]]

    mentions = collect_tool_mentions(
        "$google-drive $arabica-uae $linear",
        {
            "google-drive": "app://google_drive",
            "arabica-uae": "app://arabica_uae",
            "linear": "app://linear",
        },
    )
    assert find_app_mentions(mentions, apps, set()) == [apps[0]]


def test_find_app_mentions_rejects_ambiguous_slug_and_skill_name_collision() -> None:
    apps = [AppInfo("a1", "Same App"), AppInfo("a2", "Same App"), AppInfo("s", "Docs")]

    mentions = extract_tool_mentions_from_text("$same-app $docs")

    assert find_app_mentions(mentions, apps, {"docs"}) == []


def test_skill_response_mapping_and_enabled_mentions() -> None:
    skill = ProtocolSkillMetadata(name="docs", path="/repo/SKILL.md", enabled=True, description="Long")
    disabled = ProtocolSkillMetadata(name="off", path="/off/SKILL.md", enabled=False)
    entries = [SkillsListEntry(cwd="/repo", skills=(skill, disabled))]

    assert skills_for_cwd("/repo", entries) == [skill, disabled]
    assert skills_for_cwd("/other", entries) == []
    assert protocol_skill_to_core(skill).name == "docs"
    assert [core.name for core in enabled_skills_for_mentions([skill, disabled])] == ["docs"]


class Pane:
    def __init__(self) -> None:
        self.selection = None
        self.view = None

    def show_selection_view(self, params) -> None:
        self.selection = params

    def show_view(self, view) -> None:
        self.view = view


class Features:
    def __init__(self, mentions_v2: bool = False) -> None:
        self.mentions_v2 = mentions_v2

    def enabled(self, feature: str) -> bool:
        return feature == "MentionsV2" and self.mentions_v2


class Widget:
    def __init__(self) -> None:
        self.inserted = ""
        self.bottom_pane = Pane()
        self.config = SimpleNamespace(cwd="/repo", features=Features())
        self.skills_all = []
        self.skills_initial_state = None
        self.info_messages = []
        self.set_skills_value = None

    def insert_str(self, value: str) -> None:
        self.inserted += value

    def add_info_message(self, message, hint=None) -> None:
        self.info_messages.append((message, hint))

    def set_skills(self, skills) -> None:
        self.set_skills_value = skills


def test_widget_skill_menu_manage_update_and_close_semantics() -> None:
    widget = Widget()

    open_skills_list(widget)
    assert widget.inserted == "$"
    widget.config.features = Features(mentions_v2=True)
    open_skills_list(widget)
    assert widget.inserted == "$@"

    menu = open_skills_menu(widget)
    assert menu.title == "Skills"
    assert widget.bottom_pane.selection is menu

    assert open_manage_skills_popup(widget) is None
    assert widget.info_messages == [("No skills available.", None)]

    skill = ProtocolSkillMetadata(name="docs", path="/repo/SKILL.md", enabled=True)
    widget.skills_all = [skill]
    view = open_manage_skills_popup(widget)
    assert view.items[0].skill_name == "docs"
    assert widget.skills_initial_state == {"/repo/SKILL.md": True}

    update_skill_enabled(widget, "/repo/SKILL.md", False)
    assert widget.skills_all[0].enabled is False
    assert widget.set_skills_value == []

    handle_manage_skills_closed(widget)
    assert widget.info_messages[-1] == ("0 skills enabled, 1 skills disabled", None)


def test_set_skills_from_response_updates_all_and_enabled_mentions() -> None:
    widget = Widget()
    skill = ProtocolSkillMetadata(name="docs", path="/repo/SKILL.md", enabled=True)

    set_skills_from_response(widget, {"data": [SkillsListEntry(cwd="/repo", skills=(skill,))]})

    assert widget.skills_all == [skill]
    assert widget.set_skills_value[0].name == "docs"
