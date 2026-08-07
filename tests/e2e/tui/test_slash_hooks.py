"""End-to-end coverage for the ``/hooks`` slash command."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    slash_candidate_pair,
)
from tests.e2e.tui._common import (
    SESSION_CONFIGURED_COMPOSER_PATTERN,
    ConptyInputStep,
    TerminalSize,
    TuiComparisonCommand,
    _completed_text_response,
    _isolated_codex_home_env_with_config,
    _repo_root,
    _SseFixtureServer,
    build_inline_tui_command,
    interactive_tui_comparison_capability,
    run_windows_conpty_tui_command,
)
from tests.e2e.tui._common import (
    RUN_EXPERIMENTAL_CONPTY_ENV,
    RUN_VERIFIED_CONPTY_ENV,
    RUN_VERIFIED_CONPTY_TUI_ENV,
)

pytestmark = pytest.mark.e2e

ROWS = 36
COLS = 120
EVENT_COLUMN_WIDTH = 22
COUNT_COLUMN_WIDTH = 12

EVENT_CONTRACT = (
    ("PreToolUse", "Before a tool executes"),
    ("PermissionRequest", "When permission is requested"),
    ("PostToolUse", "After a tool executes"),
    ("PreCompact", "Before context compaction"),
    ("PostCompact", "After context compaction"),
    ("SessionStart", "When a new session starts"),
    ("UserPromptSubmit", "When the user submits a prompt"),
    ("SubagentStart", "When a subagent is created"),
    ("SubagentStop", "Right before a subagent ends its turn"),
    ("Stop", "Right before Codex ends its turn"),
)


def _hooks_config(base_url: str) -> str:
    repo_root = _repo_root()
    return (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\n'
        'apps = false\n'
        'plugins = false\n\n'
        '[model_providers.pycodex_mock]\n'
        'name = "Mock provider that /hooks must not call"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )


def _hooks_config_with_user_prompt_submit(base_url: str) -> str:
    return (
        _hooks_config(base_url)
        + "\n[[hooks.UserPromptSubmit]]\n"
        + "\n[[hooks.UserPromptSubmit.hooks]]\n"
        + 'type = "command"\n'
        + 'command = "python hook-audit.py"\n'
        + 'commandWindows = "python hook-audit.py"\n'
        + "timeout = 5\n"
        + 'statusMessage = "Auditing prompt submission"\n'
    )


def _hooks_interaction_steps() -> tuple[ConptyInputStep, ...]:
    return (
        ConptyInputStep(
            "/hooks",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="/hooks",
            ready_timeout=10.0,
            ready_quiet_period=0.2,
        ),
        ConptyInputStep(
            "",
            ready_screen_text="Lifecycle hooks from config and enabled plugins.",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
            capture_name="initial",
        ),
        ConptyInputStep(
            "\x1b[B",
            ready_timeout=0.2,
        ),
        ConptyInputStep(
            "",
            ready_timeout=0.8,
            ready_quiet_period=0.4,
            capture_name="down",
        ),
        ConptyInputStep(
            "\r",
            ready_timeout=0.2,
        ),
        ConptyInputStep(
            "",
            ready_screen_text="No hooks installed for this event.",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
            capture_name="handler",
        ),
        ConptyInputStep(
            "\x1b",
            ready_timeout=0.2,
        ),
        ConptyInputStep(
            "",
            ready_screen_text="Lifecycle hooks from config and enabled plugins.",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
            capture_name="restored",
        ),
        ConptyInputStep(
            "\x1b",
            ready_timeout=0.2,
        ),
        ConptyInputStep(
            "",
            ready_timeout=0.8,
            ready_quiet_period=0.4,
            capture_name="closed",
        ),
        ConptyInputStep(
            "/quit",
            ready_timeout=1.0,
            ready_quiet_period=0.4,
            atomic_write=True,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="/quit",
            ready_timeout=10.0,
            ready_quiet_period=0.2,
        ),
    )


def _run_hooks_interaction_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    fixture_body = _completed_text_response(
        f"resp-{label}-hooks-must-not-run",
        f"msg-{label}-hooks-must-not-run",
        "HOOKS_INTERACTION_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _hooks_config(server.base_url)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=_hooks_interaction_steps(),
                env=env,
                timeout=35,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-hooks-interaction",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, request_count


def _row_text(screen: object, row_index: int) -> str:
    return "".join(
        cell.char for cell in screen.rows[row_index] if not cell.continuation
    ).rstrip()


def _line_index(screen: object, predicate) -> int:
    for row_index in range(len(screen.rows)):
        if predicate(_row_text(screen, row_index)):
            return row_index
    raise AssertionError(f"screen line not found\n{screen.text()}")


def _exact_line_index(screen: object, expected: str) -> int:
    return _line_index(screen, lambda line: line.strip() == expected)


def _token_style(screen: object, row_index: int, token: str):
    row_text = _row_text(screen, row_index)
    column = row_text.index(token)
    return screen.rows[row_index][column].style


def _expected_event_table() -> tuple[str, ...]:
    header = (
        f"{'Event':<{EVENT_COLUMN_WIDTH}}"
        f"{'Installed':<{COUNT_COLUMN_WIDTH}}"
        f"{'Active':<{COUNT_COLUMN_WIDTH}}"
        "Description"
    )
    rows = tuple(
        f"{event:<{EVENT_COLUMN_WIDTH}}"
        f"{0:<{COUNT_COLUMN_WIDTH}}"
        f"{0:<{COUNT_COLUMN_WIDTH}}"
        f"{description}"
        for event, description in EVENT_CONTRACT
    )
    return (header, *rows)


def _assert_event_page_contract(screen: object, *, selected_event: str) -> None:
    title_row = _exact_line_index(screen, "Hooks")
    title_style = _token_style(screen, title_row, "Hooks")
    assert title_style.bold is True
    assert title_style.dim is False
    assert title_style.fg is None

    subtitle = "Lifecycle hooks from config and enabled plugins."
    subtitle_row = _exact_line_index(screen, subtitle)
    assert _token_style(screen, subtitle_row, subtitle).dim is True

    table_header = _expected_event_table()[0]
    table_row = _line_index(screen, lambda line: line.lstrip() == table_header)
    actual_table = tuple(
        _row_text(screen, row_index).lstrip()
        for row_index in range(table_row, table_row + len(_expected_event_table()))
    )
    assert actual_table == _expected_event_table()
    assert all("|" not in line for line in actual_table)
    assert all(not line.startswith("> ") for line in actual_table)

    selected_row = _exact_line_index(
        screen,
        next(line for line in _expected_event_table() if line.startswith(selected_event)),
    )
    selected_style = _token_style(screen, selected_row, selected_event)
    assert selected_style.fg is not None
    assert selected_style.bold is True
    assert selected_style.dim is False

    ordinary_event = "PermissionRequest" if selected_event != "PermissionRequest" else "PreToolUse"
    ordinary_row = _line_index(
        screen,
        lambda line: line.lstrip().startswith(f"{ordinary_event:<{EVENT_COLUMN_WIDTH}}"),
    )
    ordinary_event_style = _token_style(screen, ordinary_row, ordinary_event)
    assert ordinary_event_style.fg is None
    assert ordinary_event_style.bold is False
    ordinary_line = _row_text(screen, ordinary_row)
    installed_column = ordinary_line.index(ordinary_event) + EVENT_COLUMN_WIDTH
    assert screen.rows[ordinary_row][installed_column].style.dim is True
    description = dict(EVENT_CONTRACT)[ordinary_event]
    assert _token_style(screen, ordinary_row, description).dim is True

    footer = "Press enter to view hooks; esc to close"
    footer_row = _exact_line_index(screen, footer)
    assert _token_style(screen, footer_row, "Press").dim is True


def _assert_empty_handler_contract(screen: object, *, event: str) -> None:
    title = f"{event} hooks"
    title_row = _exact_line_index(screen, title)
    assert _token_style(screen, title_row, title).bold is True

    subtitle = "Turn hooks on or off. Your changes are saved automatically."
    subtitle_row = _exact_line_index(screen, subtitle)
    assert _token_style(screen, subtitle_row, subtitle).dim is True

    empty = "No hooks installed for this event."
    empty_row = _exact_line_index(screen, empty)
    empty_style = _token_style(screen, empty_row, empty)
    assert empty_style.dim is True
    assert empty_style.italic is True

    footer = "Press esc to go back"
    footer_row = _exact_line_index(screen, footer)
    assert _token_style(screen, footer_row, footer).dim is True


def _assert_restored_event_selection(screen: object, *, selected_event: str) -> None:
    """Assert Esc returns to Events and restores the originating selection.

    The native no-alt-screen redraw can reuse terminal rows after the much
    shorter empty-handler page, so the VT test projection intentionally checks
    the restored state anchors rather than treating that incremental redraw as
    a second full-page golden.
    """

    _exact_line_index(screen, "Hooks")
    _exact_line_index(screen, "Lifecycle hooks from config and enabled plugins.")
    selected_row = _line_index(
        screen,
        lambda line: line.lstrip().startswith(
            f"{selected_event:<{EVENT_COLUMN_WIDTH}}"
        ),
    )
    selected_style = _token_style(screen, selected_row, selected_event)
    assert selected_style.fg is not None
    assert selected_style.bold is True
    assert not _row_text(screen, selected_row).lstrip().startswith("> ")
    footer = "Press enter to view hooks; esc to close"
    footer_row = _exact_line_index(screen, footer)
    assert _token_style(screen, footer_row, footer).dim is True


def test_hooks_registry_contract() -> None:
    # Rust owners:
    # - slash_dispatch calls chatwidget::hooks::add_hooks_output.
    # - hooks_rpc loads the current cwd's hook entry.
    # - bottom_pane::hooks_browser_view renders and navigates lifecycle events.
    route = terminal_slash_command_routes()[SlashCommand.HOOKS]

    assert SlashCommand.HOOKS.command() == "hooks"
    assert SlashCommand.HOOKS.supports_inline_args() is False
    assert SlashCommand.HOOKS.available_during_task() is True
    assert SlashCommand.HOOKS.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == (
        "pycodex.tui.chatwidget.hooks + "
        "pycodex.tui.bottom_pane.hooks_browser_view"
    )


def test_windows_conpty_native_and_python_hooks_browser_matches_rust_contract(
    tmp_path: Path,
) -> None:
    """Rust ``bottom_pane::hooks_browser_view`` text, style, and keys."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    captured = {}

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = _run_hooks_interaction_candidate(
            command,
            label=label,
            artifact_dir=tmp_path / label,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert "HOOKS_INTERACTION_MUST_NOT_REACH_THE_MODEL" not in output
        assert "extension area is not enabled" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
        captured[label] = transcript

    # Assert the Rust oracle first. Before the production fix, the same
    # assertions must then fail on Python for the observed /hooks divergence.
    for label in ("rust", "python"):
        transcript = captured[label]
        initial = transcript.checkpoint_cells("initial", rows=ROWS, cols=COLS)
        down = transcript.checkpoint_cells("down", rows=ROWS, cols=COLS)
        handler = transcript.checkpoint_cells("handler", rows=ROWS, cols=COLS)
        restored = transcript.checkpoint_cells("restored", rows=ROWS, cols=COLS)
        closed = transcript.checkpoint_cells("closed", rows=ROWS, cols=COLS)

        try:
            _assert_event_page_contract(initial, selected_event="PreToolUse")
            _assert_event_page_contract(down, selected_event="PermissionRequest")
            _assert_empty_handler_contract(handler, event="PermissionRequest")
            _assert_restored_event_selection(restored, selected_event="PermissionRequest")
            assert "Lifecycle hooks from config and enabled plugins." not in closed.text()
        except AssertionError as exc:
            raise AssertionError(f"{label} /hooks contract mismatch: {exc}") from exc


def test_windows_conpty_python_hooks_browser_discovers_user_config_hook(
    tmp_path: Path,
) -> None:
    """The real Python TUI lists hooks loaded from ``CODEX_HOME/config.toml``."""

    for variable in (
        RUN_EXPERIMENTAL_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_TUI_ENV,
    ):
        if os.environ.get(variable) != "1":
            pytest.skip(f"set {variable}=1 to run Python ConPTY E2E")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")
    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    command = build_inline_tui_command(
        "python",
        repo_root=_repo_root(),
        python_executable=sys.executable,
        extra_args=(
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--dangerously-bypass-hook-trust",
        ),
    )
    fixture_body = _completed_text_response(
        "resp-python-hooks-config-must-not-run",
        "msg-python-hooks-config-must-not-run",
        "HOOKS_CONFIG_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _hooks_config_with_user_prompt_submit(server.base_url)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/hooks",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/hooks",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text="Lifecycle hooks from config and enabled plugins.",
                        ready_timeout=15.0,
                        ready_quiet_period=0.4,
                        capture_name="configured",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern="Lifecycle hooks from config and enabled plugins.",
                stop_timeout=15,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )

    transcript.write_artifacts(
        tmp_path,
        prefix="python-hooks-user-config",
        rows=ROWS,
        cols=COLS,
    )
    screen = transcript.checkpoint_cells("configured", rows=ROWS, cols=COLS)
    user_prompt_row = _line_index(
        screen,
        lambda line: line.lstrip().startswith(
            f"{'UserPromptSubmit':<{EVENT_COLUMN_WIDTH}}"
        ),
    )
    row = _row_text(screen, user_prompt_row).lstrip()
    columns = row.split()
    assert columns[0] == "UserPromptSubmit"
    assert int(columns[1]) >= 1, screen.text()


def test_windows_conpty_python_prompts_to_review_untrusted_hooks_at_startup(
    tmp_path: Path,
) -> None:
    """Rust ``startup_hooks_review`` presents its three choices before App runs."""

    for variable in (
        RUN_EXPERIMENTAL_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_TUI_ENV,
    ):
        if os.environ.get(variable) != "1":
            pytest.skip(f"set {variable}=1 to run Python ConPTY E2E")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")
    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    command = build_inline_tui_command(
        "python",
        repo_root=_repo_root(),
        python_executable=sys.executable,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    fixture_body = _completed_text_response(
        "resp-python-hooks-startup-must-not-run",
        "msg-python-hooks-startup-must-not-run",
        "HOOKS_STARTUP_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _hooks_config_with_user_prompt_submit(server.base_url)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "",
                        ready_screen_text="Hooks need review",
                        ready_timeout=30.0,
                        ready_quiet_period=0.4,
                        capture_name="startup-review",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern="Continue without trusting (hooks won't run)",
                stop_timeout=15,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )

    transcript.write_artifacts(
        tmp_path,
        prefix="python-hooks-startup-review",
        rows=ROWS,
        cols=COLS,
    )
    screen = transcript.checkpoint_cells("startup-review", rows=ROWS, cols=COLS)
    rendered = screen.text()
    assert "Hooks need review" in rendered
    assert "1 hook is new or changed." in rendered
    assert "Hooks can run outside the sandbox after you trust them." in rendered
    assert "Review hooks" in rendered
    assert "Trust all and continue" in rendered
    assert "Continue without trusting (hooks won't run)" in rendered


@pytest.mark.parametrize(
    ("choice_keys", "expected_text", "trust_persisted"),
    (
        ("\r", "Lifecycle hooks from config and enabled plugins.", False),
        ("\x1b[B\r", "Ask Codex to do anything", True),
        ("\x1b[B\x1b[B\r", "Ask Codex to do anything", False),
    ),
    ids=("review-hooks", "trust-all", "continue-without-trusting"),
)
def test_windows_conpty_python_startup_hook_review_choices(
    tmp_path: Path,
    choice_keys: str,
    expected_text: str,
    trust_persisted: bool,
) -> None:
    """All three Rust startup-review choices affect the real product path."""

    for variable in (
        RUN_EXPERIMENTAL_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_TUI_ENV,
    ):
        if os.environ.get(variable) != "1":
            pytest.skip(f"set {variable}=1 to run Python ConPTY E2E")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")
    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    command = build_inline_tui_command(
        "python",
        repo_root=_repo_root(),
        python_executable=sys.executable,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    fixture_body = _completed_text_response(
        "resp-python-hooks-choice-must-not-run",
        "msg-python-hooks-choice-must-not-run",
        "HOOKS_CHOICE_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _hooks_config_with_user_prompt_submit(server.base_url)
        )
        with temp_home:
            home_path = Path(temp_home.name)
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        choice_keys,
                        ready_screen_text="Hooks need review",
                        ready_timeout=30.0,
                        ready_quiet_period=0.4,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text=expected_text,
                        ready_timeout=20.0,
                        ready_quiet_period=0.4,
                        capture_name="choice-result",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern=expected_text,
                stop_timeout=20,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
            updated_config = (home_path / "config.toml").read_text(encoding="utf-8")

    transcript.write_artifacts(
        tmp_path,
        prefix=f"python-hooks-startup-choice-{choice_keys.encode().hex()}",
        rows=ROWS,
        cols=COLS,
    )
    assert expected_text in transcript.checkpoint_cells(
        "choice-result", rows=ROWS, cols=COLS
    ).text()
    assert ("trusted_hash" in updated_config) is trust_persisted


def test_windows_conpty_python_review_hooks_can_trust_selected_hook(
    tmp_path: Path,
) -> None:
    """Startup review -> hooks browser -> trust uses the real AppEvent bus."""

    for variable in (
        RUN_EXPERIMENTAL_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_ENV,
        RUN_VERIFIED_CONPTY_TUI_ENV,
    ):
        if os.environ.get(variable) != "1":
            pytest.skip(f"set {variable}=1 to run Python ConPTY E2E")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")
    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    command = build_inline_tui_command(
        "python",
        repo_root=_repo_root(),
        python_executable=sys.executable,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    fixture_body = _completed_text_response(
        "resp-python-hooks-review-trust-must-not-run",
        "msg-python-hooks-review-trust-must-not-run",
        "HOOKS_REVIEW_TRUST_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _hooks_config_with_user_prompt_submit(server.base_url)
        )
        with temp_home:
            home_path = Path(temp_home.name)
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="Hooks need review",
                        ready_timeout=30.0,
                        ready_quiet_period=0.4,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="Lifecycle hooks from config and enabled plugins.",
                        ready_timeout=20.0,
                        ready_quiet_period=0.4,
                    ),
                    ConptyInputStep(
                        "t",
                        ready_screen_text="UserPromptSubmit hooks",
                        ready_timeout=20.0,
                        ready_quiet_period=0.4,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text="1 hook needs review before it can run.",
                        ready_timeout=20.0,
                        ready_quiet_period=0.5,
                        capture_name="trusted-one",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern="1 hook needs review before it can run.",
                stop_timeout=20,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
            updated_config = (home_path / "config.toml").read_text(encoding="utf-8")

    transcript.write_artifacts(
        tmp_path,
        prefix="python-hooks-review-trust-selected",
        rows=ROWS,
        cols=COLS,
    )
    assert "Traceback" not in transcript.normalized_combined()
    assert "trusted_hash" in updated_config
