"""Rust differential end-to-end coverage for the ``/title`` slash command."""

import json
import re
from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
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
    _responses_sse,
    _SseFixtureServer,
    build_inline_tui_command,
    interactive_tui_comparison_capability,
    run_windows_conpty_tui_command,
)

pytestmark = pytest.mark.e2e

ROWS = 32
COLS = 120
_OSC_TITLE_RE = re.compile(r"\x1b\]0;([^\x07\x1b]*)(?:\x07|\x1b\\)")
_THREAD_ID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_SPINNER_FRAMES = frozenset("\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f\u280b\u2819")

# Every Rust TerminalTitleItem has its own isolated real-terminal case.  The
# dynamic cases deliberately create the state named by the item instead of
# accepting a preview-only placeholder as evidence that the selection works.
_TITLE_ITEM_CASES = (
    ("app-name", r"codex", "startup"),
    ("project-name", r"codex-python", "startup"),
    # Rust truncates each terminal-title part to 32 characters, so a worktree
    # path may retain only the leading ``codex...`` portion of the directory.
    ("current-dir", r".*codex(?:-python|\.\.\.)", "startup"),
    ("activity", r".", "activity"),
    ("run-state", r"Ready", "startup"),
    ("thread-title", rf"(?:primary|{_THREAD_ID_PATTERN})", "startup"),
    ("git-branch", r".+", "startup"),
    ("context-remaining", r"Context 0% left", "turn"),
    ("context-used", r"Context 100% used", "turn"),
    ("five-hour-limit", r"5h 75% left", "turn"),
    ("weekly-limit", r"weekly 60% left", "turn"),
    ("codex-version", r"\d+\.\d+\.\d+(?:[-+][^ ]+)?", "startup"),
    ("used-tokens", r"6 used", "turn"),
    ("total-input-tokens", r"0 in", "startup"),
    ("total-output-tokens", r"0 out", "startup"),
    ("thread-id", r"[0-9a-f-]{29}\.\.\.", "startup"),
    ("fast-mode", r"Fast off", "startup"),
    ("model", r"mock-model", "startup"),
    ("model-with-reasoning", r"mock-model high", "startup"),
    ("task-progress", r"Tasks 1/3", "plan"),
)


