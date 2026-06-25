from dataclasses import dataclass

from pycodex.tui.bottom_pane.mentions_v2.candidate import MentionType, Selection
from pycodex.tui.bottom_pane.mentions_v2.search_catalog import build_search_catalog
from pycodex.tui.bottom_pane.mentions_v2.search_catalog import optional_skill_description
from pycodex.tui.bottom_pane.mentions_v2.search_catalog import plugin_candidate
from pycodex.tui.bottom_pane.mentions_v2.search_catalog import plugin_capability_labels
from pycodex.tui.bottom_pane.mentions_v2.search_catalog import plugin_description
from pycodex.tui.bottom_pane.mentions_v2.search_catalog import skill_candidate


@dataclass
class Skill:
    name: str
    display_name: str | None = None
    description: str | None = None
    path_to_skills_md: str = "skills/demo/SKILL.md"


@dataclass
class Plugin:
    config_name: str
    display_name: str
    description: str | None = None
    has_skills: bool = False
    mcp_server_names: tuple[str, ...] = ()
    app_connector_ids: tuple[str, ...] = ()


def test_build_search_catalog_preserves_skill_then_plugin_order_and_handles_none():
    skill = Skill(name="writer", display_name="Writer")
    plugin = Plugin(config_name="tools@market", display_name="Tools")
    candidates = build_search_catalog([skill], [plugin])
    assert [candidate.mention_type for candidate in candidates] == [MentionType.SKILL, MentionType.PLUGIN]
    assert build_search_catalog(None, None) == []


def test_skill_candidate_uses_display_name_description_terms_and_tool_selection():
    candidate = skill_candidate(Skill(name="writer", display_name="Writer", description="  Helps write  ", path_to_skills_md="/tmp/SKILL.md"))
    assert candidate.display_name == "Writer"
    assert candidate.description == "Helps write"
    assert candidate.search_terms == ["writer", "Writer"]
    assert candidate.mention_type is MentionType.SKILL
    assert candidate.selection == Selection.Tool("$writer", path="/tmp/SKILL.md")


def test_skill_candidate_omits_duplicate_display_name_and_blank_description():
    candidate = skill_candidate(Skill(name="writer", display_name="writer", description="   "))
    assert candidate.search_terms == ["writer"]
    assert candidate.description is None
    assert optional_skill_description({"description": "\n"}) is None


def test_plugin_candidate_splits_marketplace_name_and_builds_terms_selection():
    candidate = plugin_candidate(Plugin(config_name="plugin-name@marketplace", display_name="Plugin Display", description="Desc"))
    assert candidate.display_name == "Plugin Display"
    assert candidate.description == "Desc"
    assert candidate.search_terms == ["plugin-name", "plugin-name@marketplace", "Plugin Display", "marketplace"]
    assert candidate.mention_type is MentionType.PLUGIN
    assert candidate.selection == Selection.Tool("$plugin-name", path="plugin://plugin-name@marketplace")


def test_plugin_candidate_without_marketplace_or_display_alias_terms():
    candidate = plugin_candidate(Plugin(config_name="plugin-name", display_name="plugin-name"))
    assert candidate.search_terms == ["plugin-name", "plugin-name"]
    assert candidate.selection.insert_text == "$plugin-name"


def test_plugin_description_prefers_explicit_description():
    plugin = Plugin(config_name="p", display_name="P", description="Custom", has_skills=True, mcp_server_names=("m",))
    assert plugin_description(plugin) == "Custom"


def test_plugin_capability_labels_and_fallback_descriptions():
    assert plugin_capability_labels(Plugin(config_name="p", display_name="P", has_skills=True)) == ["skills"]
    assert plugin_capability_labels(Plugin(config_name="p", display_name="P", mcp_server_names=("one",))) == ["1 MCP server"]
    assert plugin_capability_labels(Plugin(config_name="p", display_name="P", mcp_server_names=("one", "two"))) == ["2 MCP servers"]
    assert plugin_capability_labels(Plugin(config_name="p", display_name="P", app_connector_ids=("one",))) == ["1 app"]
    assert plugin_capability_labels(Plugin(config_name="p", display_name="P", app_connector_ids=("one", "two"))) == ["2 apps"]
    plugin = Plugin(config_name="p", display_name="P", has_skills=True, mcp_server_names=("m1", "m2"), app_connector_ids=("a",))
    assert plugin_description(plugin) == "Plugin - skills - 2 MCP servers - 1 app"
    assert plugin_description(Plugin(config_name="p", display_name="P")) == "Plugin"
