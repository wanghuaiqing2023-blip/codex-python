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
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::hooks_browser_view",
    source="codex/codex-rs/tui/src/bottom_pane/hooks_browser_view.rs",
    status="complete",
)

EVENT_COLUMN_WIDTH = 22
COUNT_COLUMN_WIDTH = 12
MAX_COMMAND_DETAIL_LINES = 3

HOOK_EVENT_ORDER = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "Stop",
    "SubagentStop",
    "PreCompact",
    "SessionEnd",
    "PermissionRequest",
)

_EVENT_LABELS = {
    "SessionStart": "Session start",
    "UserPromptSubmit": "User prompt submit",
    "PreToolUse": "Pre tool use",
    "PostToolUse": "Post tool use",
    "Notification": "Notification",
    "Stop": "Stop",
    "SubagentStop": "Subagent stop",
    "PreCompact": "Pre compact",
    "SessionEnd": "Session end",
    "PermissionRequest": "Permission request",
}

_EVENT_DESCRIPTIONS = {
    "SessionStart": "Runs when a session starts.",
    "UserPromptSubmit": "Runs before a user prompt is submitted.",
    "PreToolUse": "Runs before a tool call executes.",
    "PostToolUse": "Runs after a tool call completes.",
    "Notification": "Runs when Codex emits a notification.",
    "Stop": "Runs when a turn stops.",
    "SubagentStop": "Runs when a subagent stops.",
    "PreCompact": "Runs before conversation compaction.",
    "SessionEnd": "Runs when a session ends.",
    "PermissionRequest": "Runs when Codex requests permission.",
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


class HooksBrowserView:
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
        self._move(-1, wrap=True)

    def move_down(self) -> None:
        self._move(1, wrap=True)

    def page_up(self) -> None:
        self._move(-self.max_visible_rows(), wrap=False)

    def page_down(self) -> None:
        self._move(self.max_visible_rows(), wrap=False)

    def jump_top(self) -> None:
        if self.page_len() > 0:
            self.state.selected_idx = 0

    def jump_bottom(self) -> None:
        if self.page_len() > 0:
            self.state.selected_idx = self.page_len() - 1

    def _move(self, delta: int, *, wrap: bool) -> None:
        length = self.page_len()
        if length == 0:
            return
        current = 0 if self.state.selected_idx is None else self.state.selected_idx
        next_idx = current + delta
        if wrap:
            next_idx %= length
        else:
            next_idx = max(0, min(length - 1, next_idx))
        self.state.selected_idx = next_idx

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
        header = ["Event", "Installed", "Active"]
        if show_review:
            header.append("Review")
        header.append("Description")
        lines = [" | ".join(header)]
        for idx, row in enumerate(rows):
            marker = "> " if self.state.selected_idx == idx else "  "
            cells = [
                event_label(row.event_name),
                str(row.installed),
                str(row.active),
            ]
            if show_review:
                cells.append(str(row.needs_review))
            cells.append(event_description(row.event_name))
            lines.append(marker + " | ".join(cells))
        return lines

    def event_issue_lines(self) -> List[str]:
        if not self.entry.warnings and not self.entry.errors:
            return []
        lines = ["Issues"]
        lines.extend(f"! {warning}" for warning in self.entry.warnings)
        for error in self.entry.errors:
            lines.append(f"x {get_value(error, 'path')}: {get_value(error, 'message')}")
        return lines

    def event_page_lines(self) -> List[str]:
        lines = self.event_header_lines() + [""]
        message = review_needed_message(self.review_needed_total_count())
        if message:
            lines.extend([f"! {message}", ""])
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
                suffix = " - modified"
            elif trust_status == HookTrustStatus.UNTRUSTED.value:
                suffix = " - new"
            selected = "> " if self.state.selected_idx == idx else "  "
            line = f"{selected}[{marker}] {hook_title(idx)}{suffix}"
            lines.append(line if len(line) <= width else line[: max(0, width - 1)] + "...")
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
                return "Press t to trust all; Enter to review hooks; Esc to close"
            return "Press Enter to view hooks; Esc to close"
        hook = self.selected_hook(self.page_event or "")
        if hook is None:
            return "Press Esc to go back"
        if bool(get_value(hook, "is_managed", False)):
            return "Managed hooks are always on; press Esc to go back"
        if hook_needs_review(hook):
            return "Press t to trust; Esc to go back"
        return "Press Space or Enter to toggle; Esc to go back"

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
        return min(MAX_POPUP_ROWS + 8, len(self.render(width).lines) + 1)

    def render(self, width: int = 80) -> RenderedHooksBrowser:
        if self.page == HooksBrowserPage.EVENTS:
            lines = self.event_page_lines()
        else:
            event_name = self.page_event or ""
            lines = self.handler_header_lines(event_name) + [""]
            lines.extend(self.handler_row_lines(event_name, width))
            lines.append("")
            lines.extend(self.detail_lines(event_name, width))
        return RenderedHooksBrowser(
            page=self.page,
            lines=tuple(lines),
            footer=self.render_footer(),
            desired_height=min(MAX_POPUP_ROWS + 8, len(lines) + 1),
        )

    def render_lines(self, width: int = 80) -> List[str]:
        rendered = self.render(width)
        return [*rendered.lines, rendered.footer]

    def _emit(self, event: Dict[str, Any]) -> None:
        self.emitted_events.append(event)
        sender = self.app_event_tx
        if sender is None:
            return
        if hasattr(sender, "send"):
            sender.send(event)
        elif callable(sender):
            sender(event)


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
    text = str(event_name)
    return text.split(".")[-1]


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
    if hook_needs_review(hook):
        return False
    return bool(get_value(hook, "is_managed", False)) or bool(get_value(hook, "enabled", False))


def review_needed_message(count: int) -> Optional[str]:
    if count == 0:
        return None
    noun = "hook" if count == 1 else "hooks"
    return f"{count} {noun} need review before they can run."


def hook_trust_label(status: Any) -> str:
    return normalize_trust_status(status)


def event_label(event_name: Any) -> str:
    normalized = normalize_event_name(event_name)
    return _EVENT_LABELS.get(normalized, normalized)


def event_description(event_name: Any) -> str:
    normalized = normalize_event_name(event_name)
    return _EVENT_DESCRIPTIONS.get(normalized, "Lifecycle hook event.")


def hook_title(index: int) -> str:
    return f"Hook {index + 1}"


def hook_source_summary(hook: Any) -> str:
    source = str(get_value(hook, "source", HookSource.USER.value)).split(".")[-1]
    plugin_id = get_value(hook, "plugin_id", None)
    if plugin_id:
        return f"Plugin {plugin_id}"
    return source


def detail_source_value(hook: Any) -> str:
    source_path = get_value(hook, "source_path", None)
    summary = hook_source_summary(hook)
    return f"{summary} ({source_path})" if source_path else summary


def config_source_label(source: Any) -> str:
    return str(source).split(".")[-1]


def detail_line(label: str, value: str) -> str:
    return f"{label}: {value}"


def detail_wrapped_lines(label: str, value: str, width: int, max_lines: Optional[int] = None) -> List[str]:
    prefix = f"{label}: "
    available = max(1, width - len(prefix))
    wrapped = wrap(value, available) or [""]
    if max_lines is not None:
        wrapped = wrapped[:max_lines]
    lines = []
    for idx, chunk in enumerate(wrapped):
        lines.append((prefix if idx == 0 else " " * len(prefix)) + chunk)
    return lines


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
