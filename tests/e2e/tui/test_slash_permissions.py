"""End-to-end coverage for the ``/permissions`` slash command."""

from pycodex.tui.chatwidget.slash_dispatch import (
    plan_terminal_local_command,
    terminal_slash_command_routes,
)
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


def test_permissions_slash_command_routes_to_owned_selection_view() -> None:
    route = terminal_slash_command_routes()[SlashCommand.PERMISSIONS]

    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.permission_popups"
    assert plan_terminal_local_command("/permissions").action == "none"
    assert SlashCommand.PERMISSIONS.supports_inline_args() is False
    assert SlashCommand.PERMISSIONS.available_during_task() is False
    assert SlashCommand.PERMISSIONS.available_in_side_conversation() is False


def test_windows_conpty_native_and_python_permissions_popup_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Permissions
    #   to ChatWidget::open_permissions_popup().
    # - codex-tui::chatwidget::permission_popups builds the
    #   "Update Model Permissions" view from codex-utils-approval-presets.
    # - chatwidget/tests/permissions.rs::approvals_selection_popup_snapshot
    #   defines the Windows preset rows: Read Only, Default, Full Access.
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
            "/permissions",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="/permissions",
            ready_timeout=10.0,
            ready_quiet_period=0.2,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Update Model Permissions",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Update Model Permissions",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=32, cols=120)
        compact_screen = re.sub(r"\s+", "", screen)
        assert "OpenAI Codex" in output
        assert "Update Model Permissions" in screen
        assert "ReadOnly" in compact_screen
        assert "Default" in screen
        assert "FullAccess" in compact_screen
        assert "Agent" not in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()
