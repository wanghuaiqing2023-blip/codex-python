# Rust owner: codex-tui::chatwidget::slash_dispatch.
import inspect
from pathlib import Path
from types import SimpleNamespace

import pycodex.tui.chatwidget.slash_dispatch as slash_dispatch_module

from pycodex.tui.history_cell.base import line_text
from pycodex.tui.chatwidget.slash_dispatch import (
    ByteRange,
    GOAL_USAGE,
    GOAL_USAGE_HINT,
    RAW_USAGE,
    SIDE_SLASH_COMMAND_UNAVAILABLE_HINT,
    SIDE_STARTING_CONTEXT_LABEL,
    GuardResult,
    PreparedSlashCommandArgs,
    QueueDrain,
    SlashCommandDispatchSource,
    TERMINAL_LOCAL_HELP_MESSAGE,
    TerminalLocalCommandDispatcher,
    TerminalLocalCommandPlan,
    TerminalPromptDispatcher,
    TerminalPromptDispatchResult,
    TerminalSlashCommandEffectDispatcher,
    TerminalSlashCommandViewDispatchResult,
    TerminalSlashCommandViewDispatcher,
    TextElement,
    ensure_side_command_allowed_outside_review,
    ensure_slash_command_allowed_in_side_conversation,
    keymap_arg_action,
    mcp_detail_arg,
    pets_disable_arg,
    plan_terminal_local_command,
    prepared_inline_user_message,
    queued_command_drain_result,
    raw_output_mode_arg,
    run_terminal_local_command,
    run_terminal_local_command_plan,
    run_terminal_prompt_dispatch,
    slash_command_args_elements,
    terminal_slash_command_from_name,
    terminal_slash_command_routes,
)
from pycodex.tui.bottom_pane.chat_composer import InputResult
from pycodex.tui.slash_command import SlashCommand
from pycodex.tui.app_event import AppEvent, ThreadGoalSetMode
from pycodex.tui.auto_review_denials import denied_event
from pycodex.tui.chatwidget.protocol import ChatWidgetProtocolRuntime
from pycodex.protocol import ModeKind
from pycodex.tui.app.runtime import ExecFunctionActiveThreadRuntime, TuiAppRuntime


# Fixed Rust baseline: codex/codex-rs/tui/prompt_for_init_command.md.
# This test fixture is deliberately Python-owned: normal Python tests must not
# need the Rust source tree in order to define or verify the product contract.
EXPECTED_INIT_PROMPT = """Generate a file named AGENTS.md that serves as a contributor guide for this repository.
Your goal is to produce a clear, concise, and well-structured document with descriptive headings and actionable explanations for each section.
Follow the outline below, but adapt as needed — add sections if relevant, and omit those that do not apply to this project.

Document Requirements

- Title the document "Repository Guidelines".
- Use Markdown headings (#, ##, etc.) for structure.
- Keep the document concise. 200-400 words is optimal.
- Keep explanations short, direct, and specific to this repository.
- Provide examples where helpful (commands, directory paths, naming patterns).
- Maintain a professional, instructional tone.

Recommended Sections

Project Structure & Module Organization

- Outline the project structure, including where the source code, tests, and assets are located.

Build, Test, and Development Commands

- List key commands for building, testing, and running locally (e.g., npm test, make build).
- Briefly explain what each command does.

Coding Style & Naming Conventions

- Specify indentation rules, language-specific style preferences, and naming patterns.
- Include any formatting or linting tools used.

Testing Guidelines

- Identify testing frameworks and coverage requirements.
- State test naming conventions and how to run tests.

Commit & Pull Request Guidelines

- Summarize commit message conventions found in the project’s Git history.
- Outline pull request requirements (descriptions, linked issues, screenshots, etc.).

(Optional) Add other sections if relevant, such as Security & Configuration Tips, Architecture Overview, or Agent-Specific Instructions.
""".replace("\n", "\r\n")


def test_constants_match_rust_user_facing_text() -> None:
    assert SIDE_STARTING_CONTEXT_LABEL == "Side starting..."
    assert SIDE_SLASH_COMMAND_UNAVAILABLE_HINT == "Press Ctrl+C to return to the main thread first."
    assert GOAL_USAGE == "Usage: /goal <objective>"
    assert GOAL_USAGE_HINT == "Example: /goal improve benchmark coverage"
    assert RAW_USAGE == "Usage: /raw [on|off]"


def test_side_conversation_guard_allows_only_side_safe_commands() -> None:
    assert ensure_slash_command_allowed_in_side_conversation(False, SlashCommand.MODEL) == GuardResult(True)
    assert ensure_slash_command_allowed_in_side_conversation(True, SlashCommand.RAW) == GuardResult(True)

    denied = ensure_slash_command_allowed_in_side_conversation(True, SlashCommand.MODEL)
    assert denied.allowed is False
    assert denied.drain_pending_submission is True
    assert denied.error_message == "'/model' is unavailable in side conversations. Press Ctrl+C to return to the main thread first."


def test_side_command_rejected_while_review_running() -> None:
    assert ensure_side_command_allowed_outside_review(True, SlashCommand.MODEL) == GuardResult(True)

    denied = ensure_side_command_allowed_outside_review(True, SlashCommand.SIDE)
    assert denied.allowed is False
    assert denied.drain_pending_submission is True
    assert denied.error_message == "'/side' is unavailable while code review is running."


