"""End-to-end coverage for the Rust-owned ``/theme`` slash command."""

import io
import json
import re
from pathlib import Path

import pytest

from pycodex.tui.ratatui_bridge import Buffer, Rect, draw_buffer_to_ansi
from pycodex.tui.render.highlight import (
    BUILTIN_THEME_NAMES,
    configured_theme_name,
    set_theme_override,
)
from pycodex.tui.theme_picker import (
    NARROW_PREVIEW_ROWS,
    WIDE_PREVIEW_ROWS,
    ThemePreviewWideRenderable,
)
from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.support.theme_preview_oracle import (
    RUST_REVISION,
    TERMINAL_COLS,
    TERMINAL_ROWS,
    TWO_FACE_VERSION,
    extract_preview_contract,
    extract_preview_rows,
    extract_text_run_contract,
    load_theme_preview_contract,
)
from tests.e2e.support.vt_screen import vt_screen_cells
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    run_theme_slash_candidate,
    run_theme_applied_code_candidate,
    run_theme_interaction_candidate,
    slash_candidate_pair,
)
from tests.e2e.tui._common import (
    SESSION_CONFIGURED_COMPOSER_PATTERN,
    ConptyInputStep,
)

pytestmark = pytest.mark.e2e


def _portable_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Drop transcript placement while retaining every visible code cell style."""

    return [
        {
            "line_no": row["line_no"],
            "kind": row["kind"],
            "visible_text": row["visible_text"],
            "runs": row["runs"],
        }
        for row in rows
    ]


def _style_at(row: dict[str, object], offset: int) -> object:
    for run in row.get("runs", []):
        if int(run["start"]) <= offset < int(run["end"]):
            return run["style"]
    return None


def _first_contract_difference(
    expected: list[dict[str, object]],
    actual: list[dict[str, object]],
) -> dict[str, object] | None:
    for row_index, (left, right) in enumerate(zip(expected, actual)):
        left_text = str(left.get("visible_text", ""))
        right_text = str(right.get("visible_text", ""))
        limit = max(len(left_text), len(right_text))
        for offset in range(limit):
            left_char = left_text[offset] if offset < len(left_text) else None
            right_char = right_text[offset] if offset < len(right_text) else None
            left_style = _style_at(left, offset)
            right_style = _style_at(right, offset)
            if left_char != right_char or left_style != right_style:
                match = re.search(r"[A-Za-z_][A-Za-z0-9_]*", left_text[offset:])
                word = match.group(0) if match and match.start() == 0 else left_char
                return {
                    "row_index": row_index,
                    "source_line": left.get("line_no"),
                    "word": word,
                    "character_offset": offset,
                    "expected_character": left_char,
                    "actual_character": right_char,
                    "expected_style": left_style,
                    "actual_style": right_style,
                }
        if left.get("runs") != right.get("runs"):
            return {
                "row_index": row_index,
                "source_line": left.get("line_no"),
                "word": None,
                "character_offset": None,
                "expected_runs": left.get("runs"),
                "actual_runs": right.get("runs"),
            }
    if len(expected) != len(actual):
        return {"expected_row_count": len(expected), "actual_row_count": len(actual)}
    return None


def _assert_contract(
    *,
    theme_name: str,
    expected: list[dict[str, object]],
    actual: list[dict[str, object]],
    comparison: str,
    artifact_dir: Path,
) -> None:
    expected_portable = _portable_rows(expected)
    actual_portable = _portable_rows(actual)
    difference = _first_contract_difference(expected_portable, actual_portable)
    if difference is None:
        return
    report = {
        "theme": theme_name,
        "comparison": comparison,
        "difference": difference,
        "expected": expected_portable,
        "actual": actual_portable,
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifact_dir / f"{comparison}.diff.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    pytest.fail(
        f"{theme_name}: {comparison} styled preview mismatch: {difference}; "
        f"diff={report_path}"
    )


def test_theme_slash_command_uses_theme_picker_view_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.THEME]

    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.theme_picker"
    assert SlashCommand.THEME.available_during_task() is False
    assert SlashCommand.THEME.available_in_side_conversation() is False


def test_theme_golden_metadata_pins_rust_and_builtin_inventory() -> None:
    contract = load_theme_preview_contract()

    assert contract["rust_revision"] == RUST_REVISION
    assert contract["two_face_version"] == TWO_FACE_VERSION
    assert contract["terminal"] == {"rows": TERMINAL_ROWS, "cols": TERMINAL_COLS}
    assert contract["theme_names"] == list(BUILTIN_THEME_NAMES)
    assert set(contract["themes"]) == set(BUILTIN_THEME_NAMES)


@pytest.mark.parametrize("theme_name", BUILTIN_THEME_NAMES)
def test_python_styled_buffer_matches_rust_golden_for_every_builtin_theme(
    theme_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast contract: the generic Python preview matches Rust cell styles."""

    contract = load_theme_preview_contract()
    original = configured_theme_name()
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("COLORTERM", raising=False)
    try:
        assert set_theme_override(theme_name) is None
        area = Rect.new(0, 0, 77, 12)
        buffer = Buffer.empty(area)
        ThemePreviewWideRenderable().render(area, buffer)
        writer = io.StringIO()
        draw_buffer_to_ansi(writer, buffer)
        actual = extract_preview_contract(
            vt_screen_cells(writer.getvalue(), rows=12, cols=77)
        )
    finally:
        set_theme_override(original)

    _assert_contract(
        theme_name=theme_name,
        expected=contract["themes"][theme_name],
        actual=actual,
        comparison="python-buffer-vs-rust-golden",
        artifact_dir=tmp_path,
    )


