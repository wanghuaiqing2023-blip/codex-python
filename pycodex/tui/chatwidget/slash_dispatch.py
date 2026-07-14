"""Slash-command dispatch helpers for Rust ``chatwidget::slash_dispatch``.

The full Rust module dispatches many commands through ``ChatWidget``.  Python
keeps the module-owned pure contracts here: dispatch-source tagging, prepared
argument payloads, side/review guard messages, queued-drain decisions, and
inline-argument text-element remapping.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, List, Mapping, Optional, Protocol, Set, Union

from .._porting import RustTuiModule
from ..app_event import AppEvent, ThreadGoalSetMode
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
    prepared_args: PreparedSlashCommandArgs | None = None


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
    dispatch_command: Any = None
    guard_command: Any = None

    def dispatch(self, prompt: Any) -> TerminalPromptDispatchResult:
        return run_terminal_prompt_dispatch(
            prompt,
            run_local_command=self.run_local_command,
            open_command_view=self.open_command_view,
            open_command_with_args=self.open_command_with_args,
            dispatch_command=self.dispatch_command,
            guard_command=self.guard_command,
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

    def __init__(
        self,
        handlers: Mapping[SlashCommand, TerminalSlashCommandViewHandler],
        *,
        dispatch_app_event: Callable[[AppEvent], Any] | None = None,
    ) -> None:
        self._handlers = dict(handlers)
        self._active_handler: TerminalSlashCommandViewHandler | None = None
        self._dispatch_app_event = dispatch_app_event

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
        from .settings_popups import TerminalSettingsPopupController
        from ..resume_picker import TerminalResumePopupController

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
                SlashCommand.SETTINGS: TerminalSettingsPopupController(app_runtime),
                SlashCommand.RESUME: TerminalResumePopupController(app_runtime),
            },
            dispatch_app_event=getattr(app_runtime, "handle_app_event", None),
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
        if self._active_handler is not None:
            return self._active_handler.handle_events(events)
        for event in events:
            if isinstance(event, AppEvent) and self._dispatch_app_event is not None:
                self._dispatch_app_event(event)
        return None

    def clear_active_handler(self) -> None:
        """Release command-owned event routing before an App-owned view opens."""

        self._active_handler = None

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


@dataclass(frozen=True)
class TerminalSlashCommandRoute:
    """Auditable product route for one registered slash command."""

    category: str
    outcome: str
    rust_owner: str
    argument_form: str
    guards: tuple[str, ...]
    expected_effect: str
    python_owner: str
    product_test: str


_VIEW_COMMANDS = {
    SlashCommand.MODEL,
    SlashCommand.REVIEW,
    SlashCommand.PERMISSIONS,
    SlashCommand.AUTO_REVIEW,
    SlashCommand.KEYMAP,
    SlashCommand.SETTINGS,
}

_LOCAL_COMMANDS = {
    SlashCommand.STATUS,
    SlashCommand.CLEAR,
    SlashCommand.QUIT,
    SlashCommand.EXIT,
}

_CORE_EFFECT_COMMANDS = {
    SlashCommand.COPY,
    SlashCommand.RAW,
    SlashCommand.DIFF,
    SlashCommand.RENAME,
    SlashCommand.NEW,
    SlashCommand.RESUME,
    SlashCommand.FORK,
    SlashCommand.INIT,
    SlashCommand.COMPACT,
    SlashCommand.PLAN,
    SlashCommand.GOAL,
    SlashCommand.MENTION,
}

_DEFERRED_EXTENSION_COMMANDS = {
    SlashCommand.IDE,
    SlashCommand.SKILLS,
    SlashCommand.HOOKS,
    SlashCommand.AGENT,
    SlashCommand.MULTI_AGENTS,
    SlashCommand.MCP,
    SlashCommand.APPS,
    SlashCommand.PLUGINS,
}

_COMPATIBILITY_SHIM_COMMANDS = {
    SlashCommand.VIM,
    SlashCommand.ELEVATE_SANDBOX,
    SlashCommand.SANDBOX_READ_ROOT,
    SlashCommand.EXPERIMENTAL,
    SlashCommand.MEMORIES,
    SlashCommand.SIDE,
    SlashCommand.BTW,
    SlashCommand.DEBUG_CONFIG,
    SlashCommand.TITLE,
    SlashCommand.STATUSLINE,
    SlashCommand.THEME,
    SlashCommand.PETS,
    SlashCommand.LOGOUT,
    SlashCommand.FEEDBACK,
    SlashCommand.ROLLOUT,
    SlashCommand.PS,
    SlashCommand.STOP,
    SlashCommand.PERSONALITY,
    SlashCommand.REALTIME,
    SlashCommand.TEST_APPROVAL,
    SlashCommand.MEMORY_DROP,
    SlashCommand.MEMORY_UPDATE,
}


def terminal_slash_command_routes() -> Mapping[SlashCommand, TerminalSlashCommandRoute]:
    """Return the exhaustive terminal product dispatch matrix.

    This deliberately enumerates every ``SlashCommand``. Adding an upstream
    command without choosing a product outcome fails loudly instead of falling
    back to the former silent ``handled`` branch.
    """

    routes: dict[SlashCommand, TerminalSlashCommandRoute] = {}
    for command in _LOCAL_COMMANDS:
        routes[command] = _terminal_route(command, "local", "effect")
    for command in _VIEW_COMMANDS:
        routes[command] = _terminal_route(command, "view", "view")
    for command in _CORE_EFFECT_COMMANDS:
        routes[command] = _terminal_route(command, "core", "effect")
    for command in _DEFERRED_EXTENSION_COMMANDS:
        routes[command] = _terminal_route(command, "extension", "shim")
    for command in _COMPATIBILITY_SHIM_COMMANDS:
        routes[command] = _terminal_route(command, "compatibility", "shim")
    missing = set(SlashCommand) - set(routes)
    if missing:
        names = ", ".join(sorted(command.command() for command in missing))
        raise AssertionError(f"missing explicit terminal slash routes: {names}")
    return routes


_VIEW_PYTHON_OWNERS = {
    SlashCommand.MODEL: "pycodex.tui.chatwidget.model_popups",
    SlashCommand.REVIEW: "pycodex.tui.chatwidget.review_popups",
    SlashCommand.PERMISSIONS: "pycodex.tui.chatwidget.permissions_menu",
    SlashCommand.AUTO_REVIEW: "pycodex.tui.chatwidget.permission_popups",
    SlashCommand.KEYMAP: "pycodex.tui.chatwidget.keymap_picker",
    SlashCommand.SETTINGS: "pycodex.tui.chatwidget.settings_popups",
    SlashCommand.RESUME: "pycodex.tui.resume_picker + pycodex.tui.chatwidget.slash_dispatch",
}


def _terminal_route(command: SlashCommand, category: str, outcome: str) -> TerminalSlashCommandRoute:
    guards = ["side-conversation availability", "active-task availability"]
    if command in {SlashCommand.SIDE, SlashCommand.BTW}:
        guards.append("review-mode availability")
    if category == "extension":
        effect = f"visible deferred-extension compatibility result for /{command.command()}"
    elif category == "compatibility":
        effect = f"visible compatibility result for /{command.command()}"
    elif outcome == "view":
        effect = f"open /{command.command()} through the active BottomPaneView stack"
    else:
        effect = f"execute the registered /{command.command()} product effect without a UserTurn fallback"
    owner = _VIEW_PYTHON_OWNERS.get(command, "pycodex.tui.chatwidget.slash_dispatch")
    test = (
        "pycodex/tui/tui/tests/test_terminal_runtime.py"
        if category in {"local", "core", "view"}
        else "pycodex/tui/chatwidget/tests/test_slash_dispatch.py"
    )
    return TerminalSlashCommandRoute(
        category=category,
        outcome=outcome,
        rust_owner="codex-tui::slash_command + codex-tui::chatwidget::slash_dispatch",
        argument_form="inline-or-bare" if command.supports_inline_args() else "bare",
        guards=tuple(guards),
        expected_effect=effect,
        python_owner=owner,
        product_test=test,
    )


@dataclass
class TerminalSlashCommandEffectDispatcher:
    """Execute non-view slash commands at the Rust slash-dispatch boundary."""

    app_runtime: Any
    submit_operation: Callable[[str, Callable[[], Any]], Any] | None = None

    def guard(self, command: SlashCommand) -> TerminalPromptDispatchResult | None:
        widget = self.app_runtime.chat_widget
        side_guard = ensure_slash_command_allowed_in_side_conversation(
            bool(getattr(widget, "active_side_conversation", False)),
            command,
        )
        if not side_guard.allowed:
            self._message(side_guard.error_message or "Command unavailable.", error=True)
            return self._handled(command)
        review_guard = ensure_side_command_allowed_outside_review(
            bool(getattr(getattr(widget, "review", None), "is_review_mode", False)),
            command,
        )
        if not review_guard.allowed:
            self._message(review_guard.error_message or "Command unavailable.", error=True)
            return self._handled(command)
        task_running = bool(
            getattr(getattr(getattr(widget, "turn", None), "bottom_pane", None), "task_running", False)
        )
        if task_running and not command.available_during_task():
            self._message(f"'/{command.command()}' is unavailable while a task is running.", error=True)
            return self._handled(command)
        return None

    def dispatch(self, command: SlashCommand, args: str = "") -> TerminalPromptDispatchResult:
        route = terminal_slash_command_routes().get(command)
        if route is None:
            raise AssertionError(f"missing terminal slash route for {command!r}")
        try:
            return self._dispatch(command, args.strip())
        except Exception as error:
            self._message(f"/{command.command()} failed: {error}", error=True)
            return TerminalPromptDispatchResult("handled", command=command)

    def _dispatch(self, command: SlashCommand, args: str) -> TerminalPromptDispatchResult:
        if command is SlashCommand.COPY:
            from ..clipboard_copy import copy_to_clipboard
            widget = self.app_runtime.chat_widget
            markdown = getattr(widget.transcript, "last_agent_markdown", None)
            if not markdown:
                self._message("No agent response to copy", error=True)
                return self._handled(command)
            try:
                widget.clipboard_lease = copy_to_clipboard(markdown)
            except Exception as error:
                self._message(f"Copy failed: {error}", error=True)
                return self._handled(command)
            self._message("Copied last message to clipboard")
            widget.request_redraw()
            return self._handled(command)
        if command is SlashCommand.RAW:
            return self._raw(command, args)
        if command is SlashCommand.DIFF:
            return self._diff(command)
        if command is SlashCommand.RENAME:
            return self._rename(command, args)
        if command is SlashCommand.COMPACT:
            from ..app_command import AppCommand

            return self._submit_operation(command, "Compacting conversation", AppCommand.compact())
        if command is SlashCommand.INIT:
            return self._init(command)
        if command is SlashCommand.PLAN:
            self.app_runtime.activate_plan_mode()
            self._message("Plan mode enabled.")
            if args:
                return TerminalPromptDispatchResult("submit", prompt=args, command=command)
            return self._handled(command)
        if command is SlashCommand.GOAL:
            return self._goal(command, args)
        if command is SlashCommand.MENTION:
            return TerminalPromptDispatchResult("compose", prompt="@", command=command)
        if command in {SlashCommand.NEW, SlashCommand.RESUME, SlashCommand.FORK}:
            return self._session_command(command, args)
        if command in _DEFERRED_EXTENSION_COMMANDS:
            self._message(
                f"/{command.command()} is recognized, but this extension area is not enabled "
                "in the current PyCodex terminal runtime."
            )
            return self._handled(command)

        self._message(
            f"/{command.command()} is recognized, but its product effect is not yet available "
            "in the current PyCodex terminal runtime."
        )
        return self._handled(command)

    def _raw(self, command: SlashCommand, args: str) -> TerminalPromptDispatchResult:
        current = bool(getattr(self.app_runtime.chat_widget, "raw_mode", False))
        if args and args.lower() not in {"on", "off"}:
            self._message(RAW_USAGE, error=True)
            return self._handled(command)
        enabled = (args.lower() == "on") if args else not current
        self.app_runtime.handle_app_event(AppEvent.raw_output_mode_changed(enabled))
        self._message(
            "Raw output mode on: transcript text is shown for clean terminal selection."
            if enabled
            else "Raw output mode off: rich transcript rendering restored."
        )
        return self._handled(command)

    def _diff(self, command: SlashCommand) -> TerminalPromptDispatchResult:
        from ..get_git_diff import get_git_diff

        widget = self.app_runtime.chat_widget
        widget.add_diff_in_progress()
        active = self.app_runtime.active_thread_runtime
        runner = active.workspace_command_runner()
        cwd = Path(getattr(getattr(active, "session_config", None), "cwd", None) or Path.cwd())
        inside_repo, diff = _run_sync(get_git_diff(runner, cwd))
        if not inside_repo:
            self._message("Not inside a Git repository.", error=True)
        elif diff:
            self.app_runtime.insert_info_history_message(diff)
        else:
            self._message("No git changes found.")
        widget.on_diff_complete(diff)
        return self._handled(command)

    def _rename(self, command: SlashCommand, args: str) -> TerminalPromptDispatchResult:
        if not args:
            self._message("Usage: /rename <name>", error=True)
            return self._handled(command)
        from ..app_command import AppCommand
        from pycodex.core.util import normalize_thread_name

        name = normalize_thread_name(args)
        if not name:
            self._message("Thread name cannot be empty.", error=True)
            return self._handled(command)
        return self._submit_operation(command, f"Renaming thread to {name}", AppCommand.set_thread_name(name))

    def _init(self, command: SlashCommand) -> TerminalPromptDispatchResult:
        active = self.app_runtime.active_thread_runtime
        cwd = Path(getattr(getattr(active, "session_config", None), "cwd", None) or Path.cwd())
        if (cwd / "AGENTS.md").exists():
            self._message("AGENTS.md already exists in this directory.")
            return self._handled(command)
        prompt_path = Path(__file__).parents[3] / "codex" / "codex-rs" / "tui" / "prompt_for_init_command.md"
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else (
            "Create an AGENTS.md file that explains how to work effectively in this repository."
        )
        return TerminalPromptDispatchResult("submit", prompt=prompt, command=command)

    def _goal(self, command: SlashCommand, args: str) -> TerminalPromptDispatchResult:
        thread_id = getattr(self.app_runtime.routing_state, "active_thread_id", None)
        if not args:
            if thread_id is None:
                self._message(GOAL_USAGE, GOAL_USAGE_HINT)
            else:
                self.app_runtime.handle_app_event(AppEvent.open_thread_goal_menu(thread_id))
                self._append_goal_history("/goal")
            return self._handled(command)
        lowered = args.lower()
        if lowered == "edit":
            self.app_runtime.handle_app_event(AppEvent.open_thread_goal_editor(thread_id))
            return self._handled(command)
        if lowered == "clear":
            if thread_id is None:
                self._message(GOAL_USAGE, "The session must start before you can change a goal.")
                return self._handled(command)
            self.app_runtime.handle_app_event(AppEvent.clear_thread_goal(thread_id))
            self._append_goal_history("/goal clear")
            return self._handled(command)
        status = {"pause": "paused", "resume": "active"}.get(lowered)
        if status is not None:
            if thread_id is None:
                self._message(GOAL_USAGE, "The session must start before you can change a goal.")
                return self._handled(command)
            self.app_runtime.handle_app_event(AppEvent.set_thread_goal_status(thread_id, status))
            self._append_goal_history(f"/goal {lowered}")
            return self._handled(command)
        objective = args.strip()
        if not objective:
            self._message("Goal objective must not be empty.", error=True)
            self._message(GOAL_USAGE, GOAL_USAGE_HINT)
            return self._handled(command)
        if thread_id is None:
            self._message(GOAL_USAGE, "The session must start before you can set a goal.")
            return self._handled(command)
        self.app_runtime.handle_app_event(
            AppEvent.set_thread_goal_objective(
                thread_id,
                objective,
                ThreadGoalSetMode.confirm_if_exists(),
            )
        )
        self._append_goal_history(f"/goal {objective}")
        return self._handled(command)

    def _append_goal_history(self, text: str) -> None:
        append = getattr(self.app_runtime, "append_message_history_entry", None)
        if callable(append):
            append(text)

    def _session_command(self, command: SlashCommand, args: str) -> TerminalPromptDispatchResult:
        if command is SlashCommand.NEW:
            thread_id = self.app_runtime.start_fresh_session()
        elif command is SlashCommand.FORK:
            thread_id = self.app_runtime.fork_current_session()
        elif args:
            thread_id = self.app_runtime.resume_session_by_id_or_name(args)
        else:
            self._message("Select a session from the resume picker.")
            return self._handled(command)
        verb = {
            SlashCommand.NEW: "Started new session",
            SlashCommand.RESUME: "Resumed session",
            SlashCommand.FORK: "Forked session",
        }[command]
        self._message(f"{verb} {thread_id}.")
        return self._handled(command)

    def _submit_operation(
        self,
        command: SlashCommand,
        summary: str,
        operation: Any,
    ) -> TerminalPromptDispatchResult:
        if self.submit_operation is None:
            self._message(f"/{command.command()} cannot run without an active operation stream.", error=True)
            return self._handled(command)
        self.submit_operation(summary, lambda: self.app_runtime.submit_op(operation))
        return TerminalPromptDispatchResult("handled", command=command, operation=operation)

    def _message(self, message: str, hint: str | None = None, *, error: bool = False) -> None:
        if error:
            from ..history_cell.notices import new_error_event

            self.app_runtime.insert_history_cell(new_error_event(message))
            return
        self.app_runtime.insert_info_history_message(message, hint)

    @staticmethod
    def _handled(command: SlashCommand) -> TerminalPromptDispatchResult:
        return TerminalPromptDispatchResult("handled", command=command)


def _run_sync(awaitable: Any) -> Any:
    """Run a slash-owned async helper from the synchronous terminal loop."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("cannot run synchronous slash effect inside an active event loop")


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
    dispatch_command: Any = None,
    guard_command: Any = None,
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
            guarded = guard_command(command) if guard_command is not None else None
            if guarded is not None:
                return guarded
            if prompt.kind == "CommandWithArgs":
                prepared_args = PreparedSlashCommandArgs(
                    args=prompt.args or "",
                    text_elements=tuple(prompt.text_elements),
                )
                view = (
                    open_command_with_args(command, prompt.args or "")
                    if open_command_with_args is not None
                    else None
                )
                if view is not None:
                    return TerminalPromptDispatchResult(
                        "show_view",
                        command=command,
                        view=view,
                        prepared_args=prepared_args,
                    )
                if dispatch_command is not None:
                    return replace(
                        dispatch_command(command, prompt.args or ""),
                        prepared_args=prepared_args,
                    )
                raise RuntimeError(f"no terminal slash effect dispatcher for /{command.command()}")
            command_result = run_local_command(f"/{command.command()}")
            if command_result == "exit":
                return TerminalPromptDispatchResult("exit", command=command)
            if command_result:
                return TerminalPromptDispatchResult("handled", command=command)
            view = open_command_view(command.command()) if open_command_view is not None else None
            if view is not None:
                return TerminalPromptDispatchResult("show_view", command=command, view=view)
            if dispatch_command is not None:
                return dispatch_command(command, "")
            raise RuntimeError(f"no terminal slash effect dispatcher for /{command.command()}")

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
    "TerminalSlashCommandEffectDispatcher",
    "TerminalSlashCommandRoute",
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
    "terminal_slash_command_routes",
]