def test_queued_command_drain_result_matches_rust_command_sets() -> None:
    assert queued_command_drain_result(SlashCommand.STATUS) is QueueDrain.CONTINUE
    assert queued_command_drain_result(SlashCommand.RAW) is QueueDrain.CONTINUE
    assert queued_command_drain_result(SlashCommand.MODEL) is QueueDrain.STOP
    assert queued_command_drain_result(SlashCommand.STATUS, user_turn_pending_or_running=True) is QueueDrain.STOP
    assert queued_command_drain_result(SlashCommand.STATUS, no_modal_or_popup_active=False) is QueueDrain.STOP


def test_terminal_slash_command_view_dispatcher_routes_model_view_to_registered_owner() -> None:
    # Rust owner: chatwidget::slash_dispatch receives InputResult::Command and
    # chooses command-specific owners such as chatwidget::model_popups for
    # view-opening commands. bottom_pane/chat_composer should not name /model.
    class Handler:
        def __init__(self) -> None:
            self.opened = 0
            self.events: list[tuple[object, ...]] = []

        def open_view(self) -> str:
            self.opened += 1
            return "model-view"

        def handle_events(self, events: tuple[object, ...]) -> str:
            self.events.append(events)
            return "next-view"

    handler = Handler()
    dispatcher = TerminalSlashCommandViewDispatcher.for_model_popup(handler)

    assert terminal_slash_command_from_name("model") is SlashCommand.MODEL
    assert terminal_slash_command_from_name("/model") is SlashCommand.MODEL
    assert terminal_slash_command_from_name("unknown") is None
    assert dispatcher.open_command_view("status") is None
    assert dispatcher.open_command_view("model") == "model-view"
    assert handler.opened == 1
    assert dispatcher.handle_selection_events(("selected",)) == "next-view"
    assert handler.events == [("selected",)]


def test_registered_view_command_can_handle_without_opening_a_view() -> None:
    # Rust chatwidget::slash_dispatch treats owner-produced empty states as the
    # completed command effect. It must not invoke a fallback effect dispatcher.
    class EmptyStateHandler:
        def __init__(self) -> None:
            self.opened = 0

        def open_view(self) -> None:
            self.opened += 1

        def handle_events(self, _events: tuple[object, ...]) -> None:
            return None

    handler = EmptyStateHandler()
    dispatcher = TerminalSlashCommandViewDispatcher(
        {SlashCommand.AUTO_REVIEW: handler}
    )
    fallbacks: list[SlashCommand] = []

    result = run_terminal_prompt_dispatch(
        InputResult.Command(SlashCommand.AUTO_REVIEW),
        run_local_command=lambda _prompt: False,
        open_command_view=dispatcher.dispatch_command_view,
        dispatch_command=lambda command, _args: (
            fallbacks.append(command)
            or TerminalPromptDispatchResult("handled", command=command)
        ),
    )

    assert result.action == "handled"
    assert result.command is SlashCommand.AUTO_REVIEW
    assert handler.opened == 1
    assert fallbacks == []
    assert dispatcher.dispatch_command_view("unknown") == (
        TerminalSlashCommandViewDispatchResult(False)
    )


def test_terminal_slash_command_view_dispatcher_builds_runtime_model_view_owner() -> None:
    # Rust owner: chatwidget::slash_dispatch owns the command-to-view registry,
    # while chatwidget::model_popups owns the concrete /model picker session.
    # codex-tui::tui should not construct the model popup controller directly.
    runtime = SimpleNamespace(
        session_config=SimpleNamespace(
            model="gpt-5.4",
            model_reasoning_effort="low",
            available_models=(
                SimpleNamespace(
                    model="gpt-5.4",
                    description="Strong model",
                    default_reasoning_effort="medium",
                    supported_reasoning_efforts=(),
                ),
            ),
        )
    )
    app_runtime = SimpleNamespace(active_thread_runtime=runtime, handle_app_event=lambda event: None)
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    view = dispatcher.open_command_view("model")

    assert view is not None
    assert view.header[0] == "Select Model and Effort"
    assert [item.name for item in view.items] == ["gpt-5.4"]


def test_runtime_view_dispatcher_routes_bare_rename_to_interaction_prompt() -> None:
    widget = ChatWidgetProtocolRuntime()
    widget.thread_name = "Current title"
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        active_thread_runtime=SimpleNamespace(),
        handle_app_event=lambda _event: None,
    )

    view = TerminalSlashCommandViewDispatcher.for_runtime(
        app_runtime
    ).open_command_view("rename")

    assert view is not None
    assert view.title == "Rename thread"
    assert view.textarea.text() == "Current title"