@pytest.mark.parametrize("theme_name", BUILTIN_THEME_NAMES)
def test_windows_conpty_rust_python_and_golden_match_for_every_builtin_theme(
    theme_name: str,
    tmp_path: Path,
) -> None:
    """Real product gate: Rust, Python, and the pinned oracle must all agree."""

    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)
    theme_artifacts = tmp_path / theme_name
    expected = load_theme_preview_contract()["themes"][theme_name]
    captured: dict[str, list[dict[str, object]]] = {}

    for label, command in (("rust", rust_command), ("python", python_command)):
        transcript, request_count = run_theme_slash_candidate(
            command,
            label=label,
            theme_name=theme_name,
            artifact_dir=theme_artifacts,
            rows=TERMINAL_ROWS,
            cols=TERMINAL_COLS,
        )
        assert request_count == 0, f"{label}: /theme reached the model"
        screen = transcript.checkpoint_cells(
            "preview",
            rows=TERMINAL_ROWS,
            cols=TERMINAL_COLS,
        )
        rows = extract_preview_contract(screen)
        assert all(row["code_start"] == 87 for row in rows)
        assert [row["screen_y"] for row in rows] == list(
            range(rows[0]["screen_y"], rows[0]["screen_y"] + 8)
        )
        screen_text = screen.text()
        assert "Select Syntax Theme" in screen_text
        assert f"{theme_name} (current)" in screen_text
        captured[label] = rows
        _assert_contract(
            theme_name=theme_name,
            expected=expected,
            actual=rows,
            comparison=f"{label}-vs-rust-golden",
            artifact_dir=theme_artifacts,
        )

    _assert_contract(
        theme_name=theme_name,
        expected=captured["rust"],
        actual=captured["python"],
        comparison="python-vs-live-rust",
        artifact_dir=theme_artifacts,
    )


def _theme_interaction_steps() -> tuple[ConptyInputStep, ...]:
    return (
        ConptyInputStep(
            "/theme\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
        ),
        ConptyInputStep(
            "\x1b[B",
            ready_screen_text="fn summarize",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
            capture_name="initial",
        ),
        ConptyInputStep("", ready_timeout=0.5, capture_name="down"),
        ConptyInputStep(
            "nord",
            ready_screen_text="coldark-cold",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="nord",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="filtered-nord",
        ),
        ConptyInputStep(
            "\x15/theme",
            ready_timeout=1.5,
            atomic_write=True,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="/theme",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
        ),
        ConptyInputStep(
            "",
            ready_screen_text="nord (current)",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
            capture_name="reopened",
        ),
    )


