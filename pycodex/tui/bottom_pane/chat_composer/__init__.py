"""Semantic port for Rust ``bottom_pane/chat_composer.rs``.

The Rust chat composer is a large bottom-pane input state machine. This Python
module carries the module-owned public data/config boundary and keeps editor,
popup, history, paste-burst, and rendering runtime behavior as explicit
neighboring modules or dependency boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
import unicodedata
from typing import Any, Callable, MutableSequence, TextIO

from ..._porting import RustTuiModule
from ..command_popup import CommandPopup, CommandPopupFlags
from ..paste_burst import CharDecision, FlushResultKind, PasteBurst
from ..selection_popup_common import TerminalPopupLine
from ..textarea import TextArea, TextAreaState
from .draft_state import DraftState
from .slash_input import terminal_command_popup_visible_for_draft

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
    status="complete",
)

LARGE_PASTE_CHAR_THRESHOLD = 1000
MAX_USER_INPUT_TEXT_CHARS = 512_000
TERMINAL_COMPOSER_SHUTDOWN_PLACEHOLDER = "Shutting down..."
FOOTER_SPACING_HEIGHT = 0


def user_input_too_large_message(actual_chars: int) -> str:
    return (
        f"Message exceeds the maximum length of {MAX_USER_INPUT_TEXT_CHARS} "
        f"characters ({int(actual_chars)} provided)."
    )


class QueuedInputAction(Enum):
    Plain = "plain"
    ParseSlash = "parse_slash"
    RunShell = "run_shell"


@dataclass(frozen=True)
class KeyEvent:
    code: str
    modifiers: tuple[str, ...] = ()
    kind: str = "press"
    char: str | None = None

    @classmethod
    def char_event(
        cls,
        char: str,
        *,
        modifiers: tuple[str, ...] | list[str] = (),
        kind: str = "press",
    ) -> "KeyEvent":
        return cls(code="char", modifiers=tuple(modifiers), kind=kind, char=char)

    @classmethod
    def key(
        cls,
        code: str,
        *,
        modifiers: tuple[str, ...] | list[str] = (),
        kind: str = "press",
    ) -> "KeyEvent":
        return cls(code=code, modifiers=tuple(modifiers), kind=kind)

    def binding_key(self) -> tuple[str, tuple[str, ...], str | None]:
        return (self.code.lower(), tuple(sorted(m.lower() for m in self.modifiers)), self.char)


@dataclass(frozen=True)
class InputResult:
    kind: str
    text: str | None = None
    text_elements: list[Any] = field(default_factory=list)
    action: QueuedInputAction | None = None
    command: Any = None
    args: str | None = None

    @classmethod
    def Submitted(cls, text: str, text_elements: list[Any] | None = None) -> "InputResult":
        return cls("Submitted", text=text, text_elements=list(text_elements or []))

    @classmethod
    def Queued(
        cls,
        text: str,
        text_elements: list[Any] | None = None,
        action: QueuedInputAction = QueuedInputAction.Plain,
    ) -> "InputResult":
        return cls("Queued", text=text, text_elements=list(text_elements or []), action=QueuedInputAction(action))

    @classmethod
    def Command(cls, command: Any) -> "InputResult":
        return cls("Command", command=command)

    @classmethod
    def ServiceTierCommand(cls, command: Any) -> "InputResult":
        return cls("ServiceTierCommand", command=command)

    @classmethod
    def CommandWithArgs(cls, command: Any, args: str, text_elements: list[Any] | None = None) -> "InputResult":
        return cls("CommandWithArgs", command=command, args=args, text_elements=list(text_elements or []))

    @classmethod
    def None_(cls) -> "InputResult":
        return cls("None")


def terminal_input_result_from_line(
    line: str,
    text_elements: list[Any] | None = None,
) -> InputResult:
    """Parse one completed terminal line using Rust composer semantics.

    Rust ``ChatComposer`` returns slash commands as structured ``InputResult``
    variants before ``chatwidget::slash_dispatch`` sees them.  The hybrid
    terminal reader must preserve that boundary instead of reducing every
    completed line to a user-turn string.
    """

    from ...slash_command import SlashCommand

    text = str(line).rstrip("\r\n")
    if "\n" not in text and text.startswith("/"):
        command_text, separator, args = text[1:].partition(" ")
        try:
            command = SlashCommand.parse(command_text)
        except ValueError:
            command = None
        if command is not None:
            trimmed_args = args.strip() if separator else ""
            if trimmed_args and command.supports_inline_args():
                return InputResult.CommandWithArgs(
                    command,
                    trimmed_args,
                    _rebase_inline_text_elements(text, args, text_elements or []),
                )
            if not trimmed_args:
                return InputResult.Command(command)
    return InputResult.Submitted(text)


@dataclass(frozen=True)
class ChatComposerConfig:
    popups_enabled: bool = True
    slash_commands_enabled: bool = True
    image_paste_enabled: bool = True

    @classmethod
    def default(cls) -> "ChatComposerConfig":
        return cls()

    @classmethod
    def plain_text(cls) -> "ChatComposerConfig":
        return cls(popups_enabled=False, slash_commands_enabled=False, image_paste_enabled=False)


@dataclass(frozen=True)
class ComposerDraftSnapshot:
    text: str
    text_elements: list[Any] = field(default_factory=list)
    local_images: list[Any] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)
    mention_bindings: list[Any] = field(default_factory=list)
    pending_pastes: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class TerminalComposerInputAction:
    """Text-only composer action for the terminal scrollback product path."""

    kind: str
    draft: str = ""
    line: str | None = None


@dataclass(frozen=True)
class TerminalCommandPopupInputAction:
    """Terminal slash-popup action planned by the chat composer owner."""

    kind: str
    draft: str | None = None
    command: str | None = None


@dataclass
class TerminalCommandPopupState:
    """Terminal slash-popup state owned by the chat composer boundary."""

    popup: CommandPopup
    visible: bool = False

    @classmethod
    def new(
        cls,
        flags: CommandPopupFlags | None = None,
        service_tier_commands: tuple[Any, ...] = (),
    ) -> "TerminalCommandPopupState":
        return cls(CommandPopup.new(flags or CommandPopupFlags(), service_tier_commands))

    def sync_draft(
        self,
        draft: str,
        *,
        cursor: int | None = None,
        active_view_present: bool = False,
    ) -> bool:
        """Sync popup visibility and filter from the current composer draft.

        Rust owner: ``codex-tui::bottom_pane::chat_composer::sync_popups``
        owns the command-popup lifecycle; ``command_popup`` owns filtering and
        selection internals.
        """

        if active_view_present:
            self.visible = False
            return False
        visible = terminal_command_popup_visible_for_draft(draft, cursor=cursor)
        self.visible = visible
        if visible:
            first_line = str(draft).split("\n", 1)[0]
            cursor = len(first_line) if cursor is None else max(0, min(int(cursor), len(first_line)))
            self.popup.on_composer_text_change(first_line[:cursor])
        return visible

    def hide(self) -> None:
        self.visible = False

    def selected_item(self) -> Any:
        return self.popup.selected_item()

    def move_up(self) -> None:
        self.popup.move_up()

    def move_down(self) -> None:
        self.popup.move_down()

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        if not self.visible:
            return []
        return list(self.popup.terminal_lines(width=width))


@dataclass(frozen=True)
class TerminalComposerProjection:
    lines: tuple[str, ...]
    cursor_row_offset: int
    cursor_column: int

    @property
    def line(self) -> str:
        """Return the first row for compatibility with single-line callers."""

        return self.lines[0]

    @property
    def height(self) -> int:
        return len(self.lines)


TERMINAL_COMPOSER_INPUT_CONTINUE = object()


def run_terminal_composer_input_action(
    action: TerminalComposerInputAction,
    *,
    render: Callable[[], Any],
    submit: Callable[[str], Any],
    interrupt: Callable[[], Any],
    eof: Callable[[], Any],
) -> Any:
    """Dispatch a terminal composer action to product-path effects.

    Rust ``bottom_pane::chat_composer`` owns the interpretation of composer
    input outcomes. The terminal runner supplies the concrete repaint,
    submission, and shutdown effects without branching on composer action
    variants itself.
    """

    if action.kind == "render":
        render()
        return TERMINAL_COMPOSER_INPUT_CONTINUE
    if action.kind == "submit":
        return submit(action.line if action.line is not None else "")
    if action.kind == "interrupt":
        return interrupt()
    if action.kind == "eof":
        return eof()
    return TERMINAL_COMPOSER_INPUT_CONTINUE


def run_terminal_composer_submit(
    line: str,
    *,
    clear_bottom_pane: Callable[[], Any],
) -> str:
    """Apply terminal product-path submit effects for a completed line."""

    clear_bottom_pane()
    return line


def run_terminal_composer_eof(
    *,
    clear_bottom_pane: Callable[[], Any],
) -> None:
    """Apply terminal product-path EOF effects for composer shutdown."""

    clear_bottom_pane()
    return None


@dataclass(frozen=True)
class TerminalComposerEffectRunner:
    """Runtime-bound terminal composer prompt/submit/EOF effect callbacks."""

    writer: TextIO
    clear_bottom_pane: Callable[[], Any]

    def write_nonterminal_prompt(self) -> None:
        run_terminal_composer_write_nonterminal_prompt(self.writer)

    def submit(self, line: str) -> str:
        return run_terminal_composer_submit(
            line,
            clear_bottom_pane=self.clear_bottom_pane,
        )

    def interrupt(self) -> None:
        return run_terminal_composer_interrupt()

    def eof(self) -> None:
        return run_terminal_composer_eof(
            clear_bottom_pane=self.clear_bottom_pane,
        )


def run_terminal_composer_interrupt() -> None:
    """Apply terminal product-path interrupt semantics."""

    raise KeyboardInterrupt


def run_terminal_composer_prompt_loop(
    source: Any,
    *,
    poll_timeout: float,
    apply_draft: Callable[[str], Any],
    check_resize: Callable[[], Any],
    render: Callable[[], Any],
    submit: Callable[[str], Any],
    interrupt: Callable[[], Any],
    eof: Callable[[], Any],
    handle_global_key: Callable[[str, str], bool] | None = None,
    record_submission: Callable[[str], Any] | None = None,
    initial_draft: str = "",
    composer: "ChatComposer | None" = None,
    handle_event: Callable[[str, str, float, bool], Any] | None = None,
) -> Any:
    """Run the terminal product-path composer input loop.

    Rust ``bottom_pane::chat_composer`` owns composer draft mutation and submit
    outcomes. The terminal runner supplies the event source and concrete
    terminal effects while this helper keeps the draft/render/submit sequence
    together with the composer boundary.
    """

    legacy_result_shape = composer is None and handle_event is None
    owner = composer or ChatComposer(
        text=str(initial_draft),
        disable_paste_burst=not bool(getattr(source, "detect_paste_bursts", False)),
    )
    if composer is not None:
        owner.set_text_content(str(initial_draft))
    seeded_line_prefix_pending = bool(initial_draft)
    paste_burst_enabled = bool(getattr(source, "detect_paste_bursts", False))

    def flush_paste_burst(now: float) -> bool:
        changed = paste_burst_enabled and owner.flush_paste_burst_if_due(now)
        if changed:
            apply_draft(owner.current_text())
            render()
        return bool(changed)

    apply_draft(owner.current_text())
    render()
    while True:
        event = source.poll(poll_timeout)
        check_resize()
        now = time.monotonic()
        if event is None:
            flush_paste_burst(now)
            continue

        # Fixed Rust commit 1c7832f, ChatComposer::handle_input_basic_with_time:
        # flush an expired held char or burst before handling every new key.
        # A console source may remain continuously readable, so relying only
        # on idle polls would let on_plain_char() replace an expired pending
        # first character and visibly drop ordinary typed text.
        flush_paste_burst(now)
        event_kind = getattr(event, "kind", "")
        if event_kind == "resize":
            check_resize()
            continue
        event_text = str(getattr(event, "text", ""))
        if event_kind == "line" and seeded_line_prefix_pending:
            event_text = owner.current_text() + event_text
            owner.clear_draft()
            seeded_line_prefix_pending = False
            apply_draft(owner.current_text())

        # Rust ``app::input`` receives global shortcuts before the composer.
        # Keep that ordering here so Ctrl+T opens the transcript without
        # mutating or submitting the current draft.
        if handle_global_key is not None and handle_global_key(event_kind, event_text):
            owner._flush_paste_before_modified_input()
            apply_draft(owner.current_text())
            render()
            continue

        before_event_text = owner.current_text()
        outcome = (
            handle_event(event_kind, event_text, now, paste_burst_enabled)
            if handle_event is not None
            else owner.handle_terminal_event(
                event_kind,
                event_text,
                now=now,
                detect_paste_bursts=paste_burst_enabled,
            )
        )
        if isinstance(outcome, InputResult):
            apply_draft(owner.current_text())
            if legacy_result_shape:
                if outcome.kind == "Command" and outcome.command is not None:
                    submitted = f"/{outcome.command.command()}\n"
                else:
                    submitted = before_event_text + "\n"
                if record_submission is not None:
                    record_submission(submitted)
                return submit(submitted)
            if outcome.kind == "Submitted":
                submitted = str(outcome.text or "") + "\n"
                if record_submission is not None:
                    record_submission(submitted)
                submit(submitted)
            elif record_submission is not None and outcome.command is not None:
                record_submission(f"/{outcome.command.command()}")
            return outcome
        action = outcome
        apply_draft(owner.current_text())
        result = run_terminal_composer_input_action(
            action,
            render=render,
            submit=submit,
            interrupt=interrupt,
            eof=eof,
        )
        if result is TERMINAL_COMPOSER_INPUT_CONTINUE:
            continue
        return result


def run_terminal_composer_blocking_line_prompt(
    *,
    read_line: Callable[[], str],
    apply_draft: Callable[[str], Any],
    check_resize: Callable[[], Any],
    render: Callable[[], Any],
    clear_bottom_pane: Callable[[], Any],
    record_submission: Callable[[str], Any] | None = None,
    initial_draft: str = "",
) -> str | None:
    """Run the blocking-line fallback for terminal composer input.

    This preserves the same terminal product-path sequence as the polled
    composer loop: clear the draft, render the bottom pane, read one input
    line, process a resize tick, and clear the live pane before returning.
    """

    apply_draft(str(initial_draft))
    render()
    line = read_line()
    check_resize()
    clear_bottom_pane()
    if line == "":
        return None
    submitted = str(initial_draft) + line
    if record_submission is not None:
        record_submission(submitted)
    return submitted


def run_terminal_composer_write_nonterminal_prompt(writer: TextIO) -> None:
    """Write the non-TTY fallback prompt owned by the composer boundary."""

    writer.write("\n\u203a ")
    writer.flush()


def run_terminal_composer_read_prompt(
    *,
    terminal_active: bool,
    get_input_source: Callable[[], Any],
    read_line: Callable[[], str],
    write_nonterminal_prompt: Callable[[], Any],
    apply_draft: Callable[[str], Any],
    check_resize: Callable[[], Any],
    render: Callable[[], Any],
    clear_bottom_pane: Callable[[], Any],
    submit: Callable[[str], Any],
    interrupt: Callable[[], Any],
    eof: Callable[[], Any],
    poll_timeout: float = 0.1,
    handle_global_key: Callable[[str, str], bool] | None = None,
    record_submission: Callable[[str], Any] | None = None,
    initial_draft: str = "",
    composer: "ChatComposer | None" = None,
    handle_event: Callable[[str, str, float, bool], Any] | None = None,
) -> Any:
    """Read one terminal product-path composer prompt.

    Rust ``bottom_pane::chat_composer`` owns the prompt input lifecycle and
    submit/EOF/interrupt outcomes. ``tui::tui`` supplies terminal IO callbacks
    and the event source.
    """

    if terminal_active:
        source = get_input_source()
        if source is None:
            return run_terminal_composer_blocking_line_prompt(
                read_line=read_line,
                apply_draft=apply_draft,
                check_resize=check_resize,
                render=render,
                clear_bottom_pane=clear_bottom_pane,
                record_submission=record_submission,
                initial_draft=initial_draft,
            )
        return run_terminal_composer_prompt_loop(
            source,
            poll_timeout=poll_timeout,
            apply_draft=apply_draft,
            check_resize=check_resize,
            render=render,
            submit=submit,
            interrupt=interrupt,
            eof=eof,
            handle_global_key=handle_global_key,
            record_submission=record_submission,
            initial_draft=initial_draft,
            composer=composer,
            handle_event=handle_event,
        )

    write_nonterminal_prompt()
    line = read_line()
    if line == "":
        return None
    submitted = str(initial_draft) + line
    if record_submission is not None:
        record_submission(submitted)
    return submitted


@dataclass
class TerminalComposerPromptReader:
    """Runtime-bound terminal composer prompt reader callback package."""

    terminal_active: Callable[[], bool]
    get_input_source: Callable[[], Any]
    read_line: Callable[[], str]
    write_nonterminal_prompt: Callable[[], Any]
    apply_draft: Callable[[str], Any]
    check_resize: Callable[[], Any]
    render: Callable[[], Any]
    clear_bottom_pane: Callable[[], Any]
    submit: Callable[[str], Any]
    interrupt: Callable[[], Any]
    eof: Callable[[], Any]
    composer: "ChatComposer | None" = None
    handle_event: Callable[[str, str, float, bool], Any] | None = None
    handle_global_key: Callable[[str, str], bool] | None = None
    record_submission: Callable[[str], Any] | None = None
    poll_timeout: float = 0.1
    _pending_draft: str = field(default="", init=False, repr=False)

    def seed_draft(self, text: str) -> None:
        """Seed the next composer read without submitting a user turn."""

        self._pending_draft = str(text)

    def read(self) -> Any:
        initial_draft = self._pending_draft
        self._pending_draft = ""
        result = run_terminal_composer_read_prompt(
            terminal_active=self.terminal_active(),
            get_input_source=self.get_input_source,
            read_line=self.read_line,
            write_nonterminal_prompt=self.write_nonterminal_prompt,
            apply_draft=self.apply_draft,
            check_resize=self.check_resize,
            render=self.render,
            clear_bottom_pane=self.clear_bottom_pane,
            submit=self.submit,
            interrupt=self.interrupt,
            eof=self.eof,
            poll_timeout=self.poll_timeout,
            handle_global_key=self.handle_global_key,
            record_submission=self.record_submission,
            initial_draft=initial_draft,
            composer=self.composer,
            handle_event=self.handle_event,
        )
        if isinstance(result, InputResult) or result is None:
            return result
        return terminal_input_result_from_line(str(result))


def terminal_composer_draft_cleared() -> str:
    """Return the empty terminal product-path composer draft."""

    return ""


def terminal_composer_submitted_line(draft: str) -> str:
    """Return the line submitted by pressing Enter in the terminal composer."""

    return str(draft) + "\n"


def terminal_composer_line_text(draft: str) -> str:
    """Return the single-line terminal rendering of the composer draft."""

    visible_draft = str(draft).replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    return f"\u203a {visible_draft}"


def terminal_composer_projection(
    draft: str | TextArea | DraftState | "ChatComposer",
    columns: int,
) -> TerminalComposerProjection:
    """Project the terminal composer into wrapped live-pane rows and cursor.

    Rust owner: ``codex-tui::bottom_pane::chat_composer`` owns composer text
    projection before the terminal surface adapts it into the live viewport.
    """

    if isinstance(draft, ChatComposer):
        textarea = draft.draft.textarea
        textarea_state = draft.draft.textarea_state
    elif isinstance(draft, DraftState):
        textarea = draft.textarea
        textarea_state = draft.textarea_state
    elif isinstance(draft, TextArea):
        textarea = draft
        textarea_state = TextAreaState()
    else:
        textarea = TextArea.new()
        textarea.set_text_clearing_elements(str(draft))
        textarea.set_cursor(len(textarea.text()))
        textarea_state = TextAreaState()

    safe_columns = max(1, int(columns))
    prefix = "\u203a "
    continuation = " " * _terminal_display_width(prefix)
    content_width = max(1, safe_columns - _terminal_display_width(prefix) - 1)
    ranges = textarea.wrapped_lines(content_width)
    wrapped = tuple(textarea.text()[line.start : line.stop].rstrip() for line in ranges)
    lines = tuple(
        (prefix if index == 0 else continuation) + row
        for index, row in enumerate(wrapped)
    )
    cursor = textarea.cursor_pos_with_state(
        {
            "x": _terminal_display_width(prefix),
            "y": 0,
            "width": content_width,
            "height": max(1, len(lines)),
        },
        textarea_state,
    )
    cursor_x, cursor_y = cursor or (_terminal_display_width(prefix), 0)
    cursor_row_offset = max(0, min(int(cursor_y), len(lines) - 1))
    cursor_column = min(safe_columns, max(1, 1 + int(cursor_x)))
    return TerminalComposerProjection(
        lines=lines,
        cursor_row_offset=cursor_row_offset,
        cursor_column=cursor_column,
    )


def _terminal_wrap_display_width(text: str, width: int) -> tuple[str, ...]:
    """Wrap composer text using terminal-cell width and first-fit word breaks."""

    safe_width = max(1, int(width))
    rows: list[str] = []
    logical_lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for logical in logical_lines:
        remaining = logical
        if not remaining:
            rows.append("")
            continue
        while remaining:
            consumed = 0
            used = 0
            last_space = -1
            for index, char in enumerate(remaining):
                char_width = _terminal_char_display_width(char)
                if used + char_width > safe_width:
                    break
                used += char_width
                consumed = index + 1
                if char.isspace():
                    last_space = consumed
            if consumed >= len(remaining):
                rows.append(remaining)
                break
            split_at = last_space if last_space > 0 else max(1, consumed)
            rows.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
    return tuple(rows or ("",))


def terminal_popup_key(event_kind: str, event_text: str = "") -> str:
    """Map terminal product-path input events into popup navigation keys.

    Rust owner: ``codex-tui::bottom_pane::chat_composer`` performs popup-first
    key routing after ``tui::event_stream`` has normalized terminal payloads.
    """

    kind = str(event_kind).lower()
    raw_text = str(event_text)
    text = raw_text.lower()
    if kind in {"text", "line", "paste"}:
        if raw_text in {"\r", "\n", "\r\n"} or text in {"enter", "return"}:
            return "enter"
        if raw_text == "\t":
            return "tab"
        if raw_text == "\x1b" or text in {"escape", "esc"}:
            return "esc"
        if kind == "line" and raw_text == "":
            return "enter"
        return ""
    if kind == "key":
        if text in {"up", "down", "tab", "\t", "enter", "return", "\r", "\n", "escape", "esc", "\x1b"}:
            if text in {"enter", "return", "\r", "\n"}:
                return "enter"
            if text in {"escape", "\x1b"}:
                return "esc"
            return "tab" if text == "\t" else text
        if text:
            # Active key-capture/debug views need the complete normalized key
            # name (for example ``f12``), while list views safely ignore keys
            # they do not own.
            return text
    if kind in {"up", "down", "tab", "enter", "return", "esc", "escape"}:
        if kind == "return":
            return "enter"
        if kind == "escape":
            return "esc"
        return kind
    return ""


def terminal_command_popup_input_action(
    draft: str,
    key: str,
    *,
    selected_command: Any = None,
) -> TerminalCommandPopupInputAction:
    """Plan popup handling for terminal slash command input.

    Rust owner: ``codex-tui::bottom_pane::chat_composer`` routes keys to the
    active slash popup before normal input.  ``command_popup`` owns selection
    mutation; this helper owns which action a popup key requests.
    """

    normalized_key = str(key).lower()
    if normalized_key == "up":
        return TerminalCommandPopupInputAction("move_up")
    if normalized_key == "down":
        return TerminalCommandPopupInputAction("move_down")
    if normalized_key == "tab":
        command = _terminal_selected_command_name(selected_command)
        if not command:
            return TerminalCommandPopupInputAction("handled", str(draft))
        return TerminalCommandPopupInputAction("complete", f"/{command} ", command)
    if normalized_key == "enter":
        command = _terminal_selected_command_name(selected_command) or _terminal_draft_command_name(draft)
        if command:
            return TerminalCommandPopupInputAction("open_command_view", "", command)
    return TerminalCommandPopupInputAction("unhandled", str(draft))


def run_terminal_command_popup_input_action(
    state: TerminalCommandPopupState,
    draft: str,
    key: str,
    *,
    open_command_view: Callable[[str], Any | None] | None = None,
    show_selection_view: Callable[[Any], Any] | None = None,
) -> str | InputResult | None:
    """Apply a terminal slash-popup key action within the composer owner.

    Rust owner: ``codex-tui::bottom_pane::chat_composer`` decides whether a
    popup key moves selection, completes the highlighted slash command, opens a
    command-owned view, or falls through to normal composer input. The terminal
    controller supplies only concrete view-opening callbacks.
    """

    if not state.visible:
        return None

    action = terminal_command_popup_input_action(
        draft,
        key,
        selected_command=state.selected_item(),
    )
    if action.kind == "move_up":
        state.move_up()
        return draft
    if action.kind == "move_down":
        state.move_down()
        return draft
    if action.kind == "complete":
        return action.draft if action.draft is not None else draft
    if action.kind == "open_command_view":
        params = open_command_view(action.command or "") if open_command_view is not None else None
        if params is not None and show_selection_view is not None:
            show_selection_view(params)
            return action.draft if action.draft is not None else ""
        from ...slash_command import SlashCommand

        try:
            command = SlashCommand.parse(action.command or "")
        except ValueError:
            return None
        state.hide()
        return InputResult.Command(command)
    if action.kind == "handled":
        return action.draft if action.draft is not None else draft
    return None


@dataclass(frozen=True)
class ChatComposerRenderSnapshot:
    area: Any = None
    mask_char: str | None = None
    textarea_right_reserve: int = 0
    active_popup: str = "none"
    prompt: str = ">"
    text: str = ""
    placeholder: str | None = None
    remote_image_urls: tuple[str, ...] = ()
    footer: tuple[str, ...] = ()
    input_enabled: bool = True


class ChatComposer:
    """Semantic entry boundary for Rust's full composer state machine."""

    def __init__(self, *args: Any, config: ChatComposerConfig | None = None, **kwargs: Any) -> None:
        from ..chat_composer_history import ChatComposerHistory

        self.config = ChatComposerConfig.default() if config is None else config
        self.draft = DraftState.new()
        self.draft.input_enabled = bool(kwargs.pop("input_enabled", True))
        self.draft.input_disabled_placeholder = kwargs.pop("input_disabled_placeholder", None)
        self.draft.is_bash_mode = bool(kwargs.pop("is_bash_mode", False))
        self.draft.disable_paste_burst = bool(kwargs.pop("disable_paste_burst", False))
        self.placeholder_text = kwargs.pop("placeholder_text", "Ask Codex to do anything")
        self.is_task_running = bool(kwargs.pop("is_task_running", False))
        self.history_search_active = bool(kwargs.pop("history_search_active", False))
        self.active_popup = str(kwargs.pop("active_popup", "none")).lower()
        self.history_search_previous_keys = {
            _binding_key(item)
            for item in kwargs.pop(
                "history_search_previous_keys",
                [KeyEvent.char_event("r", modifiers=("control",))],
            )
        }
        self.remote_image_urls = list(kwargs.pop("remote_image_urls", []))
        self.footer = list(kwargs.pop("footer", []))
        self.handlers: dict[str, Callable[[KeyEvent], tuple[InputResult, bool]]] = dict(
            kwargs.pop("handlers", {})
        )
        self.dispatch_log: list[str] = []
        self.errors: list[str] = []
        self.sync_count = 0
        self.reset_vim_count = 0
        self.render_log: list[tuple[str, Any, str | None, int]] = []
        initial_text = str(kwargs.pop("text", ""))
        initial_elements = list(kwargs.pop("text_elements", []))
        if initial_elements:
            self.draft.textarea.set_text_with_elements(initial_text, initial_elements)
        else:
            self.draft.textarea.set_text_clearing_elements(initial_text)
        self.draft.textarea.set_cursor(len(initial_text))
        self.draft.pending_pastes = list(kwargs.pop("pending_pastes", []))
        self.history = ChatComposerHistory.new()
        self.history_lookup: Callable[[int, int], object | None] | None = None
        self.command_popup_state = TerminalCommandPopupState.new(
            kwargs.pop("command_popup_flags", None)
        )

    @classmethod
    def new_with_config(cls, *args: Any, config: ChatComposerConfig | None = None, **kwargs: Any) -> "ChatComposer":
        return cls(*args, config=config or ChatComposerConfig.default(), **kwargs)

    def handle_key_event(self, key_event: KeyEvent | dict[str, Any] | str, **kwargs: Any) -> tuple[InputResult, bool]:
        event = _coerce_key_event(key_event, **kwargs)
        if not self.input_enabled:
            return (InputResult.None_(), False)
        if event.kind.lower() == "release":
            return (InputResult.None_(), False)
        if self.history_search_active:
            return self._dispatch("history_search", event)
        if self.is_history_search_key(event):
            return self.begin_history_search()

        target = {
            "command": "slash_popup",
            "file": "file_popup",
            "skill": "skill_popup",
            "mentionv2": "mentions_v2_popup",
            "mention_v2": "mentions_v2_popup",
        }.get(self.active_popup, "without_popup")
        if target == "without_popup" and self.active_popup not in {"none", "", "without_popup"}:
            self.dispatch_log.append(self.active_popup)
            return (InputResult.None_(), False)
        result = self._dispatch(target, event)
        self.reset_vim_mode_after_successful_dispatch(result[0])
        self.sync_popups()
        return result

    def is_history_search_key(self, key_event: KeyEvent) -> bool:
        return key_event.binding_key() in self.history_search_previous_keys

    def begin_history_search(self) -> tuple[InputResult, bool]:
        self.history_search_active = True
        self.dispatch_log.append("begin_history_search")
        return (InputResult.None_(), True)

    def reset_vim_mode_after_successful_dispatch(self, result: InputResult) -> None:
        if result.kind != "None":
            self.reset_vim_count += 1

    def sync_popups(self, *, active_view_present: bool = False) -> None:
        self.sync_count += 1
        if not self.config.popups_enabled or not self.config.slash_commands_enabled:
            self.command_popup_state.hide()
            if self.active_popup == "command":
                self.active_popup = "none"
            return
        visible = self.command_popup_state.sync_draft(
            self.current_text(),
            cursor=self.draft.textarea.cursor(),
            active_view_present=active_view_present,
        )
        if visible:
            self.active_popup = "command"
        elif self.active_popup == "command":
            self.active_popup = "none"

    def render(self, area: Any = None, buf: MutableSequence[Any] | None = None) -> ChatComposerRenderSnapshot:
        return self.render_with_mask(area, buf, None)

    def render_with_mask(
        self,
        area: Any = None,
        buf: MutableSequence[Any] | None = None,
        mask_char: str | None = None,
    ) -> ChatComposerRenderSnapshot:
        return self.render_with_mask_and_textarea_right_reserve(area, buf, mask_char, 0)

    def render_with_mask_and_textarea_right_reserve(
        self,
        area: Any = None,
        buf: MutableSequence[Any] | None = None,
        mask_char: str | None = None,
        textarea_right_reserve: int = 0,
    ) -> ChatComposerRenderSnapshot:
        self.render_log.append(("render_with_mask_and_textarea_right_reserve", area, mask_char, int(textarea_right_reserve)))
        text = self.current_text()
        visible_text = text if mask_char is None else mask_char * len(text)
        placeholder = None
        if not self.input_enabled:
            placeholder = self.input_disabled_placeholder or "Input disabled."
        elif not text and not self.is_bash_mode:
            placeholder = self.placeholder_text
        snapshot = ChatComposerRenderSnapshot(
            area=area,
            mask_char=mask_char,
            textarea_right_reserve=int(textarea_right_reserve),
            active_popup=self.active_popup,
            prompt="!" if self.is_bash_mode else ">",
            text=visible_text,
            placeholder=placeholder,
            remote_image_urls=tuple(self.remote_image_urls),
            footer=tuple(self.footer),
            input_enabled=self.input_enabled,
        )
        if buf is not None and hasattr(buf, "append"):
            buf.append(snapshot)
        return snapshot

    def _dispatch(self, target: str, key_event: KeyEvent) -> tuple[InputResult, bool]:
        self.dispatch_log.append(target)
        handler = self.handlers.get(target)
        if handler is not None:
            return handler(key_event)
        if target == "slash_popup" and key_event.code.lower() in {
            "char",
            "left",
            "right",
            "home",
            "end",
            "backspace",
            "delete",
        }:
            return self._dispatch_without_popup(key_event)
        if target == "without_popup":
            return self._dispatch_without_popup(key_event)
        return (InputResult.None_(), False)

    def _dispatch_without_popup(self, key_event: KeyEvent) -> tuple[InputResult, bool]:
        code = key_event.code.lower().replace("_", "-")
        if code == "char" and key_event.char is not None:
            self.insert_text(key_event.char)
            return (InputResult.None_(), True)
        if code == "enter" and _has_modifier(key_event, "shift"):
            self.draft.textarea.input("enter")
            return (InputResult.None_(), True)
        if code == "enter" and not key_event.modifiers:
            slash_result = terminal_input_result_from_line(
                self.current_text(),
                self.text_elements,
            )
            if slash_result.kind in {"Command", "CommandWithArgs", "ServiceTierCommand"}:
                self.record_submission(self.current_text())
                self.clear_draft()
                return (slash_result, True)
            prepared = self.prepare_submission_text(record_history=True)
            if prepared is None:
                return (InputResult.None_(), bool(self.errors))
            text, text_elements = prepared
            self.record_submission(self.current_text())
            self.clear_draft()
            return (InputResult.Submitted(text, text_elements), True)

        before = (self.current_text(), self.draft.textarea.cursor())
        self.draft.textarea.input(code)
        self._retain_live_pending_pastes()
        after = (self.current_text(), self.draft.textarea.cursor())
        return (InputResult.None_(), before != after)

    def current_text(self) -> str:
        return self.draft.textarea.text()

    @property
    def input_enabled(self) -> bool:
        return self.draft.input_enabled

    @input_enabled.setter
    def input_enabled(self, enabled: bool) -> None:
        self.draft.input_enabled = bool(enabled)

    @property
    def input_disabled_placeholder(self) -> str | None:
        return self.draft.input_disabled_placeholder

    @input_disabled_placeholder.setter
    def input_disabled_placeholder(self, placeholder: str | None) -> None:
        self.draft.input_disabled_placeholder = placeholder

    @property
    def is_bash_mode(self) -> bool:
        return self.draft.is_bash_mode

    @is_bash_mode.setter
    def is_bash_mode(self, enabled: bool) -> None:
        self.draft.is_bash_mode = bool(enabled)

    @property
    def text_elements(self) -> list[Any]:
        return list(self.draft.textarea.text_elements())

    @text_elements.setter
    def text_elements(self, elements: list[Any]) -> None:
        cursor = self.draft.textarea.cursor()
        self.draft.textarea.set_text_with_elements(self.current_text(), list(elements))
        self.draft.textarea.set_cursor(cursor)

    @property
    def pending_pastes(self) -> list[tuple[str, str]]:
        return self.draft.pending_pastes

    @pending_pastes.setter
    def pending_pastes(self, pending: list[tuple[str, str]]) -> None:
        self.draft.pending_pastes = list(pending)

    def set_text_content(
        self,
        text: str,
        text_elements: list[Any] | None = None,
        local_image_paths: list[Any] | None = None,
    ) -> None:
        source = str(text)
        if text_elements:
            self.draft.textarea.set_text_with_elements(source, list(text_elements))
        else:
            self.draft.textarea.set_text_clearing_elements(source)
        self.draft.textarea.set_cursor(len(source))
        self.sync_popups()

    def clear_draft(self) -> None:
        self.draft.textarea.set_text_clearing_elements("")
        self.draft.textarea.set_cursor(0)
        self.draft.pending_pastes.clear()
        self.command_popup_state.hide()
        if self.active_popup == "command":
            self.active_popup = "none"

    def insert_text(self, text: str) -> bool:
        normalized = _normalize_pasted_text(str(text))
        if not normalized or not self.input_enabled:
            return False
        if len(normalized) == 1:
            self.draft.textarea.input(normalized)
        else:
            self.draft.textarea.insert_str(normalized)
        return True

    def cursor(self) -> int:
        return self.draft.textarea.cursor()

    def set_cursor(self, cursor: int) -> None:
        self.draft.textarea.set_cursor(cursor)
        self.sync_popups()

    def cursor_pos(self, area: Any) -> tuple[int, int] | None:
        if not self.input_enabled:
            return None
        return self.draft.textarea.cursor_pos_with_state(area, self.draft.textarea_state)

    def terminal_projection(self, columns: int) -> TerminalComposerProjection:
        return terminal_composer_projection(self, columns)

    def set_remote_image_urls(self, urls: list[str]) -> None:
        self.remote_image_urls = list(urls)

    def take_remote_image_urls(self) -> list[str]:
        urls = self.remote_image_urls
        self.remote_image_urls = []
        return urls

    def remote_image_urls_value(self) -> list[str]:
        return list(self.remote_image_urls)

    def set_pending_pastes(self, pending_pastes: list[tuple[str, str]]) -> None:
        self.draft.pending_pastes = list(pending_pastes)

    def pending_pastes_value(self) -> list[tuple[str, str]]:
        return list(self.draft.pending_pastes)

    def handle_paste(self, pasted: str) -> bool:
        if not self.input_enabled:
            return False
        normalized = _normalize_pasted_text(str(pasted))
        if not normalized:
            return False
        if len(normalized) > LARGE_PASTE_CHAR_THRESHOLD:
            placeholder = self.next_large_paste_placeholder(len(normalized))
            self.draft.textarea.insert_element(placeholder)
            self.draft.pending_pastes.append((placeholder, normalized))
        else:
            self.draft.textarea.insert_str(normalized)
        self.draft.paste_burst.clear_after_explicit_paste()
        self.sync_popups()
        return True

    def next_large_paste_placeholder(self, char_count: int) -> str:
        base = f"[Pasted Content {int(char_count)} chars]"
        used = {placeholder for placeholder, _payload in self.draft.pending_pastes}
        if base not in used:
            return base
        suffix = 2
        while f"{base} #{suffix}" in used:
            suffix += 1
        return f"{base} #{suffix}"

    def current_text_with_pending(self) -> str:
        expanded, _elements = expand_pending_pastes(
            self.current_text(),
            self.text_elements,
            self.draft.pending_pastes,
        )
        return expanded

    def prepare_submission_text(self, record_history: bool = True) -> tuple[str, list[Any]] | None:
        expanded, elements = expand_pending_pastes(
            self.current_text(),
            self.text_elements,
            self.draft.pending_pastes,
        )
        trimmed, elements = _trim_and_rebase_elements(expanded, elements)
        if not trimmed and not self.remote_image_urls:
            return None
        actual_chars = len(trimmed)
        if actual_chars > MAX_USER_INPUT_TEXT_CHARS:
            self.errors.append(user_input_too_large_message(actual_chars))
            return None
        return trimmed, elements

    def _retain_live_pending_pastes(self) -> None:
        text = self.current_text()
        self.draft.pending_pastes[:] = [
            item for item in self.draft.pending_pastes if item[0] in text
        ]

    def record_submission(self, text: str) -> None:
        from ..chat_composer_history import HistoryEntry

        self.history.record_local_submission(HistoryEntry.new(str(text).rstrip("\r\n")))

    def configure_history(
        self,
        thread_id: object,
        log_id: int,
        entry_count: int,
        lookup: Callable[[int, int], object | None] | None,
    ) -> None:
        self.history.set_metadata(thread_id, int(log_id), int(entry_count))
        self.history_lookup = lookup

    def _resolve_pending_history_entry(self, entry: Any) -> Any:
        if entry is not None or self.history_lookup is None:
            return entry
        offset = self.history.history_cursor
        log_id = self.history.persistent_log_id
        if offset is None or log_id is None or offset >= self.history.persistent_entry_count:
            return None
        fetched = self.history_lookup(log_id, offset)
        text = getattr(fetched, "text", fetched)
        response = self.history.on_entry_response(
            log_id,
            offset,
            None if text is None else str(text),
        )
        return response.entry if response.kind == "Found" else None

    def navigate_history(self, key: str) -> bool:
        if key not in {"up", "down"} or self.command_popup_state.visible:
            return False
        text = self.current_text()
        cursor_bytes = len(text[: self.cursor()].encode("utf-8"))
        if not self.history.should_handle_navigation(text, cursor_bytes):
            return False
        entry = self.history.navigate_up() if key == "up" else self.history.navigate_down()
        entry = self._resolve_pending_history_entry(entry)
        if entry is not None:
            self.set_text_content(entry.text, entry.text_elements, entry.local_image_paths)
            self.draft.pending_pastes = list(entry.pending_pastes)
            self.remote_image_urls = list(entry.remote_image_urls)
        return True

    def flush_paste_burst_if_due(self, now: float | None = None) -> bool:
        flushed = self.draft.paste_burst.flush_if_due(time.monotonic() if now is None else now)
        if flushed.kind is FlushResultKind.PASTE:
            return self.handle_paste(str(flushed.value or ""))
        if flushed.kind is FlushResultKind.TYPED:
            changed = self.insert_text(str(flushed.value or ""))
            if changed:
                self.sync_popups()
            return changed
        return False

    def _flush_paste_before_modified_input(self) -> bool:
        pasted = self.draft.paste_burst.flush_before_modified_input()
        return False if pasted is None else self.handle_paste(pasted)

    def _handle_plain_char(self, char: str, now: float) -> bool:
        burst = self.draft.paste_burst
        if self.draft.disable_paste_burst:
            changed = self.insert_text(char)
            if changed:
                self.sync_popups()
            return changed

        if not char.isascii():
            if burst.try_append_char_if_active(char, now):
                return False
            changed = self._flush_paste_before_modified_input()
            decision = burst.on_plain_char_no_hold(now)
            if decision == CharDecision.BUFFER_APPEND:
                burst.append_char_to_buffer(char, now)
                return changed
            if decision is not None and decision.kind == "BeginBuffer":
                cursor = self.cursor()
                before = self.current_text()[:cursor]
                grab = burst.decide_begin_buffer(now, before, int(decision.retro_chars or 0))
                if grab is not None:
                    start = len(before.encode("utf-8")[: grab.start_byte].decode("utf-8"))
                    if grab.grabbed:
                        self.draft.textarea.replace_range(range(start, cursor), "")
                    burst.append_char_to_buffer(char, now)
                    self.sync_popups()
                    return True
            inserted = self.insert_text(char)
            if inserted:
                self.sync_popups()
            return changed or inserted

        decision = burst.on_plain_char(char, now)
        if decision == CharDecision.RETAIN_FIRST_CHAR:
            return False
        if decision in {CharDecision.BEGIN_BUFFER_FROM_PENDING, CharDecision.BUFFER_APPEND}:
            burst.append_char_to_buffer(char, now)
            return False
        if decision.kind == "BeginBuffer":
            cursor = self.cursor()
            before = self.current_text()[:cursor]
            grab = burst.decide_begin_buffer(now, before, int(decision.retro_chars or 0))
            if grab is not None:
                start = len(before.encode("utf-8")[: grab.start_byte].decode("utf-8"))
                if grab.grabbed:
                    self.draft.textarea.replace_range(range(start, cursor), "")
                burst.append_char_to_buffer(char, now)
                self.sync_popups()
                return True
        changed = self.insert_text(char)
        if changed:
            self.sync_popups()
        return changed

    def handle_terminal_event(
        self,
        event_kind: str,
        event_text: str = "",
        *,
        now: float | None = None,
        detect_paste_bursts: bool = False,
        active_view_present: bool = False,
        open_command_view: Callable[[str], Any | None] | None = None,
        show_selection_view: Callable[[Any], Any] | None = None,
    ) -> TerminalComposerInputAction | InputResult:
        """Handle one normalized terminal event through the Rust composer owner."""

        timestamp = time.monotonic() if now is None else now
        changed = self.flush_paste_burst_if_due(timestamp) if detect_paste_bursts else False
        kind = str(event_kind).lower()
        text = str(event_text)
        if kind == "release":
            return TerminalComposerInputAction("render" if changed else "continue", self.current_text())
        if kind == "resize":
            return TerminalComposerInputAction("continue", self.current_text())
        if kind == "eof":
            return TerminalComposerInputAction("eof", self.current_text())
        if kind == "interrupt":
            return TerminalComposerInputAction("interrupt", self.current_text())
        if kind == "paste":
            changed = self._flush_paste_before_modified_input() or changed
            changed = self.handle_paste(text) or changed
            return TerminalComposerInputAction("render" if changed else "continue", self.current_text())

        if kind == "line":
            self.set_text_content(text.rstrip("\r\n"))
            return self.handle_terminal_event(
                "enter",
                now=timestamp,
                detect_paste_bursts=False,
                active_view_present=active_view_present,
                open_command_view=open_command_view,
                show_selection_view=show_selection_view,
            )

        popup_key = terminal_popup_key(kind, text)
        if self.command_popup_state.visible and popup_key in {"up", "down", "tab", "enter", "esc"}:
            if popup_key == "esc":
                self.command_popup_state.hide()
                self.active_popup = "none"
                return TerminalComposerInputAction("render", self.current_text())
            popup_result = run_terminal_command_popup_input_action(
                self.command_popup_state,
                self.current_text(),
                popup_key,
                open_command_view=open_command_view,
                show_selection_view=show_selection_view,
            )
            if isinstance(popup_result, InputResult):
                self.record_submission(f"/{popup_result.command.command()}")
                self.clear_draft()
                return popup_result
            if popup_result is not None:
                if popup_result != self.current_text():
                    self.set_text_content(popup_result)
                return TerminalComposerInputAction("render", self.current_text())

        if popup_key in {"up", "down"} and self.navigate_history(popup_key):
            return TerminalComposerInputAction("render", self.current_text())

        if detect_paste_bursts and kind == "enter":
            if self.draft.paste_burst.append_newline_if_active(timestamp):
                return TerminalComposerInputAction("continue", self.current_text())
            if self.draft.paste_burst.newline_should_insert_instead_of_submit(timestamp):
                self.draft.textarea.insert_str("\n")
                self.draft.paste_burst.extend_window(timestamp)
                self.sync_popups(active_view_present=active_view_present)
                return TerminalComposerInputAction("render", self.current_text())

        if detect_paste_bursts and kind == "text" and len(text) == 1 and text >= " ":
            if self.current_text().startswith("/") or (not self.current_text() and text == "/"):
                changed = self._flush_paste_before_modified_input() or changed
                changed = self.insert_text(text) or changed
                self.sync_popups(active_view_present=active_view_present)
                return TerminalComposerInputAction("render" if changed else "continue", self.current_text())
            changed = self._handle_plain_char(text, timestamp) or changed
            return TerminalComposerInputAction("render" if changed else "continue", self.current_text())

        if detect_paste_bursts and kind not in {"text", "enter"}:
            changed = self._flush_paste_before_modified_input() or changed

        if kind == "text":
            if text in {"\r", "\n", "\r\n"}:
                kind = "enter"
            elif text == "\t":
                kind = "tab"
            elif text:
                changed = self.insert_text(text) or changed
                self.sync_popups(active_view_present=active_view_present)
                return TerminalComposerInputAction("render" if changed else "continue", self.current_text())
            else:
                return TerminalComposerInputAction("render" if changed else "continue", self.current_text())
        elif kind == "key":
            kind = text.lower().replace("_", "-")
        else:
            kind = kind.replace("_", "-")

        result, redraw = self.handle_key_event(KeyEvent.key(kind))
        if result.kind != "None":
            return result
        return TerminalComposerInputAction(
            "render" if changed or redraw else "continue",
            self.current_text(),
        )


