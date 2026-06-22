"""CLI entrypoint glue for Rust ``codex-debug-client/src/main.rs``."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
import sys
from typing import Any, Iterable, TextIO

from .client import AppServerClient, build_thread_resume_params, build_thread_start_params
from .commands import InputAction, ParseError, UserCommand, parse_input
from .output import Output
from .state import ReaderEvent


@dataclass(frozen=True)
class Cli:
    codex_bin: str = "codex"
    config_overrides: list[str] = field(default_factory=list)
    thread_id: str | None = None
    approval_policy: str = "on-request"
    auto_approve: bool = False
    final_only: bool = False
    output_file: Path | None = None
    model: str | None = None
    model_provider: str | None = None
    cwd: str | None = None


def parse_args(argv: Iterable[str] | None = None) -> Cli:
    parser = argparse.ArgumentParser(prog="codex-debug-client", description="Minimal app-server client")
    parser.add_argument("--codex-bin", default="codex", help="Path to the `codex` CLI binary.")
    parser.add_argument(
        "-c",
        "--config",
        dest="config_overrides",
        action="append",
        default=[],
        metavar="key=value",
        help="Forwarded to the `codex` CLI as `--config key=value`. Repeatable.",
    )
    parser.add_argument("--thread-id", help="Resume an existing thread instead of starting a new one.")
    parser.add_argument("--approval-policy", default="on-request", help="Set the approval policy for the thread.")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve command/file-change approvals.")
    parser.add_argument("--final-only", action="store_true", help="Only show final assistant messages and tool calls.")
    parser.add_argument("--output-file", type=Path, metavar="PATH", help="Write raw server JSONL to this file.")
    parser.add_argument("--model", help="Optional model override when starting/resuming a thread.")
    parser.add_argument("--model-provider", help="Optional model provider override when starting/resuming a thread.")
    parser.add_argument("--cwd", help="Optional working directory override when starting/resuming a thread.")
    namespace = parser.parse_args(list(argv) if argv is not None else None)
    return Cli(
        codex_bin=namespace.codex_bin,
        config_overrides=list(namespace.config_overrides),
        thread_id=namespace.thread_id,
        approval_policy=namespace.approval_policy,
        auto_approve=namespace.auto_approve,
        final_only=namespace.final_only,
        output_file=namespace.output_file,
        model=namespace.model,
        model_provider=namespace.model_provider,
        cwd=namespace.cwd,
    )


def main(argv: Iterable[str] | None = None) -> int:
    run(parse_args(argv))
    return 0


def run(
    cli: Cli,
    *,
    input_lines: Iterable[str] | None = None,
    client_factory: Any | None = None,
    output: Output | None = None,
) -> None:
    jsonl_file: TextIO | None = None
    try:
        if cli.output_file is not None and output is None:
            jsonl_file = cli.output_file.open("w", encoding="utf-8")
        actual_output = output if output is not None else Output.new(jsonl_file)
        approval_policy = parse_approval_policy(cli.approval_policy)

        factory = client_factory if client_factory is not None else AppServerClient.spawn
        client = factory(cli.codex_bin, cli.config_overrides, actual_output, cli.final_only)
        client.initialize()

        if cli.thread_id is not None:
            thread_id = client.resume_thread(
                build_thread_resume_params(
                    cli.thread_id,
                    approval_policy,
                    cli.model,
                    cli.model_provider,
                    cli.cwd,
                )
            )
        else:
            thread_id = client.start_thread(
                build_thread_start_params(
                    approval_policy,
                    cli.model,
                    cli.model_provider,
                    cli.cwd,
                )
            )

        actual_output.client_line(f"connected to thread {thread_id}")
        actual_output.set_prompt(thread_id)

        events: Queue[ReaderEvent] = Queue()
        client.start_reader(events, cli.auto_approve, cli.final_only)

        print_help(actual_output)
        lines = input_lines if input_lines is not None else sys.stdin
        for raw_line in lines:
            drain_events(events, actual_output)
            prompt_thread = client.thread_id() or "no-thread"
            actual_output.prompt(prompt_thread)
            line = str(raw_line).rstrip("\n")
            action = _parse_input_or_report(line, actual_output)
            if action is None:
                continue
            if action.kind == "Message":
                active_thread = client.thread_id()
                if active_thread is None:
                    actual_output.client_line("no active thread; use :new or :resume <id>")
                    continue
                try:
                    client.send_turn(active_thread, str(action.value))
                except Exception as exc:
                    actual_output.client_line(f"failed to send turn: {exc}")
            elif action.kind == "Command":
                if not handle_command(action, client, actual_output, approval_policy, cli):
                    break
        client.shutdown()
    finally:
        if jsonl_file is not None:
            jsonl_file.close()


def handle_command(
    action: InputAction | UserCommand,
    client: AppServerClient,
    output: Output,
    approval_policy: str,
    cli: Cli,
) -> bool:
    command = action.command_name if isinstance(action, InputAction) else action
    argument = action.argument if isinstance(action, InputAction) else None

    if command is UserCommand.HELP:
        print_help(output)
        return True
    if command is UserCommand.QUIT:
        return False
    if command is UserCommand.NEW_THREAD:
        try:
            request_id = client.request_thread_start(
                build_thread_start_params(approval_policy, cli.model, cli.model_provider, cli.cwd)
            )
            output.client_line(f"requested new thread ({request_id!r})")
        except Exception as exc:
            output.client_line(f"failed to start thread: {exc}")
        return True
    if command is UserCommand.RESUME:
        try:
            request_id = client.request_thread_resume(
                build_thread_resume_params(str(argument), approval_policy, cli.model, cli.model_provider, cli.cwd)
            )
            output.client_line(f"requested thread resume ({request_id!r})")
        except Exception as exc:
            output.client_line(f"failed to resume thread: {exc}")
        return True
    if command is UserCommand.USE:
        thread_id = str(argument)
        known = client.use_thread(thread_id)
        output.set_prompt(thread_id)
        if known:
            output.client_line(f"switched active thread to {thread_id}")
        else:
            output.client_line(f"switched active thread to {thread_id} (unknown; use :resume to load)")
        return True
    if command is UserCommand.REFRESH_THREAD:
        try:
            request_id = client.request_thread_list(None)
            output.client_line(f"requested thread list ({request_id!r})")
        except Exception as exc:
            output.client_line(f"failed to list threads: {exc}")
        return True
    return True


def parse_approval_policy(value: str) -> str:
    if value in {"untrusted", "unless-trusted", "unlessTrusted"}:
        return "untrusted"
    if value in {"on-failure", "onFailure"}:
        return "on-failure"
    if value in {"on-request", "onRequest"}:
        return "on-request"
    if value == "never":
        return "never"
    raise ValueError(
        f"unknown approval policy: {value}. Expected one of: untrusted, on-failure, on-request, never"
    )


def drain_events(event_rx: Any, output: Output) -> None:
    while True:
        try:
            event = _try_recv(event_rx)
        except Empty:
            return
        if event is None:
            return
        if event.kind == "ThreadReady":
            thread_id = str(event.thread_id)
            output.client_line(f"active thread is now {thread_id}")
            output.set_prompt(thread_id)
        elif event.kind == "ThreadList":
            if not event.thread_ids:
                output.client_line("threads: (none)")
            else:
                output.client_line("threads:")
                for thread_id in event.thread_ids:
                    output.client_line(f"  {thread_id}")
            if event.next_cursor is not None:
                output.client_line(f"more threads available, next cursor: {event.next_cursor}")


def print_help(output: Output) -> None:
    output.client_line("commands:")
    output.client_line("  :help                 show this help")
    output.client_line("  :new                  start a new thread")
    output.client_line("  :resume <thread-id>   resume an existing thread")
    output.client_line("  :use <thread-id>      switch the active thread")
    output.client_line("  :refresh-thread       list available threads")
    output.client_line("  :quit                 exit")
    output.client_line("type a message to send it as a new turn")


def _parse_input_or_report(line: str, output: Output) -> InputAction | None:
    try:
        return parse_input(line)
    except ParseError as exc:
        output.client_line(exc.message())
        return None


def _try_recv(event_rx: Any) -> ReaderEvent | None:
    if hasattr(event_rx, "get_nowait"):
        return event_rx.get_nowait()
    if hasattr(event_rx, "popleft"):
        try:
            return event_rx.popleft()
        except IndexError:
            return None
    if isinstance(event_rx, list):
        if not event_rx:
            return None
        return event_rx.pop(0)
    if hasattr(event_rx, "try_recv"):
        return event_rx.try_recv()
    return None


__all__ = [
    "Cli",
    "drain_events",
    "handle_command",
    "main",
    "parse_approval_policy",
    "parse_args",
    "print_help",
    "run",
]
