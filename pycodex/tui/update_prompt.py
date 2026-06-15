"""Behavior port for Rust ``codex-tui::update_prompt``.

The Rust module is compiled only for release builds and owns the update prompt
modal shown before the TUI starts.  Python keeps the same state-machine,
visible-text contract, and a ratatui-compatible buffer render path through the
local bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional

from ._porting import RustTuiModule
from .ratatui_bridge import Buffer, Clear, Line, Rect, Span, Style
from .update_action import UpdateAction
from .version import CODEX_CLI_VERSION

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="update_prompt",
    source="codex/codex-rs/tui/src/update_prompt.rs",
    status="complete",
)

RELEASE_NOTES_URL = "https://github.com/openai/codex/releases/latest"


class FrameRequesterLike:
    def schedule_frame(self) -> Any: ...


class UpdatePromptOutcomeKind(Enum):
    CONTINUE = "continue"
    RUN_UPDATE = "run_update"


@dataclass(frozen=True)
class UpdatePromptOutcome:
    """Python semantic model for Rust ``UpdatePromptOutcome``.

    Rust's ``RunUpdate`` variant carries an ``UpdateAction``.  Python preserves
    that payload with a small immutable value object.
    """

    kind: UpdatePromptOutcomeKind
    action: Optional[UpdateAction] = None

    @classmethod
    def continue_(cls) -> "UpdatePromptOutcome":
        return cls(UpdatePromptOutcomeKind.CONTINUE)

    @classmethod
    def run_update(cls, action: UpdateAction) -> "UpdatePromptOutcome":
        return cls(UpdatePromptOutcomeKind.RUN_UPDATE, action)

    @property
    def is_continue(self) -> bool:
        return self.kind is UpdatePromptOutcomeKind.CONTINUE

    @property
    def is_run_update(self) -> bool:
        return self.kind is UpdatePromptOutcomeKind.RUN_UPDATE


class UpdateSelection(Enum):
    UPDATE_NOW = "update_now"
    NOT_NOW = "not_now"
    DONT_REMIND = "dont_remind"

    def next(self) -> "UpdateSelection":
        if self is UpdateSelection.UPDATE_NOW:
            return UpdateSelection.NOT_NOW
        if self is UpdateSelection.NOT_NOW:
            return UpdateSelection.DONT_REMIND
        return UpdateSelection.UPDATE_NOW

    def prev(self) -> "UpdateSelection":
        if self is UpdateSelection.UPDATE_NOW:
            return UpdateSelection.DONT_REMIND
        if self is UpdateSelection.NOT_NOW:
            return UpdateSelection.UPDATE_NOW
        return UpdateSelection.NOT_NOW


@dataclass(frozen=True)
class KeyEvent:
    """Small crossterm-like key event used by the Python state-machine."""

    code: str
    modifiers: frozenset[str] = frozenset()
    kind: str = "press"

    @classmethod
    def new(cls, code: str, modifiers: Any = None, kind: str = "press") -> "KeyEvent":
        return cls(code=code, modifiers=_normalize_modifiers(modifiers), kind=str(kind).lower())


class DummyFrameRequester:
    """Test/support requester that records frame scheduling."""

    def __init__(self) -> None:
        self.scheduled = 0

    def schedule_frame(self) -> None:
        self.scheduled += 1


@dataclass
class UpdatePromptScreen:
    request_frame: FrameRequesterLike
    latest_version_value: str
    update_action: UpdateAction
    current_version: str = CODEX_CLI_VERSION
    highlighted: UpdateSelection = UpdateSelection.UPDATE_NOW
    _selection: Optional[UpdateSelection] = None

    @classmethod
    def new(
        cls,
        request_frame: FrameRequesterLike,
        latest_version: str,
        update_action: UpdateAction,
        *,
        current_version: str = CODEX_CLI_VERSION,
    ) -> "UpdatePromptScreen":
        return cls(
            request_frame=request_frame,
            latest_version_value=str(latest_version),
            update_action=update_action,
            current_version=str(current_version),
        )

    def handle_key(self, key_event: Any) -> None:
        event = _coerce_key_event(key_event)
        if event.kind == "release":
            return
        if "control" in event.modifiers and event.code in {"c", "d"}:
            self.select(UpdateSelection.NOT_NOW)
            return

        code = event.code
        if code in {"up", "k"}:
            self.set_highlight(self.highlighted.prev())
        elif code in {"down", "j"}:
            self.set_highlight(self.highlighted.next())
        elif code == "1":
            self.select(UpdateSelection.UPDATE_NOW)
        elif code == "2":
            self.select(UpdateSelection.NOT_NOW)
        elif code == "3":
            self.select(UpdateSelection.DONT_REMIND)
        elif code == "enter":
            self.select(self.highlighted)
        elif code == "esc":
            self.select(UpdateSelection.NOT_NOW)

    def set_highlight(self, highlight: UpdateSelection) -> None:
        if self.highlighted != highlight:
            self.highlighted = highlight
            self.request_frame.schedule_frame()

    def select(self, selection: UpdateSelection) -> None:
        self.highlighted = selection
        self._selection = selection
        self.request_frame.schedule_frame()

    def is_done(self) -> bool:
        return self._selection is not None

    def selection(self) -> Optional[UpdateSelection]:
        return self._selection

    def latest_version(self) -> str:
        return self.latest_version_value

    def render_lines(self) -> List[str]:
        update_command = self.update_action.command_str()
        return [
            "",
            f"  Update available! {self.current_version} -> {self.latest_version_value}",
            "",
            f"  Release notes: {RELEASE_NOTES_URL}",
            "",
            _selection_row(0, f"Update now (runs `{update_command}`)", self.highlighted is UpdateSelection.UPDATE_NOW),
            _selection_row(1, "Skip", self.highlighted is UpdateSelection.NOT_NOW),
            _selection_row(2, "Skip until next version", self.highlighted is UpdateSelection.DONT_REMIND),
            "",
            "  Press Enter to continue",
        ]

    def render(self, area: Rect, buf: Buffer) -> None:
        render_ref(self, area, buf)

    def render_ref(self, area: Rect, buf: Buffer) -> None:
        render_ref(self, area, buf)


async def run_update_prompt_if_needed(
    tui: Any,
    config: Any,
    *,
    latest_version: Optional[str] = None,
    update_action: Optional[UpdateAction] = None,
    updates_module: Any = None,
    update_action_provider: Any = None,
) -> UpdatePromptOutcome:
    """Run the update prompt with explicit dependency boundaries.

    Rust asks ``updates::get_upgrade_version_for_popup(config)`` and then
    ``update_action::get_update_action()`` before entering an async TUI event
    loop.  Python preserves those decisions and requires callers/tests to
    provide either values or modules/providers with matching methods.  It does
    not fabricate network/update availability or install-source detection.
    """

    if latest_version is None:
        if updates_module is None:
            from . import updates as updates_module
        if not hasattr(updates_module, "get_upgrade_version_for_popup"):
            return UpdatePromptOutcome.continue_()
        maybe_version = updates_module.get_upgrade_version_for_popup(config)
        latest_version = await maybe_version if hasattr(maybe_version, "__await__") else maybe_version
    if latest_version is None:
        return UpdatePromptOutcome.continue_()

    if update_action is None:
        if update_action_provider is None:
            from .update_action import get_update_action as update_action_provider
        maybe_action = update_action_provider()
        update_action = await maybe_action if hasattr(maybe_action, "__await__") else maybe_action
    if update_action is None:
        return UpdatePromptOutcome.continue_()

    screen = UpdatePromptScreen.new(tui.frame_requester(), str(latest_version), update_action)
    if hasattr(tui, "draw_update_prompt"):
        tui.draw_update_prompt(screen)

    while not screen.is_done():
        event = await tui.next_event()
        if event is None:
            break
        kind = getattr(event, "kind", None)
        if kind in {"draw", "resize"} and hasattr(tui, "draw_update_prompt"):
            tui.draw_update_prompt(screen)
        elif kind == "paste":
            continue
        else:
            screen.handle_key(event)

    selection = screen.selection()
    if selection is UpdateSelection.UPDATE_NOW:
        terminal = getattr(tui, "terminal", None)
        if terminal is not None and hasattr(terminal, "clear"):
            terminal.clear()
        return UpdatePromptOutcome.run_update(update_action)
    if selection is UpdateSelection.DONT_REMIND and updates_module is not None and hasattr(updates_module, "dismiss_version"):
        dismissed = updates_module.dismiss_version(config, screen.latest_version())
        if hasattr(dismissed, "__await__"):
            await dismissed
    return UpdatePromptOutcome.continue_()


def render_ref(
    screen: UpdatePromptScreen,
    area: Optional[Rect] = None,
    buf: Optional[Buffer] = None,
    *_args: Any,
    **_kwargs: Any,
) -> List[str]:
    """Render the prompt as either semantic text or a bridge buffer widget.

    Existing Python callers use the no-buffer form for stable snapshots.  When
    ``area`` and ``buf`` are supplied this mirrors Rust's ``WidgetRef`` shape by
    clearing the target area and writing styled ``Line`` values into cells.
    """

    if area is not None and buf is not None:
        Clear().render(area, buf)
        for offset, line in enumerate(_bridge_lines(screen)):
            if offset >= area.height:
                break
            buf.set_line(area.x, area.y + offset, line, max_width=area.width)
    return screen.render_lines()


def new_prompt() -> UpdatePromptScreen:
    return UpdatePromptScreen.new(DummyFrameRequester(), "9.9.9", default_update_action())


def default_update_action() -> UpdateAction:
    for name in ("NPM_GLOBAL_LATEST", "NpmGlobalLatest", "npm_global_latest"):
        if hasattr(UpdateAction, name):
            return getattr(UpdateAction, name)
    for action in UpdateAction:
        if str(getattr(action, "name", "")).lower().replace("_", "") == "npmgloballatest":
            return action
    raise AttributeError("UpdateAction does not expose an npm global latest variant")


def update_prompt_snapshot() -> List[str]:
    return new_prompt().render_lines()


def update_prompt_confirm_selects_update() -> Optional[UpdateSelection]:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("enter"))
    return screen.selection()


def update_prompt_dismiss_option_leaves_prompt_in_normal_state() -> Optional[UpdateSelection]:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("down"))
    screen.handle_key(KeyEvent.new("enter"))
    return screen.selection()


def update_prompt_dont_remind_selects_dismissal() -> Optional[UpdateSelection]:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("down"))
    screen.handle_key(KeyEvent.new("down"))
    screen.handle_key(KeyEvent.new("enter"))
    return screen.selection()


def update_prompt_ctrl_c_skips_update() -> Optional[UpdateSelection]:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("c", {"control"}))
    return screen.selection()


def update_prompt_navigation_wraps_between_entries() -> UpdateSelection:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("up"))
    first = screen.highlighted
    screen.handle_key(KeyEvent.new("down"))
    if first is not UpdateSelection.DONT_REMIND:
        raise AssertionError("up from update-now should wrap to dont-remind")
    return screen.highlighted


def _selection_row(index: int, label: str, selected: bool) -> str:
    marker = ">" if selected else " "
    return f"  {marker} {index + 1}. {label}"


def _selection_line(index: int, label: str, selected: bool) -> Line:
    style = Style.default().bold() if selected else Style.default()
    return Line.from_spans([Span.styled(_selection_row(index, label, selected), style)])


def _bridge_lines(screen: UpdatePromptScreen) -> List[Line]:
    update_command = screen.update_action.command_str()
    bold = Style.default().bold()
    dim = Style.default().dim()
    link = Style.default().dim().underlined()
    return [
        Line.raw(""),
        Line.from_spans(
            [
                Span.raw("  "),
                Span.styled("Update available!", bold),
                Span.raw(" "),
                Span.styled(f"{screen.current_version} -> {screen.latest_version_value}", dim),
            ]
        ),
        Line.raw(""),
        Line.from_spans(
            [
                Span.raw("  "),
                Span.styled("Release notes: ", dim),
                Span.styled(RELEASE_NOTES_URL, link),
            ]
        ),
        Line.raw(""),
        _selection_line(
            0,
            f"Update now (runs `{update_command}`)",
            screen.highlighted is UpdateSelection.UPDATE_NOW,
        ),
        _selection_line(1, "Skip", screen.highlighted is UpdateSelection.NOT_NOW),
        _selection_line(2, "Skip until next version", screen.highlighted is UpdateSelection.DONT_REMIND),
        Line.raw(""),
        Line.from_spans(
            [
                Span.raw("  "),
                Span.styled("Press ", dim),
                Span.styled("Enter", bold),
                Span.styled(" to continue", dim),
            ]
        ),
    ]


def _coerce_key_event(value: Any) -> KeyEvent:
    if isinstance(value, KeyEvent):
        return value
    if isinstance(value, str):
        return KeyEvent.new(value)
    if isinstance(value, dict):
        return KeyEvent.new(value.get("code", ""), value.get("modifiers"), value.get("kind", "press"))
    code = getattr(value, "code", "")
    modifiers = getattr(value, "modifiers", None)
    kind = getattr(value, "kind", "press")
    return KeyEvent.new(str(code), modifiers, str(kind))


def _normalize_modifiers(modifiers: Any) -> frozenset[str]:
    if modifiers is None:
        return frozenset()
    if isinstance(modifiers, str):
        items = {modifiers}
    else:
        try:
            items = set(modifiers)
        except TypeError:
            items = {modifiers}
    normalized = set()
    for item in items:
        text = str(item).lower()
        if "control" in text or text == "ctrl":
            normalized.add("control")
        else:
            normalized.add(text)
    return frozenset(normalized)


__all__ = [
    "DummyFrameRequester",
    "KeyEvent",
    "RELEASE_NOTES_URL",
    "RUST_MODULE",
    "UpdatePromptOutcome",
    "UpdatePromptOutcomeKind",
    "UpdatePromptScreen",
    "UpdateSelection",
    "new_prompt",
    "default_update_action",
    "render_ref",
    "run_update_prompt_if_needed",
    "update_prompt_confirm_selects_update",
    "update_prompt_ctrl_c_skips_update",
    "update_prompt_dismiss_option_leaves_prompt_in_normal_state",
    "update_prompt_dont_remind_selects_dismissal",
    "update_prompt_navigation_wraps_between_entries",
    "update_prompt_snapshot",
]