def test_terminal_slash_command_routes_cover_every_registered_command() -> None:
    # Fixed Rust baseline 1c7832f: slash_command.rs defines the registry while
    # chatwidget::slash_dispatch must choose an effect, view, guard, or shim.
    routes = terminal_slash_command_routes()

    assert set(routes) == set(SlashCommand)
    assert {route.outcome for route in routes.values()} <= {"effect", "view", "shim"}
    assert routes[SlashCommand.DIFF].outcome == "effect"
    assert routes[SlashCommand.SETTINGS].outcome == "view"
    assert routes[SlashCommand.STATUSLINE].outcome == "view"
    assert routes[SlashCommand.STATUSLINE].python_owner == "pycodex.tui.chatwidget.status_controls"
    assert routes[SlashCommand.TITLE].outcome == "view"
    assert routes[SlashCommand.TITLE].python_owner == "pycodex.tui.chatwidget.status_controls"
    assert (
        routes[SlashCommand.PERMISSIONS].python_owner
        == "pycodex.tui.chatwidget.permission_popups"
    )
    assert routes[SlashCommand.IDE].outcome == "effect"
    assert routes[SlashCommand.IDE].python_owner == "pycodex.tui.chatwidget.ide_context"
    assert routes[SlashCommand.VIM].outcome == "effect"
    assert routes[SlashCommand.VIM].python_owner == "pycodex.tui.chatwidget.protocol"
    assert routes[SlashCommand.ELEVATE_SANDBOX].outcome == "effect"
    assert (
        routes[SlashCommand.ELEVATE_SANDBOX].python_owner
        == "pycodex.tui.chatwidget.slash_dispatch + pycodex.tui.app.event_dispatch"
    )
    assert routes[SlashCommand.SANDBOX_READ_ROOT].outcome == "effect"
    assert (
        routes[SlashCommand.SANDBOX_READ_ROOT].python_owner
        == "pycodex.tui.chatwidget.slash_dispatch + pycodex.tui.app.event_dispatch"
    )
    assert routes[SlashCommand.EXPERIMENTAL].outcome == "view"
    assert routes[SlashCommand.EXPERIMENTAL].python_owner == (
        "pycodex.tui.chatwidget.settings_popups + "
        "pycodex.tui.bottom_pane.experimental_features_view"
    )
    assert routes[SlashCommand.MCP].outcome == "effect"
    assert routes[SlashCommand.MCP].category == "extension"
    for command, route in routes.items():
        assert route.rust_owner
        assert route.argument_form == ("inline-or-bare" if command.supports_inline_args() else "bare")
        assert route.guards
        assert route.expected_effect
        assert route.python_owner
        assert route.product_test


def test_terminal_title_command_uses_registered_active_view_owner() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch maps /title to open_terminal_title_setup.
    # - bottom_pane::title_setup owns the active selection view.
    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(
            session_config=SimpleNamespace(cwd="C:/workspace/codex-python")
        ),
        chat_widget=SimpleNamespace(config=SimpleNamespace(tui_terminal_title=None)),
        handle_app_event=lambda event: None,
    )
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    view = dispatcher.open_command_view("title")

    assert view is not None
    lines = view.render_lines()
    assert lines[:2] == [
        "  Configure Terminal Title",
        "  Select which items to display in the terminal title.",
    ]
    enabled = [item.id for item in view.items if item.enabled]
    assert enabled == ["activity", "project-name"]


def test_terminal_settings_command_uses_registered_active_view_owner() -> None:
    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(session_config=SimpleNamespace()),
        chat_widget=ChatWidgetProtocolRuntime(),
        handle_app_event=lambda event: None,
    )
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    view = dispatcher.open_command_view("settings")

    assert view.title == "Settings"
    assert [item.name for item in view.items] == ["Microphone", "Speaker"]


def test_terminal_experimental_command_uses_registered_toggle_view_owner() -> None:
    from pycodex.features import Features

    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(
            session_config=SimpleNamespace(features=Features.with_defaults())
        ),
        chat_widget=ChatWidgetProtocolRuntime(),
        app_event_sender=SimpleNamespace(send=lambda _event: None),
        runtime_keymap=None,
        handle_app_event=lambda _event: None,
    )
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    view = dispatcher.open_command_view("experimental")

    assert view is not None
    assert view.header[0] == "Experimental features"
    assert view.features
    assert view.features[0].name == "Terminal resize reflow"
    assert view.features[0].enabled is True
    assert view.terminal_lines(width=100)[0].text == "Experimental features"


def test_terminal_memories_command_uses_enable_prompt_or_settings_view() -> None:
    from pycodex.config.types import MemoriesConfig
    from pycodex.features import Feature, Features

    features = Features.with_defaults()
    session_config = SimpleNamespace(
        features=features,
        memories=MemoriesConfig(use_memories=True, generate_memories=False),
    )
    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(session_config=session_config),
        chat_widget=SimpleNamespace(config=session_config),
        app_event_sender=SimpleNamespace(send=lambda _event: None),
        runtime_keymap=None,
        handle_app_event=lambda _event: None,
    )
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    enable_prompt = dispatcher.open_command_view("memories")
    assert enable_prompt.title == "Enable memories?"
    assert [item.name for item in enable_prompt.items] == [
        "Yes, enable",
        "Not now",
    ]

    features.set_enabled(Feature.MEMORY_TOOL, True)
    settings = dispatcher.open_command_view("memories")
    assert settings.settings_header()[0] == "Memories"
    assert [item.name for item in settings.items] == [
        "Use memories",
        "Generate memories",
        "Reset all memories",
    ]
    assert settings.terminal_lines(width=100)[0].text == "Memories"


def test_terminal_skills_command_uses_chatwidget_skills_menu_owner() -> None:
    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(session_config=SimpleNamespace()),
        chat_widget=SimpleNamespace(),
        handle_app_event=lambda _event: None,
    )
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    view = dispatcher.open_command_view("skills")

    assert view.title == "Skills"
    assert view.subtitle == "Choose an action"
    assert [item.name for item in view.items] == [
        "List skills",
        "Enable/Disable Skills",
    ]
    assert [item.actions[0].kind for item in view.items] == [
        "OpenSkillsList",
        "OpenManageSkillsPopup",
    ]


def test_terminal_hooks_command_uses_chatwidget_hooks_browser_owner() -> None:
    app_runtime = SimpleNamespace(
        cwd="/repo",
        config_request_handle=None,
        app_event_sender=SimpleNamespace(send=lambda _event: None),
        runtime_keymap=None,
        active_thread_runtime=SimpleNamespace(session_config=SimpleNamespace()),
        chat_widget=SimpleNamespace(),
        handle_app_event=lambda _event: None,
    )
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    view = dispatcher.open_command_view("hooks")
    lines = [line.text for line in view.terminal_lines(width=112)]

    assert lines[0] == "  Hooks"
    assert "  Lifecycle hooks from config and enabled plugins." in lines
    assert lines[-1] == "  Press enter to view hooks; esc to close"


