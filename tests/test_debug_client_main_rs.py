"""Parity tests for Rust ``codex-debug-client/src/main.rs``."""

from __future__ import annotations

from collections import deque
import io
from pathlib import Path
from queue import Queue

import pytest

from pycodex.debug_client.commands import InputAction
from pycodex.debug_client.main import (
    Cli,
    drain_events,
    handle_command,
    parse_approval_policy,
    parse_args,
    print_help,
    run,
)
from pycodex.debug_client.output import Output
from pycodex.debug_client.state import ReaderEvent


class FakeClient:
    def __init__(self, thread_id: str = "thr-1") -> None:
        self._thread_id = thread_id
        self.calls: list[tuple[str, object]] = []
        self.known = {thread_id}
        self.started_reader: tuple[object, bool, bool] | None = None
        self.shutdown_called = False

    def initialize(self) -> None:
        self.calls.append(("initialize", None))

    def start_thread(self, params: object) -> str:
        self.calls.append(("start_thread", params))
        self._thread_id = "thr-start"
        self.known.add("thr-start")
        return "thr-start"

    def resume_thread(self, params: object) -> str:
        self.calls.append(("resume_thread", params))
        self._thread_id = "thr-resume"
        self.known.add("thr-resume")
        return "thr-resume"

    def start_reader(self, events: object, auto_approve: bool, filtered_output: bool) -> None:
        self.started_reader = (events, auto_approve, filtered_output)
        self.calls.append(("start_reader", (auto_approve, filtered_output)))

    def thread_id(self) -> str | None:
        return self._thread_id

    def send_turn(self, thread_id: str, text: str) -> int:
        self.calls.append(("send_turn", (thread_id, text)))
        return 9

    def request_thread_start(self, params: object) -> int:
        self.calls.append(("request_thread_start", params))
        return 10

    def request_thread_resume(self, params: object) -> int:
        self.calls.append(("request_thread_resume", params))
        return 11

    def request_thread_list(self, cursor: str | None = None) -> int:
        self.calls.append(("request_thread_list", cursor))
        return 12

    def use_thread(self, thread_id: str) -> bool:
        known = thread_id in self.known
        self._thread_id = thread_id
        self.known.add(thread_id)
        self.calls.append(("use_thread", thread_id))
        return known

    def shutdown(self) -> None:
        self.calls.append(("shutdown", None))
        self.shutdown_called = True


def make_output() -> tuple[Output, io.StringIO, io.StringIO]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    return Output.new(None, stdout=stdout, stderr=stderr, color=False), stdout, stderr


def test_parse_args_matches_cli_defaults_and_repeat_config() -> None:
    # Rust source: Cli clap defaults and repeated --config collection.
    assert parse_args([]) == Cli()

    parsed = parse_args(
        [
            "--codex-bin",
            "codex-dev",
            "-c",
            "a=b",
            "--config",
            "c=d",
            "--thread-id",
            "thr",
            "--approval-policy",
            "never",
            "--auto-approve",
            "--final-only",
            "--output-file",
            "out.jsonl",
            "--model",
            "gpt",
            "--model-provider",
            "openai",
            "--cwd",
            "C:/repo",
        ]
    )

    assert parsed == Cli(
        codex_bin="codex-dev",
        config_overrides=["a=b", "c=d"],
        thread_id="thr",
        approval_policy="never",
        auto_approve=True,
        final_only=True,
        output_file=Path("out.jsonl"),
        model="gpt",
        model_provider="openai",
        cwd="C:/repo",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("untrusted", "untrusted"),
        ("unless-trusted", "untrusted"),
        ("unlessTrusted", "untrusted"),
        ("on-failure", "on-failure"),
        ("onFailure", "on-failure"),
        ("on-request", "on-request"),
        ("onRequest", "on-request"),
        ("never", "never"),
    ],
)
def test_parse_approval_policy_aliases(raw: str, expected: str) -> None:
    # Rust source: parse_approval_policy accepts kebab/camel aliases.
    assert parse_approval_policy(raw) == expected


def test_parse_approval_policy_rejects_unknown_value() -> None:
    # Rust source: invalid approval policy includes expected value list.
    with pytest.raises(ValueError) as exc_info:
        parse_approval_policy("bogus")

    assert str(exc_info.value) == (
        "unknown approval policy: bogus. Expected one of: untrusted, on-failure, on-request, never"
    )


def test_print_help_matches_rust_lines() -> None:
    # Rust source: print_help writes the debug-client command inventory.
    output, _stdout, stderr = make_output()

    print_help(output)

    assert stderr.getvalue() == (
        "commands:\n"
        "  :help                 show this help\n"
        "  :new                  start a new thread\n"
        "  :resume <thread-id>   resume an existing thread\n"
        "  :use <thread-id>      switch the active thread\n"
        "  :refresh-thread       list available threads\n"
        "  :quit                 exit\n"
        "type a message to send it as a new turn\n"
    )