def expand_pending_pastes(
    text: str,
    text_elements: list[Any],
    pending_pastes: list[tuple[str, str]],
) -> tuple[str, list[Any]]:
    expanded = str(text)
    rebuilt_elements = list(text_elements or [])
    for placeholder, payload in pending_pastes:
        expanded = expanded.replace(placeholder, payload, 1)
    return expanded, rebuilt_elements


def _trim_and_rebase_elements(text: str, elements: list[Any]) -> tuple[str, list[Any]]:
    left_trimmed = len(text) - len(text.lstrip())
    trimmed = text.strip()
    if not left_trimmed:
        return trimmed, elements
    rebased: list[Any] = []
    for element in elements:
        if isinstance(element, dict) and "range" in element:
            start, end = element["range"]
            new_start = max(0, int(start) - left_trimmed)
            new_end = max(new_start, int(end) - left_trimmed)
            updated = dict(element)
            updated["range"] = (new_start, new_end)
            rebased.append(updated)
        else:
            rebased.append(element)
    return trimmed, rebased


def _rebase_inline_text_elements(
    full_text: str,
    raw_args: str,
    elements: list[Any],
) -> list[Any]:
    """Rebase textarea element ranges from a slash draft to trimmed args."""

    if not raw_args or not elements:
        return []
    raw_start = len(full_text) - len(raw_args)
    leading_trim = len(raw_args) - len(raw_args.lstrip())
    args_start = raw_start + leading_trim
    args_end = args_start + len(raw_args.strip())
    rebased: list[Any] = []
    for element in elements:
        bounds = _terminal_element_bounds(element)
        if bounds is None:
            continue
        start, end = bounds
        clipped_start = max(start, args_start)
        clipped_end = min(end, args_end)
        if clipped_start >= clipped_end:
            continue
        next_start = clipped_start - args_start
        next_end = clipped_end - args_start
        if isinstance(element, dict):
            updated = dict(element)
            byte_range = updated.get("byte_range")
            if isinstance(byte_range, dict):
                updated["byte_range"] = {**byte_range, "start": next_start, "end": next_end}
            elif "range" in updated:
                updated["range"] = (next_start, next_end)
            else:
                updated["byte_range"] = {"start": next_start, "end": next_end}
            rebased.append(updated)
            continue
        map_range = getattr(element, "map_range", None)
        if callable(map_range):
            from pycodex.protocol.user_input import ByteRange

            rebased.append(map_range(lambda _range: ByteRange(next_start, next_end)))
    return rebased