def test_terminal_slash_dispatcher_routes_auto_review_denials_through_permission_owner() -> None:
    # Fixed Rust commit 1c7832f:
    # chatwidget::slash_dispatch::SlashCommand::AutoReview delegates to
    # chatwidget::permission_popups::open_auto_review_denials_popup.
    widget = ChatWidgetProtocolRuntime()
    widget.review.recent_auto_review_denials.push(denied_event("one"))
    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(session_config=SimpleNamespace()),
        chat_widget=widget,
        routing_state=SimpleNamespace(active_thread_id="thread-1"),
        thread_id="thread-1",
        handle_bottom_pane_app_event=lambda _event: None,
    )
    dispatcher = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)

    view = dispatcher.open_command_view("approve")

    assert view is not None
    assert view.title == "Auto-review Denials"
    assert view.items[1].name == "rm -rf /tmp/test-one"
    assert view.items[1].actions[0].kind == "ApproveRecentAutoReviewDenial"


def test_plan_terminal_local_command_handles_exit_aliases() -> None:
    # Rust owner: chatwidget::slash_dispatch owns slash command effect routing
    # before prompt text becomes a user turn.
    assert plan_terminal_local_command("/quit").action == "exit"
    assert plan_terminal_local_command("/exit").action == "exit"
    assert plan_terminal_local_command(":q").action == "exit"
    assert plan_terminal_local_command("q").action == "exit"
    assert plan_terminal_local_command("quit").action == "exit"


def test_plan_terminal_local_command_handles_terminal_local_subset() -> None:
    # Rust owner: chatwidget::slash_dispatch owns the command-category decision;
    # app/history_ui and status owners still execute the concrete callbacks.
    assert plan_terminal_local_command("/clear").action == "clear"
    assert plan_terminal_local_command("/status").action == "status"

    help_plan = plan_terminal_local_command("/?")
    assert help_plan.action == "help"
    assert help_plan.message == TERMINAL_LOCAL_HELP_MESSAGE

    help_plan = plan_terminal_local_command("/help")
    assert help_plan.action == "help"
    assert help_plan.message == TERMINAL_LOCAL_HELP_MESSAGE


def test_plan_terminal_local_command_leaves_rich_slash_commands_to_chatwidget_views() -> None:
    # Rust owner: chatwidget::slash_dispatch separates local command effects
    # from view-opening or richer command flows such as /model.
    assert plan_terminal_local_command("/model").action == "none"
    assert plan_terminal_local_command("/model gpt").action == "none"
    assert plan_terminal_local_command("/permissions").action == "none"
    assert plan_terminal_local_command("hello").action == "none"


def test_run_terminal_local_command_plan_dispatches_terminal_callbacks() -> None:
    # Rust owner: chatwidget::slash_dispatch chooses the effect category, while
    # terminal runtime supplies callback endpoints for the small local subset.
    calls: list[tuple[str, str]] = []

    callbacks = {
        "clear": lambda: calls.append(("clear", "")),
        "help_": lambda message: calls.append(("help", message)),
        "status": lambda: calls.append(("status", "")),
    }

    assert run_terminal_local_command_plan(TerminalLocalCommandPlan("clear"), **callbacks) is True
    assert run_terminal_local_command_plan(TerminalLocalCommandPlan("help", "hi"), **callbacks) is True
    assert run_terminal_local_command_plan(TerminalLocalCommandPlan("status"), **callbacks) is True
    assert run_terminal_local_command_plan(TerminalLocalCommandPlan("none"), **callbacks) is False
    assert run_terminal_local_command_plan(TerminalLocalCommandPlan("exit"), **callbacks) == "exit"

    assert calls == [("clear", ""), ("help", "hi"), ("status", "")]


def test_run_terminal_local_command_plans_and_dispatches_prompt() -> None:
    # Rust owner: chatwidget::slash_dispatch parses prompt text as slash/local
    # command input before terminal_runtime may submit it as a user turn.
    calls: list[tuple[str, str]] = []

    callbacks = {
        "clear": lambda: calls.append(("clear", "")),
        "help_": lambda message: calls.append(("help", message)),
        "status": lambda: calls.append(("status", "")),
    }

    assert run_terminal_local_command("/clear", **callbacks) is True
    assert run_terminal_local_command("/help", **callbacks) is True
    assert run_terminal_local_command("/status", **callbacks) is True
    assert run_terminal_local_command("/model", **callbacks) is False
    assert run_terminal_local_command("/quit", **callbacks) == "exit"

    assert calls == [("clear", ""), ("help", TERMINAL_LOCAL_HELP_MESSAGE), ("status", "")]


def test_terminal_local_command_dispatcher_owns_prompt_dispatch() -> None:
    # Rust owner: chatwidget::slash_dispatch owns prompt-to-command dispatch.
    # terminal_runtime should hold this dispatcher rather than switching on
    # command plans itself.
    calls: list[tuple[str, str]] = []
    dispatcher = TerminalLocalCommandDispatcher(
        clear=lambda: calls.append(("clear", "")),
        help_=lambda message: calls.append(("help", message)),
        status=lambda: calls.append(("status", "")),
    )

    assert dispatcher.run("/clear") is True
    assert dispatcher.run("/?") is True
    assert dispatcher.run("/status") is True
    assert dispatcher.run("hello") is False
    assert dispatcher.run("/quit") == "exit"

    assert calls == [("clear", ""), ("help", TERMINAL_LOCAL_HELP_MESSAGE), ("status", "")]


