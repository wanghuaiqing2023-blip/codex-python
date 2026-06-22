from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.thread_manager_sample import (
    Args,
    SampleAdapters,
    SampleError,
    new_config,
    parse_args,
    prompt_from_args_or_stdin,
    run_main,
    run_turn,
)


class Pipe(io.StringIO):
    def __init__(self, value: str, terminal: bool = False) -> None:
        super().__init__(value)
        self._terminal = terminal

    def isatty(self) -> bool:
        return self._terminal


@dataclass
class Event:
    msg: object


@dataclass
class TurnStartedEvent:
    turn_id: str


@dataclass
class TurnCompleteEvent:
    turn_id: str = "turn-1"


@dataclass
class ErrorEvent:
    message: str


class FakeThread:
    def __init__(self, events: list[object]) -> None:
        self.events = list(events)
        self.submitted = []
        self.shutdown = False

    async def submit(self, op):
        self.submitted.append(op)

    async def next_event(self):
        return Event(self.events.pop(0))

    async def shutdown_and_wait(self):
        self.shutdown = True


class FakeThreadManager:
    def __init__(self, thread: FakeThread) -> None:
        self.thread = thread
        self.removed = []

    async def start_thread(self, config):
        return SimpleNamespace(thread_id="thread-1", thread=self.thread)

    async def remove_thread(self, thread_id):
        self.removed.append(str(thread_id))


def test_parse_args_model_and_trailing_prompt():
    # Rust crate/module: codex-thread-manager-sample src/main.rs::Args.
    args = parse_args(["--model", "gpt-test", "hello", "world"])

    assert args.model == "gpt-test"
    assert args.prompt == ("hello", "world")


def test_prompt_from_args_or_stdin_matches_rust_rules():
    # Rust source contract: prompt args are joined with spaces; piped stdin
    # normalizes CRLF/CR to LF and cannot be blank.
    assert prompt_from_args_or_stdin(Args(model=None, prompt=("hello", "world"))) == "hello world"
    assert prompt_from_args_or_stdin(Args(model=None), Pipe("a\r\nb\rc\n")) == "a\nb\nc\n"
    with pytest.raises(SampleError, match="pass a prompt argument"):
        prompt_from_args_or_stdin(Args(model=None), Pipe("", terminal=True))
    with pytest.raises(SampleError, match="via stdin"):
        prompt_from_args_or_stdin(Args(model=None), Pipe("  \n"))


def test_new_config_sets_sample_defaults_without_cross_crate_side_effects(tmp_path: Path):
    # Rust source contract: new_config selects the OpenAI provider, read-only
    # permissions, ephemeral local config, disabled web search, and arg0 paths.
    arg0 = SimpleNamespace(
        codex_self_exe=Path("codex.exe"),
        codex_linux_sandbox_exe=Path("sandbox"),
        main_execve_wrapper_exe=Path("wrapper"),
    )
    adapters = SampleAdapters(
        find_codex_home=lambda: tmp_path,
        current_dir=lambda: tmp_path / "workspace",
        built_in_model_providers=lambda _base_url: {"openai": {"name": "OpenAI"}},
    )

    config = new_config("gpt-test", arg0, adapters)

    assert config.model == "gpt-test"
    assert config.model_provider_id == "openai"
    assert config.model_provider == {"name": "OpenAI"}
    assert config.codex_home == tmp_path
    assert config.cwd == tmp_path / "workspace"
    assert config.workspace_roots == [tmp_path / "workspace"]
    assert config.ephemeral is True
    assert config.analytics_enabled is False
    assert config.feedback_enabled is False
    assert config.codex_self_exe == Path("codex.exe")
    assert config.background_terminal_max_timeout == 300_000


def test_run_turn_writes_mapped_notifications_and_finishes():
    # Rust source contract: mapped item events after TurnStarted are written as
    # newline-delimited JSON, and TurnComplete ends the loop.
    thread = FakeThread(
        [
            TurnStartedEvent("turn-1"),
            {"type": "agent_message_content_delta", "delta": "hi"},
            TurnCompleteEvent(),
        ]
    )
    stdout = io.StringIO()
    adapters = SampleAdapters(
        item_event_to_server_notification=lambda _msg, thread_id, turn_id: {
            "thread_id": thread_id,
            "turn_id": turn_id,
        }
    )

    asyncio.run(run_turn(thread, "thread-1", "hello", stdout=stdout, adapters=adapters))

    assert thread.submitted[0].type == "user_input"
    assert '"thread_id":"thread-1"' in stdout.getvalue()
    assert '"turn_id":"turn-1"' in stdout.getvalue()


def test_run_turn_rejects_mapped_event_before_turn_started():
    thread = FakeThread([{"type": "agent_message_content_delta", "delta": "hi"}])

    with pytest.raises(SampleError, match="before turn started"):
        asyncio.run(run_turn(thread, "thread-1", "hello", stdout=io.StringIO()))


def test_run_turn_bails_on_error_and_approval_requests():
    for msg, expected in [
        (ErrorEvent("bad"), "bad"),
        ({"type": "exec_approval_request"}, "exec approval"),
        ({"type": "apply_patch_approval_request"}, "patch approval"),
        ({"type": "request_permissions"}, "permissions"),
        ({"type": "request_user_input"}, "user input"),
        ({"type": "dynamic_tool_call_request"}, "dynamic tool call"),
    ]:
        thread = FakeThread([TurnStartedEvent("turn-1"), msg])
        with pytest.raises(SampleError, match=expected):
            asyncio.run(run_turn(thread, "thread-1", "hello", stdout=io.StringIO()))


def test_run_main_starts_thread_runs_turn_shutdown_and_removes(tmp_path: Path):
    thread = FakeThread([TurnStartedEvent("turn-1"), TurnCompleteEvent()])
    manager = FakeThreadManager(thread)
    adapters = SampleAdapters(
        find_codex_home=lambda: tmp_path,
        current_dir=lambda: tmp_path / "workspace",
        built_in_model_providers=lambda _base_url: {"openai": {"name": "OpenAI"}},
        init_state_db=lambda _config: object(),
        thread_store_from_config=lambda _config, _state_db: object(),
        resolve_installation_id=lambda _home: "install-1",
        environment_manager_factory=lambda _config, _paths: object(),
        thread_manager_factory=lambda **_kwargs: manager,
    )

    asyncio.run(
        run_main(
            SimpleNamespace(
                codex_self_exe=tmp_path / "bin" / "codex",
                codex_linux_sandbox_exe=None,
                main_execve_wrapper_exe=None,
            ),
            ["hello"],
            stdout=io.StringIO(),
            adapters=adapters,
        )
    )

    assert thread.shutdown is True
    assert manager.removed == ["thread-1"]
