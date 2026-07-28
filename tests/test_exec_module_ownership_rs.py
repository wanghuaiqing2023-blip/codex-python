from __future__ import annotations

from unittest.mock import patch

import pycodex.exec.event_processor as event_processor
from pycodex.exec import events
from pycodex.exec.event_processor_with_human_output import EventProcessorWithHumanOutput
from pycodex.exec.event_processor_with_jsonl_output import EventProcessorWithJsonOutput
from pycodex.exec.main import main


def test_event_processors_use_their_rust_module_owners() -> None:
    # Rust crate: codex-exec.
    # Modules: event_processor_with_human_output.rs and
    # event_processor_with_jsonl_output.rs.
    assert EventProcessorWithHumanOutput.__module__.endswith(
        "event_processor_with_human_output"
    )
    assert EventProcessorWithJsonOutput.__module__.endswith(
        "event_processor_with_jsonl_output"
    )
    assert not hasattr(event_processor, "EventProcessorWithHumanOutput")
    assert not hasattr(event_processor, "EventProcessorWithJsonOutput")


def test_exec_events_owns_rust_output_types() -> None:
    # Rust module: codex-exec/src/exec_events.rs.
    for name in (
        "AgentMessageItem",
        "CommandExecutionItem",
        "FileChangeItem",
        "McpToolCallItem",
        "ThreadItem",
        "TodoListItem",
        "Usage",
    ):
        assert getattr(events, name).__module__ == "pycodex.exec.events"


def test_codex_exec_binary_routes_through_arg0_then_shared_cli() -> None:
    # Rust binary: codex-exec/src/main.rs.
    with (
        patch("pycodex.exec.main.arg0_dispatch_or_else") as dispatch,
        patch("pycodex.cli.main.main", return_value=0) as cli_main,
    ):
        dispatch.side_effect = lambda callback, **_kwargs: callback(object())

        assert main(["--json", "hello"]) == 0

    cli_main.assert_called_once_with(["exec", "--json", "hello"])