def _run_title_interaction_candidate(
    command: TuiComparisonCommand,
    *,
    label: str,
    input_steps: tuple[ConptyInputStep, ...],
    artifact_dir: Path,
) -> tuple[object, dict[str, object], int]:
    from pycodex.core.config.edit import read_toml_mapping

    repo_root = _repo_root()
    fixture_body = _completed_text_response(
        f"resp-{label}-title-must-not-run",
        f"msg-{label}-title-must-not-run",
        "TITLE_INTERACTION_MUST_NOT_REACH_THE_MODEL",
    )
    with _SseFixtureServer(fixture_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            '[tui]\n'
            'terminal_title = ["activity", "project-name"]\n\n'
            '[features]\n'
            'apps = false\n'
            'plugins = false\n\n'
            '[model_providers.pycodex_mock]\n'
            'name = "Mock provider that /title must not call"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = false\n'
            'request_max_retries = 0\n'
            'stream_max_retries = 0\n'
            'supports_websockets = false\n\n'
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        config_path = Path(env["CODEX_HOME"]) / "config.toml"
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=input_steps,
                env=env,
                timeout=2,
                stop_pattern=r"Configure Terminal Title",
                stop_timeout=2,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
            persisted = read_toml_mapping(config_path)
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-title-interaction",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, persisted, request_count


def _initial_steps() -> tuple[ConptyInputStep, ...]:
    return (
        ConptyInputStep(
            "/title\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
        ),
        ConptyInputStep(
            "",
            ready_screen_text="Press space to toggle",
            ready_timeout=10.0,
            ready_quiet_period=0.4,
            capture_name="initial",
        ),
    )


def _interaction_steps() -> tuple[ConptyInputStep, ...]:
    return (
        *_initial_steps(),
        ConptyInputStep("\x1b[B", ready_timeout=0.4),
        ConptyInputStep(
            "",
            ready_screen_text="› [x] project-name",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="down",
        ),
        ConptyInputStep("app-name", ready_timeout=0.8, chunk_delay=0.06),
        ConptyInputStep(
            "",
            ready_screen_text="> app-name",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="filtered",
        ),
        ConptyInputStep(" ", ready_timeout=0.5),
        ConptyInputStep(
            "",
            ready_screen_text="Action Required | codex-python | codex",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="toggled",
        ),
        ConptyInputStep("\r", ready_timeout=0.8),
        ConptyInputStep("\x15/title", ready_timeout=0.8, atomic_write=True),
        ConptyInputStep("\r", ready_screen_text="/title", ready_timeout=5.0),
        ConptyInputStep(
            "",
            ready_screen_text="› [x] activity",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="reopened",
        ),
    )


def _escape_steps() -> tuple[ConptyInputStep, ...]:
    return (
        *_initial_steps(),
        ConptyInputStep("app-name", ready_timeout=0.8, chunk_delay=0.06),
        ConptyInputStep(" ", ready_timeout=0.5),
        ConptyInputStep("\x1b", ready_timeout=1.2, ready_quiet_period=0.5),
        ConptyInputStep("\x15/title", ready_timeout=0.8, atomic_write=True),
        ConptyInputStep("\r", ready_screen_text="/title", ready_timeout=5.0),
        ConptyInputStep(
            "",
            ready_screen_text="› [x] activity",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="reopened-after-esc",
        ),
    )


def _title_events(raw: str) -> tuple[str, ...]:
    return tuple(match.group(1) for match in _OSC_TITLE_RE.finditer(raw))


def _line_index(screen: object, token: str) -> int:
    lines = screen.text().splitlines()
    return next(index for index, line in enumerate(lines) if token in line)


def _token_style(screen: object, token: str) -> object:
    row_index = _line_index(screen, token)
    row_text = "".join(cell.char for cell in screen.rows[row_index] if not cell.continuation)
    column = row_text.index(token)
    return screen.rows[row_index][column].style


def _token_column(screen: object, token: str) -> int:
    row_index = _line_index(screen, token)
    row_text = "".join(cell.char for cell in screen.rows[row_index] if not cell.continuation)
    return row_text.index(token)


def test_title_slash_command_uses_view_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.TITLE]

    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.status_controls"


def test_windows_conpty_native_and_python_title_setup_open_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust source/test contract:
    # - chatwidget::slash_dispatch maps SlashCommand::Title to
    #   ChatWidget::open_terminal_title_setup.
    # - bottom_pane::title_setup::TerminalTitleSetupView owns the multi-select
    #   title, subtitle, configured ordering, and item descriptions.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text="/title",
                stop_pattern="Configure Terminal Title",
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        for expected in (
            "Configure Terminal Title",
            "Select which items to display in the terminal title.",
            "activity",
            "project-name",
            "app-name",
        ):
            assert expected in output, (
                f"{label}: missing {expected!r}; artifacts={tmp_path}"
            )


