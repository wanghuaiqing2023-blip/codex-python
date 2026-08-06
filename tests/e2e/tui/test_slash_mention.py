"""End-to-end coverage for the ``/mention`` slash command.

Rust owners:
- ``chatwidget::slash_dispatch`` seeds the composer with ``@``.
- ``bottom_pane::chat_composer`` owns the active ``@token`` and popup input.
- ``file_search`` and ``app::event_dispatch`` own asynchronous search results.
- ``bottom_pane::file_search_popup`` owns rows, selection, and match styling.
"""

import json
from pathlib import Path
import re
import subprocess

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
    ConptyInputStep,
    TerminalSize,
    TuiComparisonCommand,
    _completed_text_response,
    _isolated_codex_home_env_with_config,
    _SseFixtureServer,
    run_windows_conpty_tui_command,
)

pytestmark = pytest.mark.e2e

ROWS = 36
COLS = 120
FILE_FIXTURES = (
    "probe-alpha.md",
    "probe-alpine.py",
    "src/probe-application.rs",
    "docs/other-probe.txt",
    "docs/probe with space.md",
    "资料/probe-中文.txt",
    "资料/zzzx-中文.txt",
)
REALISTIC_RANKING_FIXTURES = (
    "pycodex/protocol/mcp.py",
    "pycodex/protocol/auth.py",
    "pycodex/otel/provider.py",
    "pycodex/protocol/items.py",
    "pycodex/protocol/error.py",
    "pycodex/process_hardening/README.md",
    "codex/codex-rs/protocol/README.md",
    "codex/codex-rs/cli/src/doctor/progress.rs",
    "codex/codex-rs/config/src/profile_toml.rs",
    "codex/codex-rs/config/src/project_root_markers.rs",
    "docs/other-probe.txt",
    "tests/probe_contract.py",
)
REALISTIC_IGNORED_FIXTURES = (
    "%SystemDrive%/ProgramData/probe-cache.db",
    "%SystemDrive%/ProgramData/Microsoft/Windows/progress.log",
    "pycodex/__pycache__/protocol.pyc",
    "nested/ignored-probe.py",
)
WORKSPACE_READY_PATTERN = r"(?ms)model:\s+(?!loading)\S+.*directory:.*workspace"


def _workspace_command(command: TuiComparisonCommand, workspace: Path) -> TuiComparisonCommand:
    argv = list(command.argv)
    cwd_index = argv.index("-C") + 1
    argv[cwd_index] = str(workspace)
    return TuiComparisonCommand(command.kind, tuple(argv), command.cwd)


def _create_search_workspace(workspace: Path) -> None:
    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        capture_output=True,
        text=True,
    )
    for relative in FILE_FIXTURES:
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture for {relative}\n", encoding="utf-8")


def _create_realistic_search_workspace(workspace: Path, *, include_ignored_noise: bool) -> None:
    """Create a small corpus that preserves the ranking traps from the repository root."""

    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        capture_output=True,
        text=True,
    )
    (workspace / ".gitignore").write_text(
        "/%SystemDrive%/\n__pycache__/\n*.pyc\n"
        + ("" if include_ignored_noise else ".git/\n"),
        encoding="utf-8",
    )
    for relative in REALISTIC_RANKING_FIXTURES:
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture for {relative}\n", encoding="utf-8")
    if not include_ignored_noise:
        return
    nested = workspace / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / ".gitignore").write_text("ignored-probe.py\n", encoding="utf-8")
    visible_nested_control = workspace / "docs" / "visible-ignored-probe.md"
    visible_nested_control.parent.mkdir(parents=True, exist_ok=True)
    visible_nested_control.write_text("visible nested-ignore control\n", encoding="utf-8")
    for relative in REALISTIC_IGNORED_FIXTURES:
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"ignored fixture for {relative}\n", encoding="utf-8")


def _popup_candidate_rows(screen: str, query: str) -> list[str]:
    """Return every visible popup row after the active ``@query``, preserving order."""

    lines = screen.splitlines()
    composer_index = next(
        (
            index
            for index in range(len(lines) - 1, -1, -1)
            if f"@{query}" in lines[index] and lines[index].lstrip().startswith(("›", ">"))
        ),
        None,
    )
    if composer_index is None:
        return []
    rows: list[str] = []
    for line in lines[composer_index + 1 :]:
        if not line.strip():
            continue
        if not line.startswith("  "):
            break
        rows.append(line.strip())
        if len(rows) == 8:
            break
    return rows