def _terminal_element_bounds(element: Any) -> tuple[int, int] | None:
    raw = element.get("byte_range", element.get("range")) if isinstance(element, dict) else getattr(element, "byte_range", None)
    if isinstance(raw, dict):
        return (int(raw.get("start", 0)), int(raw.get("end", 0)))
    if isinstance(raw, range):
        return (raw.start, raw.stop)
    if isinstance(raw, (tuple, list)) and len(raw) >= 2:
        return (int(raw[0]), int(raw[1]))
    if raw is not None and hasattr(raw, "start") and hasattr(raw, "end"):
        return (int(raw.start), int(raw.end))
    return None


def _normalize_pasted_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _terminal_truncate_display_width(text: str, width: int) -> str:
    budget = max(1, int(width))
    current = 0
    out: list[str] = []
    for char in str(text):
        char_width = _terminal_char_display_width(char)
        if current + char_width > budget:
            break
        out.append(char)
        current += char_width
    return "".join(out)


def _terminal_display_width(text: str) -> int:
    return sum(_terminal_char_display_width(char) for char in str(text))


def _terminal_char_display_width(char: str) -> int:
    if char == "\t":
        return 4
    if not char:
        return 0
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1


def _terminal_selected_command_name(command: Any) -> str:
    if command is None:
        return ""
    command_fn = getattr(command, "command", None)
    if callable(command_fn):
        return str(command_fn())
    return str(command)


