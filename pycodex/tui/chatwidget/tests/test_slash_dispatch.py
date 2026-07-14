# Rust owner: codex-tui::chatwidget::slash_dispatch.
from types import SimpleNamespace

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


def test_terminal_slash_command_routes_cover_every_registered_command() -> None:
    # Fixed Rust baseline 1c7832f: slash_command.rs defines the registry while
    # chatwidget::slash_dispatch must choose an effect, view, guard, or shim.
    routes = terminal_slash_command_routes()

    assert set(routes) == set(SlashCommand)
    assert {route.outcome for route in routes.values()} <= {"effect", "view", "shim"}
    assert routes[SlashCommand.DIFF].outcome == "effect"
    assert routes[SlashCommand.SETTINGS].outcome == "view"
    assert routes[SlashCommand.MCP].outcome == "shim"
    for command, route in routes.items():
        assert route.rust_owner
        assert route.argument_form == ("inline-or-bare" if command.supports_inline_args() else "bare")
        assert route.guards
        assert route.expected_effect
        assert route.python_owner
        assert route.product_test


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


def test_deferred_extension_command_emits_explicit_terminal_compatibility_message() -> None:
    messages: list[tuple[str, str | None]] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        insert_info_history_message=lambda message, hint=None: messages.append((message, hint)),
        insert_history_cell=lambda _cell: None,
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    result = dispatcher.dispatch(SlashCommand.MCP)

    assert result == TerminalPromptDispatchResult("handled", command=SlashCommand.MCP)
    assert messages and "not enabled" in messages[0][0]


def test_plan_command_switches_mode_before_optional_inline_submission() -> None:
    messages: list[str] = []
    activated: list[bool] = []
    app_runtime = SimpleNamespace(
        chat_widget=ChatWidgetProtocolRuntime(),
        activate_plan_mode=lambda: activated.append(True),
        insert_info_history_message=lambda message, hint=None: messages.append(message),
        insert_history_cell=lambda _cell: None,
    )
    dispatcher = TerminalSlashCommandEffectDispatcher(app_runtime)

    bare = dispatcher.dispatch(SlashCommand.PLAN)
    inline = dispatcher.dispatch(SlashCommand.PLAN, "inspect the parser")

    assert bare == TerminalPromptDispatchResult("handled", command=SlashCommand.PLAN)
    assert inline == TerminalPromptDispatchResult(
        "submit",
        prompt="inspect the parser",
        command=SlashCommand.PLAN,
    )
    assert activated == [True, True]
    assert messages == ["Plan mode enabled.", "Plan mode enabled."]


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