def _assert_realistic_pro_ranking(rows: list[str], *, label: str) -> None:
    """Assert Nucleo's stable buckets without fixing its parallel tie order."""

    assert rows[0] == "pycodex\\protocol", f"{label}: wrong best match: {rows!r}"
    assert set(rows[1:4]) == {
        "tests\\probe_contract.py",
        "pycodex\\protocol\\mcp.py",
        "codex\\codex-rs\\protocol",
    }, f"{label}: wrong score=84,length=23 bucket: {rows!r}"
    assert set(rows[4:6]) == {
        "pycodex\\protocol\\auth.py",
        "pycodex\\otel\\provider.py",
    }, f"{label}: wrong score=84,length=24 bucket: {rows!r}"
    assert len(set(rows[6:8])) == 2
    assert set(rows[6:8]) <= {
        "pycodex\\protocol\\items.py",
        "pycodex\\protocol\\error.py",
        "pycodex\\process_hardening",
    }, f"{label}: wrong score=84,length=25 cutoff bucket: {rows!r}"


def _mention_config(workspace: Path, base_url: str, label: str) -> str:
    project = str(workspace.resolve(strict=False))
    return (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\n'
        'apps = false\n'
        'plugins = false\n'
        'mentions_v2 = false\n\n'
        '[model_providers.pycodex_mock]\n'
        f'name = "Mock provider for /mention {label}"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        f"[projects.'{project}']\n"
        'trust_level = "trusted"\n'
    )


def _candidate_cell_styles(
    transcript,
    checkpoint: str,
    names: tuple[str, ...],
    *,
    cols: int = COLS,
) -> dict[str, list[object]]:
    screen = transcript.checkpoint_cells(checkpoint, rows=ROWS, cols=cols)
    result: dict[str, list[object]] = {}
    for row in screen.rows:
        text = "".join(cell.char for cell in row)
        for name in names:
            start = text.find(name)
            if start >= 0:
                result[name] = [row[index].style for index in range(start, start + len(name))]
    return result


def _selected_popup_row(transcript, checkpoint: str) -> str | None:
    screen = transcript.checkpoint_cells(checkpoint, rows=ROWS, cols=COLS)
    for row in screen.rows:
        text = "".join(cell.char for cell in row).rstrip()
        if "probe" not in text:
            continue
        content = [cell for cell in row if not cell.char.isspace()]
        if content and all(
            cell.style.bold
            and cell.style.fg is not None
            and cell.style.fg.kind == "ansi"
            and cell.style.fg.value == 6
            for cell in content
        ):
            return text.strip()
    return None


def _style_json(style: object) -> dict[str, object]:
    def color_json(color: object | None) -> dict[str, object] | None:
        if color is None:
            return None
        return {"kind": getattr(color, "kind", None), "value": getattr(color, "value", None)}

    return {
        "fg": color_json(getattr(style, "fg", None)),
        "bg": color_json(getattr(style, "bg", None)),
        "bold": bool(getattr(style, "bold", False)),
        "dim": bool(getattr(style, "dim", False)),
        "italic": bool(getattr(style, "italic", False)),
        "underline": bool(getattr(style, "underline", False)),
        "reverse": bool(getattr(style, "reverse", False)),
    }