def _terminal_draft_command_name(draft: str) -> str:
    first_line = str(draft).replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    if not first_line.startswith("/"):
        return ""
    token = first_line[1:].lstrip()
    return token.split()[0] if token.split() else ""


def _binding_key(item: KeyEvent | dict[str, Any] | str) -> tuple[str, tuple[str, ...], str | None]:
    return _coerce_key_event(item).binding_key()


def _has_modifier(event: KeyEvent, modifier: str) -> bool:
    expected = modifier.lower()
    return any(str(value).lower() == expected for value in event.modifiers)


def _coerce_key_event(event: KeyEvent | dict[str, Any] | str, **kwargs: Any) -> KeyEvent:
    if isinstance(event, KeyEvent):
        return event
    if isinstance(event, str):
        if len(event) == 1:
            return KeyEvent.char_event(event, **kwargs)
        return KeyEvent.key(event, **kwargs)
    if isinstance(event, dict):
        data = dict(event)
        data.update(kwargs)
        code = str(data.pop("code", "char" if "char" in data else ""))
        char = data.pop("char", None)
        modifiers = data.pop("modifiers", ())
        kind = str(data.pop("kind", "press"))
        return KeyEvent(code=code, char=char, modifiers=tuple(modifiers), kind=kind)
    raise TypeError(f"unsupported key event: {event!r}")