def test_windows_conpty_title_layout_rows_styles_and_real_osc_match_rust(
    tmp_path: Path,
) -> None:
    """Catch the full-list dump, missing search/footer, and missing tab title."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    captured: dict[str, tuple[dict[str, object], tuple[str, ...]]] = {}

    for label, command in (("rust", rust), ("python", python)):
        transcript, _persisted, request_count = _run_title_interaction_candidate(
            command,
            label=f"{label}-initial",
            input_steps=_initial_steps(),
            artifact_dir=tmp_path / label,
        )
        assert request_count == 0, f"{label}: /title reached the model"
        screen = transcript.checkpoint_cells("initial", rows=ROWS, cols=COLS)
        text = screen.text()
        for expected in (
            "Configure Terminal Title",
            "Select which items to display in the terminal title.",
            "Type to search",
            "› [x] activity",
            "[x] project-name",
            "[ ] app-name",
            "[ ] current-dir",
            "[ ] run-state",
            "[ ] thread-title",
            "[ ] git-branch",
            "[ ] context-remaining",
            "[ ! ] Action Required | codex-python",
            "Press space to toggle",
            "to confirm and close",
            "to close",
        ):
            assert expected in text, f"{label}: missing {expected!r}; artifacts={tmp_path}"
        assert any(line.strip() == ">" for line in text.splitlines())
        assert "context-used" not in text, f"{label}: picker is not bounded to eight rows"
        assert " - Spinner while working" not in text
        assert _token_column(screen, "Configure Terminal Title") == 2
        assert _token_column(screen, "Type to search") == 2
        assert _token_column(screen, "› [x] activity") == 0
        assert _token_column(screen, "[ ! ] Action Required | codex-python") == 2

        first_item = _line_index(screen, "› [x] activity")
        preview = _line_index(screen, "[ ! ] Action Required | codex-python")
        footer = _line_index(screen, "Press space to toggle")
        assert preview == first_item + 9
        assert footer == preview + 1

        style_contract = {
            token: _token_style(screen, token)
            for token in (
                "Configure Terminal Title",
                "Select which items to display in the terminal title.",
                "Type to search",
                "activity",
                "project-name",
                "Spinner while working, action-required message while blocked.",
                "[ ! ] Action Required | codex-python",
                "Press space to toggle",
            )
        }
        active_style = style_contract["activity"]
        enabled_nonactive_style = style_contract["project-name"]
        assert active_style.fg is not None
        assert active_style.bold is True
        assert active_style != enabled_nonactive_style
        assert style_contract["Configure Terminal Title"].bold is True
        assert style_contract["Select which items to display in the terminal title."].dim is True
        assert style_contract["Type to search"].dim is True
        assert style_contract["Spinner while working, action-required message while blocked."].bold is True
        assert style_contract["Press space to toggle"].dim is True

        titles = _title_events(transcript.checkpoint_stdout("initial"))
        assert "codex-python" in titles, (
            f"{label}: no real OSC-0 project title was emitted; titles={titles!r}"
        )
        captured[label] = (style_contract, titles)

    assert captured["python"][0] == captured["rust"][0]


def test_windows_conpty_title_search_toggle_confirm_and_persistence_match_rust(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, persisted, request_count = _run_title_interaction_candidate(
            command,
            label=f"{label}-confirm",
            input_steps=_interaction_steps(),
            artifact_dir=tmp_path / label,
        )
        assert request_count == 0

        initial = transcript.checkpoint_screen("initial", rows=ROWS, cols=COLS)
        down = transcript.checkpoint_screen("down", rows=ROWS, cols=COLS)
        filtered = transcript.checkpoint_screen("filtered", rows=ROWS, cols=COLS)
        toggled = transcript.checkpoint_screen("toggled", rows=ROWS, cols=COLS)
        reopened = transcript.checkpoint_screen("reopened", rows=ROWS, cols=COLS)
        assert "› [x] activity" in initial
        assert "› [x] project-name" in down
        assert "> app-name" in filtered
        assert "› [ ] app-name" in filtered
        assert "project-name" not in filtered
        assert "[ ! ] Action Required | codex-python | codex" in toggled
        assert "[x] app-name" in reopened
        assert persisted["tui"]["terminal_title"] == [
            "activity",
            "project-name",
            "app-name",
        ]

        titles = _title_events(transcript.stdout)
        assert "codex-python | codex" in titles, (
            f"{label}: live/confirmed selection never changed the real title; {titles!r}"
        )


def test_windows_conpty_title_escape_reverts_preview_and_does_not_persist(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, persisted, request_count = _run_title_interaction_candidate(
            command,
            label=f"{label}-escape",
            input_steps=_escape_steps(),
            artifact_dir=tmp_path / label,
        )
        assert request_count == 0
        reopened = transcript.checkpoint_screen(
            "reopened-after-esc", rows=ROWS, cols=COLS
        )
        assert "[ ] app-name" in reopened
        assert persisted["tui"]["terminal_title"] == [
            "activity",
            "project-name",
        ]
        titles = _title_events(transcript.stdout)
        assert "codex-python | codex" in titles
        assert titles[-1] == "codex-python"


def _title_item_response_bodies(item: str, mode: str) -> bytes | tuple[bytes, ...]:
    answer = f"TITLE_ITEM_{item.upper().replace('-', '_')}_DONE"
    if mode != "plan":
        return _completed_text_response(
            f"resp-title-{item}",
            f"msg-title-{item}",
            answer,
        )
    plan = [
        {"step": "Inspect title item", "status": "completed"},
        {"step": "Project terminal title", "status": "in_progress"},
        {"step": "Verify OSC title", "status": "pending"},
    ]
    return (
        _responses_sse(
            {"type": "response.created", "response": {"id": "resp-title-plan-call"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc-title-plan",
                    "type": "function_call",
                    "call_id": "call-title-plan",
                    "name": "update_plan",
                    "arguments": json.dumps({"plan": plan}, separators=(",", ":")),
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp-title-plan-call",
                    "usage": {
                        "input_tokens": 4,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 2,
                        "output_tokens_details": None,
                        "total_tokens": 6,
                    },
                },
            },
        ),
        _completed_text_response(
            "resp-title-plan-answer",
            "msg-title-plan-answer",
            answer,
        ),
    )


def _run_isolated_title_item(
    command: TuiComparisonCommand,
    *,
    item: str,
    pattern: str,
    mode: str,
    label: str,
    artifact_dir: Path,
) -> tuple[object, tuple[str, ...], int]:
    repo_root = _repo_root()
    bodies = _title_item_response_bodies(item, mode)
    response_delay = 1.0 if mode == "activity" else 0.0
    response_headers = {
        "x-codex-primary-used-percent": "25",
        "x-codex-primary-window-minutes": "300",
        "x-codex-secondary-used-percent": "40",
        "x-codex-secondary-window-minutes": "10080",
    }
    with _SseFixtureServer(
        bodies,
        response_delay_seconds=response_delay,
        response_headers=response_headers,
    ) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'model_reasoning_effort = "high"\n'
            'model_context_window = 1000\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n\n'
            '[tui]\n'
            f'terminal_title = ["{item}"]\n\n'
            '[features]\n'
            'goals = true\n'
            'apps = false\n'
            'plugins = false\n\n'
            '[model_providers.pycodex_mock]\n'
            f'name = "Mock provider for /title {item}"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = false\n'
            'request_max_retries = 0\n'
            'stream_max_retries = 0\n'
            'supports_websockets = false\n\n'
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        if mode == "startup":
            input_steps = (
                ConptyInputStep(
                    "",
                    ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.8,
                    capture_name="ready",
                ),
            )
            expected_requests = 0
        else:
            prompt = f"TITLE_ITEM_{item.upper().replace('-', '_')}_PROBE"
            answer = f"TITLE_ITEM_{item.upper().replace('-', '_')}_DONE"
            input_steps = (
                ConptyInputStep(
                    prompt,
                    ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.3,
                    atomic_write=True,
                ),
                ConptyInputStep("\r", ready_text=prompt, ready_timeout=10.0),
                ConptyInputStep(
                    "",
                    ready_text=answer,
                    ready_timeout=40.0,
                    ready_quiet_period=0.8,
                    capture_name="after-turn",
                ),
            )
            expected_requests = 2 if mode == "plan" else 1
        title_pattern = (
            "[" + "".join(sorted(_SPINNER_FRAMES)) + "]"
            if mode == "activity"
            else pattern
        )
        osc_stop_pattern = (
            "\x1b" + r"\]0;(?:" + title_pattern + r")(?:\x07|\x1b\\)"
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=input_steps,
                env=env,
                timeout=5,
                stop_pattern=osc_stop_pattern,
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        request_count = len(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-title-item-{item}",
        rows=ROWS,
        cols=COLS,
    )
    assert request_count == expected_requests, (
        f"{label}/{item}: expected {expected_requests} model requests, got "
        f"{request_count}; artifacts={artifact_dir}"
    )
    return transcript, _title_events(transcript.stdout), request_count


def _assert_title_item_effect(
    *,
    label: str,
    item: str,
    pattern: str,
    mode: str,
    titles: tuple[str, ...],
    artifact_dir: Path,
) -> None:
    if mode == "activity":
        spinner_indexes = [
            index for index, title in enumerate(titles) if title in _SPINNER_FRAMES
        ]
        assert spinner_indexes, (
            f"{label}/{item}: selecting activity never emitted a live spinner; "
            f"titles={titles!r}; artifacts={artifact_dir}"
        )
        assert any(
            not title for index, title in enumerate(titles) if index > spinner_indexes[0]
        ), (
            f"{label}/{item}: the activity-only title was not cleared after the turn; "
            f"titles={titles!r}; artifacts={artifact_dir}"
        )
        return
    matcher = re.compile(rf"^(?:{pattern})$")
    assert any(matcher.fullmatch(title) for title in titles), (
        f"{label}/{item}: selected item never affected the actual OSC title; "
        f"expected={pattern!r}, titles={titles!r}; artifacts={artifact_dir}"
    )


def test_title_item_e2e_matrix_covers_every_rust_item() -> None:
    from pycodex.tui.bottom_pane.title_setup import TerminalTitleItem

    configured = {item for item, _pattern, _mode in _TITLE_ITEM_CASES}
    assert configured == {item.value for item in TerminalTitleItem}


@pytest.mark.parametrize(
    ("item", "pattern", "mode"),
    _TITLE_ITEM_CASES,
    ids=[item for item, _pattern, _mode in _TITLE_ITEM_CASES],
)
def test_windows_conpty_python_each_title_item_changes_real_terminal_title(
    tmp_path: Path,
    item: str,
    pattern: str,
    mode: str,
) -> None:
    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    command = build_inline_tui_command(
        "python",
        repo_root=_repo_root(),
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    artifact_dir = tmp_path / "python" / item
    _transcript, titles, _request_count = _run_isolated_title_item(
        command,
        item=item,
        pattern=pattern,
        mode=mode,
        label="python",
        artifact_dir=artifact_dir,
    )
    _assert_title_item_effect(
        label="python",
        item=item,
        pattern=pattern,
        mode=mode,
        titles=titles,
        artifact_dir=artifact_dir,
    )


@pytest.mark.parametrize(
    ("item", "pattern", "mode"),
    _TITLE_ITEM_CASES,
    ids=[item for item, _pattern, _mode in _TITLE_ITEM_CASES],
)
def test_windows_conpty_rust_each_title_item_changes_real_terminal_title(
    tmp_path: Path,
    item: str,
    pattern: str,
    mode: str,
) -> None:
    native_exe = require_native_slash_comparison()
    command = build_inline_tui_command(
        "rust",
        repo_root=_repo_root(),
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    artifact_dir = tmp_path / "rust" / item
    _transcript, titles, _request_count = _run_isolated_title_item(
        command,
        item=item,
        pattern=pattern,
        mode=mode,
        label="rust",
        artifact_dir=artifact_dir,
    )
    _assert_title_item_effect(
        label="rust",
        item=item,
        pattern=pattern,
        mode=mode,
        titles=titles,
        artifact_dir=artifact_dir,
    )
