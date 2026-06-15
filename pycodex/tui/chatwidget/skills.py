"""Skill and app mention helpers for the chat widget.

This mirrors Rust ``codex-tui::chatwidget::skills`` with standard-library
semantic DTOs.  UI methods return selection/toggle models and event records
instead of ratatui views or boxed event-channel closures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::skills",
    source="codex/codex-rs/tui/src/chatwidget/skills.rs",
    status="complete",
)

TOOL_MENTION_SIGIL = "$"
COMMON_ENV_VARS = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "PWD",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "TERM",
    "XDG_CONFIG_HOME",
}


@dataclass(frozen=True)
class SkillInterface:
    display_name: Optional[str] = None
    short_description: Optional[str] = None
    icon_small: Optional[str] = None
    icon_large: Optional[str] = None
    brand_color: Optional[str] = None
    default_prompt: Optional[str] = None


@dataclass(frozen=True)
class SkillToolDependency:
    type: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    transport: Optional[str] = None
    command: Optional[str] = None
    url: Optional[str] = None


@dataclass(frozen=True)
class SkillDependencies:
    tools: Tuple[SkillToolDependency, ...] = ()


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    interface: Optional[SkillInterface] = None
    dependencies: Optional[SkillDependencies] = None
    path_to_skills_md: str = ""
    scope: Optional[Any] = None
    plugin_id: Optional[str] = None


@dataclass(frozen=True)
class ProtocolSkillMetadata:
    name: str
    path: str
    enabled: bool = True
    description: Optional[str] = None
    short_description: Optional[str] = None
    interface: Optional[Any] = None
    dependencies: Optional[Any] = None
    scope: Optional[Any] = None


@dataclass(frozen=True)
class SkillsListEntry:
    cwd: str
    skills: Tuple[ProtocolSkillMetadata, ...] = ()


@dataclass(frozen=True)
class SkillsListResponse:
    data: Tuple[SkillsListEntry, ...] = ()


@dataclass(frozen=True)
class AppInfo:
    id: str
    name: str
    is_accessible: bool = True
    is_enabled: bool = True
    description: Optional[str] = None


@dataclass(frozen=True)
class SelectionItem:
    name: str
    description: Optional[str] = None
    actions: Tuple[Tuple[str, Any], ...] = ()
    dismiss_on_select: bool = False


@dataclass(frozen=True)
class SelectionViewParams:
    title: str
    subtitle: Optional[str] = None
    items: Tuple[SelectionItem, ...] = ()
    footer_hint: Optional[str] = "Enter to select, Esc to cancel"


@dataclass(frozen=True)
class SkillsToggleItem:
    name: str
    skill_name: str
    description: str
    enabled: bool
    path: str


@dataclass(frozen=True)
class SkillsToggleView:
    items: tuple[SkillsToggleItem, ...]


@dataclass
class ToolMentions:
    names: Set[str] = field(default_factory=set)
    linked_paths: Dict[str, str] = field(default_factory=dict)


def open_skills_list(widget: Any) -> None:
    sigil = "@" if widget.config.features.enabled("MentionsV2") else "$"
    widget.insert_str(sigil)


def open_skills_menu(widget: Any) -> SelectionViewParams:
    params = SelectionViewParams(
        title="Skills",
        subtitle="Choose an action",
        items=(
            SelectionItem(
                name="List skills",
                description="Tip: press $ to open this list directly.",
                actions=(("OpenSkillsList", None),),
                dismiss_on_select=True,
            ),
            SelectionItem(
                name="Enable/Disable Skills",
                description="Enable or disable skills.",
                actions=(("OpenManageSkillsPopup", None),),
                dismiss_on_select=True,
            ),
        ),
    )
    widget.bottom_pane.show_selection_view(params)
    return params


def open_manage_skills_popup(widget: Any) -> Optional[SkillsToggleView]:
    if not widget.skills_all:
        widget.add_info_message("No skills available.", None)
        return None
    widget.skills_initial_state = {skill.path: skill.enabled for skill in widget.skills_all}
    items = []
    for skill in widget.skills_all:
        core = protocol_skill_to_core(skill)
        if core is None:
            continue
        items.append(
            SkillsToggleItem(
                name=skill_display_name(core),
                skill_name=core.name,
                description=skill_description(core),
                enabled=skill.enabled,
                path=core.path_to_skills_md,
            )
        )
    view = SkillsToggleView(tuple(items))
    widget.bottom_pane.show_view(view)
    return view


def update_skill_enabled(widget: Any, path: str, enabled: bool) -> None:
    for index, skill in enumerate(widget.skills_all):
        if skill.path == path:
            widget.skills_all[index] = _replace_protocol_skill_enabled(skill, enabled)
    widget.set_skills(enabled_skills_for_mentions(widget.skills_all))


def handle_manage_skills_closed(widget: Any) -> None:
    initial_state = getattr(widget, "skills_initial_state", None)
    if initial_state is None:
        return
    widget.skills_initial_state = None
    current_state = {skill.path: skill.enabled for skill in widget.skills_all}
    enabled_count = 0
    disabled_count = 0
    for path, was_enabled in initial_state.items():
        if path not in current_state:
            continue
        if was_enabled != current_state[path]:
            if current_state[path]:
                enabled_count += 1
            else:
                disabled_count += 1
    if enabled_count or disabled_count:
        widget.add_info_message(
            f"{enabled_count} skills enabled, {disabled_count} skills disabled", None
        )


def set_skills_from_response(widget: Any, response: Any) -> None:
    skills = skills_for_cwd(widget.config.cwd, _get(response, "data", ()))
    widget.skills_all = skills
    widget.set_skills(enabled_skills_for_mentions(skills))


def annotate_skill_reads_in_parsed_cmd(widget: Any, parsed_cmd: List[Any]) -> List[Any]:
    if not widget.skills_all:
        return parsed_cmd
    skill_by_path = {skill.path: skill.name for skill in widget.skills_all}
    result = []
    for parsed in parsed_cmd:
        if _get(parsed, "kind", None) == "Read" and _get(parsed, "name", None) == "SKILL.md":
            path = _get(parsed, "path", None)
            if path in skill_by_path:
                result.append(_with_fields(parsed, name=f"SKILL.md ({skill_by_path[path]} skill)"))
                continue
        result.append(parsed)
    return result


def skills_for_cwd(cwd: str, skills_entries: Sequence[SkillsListEntry]) -> List[ProtocolSkillMetadata]:
    for entry in skills_entries:
        if _get(entry, "cwd") == cwd:
            return list(_get(entry, "skills", ()))
    return []


def enabled_skills_for_mentions(skills: Sequence[ProtocolSkillMetadata]) -> List[SkillMetadata]:
    return [
        core
        for skill in skills
        if _get(skill, "enabled", False)
        for core in [protocol_skill_to_core(skill)]
        if core is not None
    ]


def protocol_skill_to_core(skill: Any) -> Optional[SkillMetadata]:
    name = _get(skill, "name", None)
    path = _get(skill, "path", None)
    if not name or not path:
        return None
    return SkillMetadata(
        name=name,
        description=_get(skill, "description", None),
        short_description=_get(skill, "short_description", None),
        interface=_coerce_interface(_get(skill, "interface", None)),
        dependencies=_coerce_dependencies(_get(skill, "dependencies", None)),
        path_to_skills_md=path,
        scope=_get(skill, "scope", None),
        plugin_id=None,
    )


def collect_tool_mentions(text: str, mention_paths: Mapping[str, str]) -> ToolMentions:
    mentions = extract_tool_mentions_from_text(text)
    for name, path in mention_paths.items():
        if name in mentions.names:
            mentions.linked_paths.setdefault(name, path)
    return mentions


def find_skill_mentions_with_tool_mentions(
    mentions: ToolMentions, skills: Sequence[SkillMetadata]
) -> List[SkillMetadata]:
    mention_skill_paths = {
        normalize_skill_path(path)
        for path in mentions.linked_paths.values()
        if is_skill_path(path)
    }
    seen_names: Set[str] = set()
    seen_paths: Set[str] = set()
    matches: List[SkillMetadata] = []

    for skill in skills:
        if skill.path_to_skills_md in seen_paths:
            continue
        if skill.path_to_skills_md in mention_skill_paths:
            seen_paths.add(skill.path_to_skills_md)
            seen_names.add(skill.name)
            matches.append(skill)

    for skill in skills:
        if skill.path_to_skills_md in seen_paths:
            continue
        if skill.name in mentions.names and skill.name not in seen_names:
            seen_paths.add(skill.path_to_skills_md)
            seen_names.add(skill.name)
            matches.append(skill)

    return matches


def find_app_mentions(
    mentions: ToolMentions,
    apps: Sequence[AppInfo],
    skill_names_lower: Set[str],
) -> List[AppInfo]:
    explicit_names: Set[str] = set()
    selected_ids: Set[str] = set()
    for name, path in mentions.linked_paths.items():
        connector_id = app_id_from_path(path)
        if connector_id is not None:
            explicit_names.add(name)
            selected_ids.add(connector_id)

    slug_counts: Dict[str, int] = {}
    for app_info in apps:
        if is_app_mentionable(app_info):
            slug = connector_mention_slug(app_info)
            slug_counts[slug] = slug_counts.get(slug, 0) + 1

    for app_info in apps:
        if not is_app_mentionable(app_info):
            continue
        slug = connector_mention_slug(app_info)
        if (
            slug in mentions.names
            and slug not in explicit_names
            and slug_counts.get(slug, 0) == 1
            and slug not in skill_names_lower
        ):
            selected_ids.add(app_info.id)

    return [app_info for app_info in apps if is_app_mentionable(app_info) and app_info.id in selected_ids]


def is_app_mentionable(app: Any) -> bool:
    return bool(_get(app, "is_accessible", False) and _get(app, "is_enabled", False))


def extract_tool_mentions_from_text(text: str) -> ToolMentions:
    return extract_tool_mentions_from_text_with_sigil(text, TOOL_MENTION_SIGIL)


def extract_tool_mentions_from_text_with_sigil(text: str, sigil: str) -> ToolMentions:
    names: Set[str] = set()
    linked_paths: Dict[str, str] = {}
    index = 0
    while index < len(text):
        char = text[index]
        if char == "[":
            parsed = parse_linked_tool_mention(text, index, sigil)
            if parsed is not None:
                name, path, end_index = parsed
                if not is_common_env_var(name):
                    if is_skill_path(path):
                        names.add(name)
                    linked_paths.setdefault(name, path)
                index = end_index
                continue
        if char != sigil:
            index += 1
            continue
        name_start = index + 1
        if name_start >= len(text) or not is_mention_name_char(text[name_start]):
            index += 1
            continue
        name_end = name_start + 1
        while name_end < len(text) and is_mention_name_char(text[name_end]):
            name_end += 1
        name = text[name_start:name_end]
        if not is_common_env_var(name):
            names.add(name)
        index = name_end
    return ToolMentions(names, linked_paths)


def parse_linked_tool_mention(text: str, start: int, sigil: str = TOOL_MENTION_SIGIL) -> Optional[Tuple[str, str, int]]:
    if start + 1 >= len(text) or text[start + 1] != sigil:
        return None
    name_start = start + 2
    if name_start >= len(text) or not is_mention_name_char(text[name_start]):
        return None
    name_end = name_start + 1
    while name_end < len(text) and is_mention_name_char(text[name_end]):
        name_end += 1
    if name_end >= len(text) or text[name_end] != "]":
        return None
    path_start = name_end + 1
    while path_start < len(text) and text[path_start].isspace():
        path_start += 1
    if path_start >= len(text) or text[path_start] != "(":
        return None
    path_end = path_start + 1
    while path_end < len(text) and text[path_end] != ")":
        path_end += 1
    if path_end >= len(text) or text[path_end] != ")":
        return None
    path = text[path_start + 1 : path_end].strip()
    if not path:
        return None
    return text[name_start:name_end], path, path_end + 1


def is_common_env_var(name: str) -> bool:
    return name.upper() in COMMON_ENV_VARS


def is_mention_name_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char in {"_", "-"})


def is_skill_path(path: str) -> bool:
    return not (path.startswith("app://") or path.startswith("mcp://") or path.startswith("plugin://"))


def normalize_skill_path(path: str) -> str:
    return _strip_prefix(path, "skill://")


def app_id_from_path(path: str) -> Optional[str]:
    value = _strip_prefix(path, "app://")
    return value if value != path and value else None


def connector_mention_slug(app: Any) -> str:
    name = _get(app, "name")
    slug_chars = []
    previous_dash = False
    for char in name.lower():
        if char.isascii() and char.isalnum():
            slug_chars.append(char)
            previous_dash = False
        elif not previous_dash:
            slug_chars.append("-")
            previous_dash = True
    return "".join(slug_chars).strip("-")


def skill_display_name(skill: SkillMetadata) -> str:
    if skill.interface and skill.interface.display_name:
        return skill.interface.display_name
    return skill.name


def skill_description(skill: SkillMetadata) -> str:
    if skill.interface and skill.interface.short_description:
        return skill.interface.short_description
    return skill.short_description or skill.description or ""


def _coerce_interface(value: Optional[Any]) -> Optional[SkillInterface]:
    if value is None or isinstance(value, SkillInterface):
        return value
    return SkillInterface(**{field: value.get(field) for field in SkillInterface.__dataclass_fields__})


def _coerce_dependencies(value: Optional[Any]) -> Optional[SkillDependencies]:
    if value is None or isinstance(value, SkillDependencies):
        return value
    tools = tuple(
        tool if isinstance(tool, SkillToolDependency) else SkillToolDependency(**dict(tool))
        for tool in value.get("tools", ())
    )
    return SkillDependencies(tools=tools)


def _replace_protocol_skill_enabled(skill: ProtocolSkillMetadata, enabled: bool) -> ProtocolSkillMetadata:
    return ProtocolSkillMetadata(
        name=skill.name,
        path=skill.path,
        enabled=enabled,
        description=skill.description,
        short_description=skill.short_description,
        interface=skill.interface,
        dependencies=skill.dependencies,
        scope=skill.scope,
    )


def _with_fields(value: Any, **updates: Any) -> Any:
    if isinstance(value, Mapping):
        result = dict(value)
        result.update(updates)
        return result
    clone = value.__class__(**{**value.__dict__, **updates})
    return clone


def _get(value: Any, key: str, default: Any = ...):
    if isinstance(value, Mapping):
        if default is ...:
            return value[key]
        return value.get(key, default)
    if default is ...:
        return getattr(value, key)
    return getattr(value, key, default)


def _strip_prefix(value: str, prefix: str) -> str:
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value


__all__ = [
    "AppInfo",
    "RUST_MODULE",
    "SelectionItem",
    "SelectionViewParams",
    "SkillDependencies",
    "SkillInterface",
    "SkillMetadata",
    "SkillToolDependency",
    "SkillsListEntry",
    "SkillsListResponse",
    "SkillsToggleItem",
    "SkillsToggleView",
    "ToolMentions",
    "annotate_skill_reads_in_parsed_cmd",
    "app_id_from_path",
    "collect_tool_mentions",
    "connector_mention_slug",
    "enabled_skills_for_mentions",
    "extract_tool_mentions_from_text",
    "extract_tool_mentions_from_text_with_sigil",
    "find_app_mentions",
    "find_skill_mentions_with_tool_mentions",
    "handle_manage_skills_closed",
    "is_app_mentionable",
    "is_common_env_var",
    "is_mention_name_char",
    "is_skill_path",
    "normalize_skill_path",
    "open_manage_skills_popup",
    "open_skills_list",
    "open_skills_menu",
    "parse_linked_tool_mention",
    "protocol_skill_to_core",
    "set_skills_from_response",
    "skills_for_cwd",
    "update_skill_enabled",
]