def test_run_terminal_prompt_dispatch_skips_blank_input_before_local_command() -> None:
    # Rust owner: chatwidget::slash_dispatch owns the completed composer input
    # classification before codex-tui::tui may submit a user turn. Blank input
    # remains a prompt dispatch concern instead of a terminal_runtime branch.
    calls: list[str] = []

    result = run_terminal_prompt_dispatch("  \n", run_local_command=lambda prompt: calls.append(prompt))

    assert result == TerminalPromptDispatchResult("skip", "  ")
    assert calls == []


def test_run_terminal_prompt_dispatch_submits_normal_prompt_text() -> None:
    # Rust owner: chatwidget::slash_dispatch decides that non-command prompt
    # text flows to the normal user-turn path after terminal local commands
    # decline the input.
    calls: list[str] = []

    def run_local_command(prompt: str) -> bool | str:
        calls.append(prompt)
        return False

    result = run_terminal_prompt_dispatch("hello\n", run_local_command=run_local_command)

    assert result == TerminalPromptDispatchResult("submit", "hello")
    assert calls == ["hello"]


def test_run_terminal_prompt_dispatch_handles_local_commands_and_exit() -> None:
    # Rust owner: chatwidget::slash_dispatch owns command-effect classification;
    # terminal_runtime should consume the typed dispatch result rather than
    # switching on command strings or local command return values itself.
    calls: list[str] = []

    def run_local_command(prompt: str) -> bool | str:
        calls.append(prompt)
        if prompt == "/quit":
            return "exit"
        return True

    assert run_terminal_prompt_dispatch("/status\n", run_local_command=run_local_command) == TerminalPromptDispatchResult(
        "handled",
        "/status",
    )
    assert run_terminal_prompt_dispatch("/quit\n", run_local_command=run_local_command) == TerminalPromptDispatchResult(
        "exit",
        "/quit",
    )
    assert calls == ["/status", "/quit"]


def test_terminal_prompt_dispatcher_binds_local_command_runner() -> None:
    # Rust owner: codex-tui::chatwidget::slash_dispatch owns completed prompt
    # classification. terminal_runtime should consume this bound dispatcher
    # instead of calling run_terminal_prompt_dispatch directly in the loop.
    calls: list[str] = []
    dispatcher = TerminalPromptDispatcher(
        run_local_command=lambda prompt: calls.append(prompt) or (prompt == "/status"),
    )

    assert dispatcher.dispatch("hello\n") == TerminalPromptDispatchResult("submit", "hello")
    assert dispatcher.dispatch("/status\n") == TerminalPromptDispatchResult("handled", "/status")
    assert dispatcher.dispatch("   \n") == TerminalPromptDispatchResult("skip", "   ")
    assert calls == ["hello", "/status"]


def test_structured_inline_command_reaches_effect_dispatcher_with_arguments() -> None:
    calls: list[tuple[SlashCommand, str]] = []

    def dispatch(command: SlashCommand, args: str) -> TerminalPromptDispatchResult:
        calls.append((command, args))
        return TerminalPromptDispatchResult("handled", command=command)

    result = run_terminal_prompt_dispatch(
        InputResult.CommandWithArgs(SlashCommand.RAW, "on", ["inline-element"]),
        run_local_command=lambda _prompt: False,
        dispatch_command=dispatch,
    )

    assert result.command is SlashCommand.RAW
    assert result.prepared_args == PreparedSlashCommandArgs(
        args="on",
        text_elements=("inline-element",),
    )
    assert calls == [(SlashCommand.RAW, "on")]


def test_plugins_extension_opens_rust_owned_loading_view() -> None:
    events: list[object] = []
    widget = ChatWidgetProtocolRuntime()
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        active_thread_runtime=SimpleNamespace(
            session_config=SimpleNamespace(
                cwd=Path("/repo"),
                features=SimpleNamespace(enabled=lambda _feature: True),
            )
        ),
        handle_app_event=events.append,
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    result = dispatcher.dispatch(SlashCommand.PLUGINS)

    assert result.action == "show_view"
    assert result.command is SlashCommand.PLUGINS
    assert result.view.title == "Plugins"
    assert result.view.subtitle == "Loading available plugins..."
    assert events and getattr(events[0], "kind", None) == "FetchPluginsList"


def test_logout_dispatches_app_event_then_requests_terminal_exit() -> None:
    events: list[object] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        handle_app_event=events.append,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.LOGOUT
    )

    assert result == TerminalPromptDispatchResult(
        "exit",
        command=SlashCommand.LOGOUT,
    )
    assert events and getattr(events[0], "kind", None) == "Logout"


def test_rollout_displays_current_path_or_missing_message() -> None:
    messages: list[tuple[str, str | None]] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        rollout_path=Path("/tmp/codex-test-rollout.jsonl"),
        insert_info_history_message=lambda message, hint=None: messages.append(
            (message, hint)
        ),
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    assert dispatcher.dispatch(SlashCommand.ROLLOUT).action == "handled"
    assert messages == [
        (f"Current rollout path: {Path('/tmp/codex-test-rollout.jsonl')}", None)
    ]

    app_runtime.rollout_path = None
    dispatcher.dispatch(SlashCommand.ROLLOUT)
    assert messages[-1] == ("Rollout path is not available yet.", None)