def test_windows_conpty_theme_navigation_search_and_persistence_when_enabled(
    tmp_path: Path,
) -> None:
    """Verify real navigation, live recolor, filtering, and Enter persistence."""

    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)
    golden = load_theme_preview_contract()["themes"]

    for label, command in (("rust", rust_command), ("python", python_command)):
        artifact_dir = tmp_path / label
        transcript, persisted, request_count = run_theme_interaction_candidate(
            command,
            label=label,
            input_steps=_theme_interaction_steps(),
            artifact_dir=artifact_dir,
        )
        assert request_count == 0, f"{label}: theme interaction reached the model"
        assert persisted["tui"]["theme"] == "nord"
        for checkpoint, expected_theme in (
            ("initial", "catppuccin-mocha"),
            ("down", "coldark-cold"),
            ("filtered-nord", "nord"),
            ("reopened", "nord"),
        ):
            screen = transcript.checkpoint_cells(checkpoint, rows=40, cols=160)
            preview_rows = (
                WIDE_PREVIEW_ROWS[:4]
                if checkpoint in {"filtered-nord", "reopened"}
                else WIDE_PREVIEW_ROWS
            )
            actual = extract_preview_rows(screen, preview_rows)
            expected = golden[expected_theme][: len(preview_rows)]
            _assert_contract(
                theme_name=expected_theme,
                expected=expected,
                actual=actual,
                comparison=f"{label}-{checkpoint}",
                artifact_dir=artifact_dir,
            )


def _theme_ime_steps() -> tuple[ConptyInputStep, ...]:
    return (
        ConptyInputStep(
            "/theme\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
        ),
        ConptyInputStep(
            "主题",
            ready_screen_text="fn summarize",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
            atomic_write=True,
        ),
        ConptyInputStep(
            "",
            ready_screen_text="no matches",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="ime-no-matches",
        ),
        ConptyInputStep("\b\b", ready_timeout=0.0, chunk_delay=0.08),
        ConptyInputStep(
            "",
            ready_screen_text="1337",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            capture_name="ime-restored",
        ),
    )


def test_windows_conpty_theme_ime_query_backspace_recovers_when_enabled(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust_command), ("python", python_command)):
        transcript, persisted, request_count = run_theme_interaction_candidate(
            command,
            label=f"{label}-ime",
            input_steps=_theme_ime_steps(),
            artifact_dir=tmp_path / label,
        )
        assert request_count == 0
        assert persisted["tui"]["theme"] == "catppuccin-mocha"
        assert "no matches" in transcript.checkpoint_screen(
            "ime-no-matches", rows=40, cols=160
        )
        restored = transcript.checkpoint_screen("ime-restored", rows=40, cols=160)
        assert "1337" in restored
        assert "no matches" not in restored


def _theme_cancel_steps() -> tuple[ConptyInputStep, ...]:
    return (
        ConptyInputStep(
            "/theme\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
        ),
        ConptyInputStep(
            "\x1b[B",
            ready_screen_text="fn summarize",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
        ),
        ConptyInputStep("\x1b", ready_timeout=0.5),
        ConptyInputStep("\x15/theme", ready_timeout=0.8, atomic_write=True),
        ConptyInputStep(
            "\r",
            ready_screen_text="/theme",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
        ),
        ConptyInputStep(
            "",
            ready_screen_text="catppuccin-mocha (current)",
            ready_timeout=15.0,
            ready_quiet_period=0.4,
            capture_name="reopened-after-esc",
        ),
    )


