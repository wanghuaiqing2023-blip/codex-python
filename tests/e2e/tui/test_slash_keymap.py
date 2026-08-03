"""End-to-end coverage for the ``/keymap`` slash command."""

from pathlib import Path
import re

import pytest

from pycodex.tui.chatwidget.slash_dispatch import (
    plan_terminal_local_command,
    terminal_slash_command_routes,
)
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import *  # noqa: F401,F403
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_keymap_slash_command_routes_to_owned_selection_view() -> None:
    route = terminal_slash_command_routes()[SlashCommand.KEYMAP]

    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.keymap_picker"
    assert plan_terminal_local_command("/keymap").action == "none"
    assert SlashCommand.KEYMAP.supports_inline_args() is True
    assert SlashCommand.KEYMAP.available_during_task() is False
    assert SlashCommand.KEYMAP.available_in_side_conversation() is False


def test_windows_conpty_native_and_python_keymap_debug_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps `/keymap debug` to
    #   ChatWidget::open_keymap_debug().
    # - chatwidget/tests/slash_commands.rs::slash_keymap_debug_opens_keypress_inspector
    #   proves the inspector opens locally without sending a core op.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/keymap debug",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.0,
            atomic_write=True,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="/keymap debug",
            ready_timeout=10.0,
            ready_quiet_period=0.1,
            chunk_delay=0.0,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Keypress Inspector",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Keypress Inspector",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=32, cols=120)
        assert "OpenAI Codex" in output
        assert "Keypress Inspector" in screen
        assert "Waiting for a keypress" in screen
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_keymap_action_menu_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::keymap_setup::picker rows emit OpenKeymapActionMenu.
    # - codex-tui::chatwidget::keymap_picker::open_keymap_action_menu renders
    #   the action-specific "Edit Shortcut" menu instead of closing /keymap.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/keymap",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep("\r", ready_text="/keymap", ready_timeout=10.0),
        ConptyInputStep(
            "\r",
            ready_text="Keymap",
            ready_timeout=10.0,
            ready_quiet_period=0.2,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern="Edit Shortcut",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern="Edit Shortcut",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=32, cols=120)
        assert "OpenAI Codex" in output
        assert "Edit Shortcut" in screen
        assert "Replace binding" in screen or "Set key" in screen
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_keymap_invalid_arg_when_enabled(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "Usage: /keymap [debug]"

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text="/keymap invalid",
                stop_pattern=re.escape(expected),
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        assert expected in transcript.normalized_stdout()