def test_test_approval_projects_rust_fixture_into_apply_patch_approval() -> None:
    plans: list[object] = []
    widget = ChatWidgetProtocolRuntime()
    widget.bind_approval_request_sink(plans.append)
    app_runtime = SimpleNamespace(chat_widget=widget)

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.TEST_APPROVAL
    )

    assert result == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.TEST_APPROVAL,
    )
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind == "apply_patch"
    assert plan.data["id"] == "1"
    assert {
        path.as_posix(): change.to_dict()
        for path, change in plan.data["changes"].items()
    } == {
        "/tmp/test.txt": {"type": "add", "content": "test"},
        "/tmp/test2.txt": {
            "type": "update",
            "unified_diff": "+test\n-test2",
            "move_path": None,
        },
    }


def test_memory_drop_reports_rust_owned_tui_stub_without_operation() -> None:
    cells: list[object] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        insert_history_cell=cells.append,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.MEMORY_DROP
    )

    assert result == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.MEMORY_DROP,
    )
    rendered = "\n".join(
        line_text(line) for line in cells[0].display_lines(80)
    )
    assert "Memory maintenance: Not available in TUI yet." in rendered


def test_memory_update_reports_rust_owned_tui_stub_without_operation() -> None:
    cells: list[object] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        insert_history_cell=cells.append,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.MEMORY_UPDATE
    )

    assert result == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.MEMORY_UPDATE,
    )
    rendered = "\n".join(
        line_text(line) for line in cells[0].display_lines(80)
    )
    assert "Memory maintenance: Not available in TUI yet." in rendered


def test_ps_inserts_unified_exec_processes_history_cell() -> None:
    cells: list[object] = []
    widget = ChatWidgetProtocolRuntime()
    widget.command_lifecycle.unified_exec_processes = [
        SimpleNamespace(command_display="sleep 5", recent_chunks=["waiting"])
    ]
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        insert_history_cell=cells.append,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.PS
    )

    assert result.action == "handled"
    rendered = "\n".join(
        line_text(line) for line in cells[0].display_lines(80)
    )
    assert "Background terminals" in rendered
    assert "sleep 5" in rendered
    assert "waiting" in rendered


def test_stop_submits_cleanup_clears_processes_and_reports_confirmation() -> None:
    submitted: list[object] = []
    messages: list[tuple[str, str | None]] = []
    widget = ChatWidgetProtocolRuntime()
    widget.command_lifecycle.unified_exec_processes = [
        SimpleNamespace(command_display="sleep 5", recent_chunks=[])
    ]
    widget.command_lifecycle.sync_unified_exec_footer()
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        submit_op=lambda operation: submitted.append(operation),
        insert_info_history_message=lambda message, hint=None: messages.append(
            (message, hint)
        ),
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(
        app_runtime,
        submit_operation=lambda _summary, submit: submit(),
    )

    result = dispatcher.dispatch(SlashCommand.STOP)

    assert result.action == "handled"
    assert getattr(submitted[0], "kind", None) == "CleanBackgroundTerminals"
    assert widget.command_lifecycle.unified_exec_processes == []
    assert widget.command_lifecycle.footer_processes == []
    assert messages == [("Stopping all background terminals.", None)]


def test_realtime_starts_and_stops_through_shared_state_and_footer_override() -> None:
    from pycodex.features import Feature

    submitted: list[object] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        active_thread_runtime=SimpleNamespace(
            session_config=SimpleNamespace(
                features=SimpleNamespace(
                    enabled=lambda feature: feature is Feature.REALTIME_CONVERSATION
                )
            )
        ),
        submit_op=lambda operation: submitted.append(operation),
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(
        app_runtime,
        submit_operation=lambda _summary, submit: submit(),
    )

    first = dispatcher.dispatch(SlashCommand.REALTIME)
    second = dispatcher.dispatch(SlashCommand.REALTIME)

    assert first.action == second.action == "handled"
    assert [operation.kind for operation in submitted] == [
        "RealtimeConversationStart",
        "RealtimeConversationClose",
    ]
    assert app_runtime.footer_hint_override is None


def test_ide_command_routes_through_chatwidget_ide_context_owner() -> None:
    app_runtime = TuiAppRuntime(
        ExecFunctionActiveThreadRuntime(lambda _prompt: "ok"),
        thread_id="thread-1",
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    result = dispatcher.dispatch(SlashCommand.IDE, "off")

    assert result == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.IDE,
    )
    assert app_runtime.ide_context_state.ide_context.is_enabled() is False
    assert app_runtime.pending_history_cells


def test_agent_command_routes_through_open_agent_picker_app_event() -> None:
    # Rust: chatwidget::slash_dispatch sends AppEvent::OpenAgentPicker.
    events: list[AppEvent] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        handle_app_event=events.append,
        insert_info_history_message=lambda *_args: None,
        insert_history_cell=lambda _cell: None,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.AGENT
    )

    assert result == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.AGENT,
    )
    assert events == [AppEvent.open_agent_picker()]


