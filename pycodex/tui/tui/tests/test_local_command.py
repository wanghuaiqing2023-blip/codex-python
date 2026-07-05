from pycodex.tui.tui.local_command import (
    HELP_MESSAGE,
    TerminalLocalCommandDispatcher,
    TerminalLocalCommandPlan,
    plan_terminal_local_command,
    run_terminal_local_command,
    run_terminal_local_command_plan,
)


def test_plan_terminal_local_command_handles_exit_aliases() -> None:
    assert plan_terminal_local_command("/quit").action == "exit"
    assert plan_terminal_local_command("/exit").action == "exit"
    assert plan_terminal_local_command(":q").action == "exit"
    assert plan_terminal_local_command("q").action == "exit"
    assert plan_terminal_local_command("quit").action == "exit"


def test_plan_terminal_local_command_handles_terminal_local_subset() -> None:
    assert plan_terminal_local_command("/clear").action == "clear"
    assert plan_terminal_local_command("/status").action == "status"

    help_plan = plan_terminal_local_command("/?")
    assert help_plan.action == "help"
    assert help_plan.message == HELP_MESSAGE

    help_plan = plan_terminal_local_command("/help")
    assert help_plan.action == "help"
    assert help_plan.message == HELP_MESSAGE


def test_plan_terminal_local_command_leaves_rich_slash_commands_to_chatwidget() -> None:
    assert plan_terminal_local_command("/model").action == "none"
    assert plan_terminal_local_command("/model gpt").action == "none"
    assert plan_terminal_local_command("/permissions").action == "none"
    assert plan_terminal_local_command("hello").action == "none"


def test_run_terminal_local_command_plan_dispatches_terminal_callbacks() -> None:
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
    # Rust owner: codex-tui slash commands are parsed before chatwidget dispatch;
    # the lightweight terminal path keeps that small local subset in this module.
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

    assert calls == [("clear", ""), ("help", HELP_MESSAGE), ("status", "")]


def test_terminal_local_command_dispatcher_owns_prompt_dispatch() -> None:
    # Rust owner: tui local/slash command routing resolves prompt text before
    # normal user-turn submission. The terminal runner should hold a dispatcher
    # rather than switching on local command plans itself.
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

    assert calls == [("clear", ""), ("help", HELP_MESSAGE), ("status", "")]
