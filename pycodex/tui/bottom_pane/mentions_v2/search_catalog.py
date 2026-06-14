"""Search catalog construction for Rust bottom_pane/mentions_v2/search_catalog.rs."""

from __future__ import annotations

from typing import Any, Iterable

from ..._porting import RustTuiModule
from .candidate import Candidate, MentionType, Selection

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2::search_catalog",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/search_catalog.rs",
)


def build_search_catalog(skills: Iterable[Any] | None, plugins: Iterable[Any] | None) -> list[Candidate]:
    candidates: list[Candidate] = []
    if skills is not None:
        candidates.extend(skill_candidate(skill) for skill in skills)
    if plugins is not None:
        candidates.extend(plugin_candidate(plugin) for plugin in plugins)
    return candidates


def skill_candidate(skill: Any) -> Candidate:
    display_name = skill_display_name(skill)
    description = optional_skill_description(skill)
    skill_name = str(_get(skill, "name", ""))
    search_terms = [skill_name] if display_name == skill_name else [skill_name, display_name]
    return Candidate(
        display_name=display_name,
        description=description,
        search_terms=search_terms,
        mention_type=MentionType.SKILL,
        selection=Selection.Tool(insert_text="$" + skill_name, path=str(_get(skill, "path_to_skills_md", ""))),
    )


def plugin_candidate(plugin: Any) -> Candidate:
    config_name = str(_get(plugin, "config_name", ""))
    plugin_name, marketplace_name = _split_once(config_name, "@")
    display_name = str(_get(plugin, "display_name", plugin_name))
    search_terms = [plugin_name, config_name]
    if display_name != plugin_name:
        search_terms.append(display_name)
    if marketplace_name:
        search_terms.append(marketplace_name)
    return Candidate(
        display_name=display_name,
        description=plugin_description(plugin),
        search_terms=search_terms,
        mention_type=MentionType.PLUGIN,
        selection=Selection.Tool(insert_text="$" + plugin_name, path="plugin://" + config_name),
    )


def plugin_description(plugin: Any) -> str | None:
    description = _get(plugin, "description", None)
    if description is not None:
        return str(description)
    labels = plugin_capability_labels(plugin)
    if not labels:
        return "Plugin"
    return "Plugin - " + " - ".join(labels)


def plugin_capability_labels(plugin: Any) -> list[str]:
    labels: list[str] = []
    if bool(_get(plugin, "has_skills", False)):
        labels.append("skills")
    mcp_server_names = list(_get(plugin, "mcp_server_names", []) or [])
    if mcp_server_names:
        count = len(mcp_server_names)
        labels.append("1 MCP server" if count == 1 else f"{count} MCP servers")
    app_connector_ids = list(_get(plugin, "app_connector_ids", []) or [])
    if app_connector_ids:
        count = len(app_connector_ids)
        labels.append("1 app" if count == 1 else f"{count} apps")
    return labels


def optional_skill_description(skill: Any) -> str | None:
    description = skill_description(skill).strip()
    return description if description else None


def skill_display_name(skill: Any) -> str:
    value = _get(skill, "display_name", None)
    if value is None or str(value) == "":
        value = _get(skill, "name", "")
    return str(value)


def skill_description(skill: Any) -> str:
    value = _get(skill, "description", "")
    return "" if value is None else str(value)


def _split_once(value: str, sep: str) -> tuple[str, str]:
    if sep not in value:
        return value, ""
    left, right = value.split(sep, 1)
    return left, right


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


__all__ = [
    "RUST_MODULE",
    "build_search_catalog",
    "optional_skill_description",
    "plugin_candidate",
    "plugin_capability_labels",
    "plugin_description",
    "skill_candidate",
    "skill_description",
    "skill_display_name",
]