def test_drain_events_thread_ready_and_list() -> None:
    # Rust source: drain_events handles ThreadReady and ThreadList.
    output, _stdout, stderr = make_output()
    events: Queue[ReaderEvent] = Queue()
    events.put(ReaderEvent.thread_ready("thr-2"))
    events.put(ReaderEvent.thread_list(["thr-1", "thr-2"], "cursor"))
    events.put(ReaderEvent.thread_list([]))

    drain_events(events, output)

    assert stderr.getvalue() == (
        "active thread is now thr-2\n"
        "threads:\n"
        "  thr-1\n"
        "  thr-2\n"
        "more threads available, next cursor: cursor\n"
        "threads: (none)\n"
    )
    assert output.prompt_state.thread_id == "thr-2"


def test_drain_events_supports_list_like_receiver() -> None:
    # Rust source uses try_recv; Python accepts simple queues for tests.
    output, _stdout, stderr = make_output()
    events = deque([ReaderEvent.thread_list(["thr"])])

    drain_events(events, output)

    assert stderr.getvalue() == "threads:\n  thr\n"


def test_handle_command_help_and_quit() -> None:
    # Rust source: help prints help and quit stops the loop.
    output, _stdout, stderr = make_output()
    client = FakeClient()
    cli = Cli()

    assert handle_command(InputAction.help(), client, output, "on-request", cli) is True
    assert handle_command(InputAction.quit(), client, output, "on-request", cli) is False
    assert "commands:\n" in stderr.getvalue()


def test_handle_command_new_resume_use_and_refresh() -> None:
    # Rust source: handle_command dispatches all interactive commands to AppServerClient.
    output, _stdout, stderr = make_output()
    client = FakeClient("thr-known")
    cli = Cli(model="gpt", model_provider="openai", cwd="C:/repo")

    assert handle_command(InputAction.new_thread(), client, output, "never", cli) is True
    assert handle_command(InputAction.resume("thr-2"), client, output, "never", cli) is True
    assert handle_command(InputAction.use("thr-known"), client, output, "never", cli) is True
    assert handle_command(InputAction.use("thr-unknown"), client, output, "never", cli) is True
    assert handle_command(InputAction.refresh_thread(), client, output, "never", cli) is True

    assert [call[0] for call in client.calls] == [
        "request_thread_start",
        "request_thread_resume",
        "use_thread",
        "use_thread",
        "request_thread_list",
    ]
    assert "requested new thread (10)\n" in stderr.getvalue()
    assert "requested thread resume (11)\n" in stderr.getvalue()
    assert "switched active thread to thr-known\n" in stderr.getvalue()
    assert "switched active thread to thr-unknown (unknown; use :resume to load)\n" in stderr.getvalue()
    assert "requested thread list (12)\n" in stderr.getvalue()


def test_run_starts_new_thread_and_processes_input_lines() -> None:
    # Rust source: main initializes, starts thread, starts reader, prints help, loops over stdin lines.
    output, _stdout, stderr = make_output()
    created: list[FakeClient] = []

    def factory(codex_bin: str, config_overrides: list[str], out: Output, final_only: bool) -> FakeClient:
        client = FakeClient()
        created.append(client)
        assert codex_bin == "codex-dev"
        assert config_overrides == ["a=b"]
        assert out is output
        assert final_only is True
        return client

    run(
        Cli(codex_bin="codex-dev", config_overrides=["a=b"], final_only=True, auto_approve=True),
        input_lines=["hello\n", ":quit\n"],
        client_factory=factory,
        output=output,
    )

    client = created[0]
    assert [call[0] for call in client.calls] == [
        "initialize",
        "start_thread",
        "start_reader",
        "send_turn",
        "shutdown",
    ]
    assert client.started_reader is not None
    assert client.started_reader[1:] == (True, True)
    assert "connected to thread thr-start\n" in stderr.getvalue()
    assert "type a message to send it as a new turn\n" in stderr.getvalue()


def test_run_resumes_thread_and_reports_parse_errors() -> None:
    # Rust source: main resumes when --thread-id is present and prints parse errors.
    output, _stdout, stderr = make_output()
    created: list[FakeClient] = []

    def factory(_codex_bin: str, _config: list[str], _output: Output, _final_only: bool) -> FakeClient:
        client = FakeClient()
        created.append(client)
        return client

    run(
        Cli(thread_id="thr-old"),
        input_lines=[":bogus\n", ":quit\n"],
        client_factory=factory,
        output=output,
    )

    assert [call[0] for call in created[0].calls] == [
        "initialize",
        "resume_thread",
        "start_reader",
        "shutdown",
    ]
    assert "unknown command: bogus\n" in stderr.getvalue()
