import asyncio
import os
from pathlib import Path
import sys

from pycodex.hooks import CommandShell
from pycodex.hooks import ConfiguredHandler
from pycodex.hooks import build_command_argv
from pycodex.hooks import default_shell_command_argv
from pycodex.hooks import run_command
from pycodex.protocol import HookEventName
from pycodex.protocol import HookSource


def make_handler(
    command: str,
    *,
    timeout_sec: int = 5,
    env: dict[str, str] | None = None,
) -> ConfiguredHandler:
    return ConfiguredHandler(
        event_name=HookEventName.STOP,
        matcher=None,
        command=command,
        timeout_sec=timeout_sec,
        status_message=None,
        source_path=Path("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=0,
        env=env or {},
    )


def test_build_command_uses_default_shell_when_shell_program_is_empty():
    # Rust source contract:
    # codex-hooks/src/engine/command_runner.rs::build_command and
    # default_shell_command append the handler command after platform shell args.
    argv = build_command_argv(CommandShell(program="", args=[]), make_handler("echo hi"))

    if os.name == "nt":
        assert argv[1:] == ["/C", "echo hi"]
        assert argv[0].lower().endswith(("cmd.exe", "cmd"))
    else:
        assert argv[-2:] == ["-lc", "echo hi"]
        assert argv[0] == os.environ.get("SHELL", "/bin/sh")
    assert default_shell_command_argv() == argv[:-1]


def test_build_command_uses_custom_shell_args_then_handler_command():
    # Rust source contract: a non-empty CommandShell program receives
    # shell.args first, then handler.command.
    handler = make_handler("print('ok')")
    argv = build_command_argv(CommandShell(program=sys.executable, args=["-c"]), handler)

    assert argv == [sys.executable, "-c", "print('ok')"]


def test_run_command_writes_stdin_captures_output_cwd_env_and_exit_code(tmp_path):
    # Rust source contract: run_command pipes stdin/stdout/stderr, sets cwd,
    # overlays handler.env, and decodes process output lossily.
    script = (
        "import os, pathlib, sys; "
        "data=sys.stdin.read(); "
        "print('cwd=' + pathlib.Path.cwd().name); "
        "print('stdin=' + data); "
        "print('env=' + os.environ.get('HOOK_ENV', '')); "
        "print('err', file=sys.stderr); "
        "sys.exit(7)"
    )
    result = asyncio.run(
        run_command(
            CommandShell(program=sys.executable, args=["-c"]),
            make_handler(script, env={"HOOK_ENV": "present"}),
            '{"ok":true}',
            tmp_path,
        )
    )

    assert result.error is None
    assert result.exit_code == 7
    assert f"cwd={tmp_path.name}" in result.stdout
    assert "stdin={\"ok\":true}" in result.stdout
    assert "env=present" in result.stdout
    assert result.stderr.strip() == "err"
    assert result.completed_at >= result.started_at
    assert result.duration_ms >= 0


def test_run_command_spawn_error_returns_error_without_status(tmp_path):
    # Rust source contract: spawn errors become CommandRunResult with no status
    # and empty captured output.
    result = asyncio.run(
        run_command(
            CommandShell(program="definitely-missing-codex-hook-program", args=[]),
            make_handler("ignored"),
            "{}",
            tmp_path,
        )
    )

    assert result.exit_code is None
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.error


def test_run_command_timeout_kills_child_and_reports_rust_message(tmp_path):
    # Rust source contract: timeout returns no status/output and an exact
    # "hook timed out after {timeout}s" error message.
    script = "import time; time.sleep(5); print('late')"
    result = asyncio.run(
        run_command(
            CommandShell(program=sys.executable, args=["-c"]),
            make_handler(script, timeout_sec=0),
            "{}",
            tmp_path,
        )
    )

    assert result.exit_code is None
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.error == "hook timed out after 0s"
