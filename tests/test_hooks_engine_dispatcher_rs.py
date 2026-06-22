import asyncio
from pathlib import Path

from pycodex.hooks import CommandRunResult
from pycodex.hooks import CommandShell
from pycodex.hooks import ConfiguredHandler
from pycodex.hooks import ParsedHandler
from pycodex.hooks import completed_summary
from pycodex.hooks import execute_handlers
from pycodex.hooks import running_summary
from pycodex.hooks import scope_for_event
from pycodex.hooks import select_handlers
from pycodex.hooks import select_handlers_for_matcher_inputs
from pycodex.protocol import HookCompletedEvent
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookScope
from pycodex.protocol import HookSource


def make_handler(
    event_name: HookEventName,
    matcher: str | None,
    command: str,
    display_order: int,
) -> ConfiguredHandler:
    return ConfiguredHandler(
        event_name=event_name,
        matcher=matcher,
        command=command,
        timeout_sec=5,
        status_message=None,
        source_path=Path("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=display_order,
    )


def test_select_handlers_keeps_duplicate_stop_handlers():
    # Rust crate/module/test:
    # codex-hooks/src/engine/dispatcher.rs::select_handlers_keeps_duplicate_stop_handlers.
    handlers = [
        make_handler(HookEventName.STOP, None, "echo same", 0),
        make_handler(HookEventName.STOP, None, "echo same", 1),
    ]

    selected = select_handlers(handlers, HookEventName.STOP, None)

    assert len(selected) == 2
    assert [handler.display_order for handler in selected] == [0, 1]


def test_select_handlers_keeps_overlapping_session_start_matchers():
    # Rust crate/module/test:
    # codex-hooks/src/engine/dispatcher.rs::select_handlers_keeps_overlapping_session_start_matchers.
    handlers = [
        make_handler(HookEventName.SESSION_START, "start.*", "echo same", 0),
        make_handler(HookEventName.SESSION_START, "^startup$", "echo same", 1),
    ]

    selected = select_handlers(handlers, HookEventName.SESSION_START, "startup")

    assert len(selected) == 2
    assert [handler.display_order for handler in selected] == [0, 1]


def test_compact_hooks_match_trigger():
    # Rust crate/module/test:
    # codex-hooks/src/engine/dispatcher.rs::compact_hooks_match_trigger.
    handlers = [
        make_handler(HookEventName.PRE_COMPACT, "manual", "echo manual", 0),
        make_handler(HookEventName.PRE_COMPACT, "auto", "echo auto", 1),
    ]

    selected = select_handlers(handlers, HookEventName.PRE_COMPACT, "manual")

    assert len(selected) == 1
    assert selected[0].display_order == 0


def test_tool_use_handlers_match_tool_name_and_star_matcher():
    # Rust crate/module/tests:
    # pre_tool_use_matches_tool_name, post_tool_use_matches_tool_name, and
    # pre_tool_use_star_matcher_matches_all_tools.
    pre_handlers = [
        make_handler(HookEventName.PRE_TOOL_USE, "^Bash$", "echo same", 0),
        make_handler(HookEventName.PRE_TOOL_USE, "^Edit$", "echo same", 1),
    ]
    post_handlers = [
        make_handler(HookEventName.POST_TOOL_USE, "^Bash$", "echo same", 0),
        make_handler(HookEventName.POST_TOOL_USE, "^Edit$", "echo same", 1),
    ]
    star_handlers = [
        make_handler(HookEventName.PRE_TOOL_USE, "*", "echo same", 0),
        make_handler(HookEventName.PRE_TOOL_USE, "^Edit$", "echo same", 1),
    ]

    assert [h.display_order for h in select_handlers(pre_handlers, HookEventName.PRE_TOOL_USE, "Bash")] == [0]
    assert [h.display_order for h in select_handlers(post_handlers, HookEventName.POST_TOOL_USE, "Bash")] == [0]
    assert [h.display_order for h in select_handlers(star_handlers, HookEventName.PRE_TOOL_USE, "Bash")] == [0]


def test_pre_tool_use_regex_alternation_and_aliases_match_once_per_handler():
    # Rust crate/module/tests:
    # pre_tool_use_regex_alternation_matches_each_tool_name and
    # pre_tool_use_aliases_match_once_per_handler.
    alternating = [make_handler(HookEventName.PRE_TOOL_USE, "Edit|Write", "echo same", 0)]
    assert len(select_handlers(alternating, HookEventName.PRE_TOOL_USE, "Edit")) == 1
    assert len(select_handlers(alternating, HookEventName.PRE_TOOL_USE, "Write")) == 1
    assert len(select_handlers(alternating, HookEventName.PRE_TOOL_USE, "Bash")) == 0

    aliases = [
        make_handler(HookEventName.PRE_TOOL_USE, "^apply_patch$", "echo apply_patch", 0),
        make_handler(HookEventName.PRE_TOOL_USE, "^Write$", "echo write", 1),
        make_handler(HookEventName.PRE_TOOL_USE, "^Edit$", "echo edit", 2),
        make_handler(HookEventName.PRE_TOOL_USE, "apply_patch|Write|Edit", "echo combined", 3),
    ]
    selected = select_handlers_for_matcher_inputs(
        aliases,
        HookEventName.PRE_TOOL_USE,
        ["apply_patch", "Write", "Edit"],
    )

    assert [handler.display_order for handler in selected] == [0, 1, 2, 3]


def test_user_prompt_submit_ignores_matcher_and_selection_preserves_order():
    # Rust crate/module/tests:
    # user_prompt_submit_ignores_matcher and select_handlers_preserves_declaration_order.
    prompt_handlers = [
        make_handler(HookEventName.USER_PROMPT_SUBMIT, "^hello", "echo first", 0),
        make_handler(HookEventName.USER_PROMPT_SUBMIT, "[", "echo second", 1),
    ]
    selected_prompt = select_handlers(prompt_handlers, HookEventName.USER_PROMPT_SUBMIT, None)
    assert [handler.display_order for handler in selected_prompt] == [0, 1]

    stop_handlers = [
        make_handler(HookEventName.STOP, None, "first", 0),
        make_handler(HookEventName.STOP, None, "second", 1),
        make_handler(HookEventName.STOP, None, "third", 2),
    ]
    selected_stop = select_handlers(stop_handlers, HookEventName.STOP, None)
    assert [handler.command for handler in selected_stop] == ["first", "second", "third"]


def test_scope_and_summaries_follow_dispatcher_contract():
    # Rust source contract: scope_for_event maps start events to Thread and all
    # other hook events to Turn; summaries project command handler metadata.
    session_handler = make_handler(HookEventName.SESSION_START, None, "echo start", 7)
    stop_handler = make_handler(HookEventName.STOP, None, "echo stop", 8)
    assert scope_for_event(HookEventName.SESSION_START) == HookScope.THREAD
    assert scope_for_event(HookEventName.SUBAGENT_START) == HookScope.THREAD
    assert scope_for_event(HookEventName.STOP) == HookScope.TURN

    running = running_summary(session_handler)
    assert running.id == f"session-start:7:{Path('/tmp/hooks.json')}"
    assert running.scope == HookScope.THREAD
    assert running.status == HookRunStatus.RUNNING

    run_result = CommandRunResult(
        started_at=10,
        completed_at=12,
        duration_ms=200,
        exit_code=0,
        stdout="",
        stderr="",
    )
    completed = completed_summary(
        stop_handler,
        run_result,
        HookRunStatus.FAILED,
        [HookOutputEntry(HookOutputEntryKind.ERROR, "boom")],
    )
    assert completed.id == f"stop:8:{Path('/tmp/hooks.json')}"
    assert completed.scope == HookScope.TURN
    assert completed.started_at == 10
    assert completed.completed_at == 12
    assert completed.duration_ms == 200
    assert completed.entries[0].text == "boom"


def test_execute_handlers_assigns_completion_order_but_returns_declaration_order():
    # Rust source contract: execute_handlers records completion order as tasks
    # finish, then sorts returned ParsedHandler values by configured order.
    handlers = [
        make_handler(HookEventName.STOP, None, "slow", 0),
        make_handler(HookEventName.STOP, None, "fast", 1),
    ]

    async def fake_run_command(_shell, handler, input_json, cwd):
        assert input_json == "{}"
        assert cwd == Path("/tmp")
        if handler.command == "slow":
            await asyncio.sleep(0.02)
        return CommandRunResult(
            started_at=0,
            completed_at=1,
            duration_ms=1,
            exit_code=0,
            stdout=handler.command,
            stderr="",
        )

    def parse(handler, result, turn_id):
        return ParsedHandler(
            completed=HookCompletedEvent(
                turn_id=turn_id,
                run=completed_summary(handler, result, HookRunStatus.COMPLETED, []),
            ),
            data={"stdout": result.stdout},
        )

    parsed = asyncio.run(
        execute_handlers(
            CommandShell(program="", args=[]),
            handlers,
            "{}",
            Path("/tmp"),
            "turn-1",
            parse,
            run_command_func=fake_run_command,
        )
    )

    assert [item.data["stdout"] for item in parsed] == ["slow", "fast"]
    assert [item.completion_order for item in parsed] == [1, 0]
    assert [item.completed.turn_id for item in parsed] == ["turn-1", "turn-1"]
