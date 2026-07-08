"""Semantic port for Rust ``bottom_pane/chat_composer.rs``.

The Rust chat composer is a large bottom-pane input state machine. This Python
module carries the module-owned public data/config boundary and keeps editor,
popup, history, paste-burst, and rendering runtime behavior as explicit
neighboring modules or dependency boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import unicodedata
from typing import Any, Callable, MutableSequence, TextIO

from ..._porting import RustTuiModule
from ..command_popup import CommandPopup, CommandPopupFlags
from ..selection_popup_common import TerminalPopupLine
from .slash_input import terminal_command_popup_visible_for_draft

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
    status="complete",
)

LARGE_PASTE_CHAR_THRESHOLD = 1000
MAX_USER_INPUT_TEXT_CHARS = 512_000
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
    def new(cls) -> "TerminalCommandPopupState":
        return cls(CommandPopup.new(CommandPopupFlags(), []))

    def sync_draft(self, draft: str, *, active_view_present: bool = False) -> bool:
        """Sync popup visibility and filter from the current composer draft.

        Rust owner: ``codex-tui::bottom_pane::chat_composer::sync_popups``
        owns the command-popup lifecycle; ``command_popup`` owns filtering and
        selection internals.
        """

        if active_view_present:
            self.visible = False
            return False
        visible = terminal_command_popup_visible_for_draft(draft)
        self.visible = visible
        if visible:
            self.popup.on_composer_text_change(draft)
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
    line: str
    cursor_column: int


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
    handle_key: Callable[[str, str, str], str | None] | None = None,
) -> Any:
    """Run the terminal product-path composer input loop.

    Rust ``bottom_pane::chat_composer`` owns composer draft mutation and submit
    outcomes. The terminal runner supplies the event source and concrete
    terminal effects while this helper keeps the draft/render/submit sequence
    together with the composer boundary.
    """

    draft = terminal_composer_draft_cleared()
    apply_draft(draft)
    render()
    while True:
        event = source.poll(poll_timeout)
        check_resize()
        if event is None:
            continue
        event_kind = getattr(event, "kind", "")
        if event_kind == "resize":
            check_resize()
            continue
        event_text = str(getattr(event, "text", ""))
        if handle_key is not None:
            handled_draft = handle_key(draft, event_kind, event_text)
            if handled_draft is not None:
                previous_draft = draft
                draft = handled_draft
                if draft != previous_draft:
                    apply_draft(draft)
                render()
                continue
        action = terminal_composer_input_action(draft, event_kind, event_text)
        draft = action.draft
        apply_draft(draft)
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
) -> str | None:
    """Run the blocking-line fallback for terminal composer input.

    This preserves the same terminal product-path sequence as the polled
    composer loop: clear the draft, render the bottom pane, read one input
    line, process a resize tick, and clear the live pane before returning.
    """

    apply_draft(terminal_composer_draft_cleared())
    render()
    line = read_line()
    check_resize()
    clear_bottom_pane()
    if line == "":
        return None
    return line


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
    handle_key: Callable[[str, str, str], str | None] | None = None,
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
            handle_key=handle_key,
        )

    write_nonterminal_prompt()
    line = read_line()
    if line == "":
        return None
    return line


@dataclass(frozen=True)
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
    handle_key: Callable[[str, str, str], str | None] | None = None
    poll_timeout: float = 0.1

    def read(self) -> Any:
        return run_terminal_composer_read_prompt(
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
            handle_key=self.handle_key,
        )


def terminal_composer_draft_cleared() -> str:
    """Return the empty terminal product-path composer draft."""

    return ""


def terminal_composer_draft_after_text(draft: str, text: str) -> tuple[str, bool]:
    """Append terminal text input to a composer draft.

    Rust ``bottom_pane::chat_composer`` owns draft mutation before render.  The
    scrollback terminal product path only needs the text-only subset: normalize
    CRLF/CR and append non-empty input.
    """

    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return str(draft), False
    return str(draft) + normalized, True


def terminal_composer_draft_after_backspace(draft: str) -> str:
    """Remove the final character from a terminal composer draft."""

    source = str(draft)
    return source[:-1] if source else source


def terminal_composer_submitted_line(draft: str) -> str:
    """Return the line submitted by pressing Enter in the terminal composer."""

    return str(draft) + "\n"


def terminal_composer_line_text(draft: str) -> str:
    """Return the single-line terminal rendering of the composer draft."""

    visible_draft = str(draft).replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    return f"\u203a {visible_draft}"


def terminal_composer_projection(draft: str, columns: int) -> TerminalComposerProjection:
    """Project the terminal composer into a live-pane line and cursor column.

    Rust owner: ``codex-tui::bottom_pane::chat_composer`` owns composer text
    projection before the terminal surface adapts it into the live viewport.
    """

    safe_columns = max(1, int(columns))
    line = _terminal_truncate_display_width(terminal_composer_line_text(draft), max(1, safe_columns - 1))
    cursor_column = min(safe_columns, max(3, 1 + _terminal_display_width(line)))
    return TerminalComposerProjection(line=line, cursor_column=cursor_column)


def terminal_composer_input_action(draft: str, event_kind: str, event_text: str = "") -> TerminalComposerInputAction:
    """Plan how a terminal input event mutates or submits the composer draft.

    Rust ``bottom_pane::chat_composer`` handles key input by mutating composer
    state and returning whether the UI should render or submit.  The scrollback
    terminal product path uses a small text-only subset of that contract while
    leaving terminal polling and repaint execution in ``tui::event_stream`` and
    ``tui::tui``.
    """

    source = str(draft)
    kind = str(event_kind)
    if kind == "text":
        next_draft, changed = terminal_composer_draft_after_text(source, event_text)
        return TerminalComposerInputAction("render" if changed else "continue", next_draft)
    if kind == "backspace":
        return TerminalComposerInputAction("render", terminal_composer_draft_after_backspace(source))
    if kind == "line":
        return TerminalComposerInputAction("submit", terminal_composer_draft_cleared(), str(event_text))
    if kind == "enter":
        return TerminalComposerInputAction(
            "submit",
            terminal_composer_draft_cleared(),
            terminal_composer_submitted_line(source),
        )
    if kind == "eof":
        return TerminalComposerInputAction("eof", terminal_composer_draft_cleared())
    if kind == "interrupt":
        return TerminalComposerInputAction("interrupt", source)
    return TerminalComposerInputAction("continue", source)


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
        if len(text) == 1:
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
) -> str | None:
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
        return None
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
        self.config = ChatComposerConfig.default() if config is None else config
        self.input_enabled = bool(kwargs.pop("input_enabled", True))
        self.input_disabled_placeholder = kwargs.pop("input_disabled_placeholder", None)
        self.placeholder_text = kwargs.pop("placeholder_text", "Ask Codex to do anything")
        self.is_bash_mode = bool(kwargs.pop("is_bash_mode", False))
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
        self._text = str(kwargs.pop("text", ""))
        self.text_elements = list(kwargs.pop("text_elements", []))
        self.pending_pastes: list[tuple[str, str]] = list(kwargs.pop("pending_pastes", []))

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

    def sync_popups(self) -> None:
        self.sync_count += 1

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
        visible_text = self._text if mask_char is None else mask_char * len(self._text)
        placeholder = None
        if not self.input_enabled:
            placeholder = self.input_disabled_placeholder or "Input disabled."
        elif not self._text and not self.is_bash_mode:
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
        if target == "without_popup":
            if key_event.code.lower() == "char" and key_event.char is not None:
                self._text += key_event.char
                return (InputResult.None_(), True)
            if key_event.code.lower() == "enter" and _has_modifier(key_event, "shift"):
                self._text += "\n"
                return (InputResult.None_(), True)
            if key_event.code.lower() == "enter" and not key_event.modifiers:
                prepared = self.prepare_submission_text(record_history=True)
                if prepared is None:
                    return (InputResult.None_(), bool(self.errors))
                text, text_elements = prepared
                self._text = ""
                self.pending_pastes.clear()
                return (InputResult.Submitted(text, text_elements), True)
        return (InputResult.None_(), False)

    def current_text(self) -> str:
        return self._text

    def set_text_content(
        self,
        text: str,
        text_elements: list[Any] | None = None,
        local_image_paths: list[Any] | None = None,
    ) -> None:
        self._text = str(text)
        self.text_elements = list(text_elements or [])

    def set_remote_image_urls(self, urls: list[str]) -> None:
        self.remote_image_urls = list(urls)

    def take_remote_image_urls(self) -> list[str]:
        urls = self.remote_image_urls
        self.remote_image_urls = []
        return urls

    def remote_image_urls_value(self) -> list[str]:
        return list(self.remote_image_urls)

    def set_pending_pastes(self, pending_pastes: list[tuple[str, str]]) -> None:
        self.pending_pastes = list(pending_pastes)

    def pending_pastes_value(self) -> list[tuple[str, str]]:
        return list(self.pending_pastes)

    def handle_paste(self, pasted: str) -> bool:
        if not self.input_enabled:
            return False
        normalized = _normalize_pasted_text(str(pasted))
        if not normalized:
            return False
        if len(normalized) > LARGE_PASTE_CHAR_THRESHOLD:
            placeholder = self.next_large_paste_placeholder(len(normalized))
            self._text += placeholder
            self.text_elements.append({"range": (len(self._text) - len(placeholder), len(self._text)), "placeholder": placeholder})
            self.pending_pastes.append((placeholder, normalized))
        else:
            self._text += normalized
        return True

    def next_large_paste_placeholder(self, char_count: int) -> str:
        base = f"[Pasted Content {int(char_count)} chars]"
        used = {placeholder for placeholder, _payload in self.pending_pastes}
        if base not in used:
            return base
        suffix = 2
        while f"{base} #{suffix}" in used:
            suffix += 1
        return f"{base} #{suffix}"

    def current_text_with_pending(self) -> str:
        expanded, _elements = expand_pending_pastes(self._text, self.text_elements, self.pending_pastes)
        return expanded

    def prepare_submission_text(self, record_history: bool = True) -> tuple[str, list[Any]] | None:
        expanded, elements = expand_pending_pastes(self._text, self.text_elements, self.pending_pastes)
        trimmed, elements = _trim_and_rebase_elements(expanded, elements)
        if not trimmed and not self.remote_image_urls:
            return None
        actual_chars = len(trimmed)
        if actual_chars > MAX_USER_INPUT_TEXT_CHARS:
            self.errors.append(user_input_too_large_message(actual_chars))
            return None
        return trimmed, elements


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
    "terminal_composer_draft_after_backspace",
    "terminal_composer_draft_after_text",
    "terminal_composer_draft_cleared",
    "terminal_command_popup_input_action",
    "terminal_composer_input_action",
    "terminal_composer_line_text",
    "terminal_popup_key",
    "terminal_composer_projection",
    "terminal_composer_submitted_line",
    "user_input_too_large_message",
]
