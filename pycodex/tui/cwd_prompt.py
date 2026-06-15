"""Working-directory selection prompt for ``codex-tui::cwd_prompt``.

Rust source: ``codex/codex-rs/tui/src/cwd_prompt.rs``.
Python represents rendering as semantic text lines instead of ratatui buffers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Set, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="cwd_prompt",
    source="codex/codex-rs/tui/src/cwd_prompt.rs",
    status="complete",
)


class CwdPromptAction(Enum):
    Resume = "resume"
    Fork = "fork"

    def verb(self) -> str:
        return "resume" if self is CwdPromptAction.Resume else "fork"

    def past_participle(self) -> str:
        return "resumed" if self is CwdPromptAction.Resume else "forked"


class CwdSelection(Enum):
    Current = "current"
    Session = "session"

    def next(self) -> "CwdSelection":
        return CwdSelection.Session if self is CwdSelection.Current else CwdSelection.Current

    def prev(self) -> "CwdSelection":
        return CwdSelection.Session if self is CwdSelection.Current else CwdSelection.Current


@dataclass(frozen=True)
class CwdPromptOutcome:
    kind: str
    selection: Optional[CwdSelection] = None

    @classmethod
    def Selection(cls, selection: CwdSelection) -> "CwdPromptOutcome":
        return cls("Selection", selection)

    @classmethod
    def Exit(cls) -> "CwdPromptOutcome":
        return cls("Exit", None)


@dataclass(frozen=True)
class KeyEvent:
    code: str
    modifiers: frozenset[str] = frozenset()
    kind: str = "Press"

    @classmethod
    def new(cls, code: str, modifiers: Optional[Set[str]] = None, kind: str = "Press") -> "KeyEvent":
        return cls(code=code, modifiers=frozenset(modifiers or set()), kind=kind)


@dataclass
class FrameRequester:
    scheduled: int = 0

    def schedule_frame(self) -> None:
        self.scheduled += 1


@dataclass
class CwdPromptScreen:
    request_frame: FrameRequester
    action: CwdPromptAction
    current_cwd: str
    session_cwd: str
    highlighted: CwdSelection = CwdSelection.Session
    selected: Optional[CwdSelection] = None
    should_exit: bool = False

    @classmethod
    def new(
        cls,
        request_frame: Optional[FrameRequester],
        action: CwdPromptAction,
        current_cwd: str,
        session_cwd: str,
    ) -> "CwdPromptScreen":
        return cls(
            request_frame=request_frame or FrameRequester(),
            action=action,
            current_cwd=current_cwd,
            session_cwd=session_cwd,
        )

    def handle_key(self, key_event: Union[KeyEvent, str]) -> None:
        event = _key_event_from_any(key_event)
        if event.kind == "Release":
            return
        if "CONTROL" in event.modifiers and event.code in {"c", "d", "Char(c)", "Char(d)"}:
            self.selected = None
            self.should_exit = True
            self.request_frame.schedule_frame()
            return

        code = event.code
        if code in {"Up", "k", "Char(k)"}:
            self.set_highlight(self.highlighted.prev())
        elif code in {"Down", "j", "Char(j)"}:
            self.set_highlight(self.highlighted.next())
        elif code in {"1", "Char(1)"}:
            self.select(CwdSelection.Session)
        elif code in {"2", "Char(2)"}:
            self.select(CwdSelection.Current)
        elif code == "Enter":
            self.select(self.highlighted)
        elif code == "Esc":
            self.select(CwdSelection.Session)

    def set_highlight(self, highlight: CwdSelection) -> None:
        if self.highlighted is not highlight:
            self.highlighted = highlight
            self.request_frame.schedule_frame()

    def select(self, selection: CwdSelection) -> None:
        self.highlighted = selection
        self.selected = selection
        self.request_frame.schedule_frame()

    def is_done(self) -> bool:
        return self.should_exit or self.selected is not None

    def selection(self) -> Optional[CwdSelection]:
        return self.selected

    def render_lines(self) -> List[str]:
        action_verb = self.action.verb()
        action_past = self.action.past_participle()
        return [
            "",
            f"Choose working directory to {action_verb} this session",
            "",
            f"  Session = latest cwd recorded in the {action_past} session",
            "  Current = your current working directory",
            "",
            selection_option_row(0, f"Use session directory ({self.session_cwd})", self.highlighted is CwdSelection.Session),
            selection_option_row(1, f"Use current directory ({self.current_cwd})", self.highlighted is CwdSelection.Current),
            "",
            "  Press enter to continue",
        ]


def selection_option_row(index: int, label: str, highlighted: bool) -> str:
    marker = "›" if highlighted else " "
    return f"{marker} {index + 1}. {label}"


async def run_cwd_selection_prompt(
    tui: Any,
    action: CwdPromptAction,
    current_cwd: Union[str, Path],
    session_cwd: Union[str, Path],
) -> CwdPromptOutcome:
    frame_requester = getattr(tui, "frame_requester", lambda: FrameRequester())()
    screen = CwdPromptScreen.new(
        frame_requester,
        action,
        str(current_cwd),
        str(session_cwd),
    )
    _draw_tui(tui, screen)
    events = getattr(tui, "events", [])
    for event in events:
        kind = _event_kind(event)
        if kind == "Key":
            screen.handle_key(_event_payload(event))
        elif kind == "Paste":
            pass
        elif kind in {"Draw", "Resize"}:
            _draw_tui(tui, screen)
        else:
            screen.handle_key(event)
        if screen.is_done():
            break
    if screen.should_exit:
        return CwdPromptOutcome.Exit()
    return CwdPromptOutcome.Selection(screen.selection() or CwdSelection.Session)


def render_ref(screen: CwdPromptScreen, area: Any = None, buf: Any = None) -> List[str]:
    lines = screen.render_lines()
    if buf is not None and hasattr(buf, "draw"):
        buf.draw(lines, area)
    return lines


def new_prompt() -> CwdPromptScreen:
    return CwdPromptScreen.new(
        FrameRequester(),
        CwdPromptAction.Resume,
        "/Users/example/current",
        "/Users/example/session",
    )


def _key_event_from_any(value: Union[KeyEvent, str]) -> KeyEvent:
    if isinstance(value, KeyEvent):
        return value
    return KeyEvent.new(str(value))


def _event_kind(event: Any) -> str:
    return str(getattr(event, "kind", event.get("kind") if isinstance(event, dict) else "Key"))


def _event_payload(event: Any) -> Any:
    if isinstance(event, dict):
        return event.get("payload", event.get("key", event))
    return getattr(event, "payload", getattr(event, "key", event))


def _draw_tui(tui: Any, screen: CwdPromptScreen) -> None:
    draw = getattr(tui, "draw", None)
    if draw is not None:
        draw(render_ref(screen))


__all__ = [
    "CwdPromptAction",
    "CwdPromptOutcome",
    "CwdPromptScreen",
    "CwdSelection",
    "FrameRequester",
    "KeyEvent",
    "RUST_MODULE",
    "new_prompt",
    "render_ref",
    "run_cwd_selection_prompt",
    "selection_option_row",
]