def test_plan_command_switches_mode_before_optional_inline_submission() -> None:
    # Rust tests/chatwidget/plan_mode.rs:
    # /plan applies the collaboration mask through chatwidget::settings, emits
    # OverrideTurnContext for the thread, and does not add a success message.
    app_runtime = TuiAppRuntime(
        ExecFunctionActiveThreadRuntime(lambda _prompt: "ok"),
        thread_id="thread-1",
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    bare = dispatcher.dispatch(SlashCommand.PLAN)
    app_runtime.drain_app_events()
    inline = dispatcher.dispatch(SlashCommand.PLAN, "inspect the parser")
    app_runtime.drain_app_events()

    assert bare == TerminalPromptDispatchResult("handled", command=SlashCommand.PLAN)
    assert inline == TerminalPromptDispatchResult(
        "submit",
        prompt="inspect the parser",
        command=SlashCommand.PLAN,
    )
    assert app_runtime.chat_widget.active_collaboration_mask.mode is ModeKind.PLAN
    assert [op.kind for op in app_runtime.submitted_ops] == [
        "OverrideTurnContext",
        "OverrideTurnContext",
    ]
    assert all(
        op.payload["collaboration_mode"].mode is ModeKind.PLAN
        for op in app_runtime.submitted_ops
    )
    assert all(
        message != "Plan mode enabled."
        for message, _hint in app_runtime.chat_widget.info_messages
    )


def _goal_dispatcher(events, history, *, thread_id="thread-1"):
    return TerminalSlashCommandEffectDispatcher(
        SimpleNamespace(
            routing_state=SimpleNamespace(active_thread_id=thread_id),
            chat_widget=ChatWidgetProtocolRuntime(),
            handle_app_event=events.append,
            append_message_history_entry=history.append,
            insert_history_cell=lambda _cell: None,
        )
    )


def test_goal_objective_emits_set_event_without_direct_runtime_mutation() -> None:
    # Rust: slash_commands.rs goal submission emits SetThreadGoalObjective.
    events: list[AppEvent] = []
    history: list[str] = []

    result = _goal_dispatcher(events, history).dispatch(
        SlashCommand.GOAL,
        "improve benchmark coverage",
    )

    assert result == TerminalPromptDispatchResult("handled", command=SlashCommand.GOAL)
    assert events == [
        AppEvent.set_thread_goal_objective(
            "thread-1",
            "improve benchmark coverage",
            ThreadGoalSetMode.confirm_if_exists(),
        )
    ]
    assert history == ["/goal improve benchmark coverage"]


def test_bare_goal_emits_open_menu_event() -> None:
    events: list[AppEvent] = []
    history: list[str] = []

    result = _goal_dispatcher(events, history).dispatch(SlashCommand.GOAL)

    assert result == TerminalPromptDispatchResult("handled", command=SlashCommand.GOAL)
    assert events == [AppEvent.open_thread_goal_menu("thread-1")]
    assert history == ["/goal"]


def test_goal_edit_emits_editor_event_for_persisted_and_unstarted_threads() -> None:
    # Rust: slash_commands.rs::goal_edit_slash_command_opens_goal_editor checks
    # both Some(thread_id) and None, and emits no submit operation.
    for thread_id in ("thread-1", None):
        events: list[AppEvent] = []
        history: list[str] = []

        result = _goal_dispatcher(events, history, thread_id=thread_id).dispatch(
            SlashCommand.GOAL,
            "edit",
        )

        assert result == TerminalPromptDispatchResult("handled", command=SlashCommand.GOAL)
        assert events == [AppEvent.open_thread_goal_editor(thread_id)]
        assert history == []


def test_goal_control_commands_emit_app_events() -> None:
    events: list[AppEvent] = []
    history: list[str] = []
    dispatcher = _goal_dispatcher(events, history)

    dispatcher.dispatch(SlashCommand.GOAL, "pause")
    dispatcher.dispatch(SlashCommand.GOAL, "resume")
    dispatcher.dispatch(SlashCommand.GOAL, "clear")

    assert events == [
        AppEvent.set_thread_goal_status("thread-1", "paused"),
        AppEvent.set_thread_goal_status("thread-1", "active"),
        AppEvent.clear_thread_goal("thread-1"),
    ]
    assert history == ["/goal pause", "/goal resume", "/goal clear"]


def test_mention_command_returns_composer_mutation_instead_of_user_turn() -> None:
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        insert_info_history_message=lambda *_args: None,
        insert_history_cell=lambda _cell: None,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(SlashCommand.MENTION)

    assert result == TerminalPromptDispatchResult(
        "compose",
        prompt="@",
        command=SlashCommand.MENTION,
    )


def test_vim_command_toggles_chatwidget_state_and_notice() -> None:
    widget = ChatWidgetProtocolRuntime()
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        insert_info_history_message=lambda *_args: None,
        insert_history_cell=lambda _cell: None,
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    first = dispatcher.dispatch(SlashCommand.VIM)
    second = dispatcher.dispatch(SlashCommand.VIM)

    assert first == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.VIM,
    )
    assert second == first
    assert widget.vim_enabled is False
    assert [message for message, _hint in widget.info_messages[-2:]] == [
        "Vim mode enabled.",
        "Vim mode disabled.",
    ]


def test_setup_default_sandbox_emits_elevated_setup_app_event_on_windows(
    monkeypatch,
) -> None:
    # Rust: SlashCommand::ElevateSandbox is visible only in degraded Windows
    # sandbox mode and emits BeginWindowsSandboxElevatedSetup with the auto
    # approval preset instead of becoming a user turn.
    monkeypatch.setattr(
        "pycodex.tui.chatwidget.slash_dispatch.os.name",
        "nt",
    )
    widget = ChatWidgetProtocolRuntime()
    widget.config.windows_degraded_sandbox_active = True
    events: list[AppEvent] = []
    widget.app_event_tx = SimpleNamespace(send=events.append)
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        insert_info_history_message=lambda *_args: None,
        insert_history_cell=lambda _cell: None,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.ELEVATE_SANDBOX
    )

    assert result == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.ELEVATE_SANDBOX,
    )
    assert len(events) == 1
    assert events[0].kind == "BeginWindowsSandboxElevatedSetup"
    assert events[0].payload["preset"].id == "auto"
    assert events[0].payload["profile_selection"] is None