def test_windows_conpty_theme_escape_restores_original_theme_when_enabled(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)
    expected = load_theme_preview_contract()["themes"]["catppuccin-mocha"]

    for label, command in (("rust", rust_command), ("python", python_command)):
        artifact_dir = tmp_path / label
        transcript, persisted, request_count = run_theme_interaction_candidate(
            command,
            label=f"{label}-escape",
            input_steps=_theme_cancel_steps(),
            artifact_dir=artifact_dir,
        )
        assert request_count == 0
        assert persisted["tui"]["theme"] == "catppuccin-mocha"
        actual = extract_preview_contract(
            transcript.checkpoint_cells(
                "reopened-after-esc",
                rows=40,
                cols=160,
            )
        )
        _assert_contract(
            theme_name="catppuccin-mocha",
            expected=expected,
            actual=actual,
            comparison=f"{label}-escape-restore",
            artifact_dir=artifact_dir,
        )


def test_windows_conpty_narrow_theme_preview_matches_rust_when_enabled(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)
    captured: dict[str, list[dict[str, object]]] = {}

    for label, command in (("rust", rust_command), ("python", python_command)):
        transcript, request_count = run_theme_slash_candidate(
            command,
            label=f"{label}-narrow",
            theme_name="nord",
            artifact_dir=tmp_path / label,
            rows=35,
            cols=80,
            preview_ready_text="fn greet",
        )
        assert request_count == 0
        screen = transcript.checkpoint_cells("preview", rows=35, cols=80)
        rows = extract_preview_rows(screen, NARROW_PREVIEW_ROWS)
        assert len(rows) == 4
        captured[label] = rows

    _assert_contract(
        theme_name="nord-narrow",
        expected=captured["rust"],
        actual=captured["python"],
        comparison="python-vs-live-rust-narrow",
        artifact_dir=tmp_path,
    )


@pytest.mark.parametrize("theme_name", BUILTIN_THEME_NAMES)
def test_windows_conpty_selected_theme_applies_to_real_model_code_when_enabled(
    theme_name: str,
    tmp_path: Path,
) -> None:
    """Select `/theme`, then prove a later model code block uses that theme."""

    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)
    code = "fn applied_theme() -> usize { 42 }"
    captured: dict[str, dict[str, object]] = {}

    for label, command in (("rust", rust_command), ("python", python_command)):
        artifact_dir = tmp_path / label
        transcript, _persisted, request_count = run_theme_applied_code_candidate(
            command,
            label=label,
            theme_name=theme_name,
            artifact_dir=artifact_dir,
        )
        assert request_count == 1, (
            f"{label}: expected one real model request after local /theme selection"
        )
        captured[label] = extract_text_run_contract(
            transcript.checkpoint_cells("applied-code", rows=40, cols=160),
            code,
        )

    rust_portable = {
        "visible_text": captured["rust"]["visible_text"],
        "runs": captured["rust"]["runs"],
    }
    python_portable = {
        "visible_text": captured["python"]["visible_text"],
        "runs": captured["python"]["runs"],
    }
    if rust_portable != python_portable:
        report_path = tmp_path / f"{theme_name}-applied-code.diff.json"
        report_path.write_text(
            json.dumps(
                {
                    "theme": theme_name,
                    "rust": rust_portable,
                    "python": python_portable,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        pytest.fail(
            f"{theme_name}: selected theme did not apply equally to real Rust/Python "
            f"model code; diff={report_path}"
        )

    golden_fn_style = _style_at(
        load_theme_preview_contract()["themes"][theme_name][0],
        0,
    )
    assert _style_at(captured["rust"], 0) == golden_fn_style
    assert _style_at(captured["python"], 0) == golden_fn_style


def test_windows_conpty_native_and_python_theme_picker_open_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust source contract:
    # - chatwidget::slash_dispatch maps SlashCommand::Theme to
    #   ChatWidget::open_theme_picker.
    # - theme_picker::build_theme_picker_params constructs a searchable
    #   ListSelectionView with bundled theme rows and local-only behavior.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text="/theme",
                stop_pattern="Select Syntax Theme",
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        for expected in (
            "Select Syntax Theme",
            "catppuccin-frappe",
            "catppuccin-latte",
            "catppuccin-macchiato",
            "catppuccin-mocha",
        ):
            assert expected in output, (
                f"{label}: missing {expected!r}; artifacts={tmp_path}"
            )
