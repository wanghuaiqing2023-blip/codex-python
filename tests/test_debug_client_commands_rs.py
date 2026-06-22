"""Prepared parity tests for Rust ``codex-debug-client/src/commands.rs``.

Pytest is deferred until the full ``codex-debug-client`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

import pytest

from pycodex.debug_client.commands import InputAction, ParseError, UserCommand, parse_input


def test_parses_message() -> None:
    # Rust source: commands.rs parses_message.
    assert parse_input("hello there") == InputAction.message("hello there")


def test_parses_help_command_and_alias() -> None:
    # Rust source: commands.rs parses_help_command plus "h" alias in parse_input.
    assert parse_input(":help") == InputAction.help()
    assert parse_input(":h") == InputAction.help()


def test_parses_quit_command_aliases() -> None:
    # Rust source: parse_input recognizes quit, q, and exit.
    assert parse_input(":quit") == InputAction.quit()
    assert parse_input(":q") == InputAction.quit()
    assert parse_input(":exit") == InputAction.quit()


def test_parses_new_thread() -> None:
    # Rust source: commands.rs parses_new_thread.
    assert parse_input(":new") == InputAction.new_thread()


def test_parses_resume() -> None:
    # Rust source: commands.rs parses_resume.
    action = parse_input(":resume thr_123")

    assert action == InputAction.resume("thr_123")
    assert action is not None
    assert action.command_name is UserCommand.RESUME
    assert action.argument == "thr_123"


def test_parses_use() -> None:
    # Rust source: commands.rs parses_use.
    action = parse_input(":use thr_456")

    assert action == InputAction.use("thr_456")
    assert action is not None
    assert action.command_name is UserCommand.USE
    assert action.argument == "thr_456"


def test_parses_refresh_thread() -> None:
    # Rust source: commands.rs parses_refresh_thread.
    assert parse_input(":refresh-thread") == InputAction.refresh_thread()


def test_empty_input_and_empty_command() -> None:
    # Rust source: parse_input trims empty input to Ok(None), ":" to EmptyCommand.
    assert parse_input("  ") is None
    with pytest.raises(ParseError) as exc_info:
        parse_input(":")
    assert exc_info.value == ParseError.empty_command()
    assert exc_info.value.message() == "empty command after ':'"


def test_rejects_missing_resume_arg() -> None:
    # Rust source: commands.rs rejects_missing_resume_arg.
    with pytest.raises(ParseError) as exc_info:
        parse_input(":resume")
    assert exc_info.value == ParseError.missing_argument("thread-id")
    assert exc_info.value.message() == "missing required argument: thread-id"


def test_rejects_missing_use_arg() -> None:
    # Rust source: commands.rs rejects_missing_use_arg.
    with pytest.raises(ParseError) as exc_info:
        parse_input(":use")
    assert exc_info.value == ParseError.missing_argument("thread-id")


def test_rejects_unknown_command() -> None:
    # Rust source: ParseError::UnknownCommand preserves command token.
    with pytest.raises(ParseError) as exc_info:
        parse_input(":bogus extra")
    assert exc_info.value == ParseError.unknown_command("bogus")
    assert exc_info.value.message() == "unknown command: bogus"