def plan_mode_nudge_line() -> list[str]:
    return ["Create a plan?", "shift+tab use Plan mode", "Esc dismiss"]


__all__ = [
    "ChatComposer",
    "ChatComposerConfig",
    "ChatComposerRenderSnapshot",
    "ComposerDraftSnapshot",
    "FOOTER_SPACING_HEIGHT",
    "InputResult",
    "KeyEvent",
    "LARGE_PASTE_CHAR_THRESHOLD",
    "MAX_USER_INPUT_TEXT_CHARS",
    "QueuedInputAction",
    "RUST_MODULE",
    "TERMINAL_COMPOSER_INPUT_CONTINUE",
    "TERMINAL_COMPOSER_SHUTDOWN_PLACEHOLDER",
    "TerminalCommandPopupInputAction",
    "TerminalCommandPopupState",
    "TerminalComposerEffectRunner",
    "TerminalComposerInputAction",
    "TerminalComposerPromptReader",
    "TerminalComposerProjection",
    "expand_pending_pastes",
    "plan_mode_nudge_line",
    "run_terminal_composer_blocking_line_prompt",
    "run_terminal_composer_eof",
    "run_terminal_composer_input_action",
    "run_terminal_composer_interrupt",
    "run_terminal_composer_prompt_loop",
    "run_terminal_composer_read_prompt",
    "run_terminal_composer_submit",
    "run_terminal_composer_write_nonterminal_prompt",
    "run_terminal_command_popup_input_action",
    "terminal_composer_draft_cleared",
    "terminal_command_popup_input_action",
    "terminal_input_result_from_line",
    "terminal_composer_line_text",
    "terminal_popup_key",
    "terminal_composer_projection",
    "terminal_composer_submitted_line",
    "user_input_too_large_message",
]
