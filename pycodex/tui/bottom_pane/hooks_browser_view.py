"""Semantic port of codex-rs/tui/src/bottom_pane/hooks_browser_view.rs.

This module keeps the Rust popup's state machine and hook trust/enablement
rules while representing ratatui rendering as plain semantic lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from textwrap import wrap
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from ..ratatui_bridge import Color as RatatuiColor
from ..ratatui_bridge import Span as RatatuiSpan
from ..ratatui_bridge import Style as RatatuiStyle
from ..status.helpers import format_directory_display
from .bottom_pane_view import BottomPaneViewDefaults
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState
from .selection_popup_common import TerminalPopupLine


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::hooks_browser_view",
    source="codex/codex-rs/tui/src/bottom_pane/hooks_browser_view.rs",
    status="complete",
)

EVENT_COLUMN_WIDTH = 22
COUNT_COLUMN_WIDTH = 12
MAX_COMMAND_DETAIL_LINES = 3
SURFACE_INSET = "  "

HOOK_EVENT_ORDER = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)

_EVENT_LABELS = {event_name: event_name for event_name in HOOK_EVENT_ORDER}

_EVENT_DESCRIPTIONS = {
    "PreToolUse": "Before a tool executes",
    "PermissionRequest": "When permission is requested",
    "PostToolUse": "After a tool executes",
    "PreCompact": "Before context compaction",
    "PostCompact": "After context compaction",
    "SessionStart": "When a new session starts",
    "UserPromptSubmit": "When the user submits a prompt",
    "SubagentStart": "When a subagent is created",
    "SubagentStop": "Right before a subagent ends its turn",
    "Stop": "Right before Codex ends its turn",
}

_CANONICAL_EVENT_BY_TOKEN = {
    "".join(character.lower() for character in event if character.isalnum()): event
    for event in HOOK_EVENT_ORDER
}


class HooksBrowserPage(str, Enum):
    EVENTS = "events"
    HANDLERS = "handlers"


class HookTrustStatus(str, Enum):
    TRUSTED = "Trusted"
    UNTRUSTED = "Untrusted"
    MODIFIED = "Modified"
    MANAGED = "Managed"


class HookSource(str, Enum):
    USER = "User"
    PROJECT = "Project"
    SYSTEM = "System"
    PLUGIN = "Plugin"
    MDM = "Mdm"
    SESSION_FLAGS = "SessionFlags"
    CLOUD_REQUIREMENTS = "CloudRequirements"
    LEGACY_MANAGED_CONFIG_FILE = "LegacyManagedConfigFile"
    LEGACY_MANAGED_CONFIG_MDM = "LegacyManagedConfigMdm"
    UNKNOWN = "Unknown"


@dataclass
class HookMetadata:
    key: str
    event_name: str
    source: str = HookSource.USER.value
    command: Optional[str] = None
    enabled: bool = True
    is_managed: bool = False
    display_order: int = 0
    trust_status: str = HookTrustStatus.TRUSTED.value
    current_hash: str = ""
    matcher: Optional[str] = None
    timeout_sec: int = 0
    source_path: Optional[Any] = None
    plugin_id: Optional[str] = None


@dataclass
class HookErrorInfo:
    path: str | Path
    message: str


@dataclass
class HooksListEntry:
    cwd: str | Path = ""
    hooks: List[Any] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class EventRow:
    event_name: str
    installed: int
    active: int
    needs_review: int


@dataclass(frozen=True)
class HookTrustUpdate:
    key: str
    current_hash: str


@dataclass(frozen=True)
class RenderedHooksBrowser:
    page: HooksBrowserPage
    lines: Tuple[str, ...]
    footer: str
    desired_height: int


class HooksBrowserView(BottomPaneViewDefaults):
    def __init__(self, entry: HooksListEntry, app_event_tx: Optional[Any] = None, keymap: Optional[Any] = None) -> None:
        self.entry = normalize_entry(entry)
        self.entry.hooks.sort(key=lambda hook: int(get_value(hook, "display_order", 0)))
        self.page = HooksBrowserPage.EVENTS
        self.page_event: Optional[str] = None
        self.state = ScrollState()
        self.complete = False
        self.app_event_tx = app_event_tx
        self.keymap = keymap
        self.emitted_events: List[Dict[str, Any]] = []
        if self.page_len() > 0:
            review_index = next(
                (idx for idx, row in enumerate(self.event_rows()) if row.needs_review > 0),
                0,
            )
            self.state.selected_idx = review_index

    @classmethod
    def new(
        cls,
        hooks: List[Any],
        warnings: List[str] | None = None,
        errors: List[Any] | None = None,
        app_event_tx: Optional[Any] = None,
    ) -> "HooksBrowserView":
        return cls(
            HooksListEntry(hooks=hooks, warnings=warnings or [], errors=errors or []),
            app_event_tx,
        )

    @classmethod
    def from_entry(
        cls,
        entry: Any,
        app_event_tx: Optional[Any] = None,
        keymap: Optional[Any] = None,
    ) -> "HooksBrowserView":
        return cls(normalize_entry(entry), app_event_tx, keymap)

    def event_rows(self) -> List[EventRow]:
        rows = []
        for event_name in HOOK_EVENT_ORDER:
            hooks = list(self.handlers_for_event(event_name))
            rows.append(
                EventRow(
                    event_name=event_name,
                    installed=len(hooks),
                    active=sum(1 for hook in hooks if hook_is_active(hook)),
                    needs_review=sum(1 for hook in hooks if hook_needs_review(hook)),
                )
            )
        return rows

    def handlers_for_event(self, event_name: str) -> Iterable[Any]:
        normalized = normalize_event_name(event_name)
        return (hook for hook in self.entry.hooks if normalize_event_name(get_value(hook, "event_name")) == normalized)

    def selected_event(self) -> Optional[str]:
        idx = self.state.selected_idx
        if idx is None or idx < 0 or idx >= len(HOOK_EVENT_ORDER):
            return None
        return HOOK_EVENT_ORDER[idx]

    def selected_hook_index(self, event_name: str) -> Optional[int]:
        selected_visible_idx = self.state.selected_idx
        if selected_visible_idx is None:
            return None
        normalized = normalize_event_name(event_name)
        matches = [
            idx
            for idx, hook in enumerate(self.entry.hooks)
            if normalize_event_name(get_value(hook, "event_name")) == normalized
        ]
        if selected_visible_idx < 0 or selected_visible_idx >= len(matches):
            return None
        return matches[selected_visible_idx]

    def selected_hook(self, event_name: str) -> Optional[Any]:
        idx = self.selected_hook_index(event_name)
        return None if idx is None else self.entry.hooks[idx]

    def move_up(self) -> None:
        length = self.page_len()
        self.state.move_up_wrap(length)
        self.state.ensure_visible(length, self.max_visible_rows())

    def move_down(self) -> None:
        length = self.page_len()
        self.state.move_down_wrap(length)
        self.state.ensure_visible(length, self.max_visible_rows())

    def page_up(self) -> None:
        self.state.page_up_clamped(self.page_len(), self.max_visible_rows())

    def page_down(self) -> None:
        self.state.page_down_clamped(self.page_len(), self.max_visible_rows())

    def jump_top(self) -> None:
        self.state.jump_top(self.page_len(), self.max_visible_rows())

    def jump_bottom(self) -> None:
        self.state.jump_bottom(self.page_len(), self.max_visible_rows())

    def page_len(self) -> int:
        if self.page == HooksBrowserPage.EVENTS:
            return len(HOOK_EVENT_ORDER)
        return len(list(self.handlers_for_event(self.page_event or "")))

    def max_visible_rows(self) -> int:
        return min(MAX_POPUP_ROWS, max(1, self.page_len()))

    def open_selected_event(self) -> None:
        event_name = self.selected_event()
        if event_name is None:
            return
        self.page = HooksBrowserPage.HANDLERS
        self.page_event = event_name
        self.state = ScrollState()
        if self.page_len() > 0:
            self.state.selected_idx = 0

    def toggle_selected_hook(self, event_name: str) -> None:
        idx = self.selected_hook_index(event_name)
        if idx is None:
            return
        hook = self.entry.hooks[idx]
        if bool(get_value(hook, "is_managed", False)) or hook_needs_review(hook):
            return
        enabled = not bool(get_value(hook, "enabled", False))
        set_value(hook, "enabled", enabled)
        self._emit({"type": "SetHookEnabled", "key": get_value(hook, "key"), "enabled": enabled})

    def trust_selected_hook(self, event_name: str) -> None:
        idx = self.selected_hook_index(event_name)
        if idx is None:
            return
        hook = self.entry.hooks[idx]
        if not hook_needs_review(hook):
            return
        set_value(hook, "trust_status", HookTrustStatus.TRUSTED.value)
        self._emit(
            {
                "type": "TrustHook",
                "key": get_value(hook, "key"),
                "current_hash": get_value(hook, "current_hash", ""),
            }
        )

    def trust_all_hooks(self) -> None:
        updates = []
        for hook in self.entry.hooks:
            if not hook_needs_review(hook):
                continue
            set_value(hook, "trust_status", HookTrustStatus.TRUSTED.value)
            updates.append(
                {
                    "key": get_value(hook, "key"),
                    "current_hash": get_value(hook, "current_hash", ""),
                }
            )
        if updates:
            self._emit({"type": "TrustHooks", "updates": updates})

    def close(self) -> None:
        self.complete = True

    def return_to_events(self) -> None:
        selected_event_name = self.page_event if self.page == HooksBrowserPage.HANDLERS else None
        self.page = HooksBrowserPage.EVENTS
        self.page_event = None
        self.state = ScrollState()
        if selected_event_name in HOOK_EVENT_ORDER:
            self.state.selected_idx = HOOK_EVENT_ORDER.index(selected_event_name)
        elif self.page_len() > 0:
            self.state.selected_idx = 0

    def event_header_lines(self) -> List[str]:
        return ["Hooks", "Lifecycle hooks from config and enabled plugins."]

    def review_needed_total_count(self) -> int:
        return sum(1 for hook in self.entry.hooks if hook_needs_review(hook))

    def handler_header_lines(self, event_name: str, review_needed_count: int | None = None) -> List[str]:
        count = self.review_needed_count(event_name) if review_needed_count is None else review_needed_count
        message = review_needed_message(count)
        return [
            f"{event_label(event_name)} hooks",
            message or "Turn hooks on or off. Your changes are saved automatically.",
        ]

    def review_needed_count(self, event_name: str) -> int:
        return sum(1 for hook in self.handlers_for_event(event_name) if hook_needs_review(hook))

    def event_table_lines(self) -> List[str]:
        rows = self.event_rows()
        show_review = any(row.needs_review > 0 for row in rows)
        header = (
            f"{'Event':<{EVENT_COLUMN_WIDTH}}"
            f"{'Installed':<{COUNT_COLUMN_WIDTH}}"
            f"{'Active':<{COUNT_COLUMN_WIDTH}}"
        )
        if show_review:
            header += f"{'Review':<{COUNT_COLUMN_WIDTH}}"
        header += "Description"
        lines = [header]
        for row in rows:
            line = (
                f"{event_label(row.event_name):<{EVENT_COLUMN_WIDTH}}"
                f"{row.installed:<{COUNT_COLUMN_WIDTH}}"
                f"{row.active:<{COUNT_COLUMN_WIDTH}}"
            )
            if show_review:
                line += f"{row.needs_review:<{COUNT_COLUMN_WIDTH}}"
            lines.append(line + event_description(row.event_name))
        return lines

    def event_issue_lines(self) -> List[str]:
        if not self.entry.warnings and not self.entry.errors:
            return []
        lines = ["Issues"]
        lines.extend(f"⚠ {warning}" for warning in self.entry.warnings)
        for error in self.entry.errors:
            lines.append(f"■ {get_value(error, 'path')}: {get_value(error, 'message')}")
        return lines

    def event_page_lines(self) -> List[str]:
        lines = self.event_header_lines() + [""]
        message = review_needed_message(self.review_needed_total_count())
        if message:
            lines.extend([f"⚠ {message}", ""])
        issue_lines = self.event_issue_lines()
        if issue_lines:
            lines.extend(issue_lines + [""])
        lines.extend(self.event_table_lines())
        return lines

    def handler_row_lines(self, event_name: str, width: int = 80) -> List[str]:
        lines = []
        for idx, hook in enumerate(self.handlers_for_event(event_name)):
            marker = "!" if hook_needs_review(hook) else "x" if hook_is_active(hook) else " "
            suffix = ""
            trust_status = normalize_trust_status(get_value(hook, "trust_status", HookTrustStatus.TRUSTED.value))
            if trust_status == HookTrustStatus.MODIFIED.value:
                suffix = " · modified"
            elif trust_status == HookTrustStatus.UNTRUSTED.value:
                suffix = " · new"
            line = f"[{marker}] {hook_title(idx)}{suffix}"
            lines.append(_truncate_with_ellipsis(line, width))
        return lines

    def detail_lines(self, event_name: str, width: int = 80) -> List[str]:
        hook = self.selected_hook(event_name)
        if hook is None:
            return ["No hooks installed for this event."]
        lines = [detail_line("Event", event_label(event_name))]
        matcher = get_value(hook, "matcher", None)
        if matcher:
            lines.extend(detail_wrapped_lines("Matcher", matcher, width))
        lines.extend(detail_wrapped_lines("Source", detail_source_value(hook), width))
        lines.extend(
            detail_wrapped_lines(
                "Command",
                get_value(hook, "command", None) or "-",
                width,
                MAX_COMMAND_DETAIL_LINES,
            )
        )
        lines.append(detail_line("Timeout", f"{get_value(hook, 'timeout_sec', 0)}s"))
        lines.append(detail_line("Trust", hook_trust_label(get_value(hook, "trust_status", HookTrustStatus.TRUSTED.value))))
        return lines

    def render_footer(self) -> str:
        if self.page == HooksBrowserPage.EVENTS:
            if self.review_needed_total_count() > 0:
                return "Press t to trust all; enter to review hooks; esc to close"
            return "Press enter to view hooks; esc to close"
        hook = self.selected_hook(self.page_event or "")
        if hook is None:
            return "Press esc to go back"
        if bool(get_value(hook, "is_managed", False)):
            return "Managed hooks are always on; press esc to go back"
        if hook_needs_review(hook):
            return "Press t to trust; esc to go back"
        return "Press space or enter to toggle; esc to go back"

    def handle_key_event(self, key_event: Any) -> str:
        key = normalize_key(key_event)
        if key in {"up", "k"}:
            self.move_up()
        elif key in {"down", "j"}:
            self.move_down()
        elif key in {"pageup", "page_up"}:
            self.page_up()
        elif key in {"pagedown", "page_down"}:
            self.page_down()
        elif key in {"home", "g"}:
            self.jump_top()
        elif key in {"end", "G"}:
            self.jump_bottom()
        elif key in {"enter", "return"}:
            if self.page == HooksBrowserPage.EVENTS:
                self.open_selected_event()
            else:
                self.toggle_selected_hook(self.page_event or "")
        elif key in {"space", " "} and self.page == HooksBrowserPage.HANDLERS:
            self.toggle_selected_hook(self.page_event or "")
        elif key in {"t", "T"}:
            if self.page == HooksBrowserPage.EVENTS:
                self.trust_all_hooks()
            else:
                self.trust_selected_hook(self.page_event or "")
        elif key in {"esc", "escape", "cancel"}:
            if self.page == HooksBrowserPage.EVENTS:
                self.close()
            else:
                self.return_to_events()
        else:
            return "ignored"
        return "handled"

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> str:
        self.close()
        return "handled"

    def prefer_esc_to_handle_key_event(self) -> bool:
        return True

    def desired_height(self, width: int = 80) -> int:
        # Rust reserves the menu surface's vertical inset plus one footer row.
        return len(self._content_lines(width)) + 2

    def _content_lines(self, width: int) -> List[str]:
        if self.page == HooksBrowserPage.EVENTS:
            return [*self.event_page_lines(), ""]

        event_name = self.page_event or ""
        headers = self.handler_header_lines(event_name)
        rows = self.handler_row_lines(event_name, width)
        if not rows:
            return [*headers, "", "No hooks installed for this event.", ""]
        visible_rows = rows[
            self.state.scroll_top : self.state.scroll_top + self.max_visible_rows()
        ]
        return [
            *headers,
            "",
            *visible_rows,
            "",
            *self.detail_lines(event_name, width),
            "",
        ]

    def render(self, width: int = 80) -> RenderedHooksBrowser:
        lines = self._content_lines(max(1, int(width)))
        return RenderedHooksBrowser(
            page=self.page,
            lines=tuple(lines),
            footer=self.render_footer(),
            desired_height=len(lines) + 2,
        )

    def render_lines(self, width: int = 80) -> List[str]:
        rendered = self.render(width)
        return [*rendered.lines, rendered.footer]

    def terminal_lines(self, *, width: int) -> List[TerminalPopupLine]:
        content_width = max(1, int(width) - len(SURFACE_INSET) * 2)
        if self.page == HooksBrowserPage.EVENTS:
            lines = self._event_terminal_lines()
        else:
            lines = self._handler_terminal_lines(content_width)
        lines.append(
            _styled_popup_line(self.render_footer(), RatatuiStyle.default().dim())
        )
        return lines

    def _event_terminal_lines(self) -> List[TerminalPopupLine]:
        lines = [
            _styled_popup_line("Hooks", RatatuiStyle.default().bold()),
            _styled_popup_line(
                "Lifecycle hooks from config and enabled plugins.",
                RatatuiStyle.default().dim(),
            ),
            TerminalPopupLine(""),
        ]
        review_message = review_needed_message(self.review_needed_total_count())
        if review_message is not None:
            lines.extend(
                [
                    _styled_popup_line(
                        f"⚠ {review_message}",
                        RatatuiStyle.default().with_fg(RatatuiColor.Yellow),
                    ),
                    TerminalPopupLine(""),
                ]
            )
        if self.entry.warnings or self.entry.errors:
            lines.append(_styled_popup_line("Issues", RatatuiStyle.default().bold()))
            lines.extend(
                _plain_popup_line(f"⚠ {warning}") for warning in self.entry.warnings
            )
            lines.extend(
                _styled_popup_line(
                    f"■ {get_value(error, 'path')}: {get_value(error, 'message')}",
                    RatatuiStyle.default().with_fg(RatatuiColor.Red),
                )
                for error in self.entry.errors
            )
            lines.append(TerminalPopupLine(""))
        lines.extend(self._event_table_terminal_lines())
        lines.append(TerminalPopupLine(""))
        return lines

    def _event_table_terminal_lines(self) -> List[TerminalPopupLine]:
        rows = self.event_rows()
        show_review = any(row.needs_review > 0 for row in rows)
        header = (
            f"{'Event':<{EVENT_COLUMN_WIDTH}}"
            f"{'Installed':<{COUNT_COLUMN_WIDTH}}"
            f"{'Active':<{COUNT_COLUMN_WIDTH}}"
        )
        if show_review:
            header += f"{'Review':<{COUNT_COLUMN_WIDTH}}"
        lines = [_plain_popup_line(header + "Description")]
        accent = RatatuiStyle.default().with_fg(RatatuiColor.Cyan).bold()
        dim = RatatuiStyle.default().dim()
        yellow = RatatuiStyle.default().with_fg(RatatuiColor.Yellow)
        for index, row in enumerate(rows):
            selected = self.state.selected_idx == index
            parts = [
                (f"{event_label(row.event_name):<{EVENT_COLUMN_WIDTH}}", RatatuiStyle.default()),
                (f"{row.installed:<{COUNT_COLUMN_WIDTH}}", dim),
                (f"{row.active:<{COUNT_COLUMN_WIDTH}}", dim),
            ]
            if show_review:
                review_style = yellow if row.needs_review > 0 else dim
                parts.append((f"{row.needs_review:<{COUNT_COLUMN_WIDTH}}", review_style))
            parts.append((event_description(row.event_name), dim))
            if selected:
                parts = [(text, accent) for text, _style in parts]
            lines.append(_popup_line_from_parts(parts))
        return lines

    def _handler_terminal_lines(self, width: int) -> List[TerminalPopupLine]:
        event_name = self.page_event or ""
        review_count = self.review_needed_count(event_name)
        review_message = review_needed_message(review_count)
        subtitle = review_message or "Turn hooks on or off. Your changes are saved automatically."
        subtitle_style = (
            RatatuiStyle.default().with_fg(RatatuiColor.Yellow)
            if review_message is not None
            else RatatuiStyle.default().dim()
        )
        lines = [
            _styled_popup_line(
                f"{event_label(event_name)} hooks",
                RatatuiStyle.default().bold(),
            ),
            _styled_popup_line(subtitle, subtitle_style),
            TerminalPopupLine(""),
        ]
        hooks = list(self.handlers_for_event(event_name))
        if not hooks:
            lines.extend(
                [
                    _styled_popup_line(
                        "No hooks installed for this event.",
                        RatatuiStyle.default().dim().italic(),
                    ),
                    TerminalPopupLine(""),
                ]
            )
            return lines

        row_texts = self.handler_row_lines(event_name, width)
        visible_start = self.state.scroll_top
        visible_end = visible_start + self.max_visible_rows()
        accent = RatatuiStyle.default().with_fg(RatatuiColor.Cyan).bold()
        warning = RatatuiStyle.default().with_fg(RatatuiColor.Yellow)
        for index in range(visible_start, min(visible_end, len(hooks))):
            hook = hooks[index]
            needs_review = hook_needs_review(hook)
            if self.state.selected_idx == index:
                style = warning.bold() if needs_review else accent
            elif needs_review:
                style = warning
            elif bool(get_value(hook, "is_managed", False)):
                style = RatatuiStyle.default().dim()
            else:
                style = RatatuiStyle.default()
            lines.append(_styled_popup_line(row_texts[index], style))
        lines.append(TerminalPopupLine(""))
        lines.extend(self._detail_terminal_lines(event_name, width))
        lines.append(TerminalPopupLine(""))
        return lines

    def _detail_terminal_lines(
        self,
        event_name: str,
        width: int,
    ) -> List[TerminalPopupLine]:
        dim = RatatuiStyle.default().dim()
        lines = []
        for line in self.detail_lines(event_name, width):
            prefix = line[:10]
            value = line[10:]
            lines.append(
                _popup_line_from_parts(
                    [
                        (prefix, RatatuiStyle.default()),
                        (value, dim),
                    ]
                )
            )
        return lines

    def _emit(self, event: Dict[str, Any]) -> None:
        self.emitted_events.append(event)
        sender = self.app_event_tx
        if sender is None:
            return
        if hasattr(sender, "send"):
            from ..app_event import AppEvent

            payload = dict(event)
            variant = str(payload.pop("type"))
            sender.send(AppEvent.of(variant, **payload))
        elif callable(sender):
            sender(event)


def _popup_line_from_parts(
    parts: Iterable[Tuple[str, RatatuiStyle]],
) -> TerminalPopupLine:
    materialized = tuple(parts)
    text = SURFACE_INSET + "".join(content for content, _style in materialized)
    spans = (
        RatatuiSpan.raw(SURFACE_INSET),
        *(
            RatatuiSpan.styled(content, style)
            for content, style in materialized
        ),
    )
    return TerminalPopupLine(text, spans=spans)


def _styled_popup_line(text: str, style: RatatuiStyle) -> TerminalPopupLine:
    return _popup_line_from_parts(((text, style),))


def _plain_popup_line(text: str) -> TerminalPopupLine:
    return _styled_popup_line(text, RatatuiStyle.default())


def normalize_entry(entry: Any) -> HooksListEntry:
    if isinstance(entry, HooksListEntry):
        return entry
    return HooksListEntry(
        cwd=get_value(entry, "cwd", ""),
        hooks=list(get_value(entry, "hooks", [])),
        warnings=list(get_value(entry, "warnings", [])),
        errors=list(get_value(entry, "errors", [])),
    )


def get_value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def set_value(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


def normalize_event_name(event_name: Any) -> str:
    if isinstance(event_name, Enum):
        event_name = event_name.value
    text = str(event_name).split(".")[-1]
    token = "".join(character.lower() for character in text if character.isalnum())
    return _CANONICAL_EVENT_BY_TOKEN.get(token, text)


def normalize_trust_status(status: Any) -> str:
    if isinstance(status, Enum):
        status = status.value
    text = str(status).split(".")[-1]
    for candidate in HookTrustStatus:
        if text.lower() == candidate.value.lower():
            return candidate.value
    return text


def normalize_key(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event
    if isinstance(key_event, dict):
        return str(key_event.get("key") or key_event.get("code") or "")
    return str(getattr(key_event, "key", getattr(key_event, "code", key_event)))


def hook_needs_review(hook: Any) -> bool:
    return normalize_trust_status(get_value(hook, "trust_status", HookTrustStatus.TRUSTED.value)) in {
        HookTrustStatus.UNTRUSTED.value,
        HookTrustStatus.MODIFIED.value,
    }


def hook_is_active(hook: Any) -> bool:
    trust_status = normalize_trust_status(
        get_value(hook, "trust_status", HookTrustStatus.TRUSTED.value)
    )
    return bool(get_value(hook, "enabled", False)) and trust_status in {
        HookTrustStatus.MANAGED.value,
        HookTrustStatus.TRUSTED.value,
    }


def review_needed_message(count: int) -> Optional[str]:
    if count == 0:
        return None
    if count == 1:
        return "1 hook needs review before it can run."
    return f"{count} hooks need review before they can run."


def hook_trust_label(status: Any) -> str:
    normalized = normalize_trust_status(status)
    return {
        HookTrustStatus.MANAGED.value: "Managed",
        HookTrustStatus.TRUSTED.value: "Trusted",
        HookTrustStatus.UNTRUSTED.value: "New hook - review required",
        HookTrustStatus.MODIFIED.value: "Modified since last trusted - review required",
    }.get(normalized, normalized)


def event_label(event_name: Any) -> str:
    normalized = normalize_event_name(event_name)
    return _EVENT_LABELS.get(normalized, normalized)


def event_description(event_name: Any) -> str:
    normalized = normalize_event_name(event_name)
    return _EVENT_DESCRIPTIONS.get(normalized, "Lifecycle hook event.")


def hook_title(index: int) -> str:
    return f"Hook {index + 1}"


def hook_source_summary(hook: Any) -> str:
    source = _normalize_source(get_value(hook, "source", HookSource.USER.value))
    plugin_id = get_value(hook, "plugin_id", None)
    if source == HookSource.PLUGIN.value:
        return f"Plugin - {plugin_id}" if plugin_id else "Plugin"
    return config_source_label(source)


def detail_source_value(hook: Any) -> str:
    source = _normalize_source(get_value(hook, "source", HookSource.USER.value))
    if source == HookSource.PLUGIN.value:
        return hook_source_summary(hook)
    if source in {
        HookSource.SYSTEM.value,
        HookSource.MDM.value,
        HookSource.CLOUD_REQUIREMENTS.value,
        HookSource.LEGACY_MANAGED_CONFIG_FILE.value,
        HookSource.LEGACY_MANAGED_CONFIG_MDM.value,
    }:
        return config_source_label(source)
    source_path = get_value(hook, "source_path", None)
    if source_path is None:
        return config_source_label(source)
    return f"{config_source_label(source)} - {format_directory_display(source_path, None)}"


def config_source_label(source: Any) -> str:
    normalized = _normalize_source(source)
    return {
        HookSource.SYSTEM.value: "Admin config",
        HookSource.USER.value: "User config",
        HookSource.PROJECT.value: "Project config",
        HookSource.MDM.value: "Admin config",
        HookSource.SESSION_FLAGS.value: "Session flags",
        HookSource.CLOUD_REQUIREMENTS.value: "Admin config",
        HookSource.LEGACY_MANAGED_CONFIG_FILE.value: "Admin config",
        HookSource.LEGACY_MANAGED_CONFIG_MDM.value: "Admin config",
        HookSource.UNKNOWN.value: "Unknown source",
        HookSource.PLUGIN.value: "Plugin",
    }.get(normalized, normalized)


def detail_line(label: str, value: str) -> str:
    return f"{label:<10}{value}"


def detail_wrapped_lines(label: str, value: str, width: int, max_lines: Optional[int] = None) -> List[str]:
    prefix = f"{label:<10}"
    available = max(1, width - len(prefix))
    wrapped = wrap(value, available) or [""]
    truncated = max_lines is not None and len(wrapped) > max_lines
    if max_lines is not None:
        wrapped = wrapped[:max_lines]
    if truncated and wrapped:
        wrapped[-1] = _truncate_with_ellipsis(
            f"{wrapped[-1]}…",
            available,
        )
    lines: List[str] = []
    for idx, chunk in enumerate(wrapped):
        lines.append((prefix if idx == 0 else " " * len(prefix)) + chunk)
    return lines


def _normalize_source(source: Any) -> str:
    if isinstance(source, Enum):
        source = source.value
    text = str(source).split(".")[-1]
    token = "".join(character.lower() for character in text if character.isalnum())
    for candidate in HookSource:
        candidate_token = "".join(
            character.lower() for character in candidate.value if character.isalnum()
        )
        if token == candidate_token:
            return candidate.value
    return text


def _truncate_with_ellipsis(text: str, width: int) -> str:
    available = max(0, int(width))
    if len(text) <= available:
        return text
    if available == 0:
        return ""
    if available == 1:
        return "…"
    return text[: available - 1] + "…"


def handle_key_event(view: HooksBrowserView, key_event: Any) -> str:
    return view.handle_key_event(key_event)


def is_complete(view: HooksBrowserView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: HooksBrowserView) -> str:
    return view.on_ctrl_c()


def prefer_esc_to_handle_key_event(view: Optional[HooksBrowserView] = None) -> bool:
    return True if view is None else view.prefer_esc_to_handle_key_event()


def desired_height(view: HooksBrowserView, width: int = 80) -> int:
    return view.desired_height(width)


def render(view: HooksBrowserView, width: int = 80) -> RenderedHooksBrowser:
    return view.render(width)


def render_lines(view: HooksBrowserView, width: int = 80) -> List[str]:
    return view.render_lines(width)


def render_buffer(view: HooksBrowserView, width: int = 80) -> str:
    return "\n".join(view.render_lines(width))


def hook(
    key: str,
    event_name: str,
    source: str = HookSource.USER.value,
    plugin_id: Optional[str] = None,
    command: Optional[str] = None,
    enabled: bool = True,
    is_managed: bool = False,
    display_order: int = 0,
) -> HookMetadata:
    return HookMetadata(
        key=key,
        event_name=event_name,
        source=source,
        plugin_id=plugin_id,
        command=command,
        enabled=enabled,
        is_managed=is_managed,
        display_order=display_order,
        current_hash="sha256:current",
        trust_status=(
            HookTrustStatus.MANAGED.value
            if is_managed
            else HookTrustStatus.TRUSTED.value
        ),
    )


def view() -> HooksBrowserView:
    return HooksBrowserView.new(
        [
            hook("path:trusted", "PreToolUse", command="~/bin/trusted.sh", enabled=True, display_order=0),
            hook("path:managed", "PermissionRequest", source=HookSource.SYSTEM.value, command="/managed.sh", is_managed=True, display_order=1),
        ],
        [],
        [],
    )


__all__ = [
    "COUNT_COLUMN_WIDTH",
    "EVENT_COLUMN_WIDTH",
    "EventRow",
    "HookErrorInfo",
    "HookMetadata",
    "HookSource",
    "HookTrustStatus",
    "HookTrustUpdate",
    "HooksBrowserPage",
    "HooksBrowserView",
    "HooksListEntry",
    "MAX_COMMAND_DETAIL_LINES",
    "RenderedHooksBrowser",
    "RUST_MODULE",
    "config_source_label",
    "desired_height",
    "detail_line",
    "detail_source_value",
    "detail_wrapped_lines",
    "event_description",
    "event_label",
    "handle_key_event",
    "hook",
    "hook_is_active",
    "hook_needs_review",
    "hook_source_summary",
    "hook_title",
    "hook_trust_label",
    "is_complete",
    "on_ctrl_c",
    "prefer_esc_to_handle_key_event",
    "render",
    "render_buffer",
    "render_lines",
    "review_needed_message",
    "view",
]