def _write_search_diff_artifact(
    artifact_dir: Path,
    *,
    rust_lines: list[str],
    python_lines: list[str],
    rust_styles: dict[str, list[object]],
    python_styles: dict[str, list[object]],
) -> None:
    names = sorted(set(rust_styles) | set(python_styles))
    payload = {
        "rust_only_lines": sorted(set(rust_lines) - set(python_lines)),
        "python_only_lines": sorted(set(python_lines) - set(rust_lines)),
        "candidate_styles": {
            name: {
                "rust": [_style_json(style) for style in rust_styles.get(name, ())],
                "python": [_style_json(style) for style in python_styles.get(name, ())],
            }
            for name in names
        },
    }
    (artifact_dir / "mention-search-rust-python-diff.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_file_search_interaction(
    command: TuiComparisonCommand,
    *,
    label: str,
    workspace: Path,
    artifact_dir: Path,
):
    fixture = _completed_text_response(
        f"resp-{label}-mention-unused",
        f"msg-{label}-mention-unused",
        "MENTION_SEARCH_MUST_NOT_CALL_MODEL",
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _mention_config(workspace, server.base_url, label)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                _workspace_command(command, workspace),
                input_steps=(
                    ConptyInputStep(
                        "/mention",
                        ready_pattern=WORKSPACE_READY_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/mention",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "pro",
                        ready_screen_pattern=r"(?m)^.*@\s*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\x1b[B",
                        ready_screen_text="probe-alpha.md",
                        ready_timeout=20.0,
                        ready_quiet_period=0.5,
                        capture_name="matches",
                    ),
                    ConptyInputStep(
                        "\x1b[A",
                        ready_screen_text="probe-alpha.md",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="moved-down",
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_screen_text="probe-alpha.md",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="moved-up",
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_timeout=0.5,
                        capture_name="escape-hint",
                    ),
                    ConptyInputStep(
                        "\x1b",
                        ready_timeout=0.5,
                        capture_name="escaped",
                    ),
                    ConptyInputStep(
                        "",
                        ready_timeout=0.5,
                        capture_name="escaped-final",
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern=r"probe-alpha\.md",
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-mention-file-search",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def _run_exact_popup_snapshot(
    command: TuiComparisonCommand,
    *,
    label: str,
    workspace: Path,
    query: str,
    artifact_dir: Path,
):
    """Capture the complete visible popup without assuming either candidate order."""

    fixture = _completed_text_response(
        f"resp-{label}-mention-exact-unused",
        f"msg-{label}-mention-exact-unused",
        "MENTION_EXACT_SEARCH_MUST_NOT_CALL_MODEL",
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _mention_config(workspace, server.base_url, label)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                _workspace_command(command, workspace),
                input_steps=(
                    ConptyInputStep(
                        "/mention",
                        ready_pattern=WORKSPACE_READY_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/mention",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        query,
                        ready_screen_pattern=r"(?m)^.*@\s*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                        atomic_write=True,
                    ),
                    # Both implementations search asynchronously.  A fixed
                    # settle window avoids waiting for a candidate that would
                    # itself bias the differential assertion.
                    ConptyInputStep(
                        "",
                        ready_timeout=3.0,
                        capture_name="exact-popup",
                    ),
                ),
                env=env,
                timeout=2,
                size=TerminalSize(rows=ROWS, cols=180),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"mention-{label}-{query}-exact",
        rows=ROWS,
        cols=180,
    )
    return transcript, requests


def _run_file_search_submission(
    command: TuiComparisonCommand,
    *,
    label: str,
    workspace: Path,
    artifact_dir: Path,
):
    response_marker = f"MENTION_SUBMITTED_{label.upper()}"
    fixture = _completed_text_response(
        f"resp-{label}-mention-submit",
        f"msg-{label}-mention-submit",
        response_marker,
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _mention_config(workspace, server.base_url, label)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                _workspace_command(command, workspace),
                input_steps=(
                    ConptyInputStep(
                        "/mention",
                        ready_pattern=WORKSPACE_READY_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/mention",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "alpha",
                        ready_screen_pattern=r"(?m)^.*@\s*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="probe-alpha.md",
                        ready_timeout=20.0,
                        ready_quiet_period=0.5,
                        capture_name="matches-before-select",
                    ),
                    ConptyInputStep(
                        " use the selected file",
                        ready_screen_pattern=r"(?m)^.*probe-alpha\.md\s*$",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="selected-path",
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="use the selected file",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=3,
                stop_pattern=response_marker,
                stop_timeout=30,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-mention-file-submit",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def _run_no_match_unicode_recovery(
    command: TuiComparisonCommand,
    *,
    label: str,
    workspace: Path,
    artifact_dir: Path,
):
    response_marker = f"MENTION_UNICODE_{label.upper()}"
    fixture = _completed_text_response(
        f"resp-{label}-mention-unicode",
        f"msg-{label}-mention-unicode",
        response_marker,
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _mention_config(workspace, server.base_url, label)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                _workspace_command(command, workspace),
                input_steps=(
                    ConptyInputStep(
                        "/mention",
                        ready_pattern=WORKSPACE_READY_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_screen_text="/mention", ready_timeout=10.0),
                    ConptyInputStep("z", ready_screen_pattern=r"(?m)^.*@\s*$"),
                    ConptyInputStep("z", ready_timeout=0.35),
                    ConptyInputStep("z", ready_timeout=0.35),
                    ConptyInputStep("z", ready_timeout=0.35),
                    ConptyInputStep(
                        "\x7f",
                        ready_screen_text="no matches",
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                        capture_name="no-matches",
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="zzzx-",
                        ready_timeout=20.0,
                        ready_quiet_period=0.5,
                        capture_name="unicode-recovered",
                    ),
                    ConptyInputStep(
                        " verify unicode mention",
                        ready_timeout=1.0,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.5),
                ),
                env=env,
                timeout=3,
                stop_pattern=response_marker,
                stop_timeout=30,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = list(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-mention-unicode-recovery",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def test_mention_slash_command_uses_local_effect_route() -> None:
    assert terminal_slash_command_routes()[SlashCommand.MENTION].outcome == "effect"


def test_windows_conpty_native_and_python_mention_seeds_composer_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust source contract: chatwidget::slash_dispatch::SlashCommand::Mention
    # calls ChatWidget::insert_str("@") and must not submit `/mention` as a
    # model UserTurn.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    composer_pattern = r"(?m)^.*@$"

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text="/mention",
                stop_pattern=r"(?s)/mention.*?@",
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        screen = transcript.screen_stdout(rows=32, cols=120)
        assert re.search(composer_pattern, screen), (
            f"{label}: composer was not seeded with @; screen={screen!r}"
        )
        assert "Working" not in screen


def test_windows_conpty_native_and_python_mention_search_popup_matches_and_interacts(
    tmp_path: Path,
) -> None:
    """Prove the real ``@token -> file search -> styled popup`` path."""

    native_exe = require_native_slash_comparison()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _create_search_workspace(workspace)
    rust, python = slash_candidate_pair(native_exe)
    results = {
        label: _run_file_search_interaction(
            command,
            label=label,
            workspace=workspace,
            artifact_dir=tmp_path,
        )
        for label, command in (("rust", rust), ("python", python))
    }

    expected_names = (
        "probe-alpha.md",
        "probe-alpine.py",
        "src\\probe-application.rs",
        "docs\\other-probe.txt",
    )
    screens: dict[str, str] = {}
    styles: dict[str, dict[str, list[object]]] = {}
    moved_selections: dict[str, tuple[str, str]] = {}
    for label, (transcript, requests) in results.items():
        assert requests == [], f"{label}: file search called the model"
        screens[label] = transcript.checkpoint_screen("matches", rows=ROWS, cols=COLS)
        assert "@pro" in screens[label]
        assert "Working (" not in screens[label], f"{label}: local file search appeared as a model task"
        assert "probe-alpha.md" in screens[label]
        assert "probe-alpine.py" in screens[label]
        styles[label] = _candidate_cell_styles(
            transcript,
            "matches",
            tuple(name for name in expected_names if name in screens[label]),
        )
        assert styles[label], f"{label}: no styled file candidate cells captured"

        moved_down = _selected_popup_row(transcript, "moved-down")
        moved_up = _selected_popup_row(transcript, "moved-up")
        assert moved_down is not None, f"{label}: Down did not select a popup row"
        assert moved_up is not None, f"{label}: Up did not select a popup row"
        assert moved_down != moved_up, f"{label}: Up/Down did not move selection"
        moved_selections[label] = (moved_down, moved_up)

        for checkpoint in ("escape-hint", "escaped", "escaped-final"):
            escaped = transcript.checkpoint_screen(checkpoint, rows=ROWS, cols=COLS)
            assert "@pro" in escaped, f"{label}: Esc mutated the active query"

    rust_lines = [line.strip() for line in screens["rust"].splitlines() if "probe" in line]
    python_lines = [line.strip() for line in screens["python"].splitlines() if "probe" in line]
    _write_search_diff_artifact(
        tmp_path,
        rust_lines=rust_lines,
        python_lines=python_lines,
        rust_styles=styles["rust"],
        python_styles=styles["python"],
    )
    # Nucleo deliberately breaks equal-score/equal-length ties by the
    # parallel walker's injector index.  Rust itself can swap those tied rows
    # between runs, so parity means the same candidates and relevance buckets,
    # not a fabricated deterministic order inside that tie.
    assert set(python_lines) == set(rust_lines)
    assert [(len(line), line == "docs\\other-probe.txt") for line in python_lines] == [
        (len(line), line == "docs\\other-probe.txt") for line in rust_lines
    ]
    assert moved_selections["python"] == moved_selections["rust"]
    for lines in (rust_lines, python_lines):
        assert lines.index("probe-alpha.md") < lines.index("docs\\other-probe.txt")
    assert styles["python"] == styles["rust"]


def test_windows_conpty_native_and_python_mention_exact_popup_honors_gitignore(
    tmp_path: Path,
) -> None:
    """Compare all visible rows while exercising real Git ignore semantics."""

    native_exe = require_native_slash_comparison()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _create_realistic_search_workspace(workspace, include_ignored_noise=True)
    rust, python = slash_candidate_pair(native_exe)
    results = {
        label: _run_exact_popup_snapshot(
            command,
            label=label,
            workspace=workspace,
            query="pro",
            artifact_dir=tmp_path,
        )
        for label, command in (("rust", rust), ("python", python))
    }

    rows: dict[str, list[str]] = {}
    styles: dict[str, dict[str, list[object]]] = {}
    ignored_leaks: dict[str, list[str]] = {}
    for label, (transcript, requests) in results.items():
        assert requests == [], f"{label}: file search called the model"
        screen = transcript.checkpoint_screen("exact-popup", rows=ROWS, cols=180)
        assert "Working (" not in screen, f"{label}: local file search appeared as a model task"
        rows[label] = _popup_candidate_rows(screen, "pro")
        assert len(rows[label]) == 8, f"{label}: incomplete popup rows: {rows[label]!r}"
        ignored_leaks[label] = [
            candidate
            for candidate in rows[label]
            if any(
                ignored in candidate
                for ignored in ("%SystemDrive%", "__pycache__", "ignored-probe.py", ".git\\")
            )
        ]
        styles[label] = _candidate_cell_styles(
            transcript,
            "exact-popup",
            tuple(rows[label]),
            cols=180,
        )

    _write_search_diff_artifact(
        tmp_path,
        rust_lines=rows["rust"],
        python_lines=rows["python"],
        rust_styles=styles["rust"],
        python_styles=styles["python"],
    )
    for label in ("rust", "python"):
        assert ignored_leaks[label] == [], (
            f"{label}: gitignored candidate leaked into popup: {ignored_leaks[label]!r}; "
            f"all_rows={rows[label]!r}"
        )
        _assert_realistic_pro_ranking(rows[label], label=label)
    common = set(styles["rust"]) & set(styles["python"])
    assert len(common) >= 6
    assert {name: styles["python"][name] for name in common} == {
        name: styles["rust"][name] for name in common
    }


def test_windows_conpty_native_and_python_mention_honors_nested_gitignore(
    tmp_path: Path,
) -> None:
    """Nested ignore files must suppress matches without hiding visible controls."""

    native_exe = require_native_slash_comparison()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _create_realistic_search_workspace(workspace, include_ignored_noise=True)
    rust, python = slash_candidate_pair(native_exe)
    results = {
        label: _run_exact_popup_snapshot(
            command,
            label=label,
            workspace=workspace,
            query="ignored-probe",
            artifact_dir=tmp_path,
        )
        for label, command in (("rust", rust), ("python", python))
    }

    rows: dict[str, list[str]] = {}
    for label, (transcript, requests) in results.items():
        assert requests == [], f"{label}: file search called the model"
        screen = transcript.checkpoint_screen("exact-popup", rows=ROWS, cols=180)
        assert "Working (" not in screen, f"{label}: local file search appeared as a model task"
        rows[label] = _popup_candidate_rows(screen, "ignored-probe")

    _write_search_diff_artifact(
        tmp_path,
        rust_lines=rows["rust"],
        python_lines=rows["python"],
        rust_styles={},
        python_styles={},
    )
    for label in ("rust", "python"):
        assert "docs\\visible-ignored-probe.md" in rows[label]
        assert "nested\\ignored-probe.py" not in rows[label], (
            f"{label}: nested .gitignore was not honored: {rows[label]!r}"
        )
    assert rows["python"] == rows["rust"]


def test_windows_conpty_native_and_python_mention_exact_nucleo_ranking(
    tmp_path: Path,
) -> None:
    """Reject path-alphabetical fallback ordering for equal-looking matches."""

    native_exe = require_native_slash_comparison()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _create_realistic_search_workspace(workspace, include_ignored_noise=False)
    rust, python = slash_candidate_pair(native_exe)
    results = {
        label: _run_exact_popup_snapshot(
            command,
            label=label,
            workspace=workspace,
            query="pro",
            artifact_dir=tmp_path,
        )
        for label, command in (("rust", rust), ("python", python))
    }

    rows: dict[str, list[str]] = {}
    styles: dict[str, dict[str, list[object]]] = {}
    for label, (transcript, requests) in results.items():
        assert requests == [], f"{label}: file search called the model"
        screen = transcript.checkpoint_screen("exact-popup", rows=ROWS, cols=180)
        assert "Working (" not in screen, f"{label}: local file search appeared as a model task"
        rows[label] = _popup_candidate_rows(screen, "pro")
        assert len(rows[label]) == 8, f"{label}: incomplete popup rows: {rows[label]!r}"
        styles[label] = _candidate_cell_styles(
            transcript,
            "exact-popup",
            tuple(rows[label]),
            cols=180,
        )

    _write_search_diff_artifact(
        tmp_path,
        rust_lines=rows["rust"],
        python_lines=rows["python"],
        rust_styles=styles["rust"],
        python_styles=styles["python"],
    )
    for label in ("rust", "python"):
        _assert_realistic_pro_ranking(rows[label], label=label)
    common = set(styles["rust"]) & set(styles["python"])
    assert len(common) >= 6
    assert {name: styles["python"][name] for name in common} == {
        name: styles["rust"][name] for name in common
    }


def test_windows_conpty_native_and_python_mention_selected_path_reaches_model(
    tmp_path: Path,
) -> None:
    """Select a real popup row and prove the resulting user turn payload."""

    native_exe = require_native_slash_comparison()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _create_search_workspace(workspace)
    rust, python = slash_candidate_pair(native_exe)
    results = {
        label: _run_file_search_submission(
            command,
            label=label,
            workspace=workspace,
            artifact_dir=tmp_path,
        )
        for label, command in (("rust", rust), ("python", python))
    }

    request_text: dict[str, str] = {}
    for label, (transcript, requests) in results.items():
        assert len(requests) == 1, (
            f"{label}: expected one post-selection model request; "
            f"requests={len(requests)} screen={transcript.screen_stdout(rows=ROWS, cols=COLS)!r}"
        )
        selected = transcript.checkpoint_screen("selected-path", rows=ROWS, cols=COLS)
        assert "probe-alpha.md" in selected
        assert "@pro" not in selected
        payload = json.loads(requests[0].decode("utf-8"))
        request_text[label] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        assert "/mention" not in request_text[label]
        assert "probe-alpha.md" in request_text[label]
        assert "use the selected file" in request_text[label]

    # Provider request envelopes contain implementation-specific metadata, but
    # the selected file reference and user text must be identical.
    for token in ("probe-alpha.md", "use the selected file"):
        assert token in request_text["rust"] and token in request_text["python"]


def test_windows_conpty_native_and_python_mention_no_match_backspace_unicode_recovery(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _create_search_workspace(workspace)
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, requests = _run_no_match_unicode_recovery(
            command,
            label=label,
            workspace=workspace,
            artifact_dir=tmp_path,
        )
        no_matches = transcript.checkpoint_screen("no-matches", rows=ROWS, cols=COLS)
        recovered = transcript.checkpoint_screen("unicode-recovered", rows=ROWS, cols=COLS)
        assert "no matches" in no_matches
        assert "zzzx-" in recovered
        assert "no matches" not in recovered
        assert len(requests) == 1
        payload = json.loads(requests[0].decode("utf-8"))
        request_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        assert "资料" in request_text
        assert "zzzx-中文.txt" in request_text
        assert "verify unicode mention" in request_text