def test_sandbox_add_read_dir_emits_path_event_and_bare_usage() -> None:
    events: list[AppEvent] = []
    cells: list[object] = []
    widget = ChatWidgetProtocolRuntime()
    widget.app_event_tx = SimpleNamespace(send=events.append)
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        insert_info_history_message=lambda *_args: None,
        insert_history_cell=cells.append,
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    inline = dispatcher.dispatch(
        SlashCommand.SANDBOX_READ_ROOT,
        r"C:\missing read root",
    )
    bare = dispatcher.dispatch(SlashCommand.SANDBOX_READ_ROOT)

    assert inline == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.SANDBOX_READ_ROOT,
    )
    assert bare == inline
    assert events == [
        AppEvent.begin_windows_sandbox_grant_read_root(
            r"C:\missing read root"
        )
    ]
    assert cells


def test_init_existing_file_uses_rust_skip_notice_without_submitting(tmp_path) -> None:
    # Rust test: chatwidget/tests/slash_commands.rs keeps an existing AGENTS.md
    # intact and reports the local /init guard instead of creating a UserTurn.
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("existing", encoding="utf-8")
    messages: list[tuple[str, str | None]] = []
    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(
            session_config=SimpleNamespace(cwd=tmp_path)
        ),
        insert_info_history_message=lambda message, hint=None: messages.append(
            (message, hint)
        ),
        insert_history_cell=lambda _cell: None,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.INIT
    )

    assert result == TerminalPromptDispatchResult(
        "handled",
        command=SlashCommand.INIT,
    )
    assert agents_path.read_text(encoding="utf-8") == "existing"
    assert messages == [
        (
            "AGENTS.md already exists here. Skipping /init to avoid overwriting it.",
            None,
        )
    ]


def test_init_success_submits_fixed_complete_prompt_without_rust_runtime_dependency(
    tmp_path,
) -> None:
    # Rust anchor: SlashCommand::Init -> submit_user_message(INIT_PROMPT).
    app_runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(
            session_config=SimpleNamespace(cwd=tmp_path)
        ),
        insert_info_history_message=lambda *_args: None,
        insert_history_cell=lambda _cell: None,
    )

    result = TerminalSlashCommandEffectDispatcher(app_runtime).dispatch(
        SlashCommand.INIT
    )

    assert result.action == "submit"
    assert result.command is SlashCommand.INIT
    assert result.prompt == EXPECTED_INIT_PROMPT
    assert result.prompt.endswith("\n")
    assert "—" in result.prompt
    assert "project’s Git history" in result.prompt
    assert result.prompt != "/init"
    assert "Create an AGENTS.md file that explains" not in result.prompt
    source = inspect.getsource(slash_dispatch_module)
    assert '"codex" / "codex-rs"' not in source
    init_source = inspect.getsource(TerminalSlashCommandEffectDispatcher._init)
    assert "prompt_path" not in init_source
    assert "read_text" not in init_source


def test_init_registry_contract_is_bare_and_unavailable_during_task() -> None:
    assert SlashCommand.INIT.supports_inline_args() is False
    assert SlashCommand.INIT.available_during_task() is False


def test_guarded_command_emits_reason_instead_of_opening_or_submitting() -> None:
    cells: list[object] = []
    widget = ChatWidgetProtocolRuntime()
    widget.active_side_conversation = True
    app_runtime = SimpleNamespace(
        chat_widget=widget,
        insert_info_history_message=lambda *_args: None,
        insert_history_cell=cells.append,
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    result = dispatcher.guard(SlashCommand.MODEL)

    assert result == TerminalPromptDispatchResult("handled", command=SlashCommand.MODEL)
    assert cells


def test_slash_command_args_elements_remaps_overlapping_byte_ranges() -> None:
    elements = [
        TextElement(ByteRange(0, 4), "before"),
        TextElement(ByteRange(7, 12), "first"),
        TextElement(ByteRange(13, 20), "second"),
        TextElement(ByteRange(30, 40), "after"),
    ]

    remapped = slash_command_args_elements("hello world", 7, elements)

    assert remapped == [
        TextElement(ByteRange(0, 5), "first"),
        TextElement(ByteRange(6, 11), "second"),
    ]


def test_prepared_inline_user_message_preserves_payloads() -> None:
    prepared = PreparedSlashCommandArgs(
        args="hello",
        text_elements=("text",),
        local_images=("local",),
        remote_image_urls=("https://example.com/a.png",),
        mention_bindings=("mention",),
        source=SlashCommandDispatchSource.QUEUED,
    )

    message = prepared_inline_user_message(prepared)

    assert message.text == "hello"
    assert message.text_elements == ("text",)
    assert message.local_images == ("local",)
    assert message.remote_image_urls == ("https://example.com/a.png",)
    assert message.mention_bindings == ("mention",)


def test_inline_argument_classifiers_for_raw_mcp_keymap_and_pets() -> None:
    assert raw_output_mode_arg("ON") is True
    assert raw_output_mode_arg("off") is False
    assert raw_output_mode_arg("maybe") is None
    assert mcp_detail_arg(" verbose ") == "full"
    assert mcp_detail_arg("tools") is None
    assert keymap_arg_action("") == "picker"
    assert keymap_arg_action("debug") == "debug"
    assert keymap_arg_action("bad") is None
    assert pets_disable_arg("hidden") is True
    assert pets_disable_arg("codex") is False
