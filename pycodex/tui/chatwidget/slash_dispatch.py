"""Slash-command dispatch helpers for Rust ``chatwidget::slash_dispatch``.

The full Rust module dispatches many commands through ``ChatWidget``.  Python
keeps the module-owned pure contracts here: dispatch-source tagging, prepared
argument payloads, side/review guard messages, queued-drain decisions, and
inline-argument text-element remapping.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, List, Mapping, Optional, Protocol, Set, Union

from .._porting import RustTuiModule
from ..slash_command import SlashCommand

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::slash_dispatch",
    source="codex/codex-rs/tui/src/chatwidget/slash_dispatch.rs",
    status="complete",
)

SIDE_STARTING_CONTEXT_LABEL = "Side starting..."
SIDE_SLASH_COMMAND_UNAVAILABLE_HINT = "Press Ctrl+C to return to the main thread first."
GOAL_USAGE = "Usage: /goal <objective>"
GOAL_USAGE_HINT = "Example: /goal improve benchmark coverage"
RAW_USAGE = "Usage: /raw [on|off]"


class SlashCommandDispatchSource(Enum):
    LIVE = "live"
    QUEUED = "queued"


class QueueDrain(Enum):
    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int


@dataclass(frozen=True)
class TextElement:
    byte_range: ByteRange
    payload: Any = None

    def map_range(self, new_range: ByteRange) -> "TextElement":
        return replace(self, byte_range=new_range)


@dataclass(frozen=True)
class PreparedSlashCommandArgs:
    args: str
    text_elements: tuple[Any, ...] = ()
    local_images: tuple[Any, ...] = ()
    remote_image_urls: tuple[str, ...] = ()
    mention_bindings: tuple[Any, ...] = ()
    source: SlashCommandDispatchSource = SlashCommandDispatchSource.LIVE


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    error_message: Optional[str] = None
    drain_pending_submission: bool = False


@dataclass(frozen=True)
class PreparedUserMessage:
    text: str
    local_images: tuple[Any, ...]
    remote_image_urls: tuple[str, ...]
    text_elements: tuple[Any, ...]
    mention_bindings: tuple[Any, ...]


TERMINAL_LOCAL_HELP_MESSAGE = "\u2022 Commands: /clear, /status, /quit"


@dataclass(frozen=True)
class TerminalLocalCommandPlan:
    """Terminal-local slash command plan owned by chatwidget::slash_dispatch."""

    action: str
    message: str | None = None


@dataclass(frozen=True)
class TerminalPromptDispatchResult:
    """Terminal prompt dispatch result owned by chatwidget::slash_dispatch."""

    action: str
    prompt: str = ""
    command: SlashCommand | None = None
    view: Any = None
    operation: Any = None


@dataclass
class TerminalLocalCommandDispatcher:
    """Dispatch the terminal-local slash-command subset through runtime callbacks."""

    clear: Any
    help_: Any
    status: Any

    def run(self, prompt: str) -> bool | str:
        return run_terminal_local_command(
            prompt,
            clear=self.clear,
            help_=self.help_,
            status=self.status,
        )


@dataclass(frozen=True)
class TerminalPromptDispatcher:
    """Runtime-bound completed prompt dispatcher for the terminal path."""

    run_local_command: Any
    open_command_view: Any = None
    open_command_with_args: Any = None

    def dispatch(self, prompt: Any) -> TerminalPromptDispatchResult:
        return run_terminal_prompt_dispatch(
            prompt,
            run_local_command=self.run_local_command,
            open_command_view=self.open_command_view,
            open_command_with_args=self.open_command_with_args,
        )


class TerminalSlashCommandViewHandler(Protocol):
    """Terminal view-opening command handler owned by a chatwidget submodule."""

    def open_view(self) -> Any:
        ...

    def handle_events(self, events: tuple[object, ...]) -> Any:
        ...


class TerminalSlashCommandViewDispatcher:
    """Dispatch terminal view-opening slash commands to chatwidget owners.

    Rust owner: ``chatwidget::slash_dispatch`` receives
    ``InputResult::Command(cmd)`` from ``bottom_pane::chat_composer`` and then
    decides which command-specific ChatWidget owner handles the effect. The
    terminal product path uses the same split: the bottom pane passes a command
    name here, and this dispatcher delegates concrete view creation to the
    registered command owner.
    """

    def __init__(self, handlers: Mapping[SlashCommand, TerminalSlashCommandViewHandler]) -> None:
        self._handlers = dict(handlers)
        self._active_handler: TerminalSlashCommandViewHandler | None = None

    @classmethod
    def for_model_popup(
        cls,
        model_popup: TerminalSlashCommandViewHandler,
    ) -> "TerminalSlashCommandViewDispatcher":
        """Build the currently implemented terminal view-command dispatcher."""

        return cls({SlashCommand.MODEL: model_popup})

    @classmethod
    def for_runtime(
        cls,
        app_runtime: Any,
        *,
        submit_review: Any = None,
    ) -> "TerminalSlashCommandViewDispatcher":
        """Build terminal view-command handlers from the app runtime.

        Rust owner: ``chatwidget::slash_dispatch`` owns the command-to-view
        dispatch point.  The concrete ``/model`` popup remains owned by
        ``chatwidget::model_popups``, but ``codex-tui::tui`` should only wire
        the dispatcher into the event loop.
        """

        from .model_popups import TerminalModelPopupController
        from .keymap_picker import TerminalKeymapPopupController
        from .permissions_menu import TerminalPermissionsPopupController
        from .permission_popups import TerminalAutoReviewDenialsPopupController
        from .review_popups import TerminalReviewPopupController

        review_submitter = submit_review or (
            lambda target, _summary: app_runtime.submit_op(_review_app_command(target))
        )
        return cls(
            {
                SlashCommand.MODEL: TerminalModelPopupController(app_runtime),
                SlashCommand.REVIEW: TerminalReviewPopupController(app_runtime, review_submitter),
                SlashCommand.PERMISSIONS: TerminalPermissionsPopupController(app_runtime),
                SlashCommand.AUTO_REVIEW: TerminalAutoReviewDenialsPopupController(app_runtime),
                SlashCommand.KEYMAP: TerminalKeymapPopupController(app_runtime),
            }
        )

    def open_command_view(self, command: str) -> Any:
        cmd = terminal_slash_command_from_name(command)
        if cmd is None:
            return None
        handler = self._handlers.get(cmd)
        if handler is None:
            return None
        view = handler.open_view()
        if view is not None:
            self._active_handler = handler
        return view

    def handle_selection_events(self, events: tuple[object, ...]) -> Any:
        if self._active_handler is None:
            return None
        return self._active_handler.handle_events(events)

    def open_command_with_args(self, command: SlashCommand, args: str) -> Any:
        handler = self._handlers.get(command)
        if handler is None:
            return None
        dispatch = getattr(handler, "handle_command_with_args", None)
        if not callable(dispatch):
            return None
        view = dispatch(args)
        if view is not None:
            self._active_handler = handler
        return view


_QUEUED_CONTINUE_COMMANDS: Set[SlashCommand] = {
    SlashCommand.IDE,
    SlashCommand.STATUS,
    SlashCommand.DEBUG_CONFIG,
    SlashCommand.PS,
    SlashCommand.STOP,
    SlashCommand.MEMORY_DROP,
    SlashCommand.MEMORY_UPDATE,
    SlashCommand.MCP,
    SlashCommand.APPS,
    SlashCommand.PLUGINS,
    SlashCommand.ROLLOUT,
    SlashCommand.COPY,
    SlashCommand.RAW,
    SlashCommand.VIM,
    SlashCommand.DIFF,
    SlashCommand.RENAME,
    SlashCommand.TEST_APPROVAL,
}


def side_unavailable_message(cmd: Union[SlashCommand, str]) -> str:
    command = cmd.command() if isinstance(cmd, SlashCommand) else str(cmd).lstrip("/")
    return f"'/{command}' is unavailable in side conversations. {SIDE_SLASH_COMMAND_UNAVAILABLE_HINT}"


def before_session_unavailable_message(cmd: Union[SlashCommand, str]) -> str:
    command = cmd.command() if isinstance(cmd, SlashCommand) else str(cmd).lstrip("/")
    return f"'/{command}' is unavailable before the session starts."


def review_side_unavailable_message(cmd: Union[SlashCommand, str]) -> str:
    command = cmd.command() if isinstance(cmd, SlashCommand) else str(cmd).lstrip("/")
    return f"'/{command}' is unavailable while code review is running."


def ensure_slash_command_allowed_in_side_conversation(active_side_conversation: bool, cmd: SlashCommand) -> GuardResult:
    if not active_side_conversation or cmd.available_in_side_conversation():
        return GuardResult(True)
    return GuardResult(False, side_unavailable_message(cmd), True)


def ensure_side_command_allowed_outside_review(review_mode: bool, cmd: SlashCommand) -> GuardResult:
    if cmd not in {SlashCommand.SIDE, SlashCommand.BTW} or not review_mode:
        return GuardResult(True)
    return GuardResult(False, review_side_unavailable_message(cmd), True)


def queued_command_drain_result(
    cmd: SlashCommand,
    *,
    user_turn_pending_or_running: bool = False,
    no_modal_or_popup_active: bool = True,
) -> QueueDrain:
    if user_turn_pending_or_running or not no_modal_or_popup_active:
        return QueueDrain.STOP
    return QueueDrain.CONTINUE if cmd in _QUEUED_CONTINUE_COMMANDS else QueueDrain.STOP


def terminal_slash_command_from_name(command: str) -> SlashCommand | None:
    """Parse a terminal slash command name for dispatch, returning ``None`` on miss."""

    try:
        return SlashCommand.parse(command)
    except ValueError:
        return None


def _review_app_command(target: Any) -> Any:
    from ..app_command import AppCommand

    return AppCommand.review(target)


_EXIT_ALIASES = {":q", "q", "quit", "exit"}


def plan_terminal_local_command(prompt: str) -> TerminalLocalCommandPlan:
    """Plan the terminal-local command subset before user-turn submission.

    Rust owner: ``chatwidget::slash_dispatch`` owns slash command effect
    routing after command parsing.  The real-terminal product path still
    executes a small local subset through runner callbacks, but the decision of
    which prompts are local commands belongs with the slash-dispatch owner, not
    ``codex-tui::tui``.
    """

    stripped = prompt.strip()
    lowered = stripped.lower()
    if lowered in _EXIT_ALIASES:
        return TerminalLocalCommandPlan("exit")
    if lowered == "/?":
        return TerminalLocalCommandPlan("help", TERMINAL_LOCAL_HELP_MESSAGE)
    command = terminal_slash_command_from_name(lowered)
    if command in {SlashCommand.QUIT, SlashCommand.EXIT}:
        return TerminalLocalCommandPlan("exit")
    if command is SlashCommand.CLEAR:
        return TerminalLocalCommandPlan("clear")
    if command is SlashCommand.STATUS:
        return TerminalLocalCommandPlan("status")
    if lowered == "/help":
        return TerminalLocalCommandPlan("help", TERMINAL_LOCAL_HELP_MESSAGE)
    return TerminalLocalCommandPlan("none")


def run_terminal_local_command_plan(
    plan: TerminalLocalCommandPlan,
    *,
    clear: Any,
    help_: Any,
    status: Any,
) -> bool | str:
    """Dispatch a terminal-local command plan through runner callbacks."""

    if plan.action == "exit":
        return "exit"
    if plan.action == "clear":
        clear()
        return True
    if plan.action == "help":
        help_(plan.message or "")
        return True
    if plan.action == "status":
        status()
        return True
    return False


def run_terminal_local_command(
    prompt: str,
    *,
    clear: Any,
    help_: Any,
    status: Any,
) -> bool | str:
    """Plan and dispatch the terminal-local command subset."""

    return run_terminal_local_command_plan(
        plan_terminal_local_command(prompt),
        clear=clear,
        help_=help_,
        status=status,
    )


def run_terminal_prompt_dispatch(
    prompt: Any,
    *,
    run_local_command: Any,
    open_command_view: Any = None,
    open_command_with_args: Any = None,
) -> TerminalPromptDispatchResult:
    """Classify a completed terminal prompt before user-turn submission.

    Rust owner: ``chatwidget::slash_dispatch`` owns the boundary where completed
    composer input is interpreted as a local slash command or normal user text.
    ``codex-tui::tui`` should only run the event loop and submit prompts that
    this owner classifies as user turns.
    """

    from ..bottom_pane.chat_composer import InputResult

    if isinstance(prompt, InputResult):
        if prompt.kind == "None":
            return TerminalPromptDispatchResult("skip")
        if prompt.kind == "Submitted":
            prompt = prompt.text or ""
        elif prompt.kind in {"Command", "CommandWithArgs"}:
            command = prompt.command
            if not isinstance(command, SlashCommand):
                return TerminalPromptDispatchResult("handled")
            if prompt.kind == "CommandWithArgs":
                view = (
                    open_command_with_args(command, prompt.args or "")
                    if open_command_with_args is not None
                    else None
                )
                if view is not None:
                    return TerminalPromptDispatchResult("show_view", command=command, view=view)
                return TerminalPromptDispatchResult("handled", command=command)
            command_result = run_local_command(f"/{command.command()}")
            if command_result == "exit":
                return TerminalPromptDispatchResult("exit", command=command)
            if command_result:
                return TerminalPromptDispatchResult("handled", command=command)
            view = open_command_view(command.command()) if open_command_view is not None else None
            if view is not None:
                return TerminalPromptDispatchResult("show_view", command=command, view=view)
            # A recognized local command must never become a model prompt just
            # because the terminal product path has not wired its owner yet.
            return TerminalPromptDispatchResult("handled", command=command)

    prompt = str(prompt).rstrip("\n")
    if not prompt.strip():
        return TerminalPromptDispatchResult("skip", prompt)
    command_result = run_local_command(prompt)
    if command_result == "exit":
        return TerminalPromptDispatchResult("exit", prompt)
    if command_result:
        return TerminalPromptDispatchResult("handled", prompt)
    return TerminalPromptDispatchResult("submit", prompt)


def slash_command_args_elements(
    rest: str,
    rest_offset: int,
    text_elements: Iterable[Any],
) -> List[Any]:
    if not rest:
        return []
    out: List[Any] = []
    for elem in text_elements:
        byte_range = _byte_range(elem)
        if byte_range is None or byte_range.end <= rest_offset:
            continue
        start = max(0, byte_range.start - rest_offset)
        end = byte_range.end - rest_offset
        if start >= len(rest):
            continue
        end = min(end, len(rest))
        if start < end:
            out.append(_map_element_range(elem, ByteRange(start, end)))
    return out


def prepared_inline_user_message(prepared: PreparedSlashCommandArgs) -> PreparedUserMessage:
    return PreparedUserMessage(
        text=prepared.args,
        local_images=tuple(prepared.local_images),
        remote_image_urls=tuple(prepared.remote_image_urls),
        text_elements=tuple(prepared.text_elements),
        mention_bindings=tuple(prepared.mention_bindings),
    )


def raw_output_mode_arg(trimmed: str) -> Optional[bool]:
    value = trimmed.strip().lower()
    if value == "on":
        return True
    if value == "off":
        return False
    return None


def mcp_detail_arg(trimmed: str) -> Optional[str]:
    return "full" if trimmed.strip().lower() == "verbose" else None


def keymap_arg_action(trimmed: str) -> Optional[str]:
    value = trimmed.strip().lower()
    if value == "":
        return "picker"
    if value == "debug":
        return "debug"
    return None


def pets_disable_arg(trimmed: str) -> bool:
    return trimmed.strip().lower() in {"disable", "disabled", "hide", "hidden", "off", "none"}


def _byte_range(elem: Any) -> Optional[ByteRange]:
    raw = getattr(elem, "byte_range", None)
    if raw is None and isinstance(elem, dict):
        raw = elem.get("byte_range")
    if raw is None:
        return None
    if isinstance(raw, ByteRange):
        return raw
    if isinstance(raw, range):
        return ByteRange(raw.start, raw.stop)
    if isinstance(raw, tuple) and len(raw) == 2:
        return ByteRange(int(raw[0]), int(raw[1]))
    start = getattr(raw, "start", None)
    end = getattr(raw, "end", None)
    if start is None and isinstance(raw, dict):
        start = raw.get("start")
        end = raw.get("end")
    if start is None or end is None:
        return None
    return ByteRange(int(start), int(end))


def _map_element_range(elem: Any, byte_range: ByteRange) -> Any:
    mapper = getattr(elem, "map_range", None)
    if callable(mapper):
        try:
            return mapper(byte_range)
        except TypeError:
            return mapper(lambda _old: byte_range)
    if isinstance(elem, TextElement):
        return elem.map_range(byte_range)
    if isinstance(elem, dict):
        copy = dict(elem)
        copy["byte_range"] = byte_range
        return copy
    try:
        return replace(elem, byte_range=byte_range)
    except Exception:
        return TextElement(byte_range, elem)


__all__ = [
    "ByteRange",
    "GOAL_USAGE",
    "GOAL_USAGE_HINT",
    "GuardResult",
    "PreparedSlashCommandArgs",
    "PreparedUserMessage",
    "QueueDrain",
    "RAW_USAGE",
    "RUST_MODULE",
    "SIDE_SLASH_COMMAND_UNAVAILABLE_HINT",
    "SIDE_STARTING_CONTEXT_LABEL",
    "SlashCommandDispatchSource",
    "TERMINAL_LOCAL_HELP_MESSAGE",
    "TerminalLocalCommandDispatcher",
    "TerminalLocalCommandPlan",
    "TerminalPromptDispatcher",
    "TerminalPromptDispatchResult",
    "TerminalSlashCommandViewDispatcher",
    "TerminalSlashCommandViewHandler",
    "TextElement",
    "before_session_unavailable_message",
    "ensure_side_command_allowed_outside_review",
    "ensure_slash_command_allowed_in_side_conversation",
    "keymap_arg_action",
    "mcp_detail_arg",
    "pets_disable_arg",
    "prepared_inline_user_message",
    "queued_command_drain_result",
    "raw_output_mode_arg",
    "review_side_unavailable_message",
    "side_unavailable_message",
    "slash_command_args_elements",
    "plan_terminal_local_command",
    "run_terminal_local_command",
    "run_terminal_local_command_plan",
    "run_terminal_prompt_dispatch",
    "terminal_slash_command_from_name",
]
