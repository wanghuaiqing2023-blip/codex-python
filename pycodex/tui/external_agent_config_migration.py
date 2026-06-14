"""Behavior port slice for Rust ``codex-tui::external_agent_config_migration``.

The Rust module owns the migration prompt state machine and ratatui rendering.
Python ports the module-local state transitions and semantic render rows; real TUI
frame/event integration remains an explicit runtime boundary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="external_agent_config_migration",
    source="codex/codex-rs/tui/src/external_agent_config_migration.rs",
)


class FocusArea(str, Enum):
    ITEMS = "items"
    ACTIONS = "actions"


class ActionMenuOption(str, Enum):
    PROCEED = "proceed"
    SKIP = "skip"
    SKIP_FOREVER = "skip_forever"

    def label(self) -> str:
        if self is ActionMenuOption.PROCEED:
            return "Proceed with selected"
        if self is ActionMenuOption.SKIP:
            return "Skip for now"
        return "Don't ask again"

    def previous(self) -> "ActionMenuOption | None":
        if self is ActionMenuOption.PROCEED:
            return None
        if self is ActionMenuOption.SKIP:
            return ActionMenuOption.PROCEED
        return ActionMenuOption.SKIP

    def next(self) -> "ActionMenuOption | None":
        if self is ActionMenuOption.PROCEED:
            return ActionMenuOption.SKIP
        if self is ActionMenuOption.SKIP:
            return ActionMenuOption.SKIP_FOREVER
        return None


@dataclass(frozen=True)
class ExternalAgentConfigMigrationOutcome:
    kind: str
    items: tuple[Any, ...] = ()

    @classmethod
    def Proceed(cls, items: Iterable[Any]) -> "ExternalAgentConfigMigrationOutcome":
        return cls("proceed", tuple(items))

    @classmethod
    def Skip(cls) -> "ExternalAgentConfigMigrationOutcome":
        return cls("skip")

    @classmethod
    def SkipForever(cls) -> "ExternalAgentConfigMigrationOutcome":
        return cls("skip_forever")

    @classmethod
    def Exit(cls) -> "ExternalAgentConfigMigrationOutcome":
        return cls("exit")


@dataclass(frozen=True)
class PluginsMigration:
    marketplace_name: str
    plugin_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class MigrationDetails:
    plugins: tuple[PluginsMigration, ...] = ()


@dataclass(frozen=True)
class ExternalAgentConfigMigrationItem:
    item_type: str = "config"
    description: str = ""
    cwd: str | Path | None = None
    details: MigrationDetails | None = None


@dataclass
class MigrationSelection:
    item: Any
    enabled: bool


class RenderLineKind(str, Enum):
    SECTION = "section"
    ITEM = "item"
    ITEM_DETAIL = "item_detail"


@dataclass(frozen=True)
class RenderLineEntry:
    item_idx: int | None
    kind: RenderLineKind
    text: str
    selected: bool = False


@dataclass
class FrameRequesterStub:
    scheduled: int = 0

    def schedule_frame(self) -> None:
        self.scheduled += 1


@dataclass
class ExternalAgentConfigMigrationScreen:
    request_frame: Any
    items: list[MigrationSelection]
    selected_item_idx: int | None = 0
    scroll_top: int = 0
    focus: FocusArea = FocusArea.ITEMS
    highlighted_action: ActionMenuOption = ActionMenuOption.PROCEED
    done: bool = False
    current_outcome: ExternalAgentConfigMigrationOutcome = field(default_factory=ExternalAgentConfigMigrationOutcome.Skip)
    error: str | None = None

    @classmethod
    def new(
        cls,
        request_frame: Any,
        items: Sequence[Any],
        selected_items: Sequence[Any],
        error: str | None = None,
    ) -> "ExternalAgentConfigMigrationScreen":
        selected = list(selected_items)
        selections = [MigrationSelection(item=item, enabled=item in selected) for item in items]
        return cls(
            request_frame=request_frame,
            items=selections,
            selected_item_idx=0 if selections else None,
            error=error,
        )

    def proceed_enabled(self) -> bool:
        return self.selected_count() > 0

    def first_available_action(self) -> ActionMenuOption:
        return ActionMenuOption.PROCEED if self.proceed_enabled() else ActionMenuOption.SKIP

    def previous_available_action(self, action: ActionMenuOption) -> ActionMenuOption | None:
        candidate = action.previous()
        while candidate is not None:
            if candidate is not ActionMenuOption.PROCEED or self.proceed_enabled():
                return candidate
            candidate = candidate.previous()
        return None

    def next_available_action(self, action: ActionMenuOption) -> ActionMenuOption | None:
        candidate = action.next()
        while candidate is not None:
            if candidate is not ActionMenuOption.PROCEED or self.proceed_enabled():
                return candidate
            candidate = candidate.next()
        return None

    def normalize_highlighted_action(self) -> None:
        if self.highlighted_action is ActionMenuOption.PROCEED and not self.proceed_enabled():
            self.highlighted_action = self.first_available_action()

    @staticmethod
    def display_description(item: Any) -> str:
        description = str(_get(item, "description", ""))
        cwd = _get(item, "cwd")
        if cwd is None:
            return description
        cwd_path = Path(cwd)

        for prefix, separator in (
            ("Migrate ", " into "),
            ("Migrate skills from ", " to "),
            ("Migrate ", " to "),
            ("Import ", " to "),
        ):
            reformatted = _reformat_description(description, prefix, separator, cwd_path)
            if reformatted is not None:
                return reformatted

        source = _strip_prefix(description, "Migrate enabled plugins from ")
        if source is not None:
            base = f"Migrate enabled plugins from {_display_path_for(Path(source), cwd_path)}"
            details = _coerce_details(_get(item, "details"))
            if details is None:
                return base
            marketplace_count = len(details.plugins)
            plugin_count = sum(len(group.plugin_names) for group in details.plugins)
            marketplace_label = "marketplace" if marketplace_count == 1 else "marketplaces"
            plugin_label = "plugin" if plugin_count == 1 else "plugins"
            return f"{base} ({marketplace_count} {marketplace_label}, {plugin_count} {plugin_label})"

        return description

    @staticmethod
    def plugin_detail_lines(plugin_groups: Sequence[Any]) -> list[str]:
        groups = [_coerce_plugin_group(group) for group in plugin_groups]
        lines = []
        for group in groups[:3]:
            plugin_names = list(group.plugin_names[:2])
            hidden_plugin_count = max(len(group.plugin_names) - len(plugin_names), 0)
            if hidden_plugin_count > 0:
                plugin_names.append(f"+{hidden_plugin_count} more")
            lines.append(f"      - {group.marketplace_name}: {', '.join(plugin_names)}")
        hidden_marketplace_count = max(len(groups) - len(lines), 0)
        if hidden_marketplace_count > 0:
            lines.append(f"      - +{hidden_marketplace_count} more marketplaces")
        return lines

    def is_done(self) -> bool:
        return self.done

    def outcome(self) -> ExternalAgentConfigMigrationOutcome:
        return self.current_outcome

    def finish_with(self, outcome: ExternalAgentConfigMigrationOutcome) -> None:
        self.current_outcome = outcome
        self.done = True
        _schedule_frame(self.request_frame)

    def proceed(self) -> None:
        selected = self.selected_items()
        if not selected:
            self.error = "Select at least one item or choose a skip option."
            _schedule_frame(self.request_frame)
            return
        self.finish_with(ExternalAgentConfigMigrationOutcome.Proceed(selected))

    def skip(self) -> None:
        self.finish_with(ExternalAgentConfigMigrationOutcome.Skip())

    def skip_forever(self) -> None:
        self.finish_with(ExternalAgentConfigMigrationOutcome.SkipForever())

    def exit(self) -> None:
        self.finish_with(ExternalAgentConfigMigrationOutcome.Exit())

    def selected_items(self) -> list[Any]:
        return [selection.item for selection in self.items if selection.enabled]

    def selected_count(self) -> int:
        return sum(1 for selection in self.items if selection.enabled)

    def set_all_enabled(self, enabled: bool) -> None:
        for selection in self.items:
            selection.enabled = enabled
        self.error = None
        self.normalize_highlighted_action()
        _schedule_frame(self.request_frame)

    def toggle_selected_item(self) -> None:
        if self.focus is not FocusArea.ITEMS or self.selected_item_idx is None:
            return
        if not (0 <= self.selected_item_idx < len(self.items)):
            return
        self.items[self.selected_item_idx].enabled = not self.items[self.selected_item_idx].enabled
        self.error = None
        self.normalize_highlighted_action()
        _schedule_frame(self.request_frame)

    def move_up(self) -> None:
        if self.focus is FocusArea.ITEMS:
            if self.selected_item_idx == 0:
                self.focus = FocusArea.ACTIONS
                self.highlighted_action = ActionMenuOption.SKIP_FOREVER
            elif self.selected_item_idx is not None:
                self.selected_item_idx = max(self.selected_item_idx - 1, 0)
            else:
                self.focus = FocusArea.ACTIONS
                self.highlighted_action = ActionMenuOption.SKIP_FOREVER
        else:
            previous = self.previous_available_action(self.highlighted_action)
            if previous is not None:
                self.highlighted_action = previous
            else:
                self.focus = FocusArea.ITEMS
                if self.items:
                    self.selected_item_idx = len(self.items) - 1
        self.ensure_selected_item_visible()
        _schedule_frame(self.request_frame)

    def move_down(self) -> None:
        if self.focus is FocusArea.ITEMS:
            if self.selected_item_idx is not None and self.selected_item_idx + 1 < len(self.items):
                self.selected_item_idx += 1
            else:
                self.focus = FocusArea.ACTIONS
                self.highlighted_action = self.first_available_action()
        else:
            next_action = self.next_available_action(self.highlighted_action)
            if next_action is not None:
                self.highlighted_action = next_action
            else:
                self.focus = FocusArea.ITEMS
                if self.items:
                    self.selected_item_idx = 0
        self.ensure_selected_item_visible()
        _schedule_frame(self.request_frame)

    def confirm_selection(self) -> None:
        if self.focus is FocusArea.ITEMS:
            self.toggle_selected_item()
        elif self.highlighted_action is ActionMenuOption.PROCEED:
            self.proceed()
        elif self.highlighted_action is ActionMenuOption.SKIP:
            self.skip()
        else:
            self.skip_forever()

    def handle_key(self, key_event: Any) -> None:
        if _get(key_event, "kind") == "release":
            return
        if is_ctrl_exit_combo(key_event):
            self.exit()
            return
        code = _key_code(key_event)
        if code in {"up", "k"}:
            self.move_up()
        elif code in {"down", "j"}:
            self.move_down()
        elif code == "1":
            self.focus = FocusArea.ACTIONS
            self.highlighted_action = ActionMenuOption.PROCEED
            self.proceed()
        elif code == "2":
            self.focus = FocusArea.ACTIONS
            self.highlighted_action = ActionMenuOption.SKIP
            self.skip()
        elif code == "3":
            self.focus = FocusArea.ACTIONS
            self.highlighted_action = ActionMenuOption.SKIP_FOREVER
            self.skip_forever()
        elif code == " ":
            self.toggle_selected_item()
        elif code == "a":
            self.set_all_enabled(True)
        elif code == "n":
            self.set_all_enabled(False)
        elif code == "enter":
            self.confirm_selection()
        elif code == "esc":
            self.skip()

    def ensure_selected_item_visible(self) -> None:
        if self.selected_item_idx is None:
            self.scroll_top = 0
            return
        selected_render_idx = self.selected_render_line_index(self.selected_item_idx)
        visible_rows = max(self.render_line_count(), 1)
        if selected_render_idx < self.scroll_top:
            self.scroll_top = selected_render_idx
        else:
            bottom = self.scroll_top + max(visible_rows - 1, 0)
            if selected_render_idx > bottom:
                self.scroll_top = selected_render_idx + 1 - visible_rows

    def render_line_count(self) -> int:
        return len(self.build_render_lines())

    def selected_render_line_index(self, selected_item_idx: int) -> int:
        for index, entry in enumerate(self.build_render_lines()):
            if entry.item_idx == selected_item_idx:
                return index
        return selected_item_idx

    @staticmethod
    def section_title(cwd: str | Path | None) -> str:
        return "Home" if cwd is None else f"Project: {Path(cwd)}"

    def build_render_lines(self) -> list[RenderLineEntry]:
        lines: list[RenderLineEntry] = []
        current_scope = object()
        for idx, selection in enumerate(self.items):
            item = selection.item
            scope = _get(item, "cwd")
            scope_key = None if scope is None else str(Path(scope))
            if current_scope != scope_key:
                if current_scope is not object() and lines:
                    lines.append(RenderLineEntry(None, RenderLineKind.SECTION, ""))
                lines.append(RenderLineEntry(None, RenderLineKind.SECTION, self.section_title(scope)))
                current_scope = scope_key
            checkbox = "x" if selection.enabled else " "
            selected = self.focus is FocusArea.ITEMS and self.selected_item_idx == idx
            lines.append(
                RenderLineEntry(
                    idx,
                    RenderLineKind.ITEM,
                    f"  [{checkbox}] {self.display_description(item)}",
                    selected=selected,
                )
            )
            details = _coerce_details(_get(item, "details"))
            if details is not None:
                for line in self.plugin_detail_lines(details.plugins):
                    lines.append(RenderLineEntry(None, RenderLineKind.ITEM_DETAIL, line))
        return lines

    def render_items(self, height: int | None = None) -> list[RenderLineEntry]:
        rows = self.build_render_lines()
        if height is None:
            return rows[self.scroll_top :]
        return rows[self.scroll_top : self.scroll_top + max(height, 0)]

    def render_semantic(self) -> list[str]:
        lines = [
            "> External agent config detected",
            "We found settings from another agent that you can add to this project.",
            "Select what to import",
        ]
        if self.error:
            lines.append(self.error)
        lines.extend(entry.text for entry in self.build_render_lines())
        lines.append(f"Selected {self.selected_count()} of {len(self.items)} item(s).")
        for index, action in enumerate((ActionMenuOption.PROCEED, ActionMenuOption.SKIP, ActionMenuOption.SKIP_FOREVER), start=1):
            marker = ">" if self.focus is FocusArea.ACTIONS and self.highlighted_action is action else " "
            dimmed = action is ActionMenuOption.PROCEED and not self.proceed_enabled()
            suffix = " (disabled)" if dimmed else ""
            lines.append(f"{marker} {index}. {action.label()}{suffix}")
        lines.append("Use Up/Down to move, Space to toggle, 1/2/3 to choose, a/n for all/none")
        return lines


async def run_external_agent_config_migration_prompt(*args: Any, **kwargs: Any) -> ExternalAgentConfigMigrationOutcome:
    raise NotImplementedError("interactive TUI event-loop integration is a runtime boundary")


def render_ref(screen: ExternalAgentConfigMigrationScreen, *args: Any, **kwargs: Any) -> list[str]:
    return screen.render_semantic()


def is_ctrl_exit_combo(key_event: Any) -> bool:
    code = _key_code(key_event)
    modifiers = _get(key_event, "modifiers", set())
    if isinstance(modifiers, str):
        has_control = modifiers.lower() in {"control", "ctrl"}
    else:
        has_control = "control" in {str(item).lower() for item in modifiers} or "ctrl" in {str(item).lower() for item in modifiers}
    return has_control and code in {"c", "d"}


def sample_plugin_details() -> MigrationDetails:
    return MigrationDetails(
        plugins=(
            PluginsMigration("acme-tools", ("deployer", "formatter", "lint")),
            PluginsMigration("team-marketplace", ("asana",)),
            PluginsMigration("debug", ("sample",)),
            PluginsMigration("data-tools", ("warehouse",)),
        )
    )


def sample_project_root() -> Path:
    return Path(r"C:\workspace\project") if os.name == "nt" else Path("/workspace/project")


def sample_project_path(path: str) -> str:
    return str(sample_project_root() / path)


def sample_items() -> list[ExternalAgentConfigMigrationItem]:
    project_root = sample_project_root()
    return [
        ExternalAgentConfigMigrationItem(
            item_type="Config",
            description="Migrate /Users/alex/.claude/settings.json into /Users/alex/.codex/config.toml",
            cwd=None,
        ),
        ExternalAgentConfigMigrationItem(
            item_type="Plugins",
            description=f"Migrate enabled plugins from {sample_project_path('.claude/settings.json')}",
            cwd=project_root,
            details=sample_plugin_details(),
        ),
        ExternalAgentConfigMigrationItem(
            item_type="AgentsMd",
            description=f"Migrate {sample_project_path('CLAUDE.md')} to {sample_project_path('AGENTS.md')}",
            cwd=project_root,
        ),
    ]


def render_screen(screen: ExternalAgentConfigMigrationScreen, width: int = 80, height: int = 21) -> str:
    return "\n".join(screen.render_semantic()[:height])


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _strip_prefix(value: str, prefix: str) -> str | None:
    return value[len(prefix) :] if value.startswith(prefix) else None


def _reformat_description(description: str, prefix: str, separator: str, cwd: Path) -> str | None:
    remainder = _strip_prefix(description, prefix)
    if remainder is None or separator not in remainder:
        return None
    left, right = remainder.split(separator, 1)
    return f"{prefix}{_display_path_for(Path(left), cwd)}{separator}{_display_path_for(Path(right), cwd)}"


def _display_path_for(path: Path, cwd: Path) -> str:
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path)


def _coerce_plugin_group(value: Any) -> PluginsMigration:
    if isinstance(value, PluginsMigration):
        return value
    names = tuple(str(name) for name in (_get(value, "plugin_names", []) or []))
    return PluginsMigration(str(_get(value, "marketplace_name", "")), names)


def _coerce_details(value: Any) -> MigrationDetails | None:
    if value is None:
        return None
    if isinstance(value, MigrationDetails):
        return value
    plugins = tuple(_coerce_plugin_group(group) for group in (_get(value, "plugins", []) or []))
    return MigrationDetails(plugins=plugins)


def _schedule_frame(request_frame: Any) -> None:
    if hasattr(request_frame, "schedule_frame"):
        request_frame.schedule_frame()


def _key_code(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event.lower()
    code = _get(key_event, "code", key_event)
    if isinstance(code, dict):
        code = code.get("char") or code.get("key") or code.get("code")
    raw = str(code).lower()
    aliases = {
        "keycode::up": "up",
        "keycode::down": "down",
        "keycode::enter": "enter",
        "keycode::esc": "esc",
        "escape": "esc",
        "space": " ",
    }
    if raw.startswith("char(") and raw.endswith(")"):
        return raw[5:-1].strip("'\"")
    return aliases.get(raw, raw)


# Test-name compatibility helpers.
def prompt_snapshot(*args: Any, **kwargs: Any) -> str:
    return render_screen(*args, **kwargs)


def proceed_returns_selected_items(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rust test helper; use ExternalAgentConfigMigrationScreen directly")


def toggle_item_then_proceed_keeps_remaining_selection(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rust test helper; use ExternalAgentConfigMigrationScreen directly")


def escape_skips_prompt(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rust test helper; use ExternalAgentConfigMigrationScreen directly")


def skip_forever_returns_skip_forever_outcome(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rust test helper; use ExternalAgentConfigMigrationScreen directly")


def proceed_requires_at_least_one_selected_item(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rust test helper; use ExternalAgentConfigMigrationScreen directly")


def proceed_action_is_skipped_when_no_items_are_selected(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rust test helper; use ExternalAgentConfigMigrationScreen directly")


def numeric_shortcuts_choose_actions(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rust test helper; use ExternalAgentConfigMigrationScreen directly")


__all__ = [
    "ActionMenuOption",
    "ExternalAgentConfigMigrationItem",
    "ExternalAgentConfigMigrationOutcome",
    "ExternalAgentConfigMigrationScreen",
    "FocusArea",
    "FrameRequesterStub",
    "MigrationDetails",
    "MigrationSelection",
    "PluginsMigration",
    "RUST_MODULE",
    "RenderLineEntry",
    "RenderLineKind",
    "escape_skips_prompt",
    "is_ctrl_exit_combo",
    "numeric_shortcuts_choose_actions",
    "proceed_action_is_skipped_when_no_items_are_selected",
    "proceed_requires_at_least_one_selected_item",
    "proceed_returns_selected_items",
    "prompt_snapshot",
    "render_ref",
    "render_screen",
    "run_external_agent_config_migration_prompt",
    "sample_items",
    "sample_plugin_details",
    "sample_project_path",
    "sample_project_root",
    "skip_forever_returns_skip_forever_outcome",
    "toggle_item_then_proceed_keeps_remaining_selection",
]
