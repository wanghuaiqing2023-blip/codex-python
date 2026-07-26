"""Shared fixtures and assertions for terminal conversation E2E scenarios."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from pycodex.core.config.edit import read_toml_mapping
from pycodex.tui.chatwidget.plan_implementation import (
    PLAN_IMPLEMENTATION_CLEAR_CONTEXT_PREFIX,
    PLAN_IMPLEMENTATION_TITLE,
)
from tests.e2e.support.conpty_driver import (
    ConptyInputStep,
    TerminalSize,
    _conpty_input_chunks,
    _semantic_conpty_text,
    _wait_for_windows_conpty_ordered_semantic_text,
    _wait_for_windows_conpty_output_pattern,
    _wait_for_windows_conpty_quiet,
    _wait_for_windows_conpty_screen_text,
    _wait_for_windows_conpty_semantic_text,
    run_windows_conpty_tui_command,
)
from tests.e2e.support.evidence import TuiProcessTranscript
from tests.e2e.support.product_pair import (
    DEFAULT_NATIVE_CODEX_EXE,
    NATIVE_CODEX_EXE_ENV,
    RUN_EXPERIMENTAL_CONPTY_ENV,
    RUN_NATIVE_COMPARISON_ENV,
    RUN_VERIFIED_CONPTY_ENV,
    RUN_VERIFIED_CONPTY_TUI_ENV,
    NativeComparisonLayer,
    TuiComparisonCommand,
    build_inline_tui_command,
    build_rust_python_inline_pair,
    interactive_tui_comparison_capability,
    native_codex_exe_from_env,
    native_comparison_enabled,
    run_piped_tui_command,
)
from tests.e2e.support.responses_fixture import (
    _SseFixtureServer,
    _completed_text_response,
    _responses_sse,
)
from tests.e2e.support.vt_screen import normalize_tui_text, vt_screen_text

RUN_NATIVE_LIVE_PROMPT_ENV = "PYCODEX_RUN_NATIVE_TUI_LIVE_PROMPT"
RUN_NATIVE_MULTI_TURN_ENV = "PYCODEX_RUN_NATIVE_TUI_MULTI_TURN"
RUN_NATIVE_COMPLEX_LIVE_PROMPT_ENV = "PYCODEX_RUN_NATIVE_TUI_COMPLEX_LIVE_PROMPT"
RUN_NATIVE_HISTORY_RECALL_ENV = "PYCODEX_RUN_NATIVE_TUI_HISTORY_RECALL"
READY_COMPOSER_PATTERN = "(?m)>\\s*$|^\\s*\\u203a\\s+.+$"
SESSION_CONFIGURED_COMPOSER_PATTERN = (
    "(?ms)model:\\s+(?!loading)\\S+.*directory:.*codex-python"
)

def _with_rust_startup_tip_ready(input_steps: tuple[ConptyInputStep, ...]) -> tuple[ConptyInputStep, ...]:
    first, *rest = input_steps
    return (
        ConptyInputStep(
            first.text,
            resize=first.resize,
            ready_text="Tip:",
            ready_timeout=first.ready_timeout,
            chunk_delay=first.chunk_delay,
            ready_quiet_period=first.ready_quiet_period,
        ),
        *rest,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _conpty_tui_env() -> dict[str, str]:
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    # ConPTY transports UTF-8 bytes. Force Python's standard streams to use
    # the same encoding as the native Rust TUI instead of the host OEM code
    # page, otherwise box drawing and arrow glyphs are mojibake in captures.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _isolated_codex_home_env() -> tuple[dict[str, str], tempfile.TemporaryDirectory[str]]:
    temp_home = tempfile.TemporaryDirectory(prefix="pycodex-native-home-")
    home_path = Path(temp_home.name)
    source_auth = Path.home() / ".codex" / "auth.json"
    if source_auth.exists():
        (home_path / "auth.json").write_bytes(source_auth.read_bytes())
    trust_key = str(_repo_root().resolve(strict=False)).lower()
    (home_path / "config.toml").write_text(
        f"[projects.'{trust_key}']\ntrust_level = \"trusted\"\n",
        encoding="utf-8",
    )
    env = _conpty_tui_env()
    env["CODEX_HOME"] = str(home_path)
    return env, temp_home


def _write_rust_thread_store_seed(
    codex_home: Path,
    *,
    cwd: Path,
    thread_id: str = "11111111-2222-4333-8444-555555555555",
    ts: str = "2025-01-03T10-11-12",
    first_user_message: str = "Seeded resume picker prompt",
) -> Path:
    """Write the minimal rollout shape used by Rust thread-store tests."""

    day_dir = codex_home / "sessions" / "2025" / "01" / "03"
    day_dir.mkdir(parents=True, exist_ok=True)
    rollout_path = day_dir / f"rollout-{ts}-{thread_id}.jsonl"
    meta = {
        "timestamp": ts,
        "type": "session_meta",
        "payload": {
            "id": thread_id,
            "forked_from_id": None,
            "timestamp": ts,
            "cwd": str(cwd),
            "originator": "test_originator",
            "cli_version": "test_version",
            "source": "cli",
            "model_provider": "openai",
            "git": {
                "commit_hash": "abcdef",
                "branch": "main",
                "repository_url": "https://example.com/repo.git",
            },
        },
    }
    user_event = {
        "timestamp": ts,
        "type": "event_msg",
        "payload": {
            "type": "user_message",
            "message": first_user_message,
            "kind": "plain",
        },
    }
    rollout_path.write_text(
        "\n".join(json.dumps(item, separators=(",", ":")) for item in (meta, user_event)) + "\n",
        encoding="utf-8",
    )
    return rollout_path


def _write_message_history_seed(
    codex_home: Path,
    *entries: str,
    session_id: str = "11111111-2222-4333-8444-555555555555",
) -> Path:
    history_path = codex_home / "history.jsonl"
    history_path.write_text(
        "\n".join(
            json.dumps(
                {"session_id": session_id, "ts": 1_735_906_272 + index, "text": text},
                separators=(",", ":"),
            )
            for index, text in enumerate(entries)
        )
        + "\n",
        encoding="utf-8",
    )
    return history_path


def _read_jsonl_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _isolated_codex_home_env_with_config(config_text: str) -> tuple[dict[str, str], tempfile.TemporaryDirectory[str]]:
    temp_home = tempfile.TemporaryDirectory(prefix="pycodex-native-home-")
    home_path = Path(temp_home.name)
    (home_path / "config.toml").write_text(config_text, encoding="utf-8")
    (home_path / "auth.json").write_text(
        '{"OPENAI_API_KEY":"dummy","tokens":null,"last_refresh":null}',
        encoding="utf-8",
    )
    env = _conpty_tui_env()
    env["CODEX_HOME"] = str(home_path)
    env["OPENAI_API_KEY"] = "dummy"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    return env, temp_home


def _seed_windows_sandbox_setup(target_home: Path) -> None:
    """Copy the host's provisioned sandbox identities into an isolated test home."""

    source_home = Path.home() / ".codex"
    relative_paths = (
        Path(".sandbox") / "setup_marker.json",
        Path(".sandbox-secrets") / "sandbox_users.json",
    )
    for relative_path in relative_paths:
        source = source_home / relative_path
        if not source.is_file():
            pytest.skip(f"Windows sandbox setup is incomplete: missing {source}")
        target = target_home / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

    marker = json.loads((target_home / relative_paths[0]).read_text(encoding="utf-8"))
    offline_username = marker.get("offline_username")
    if not isinstance(offline_username, str) or not offline_username:
        pytest.skip("Windows sandbox setup marker has no offline_username")


def _normalized_first_turn_request_context(request: dict[str, object]) -> dict[str, object]:
    """Normalize only nondeterministic identifiers in a captured Responses request."""

    uuid_pattern = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    isolated_home_pattern = re.compile(r"pycodex-native-home-[^/\\\s)]+")
    goal_timestamp_pattern = re.compile(r'("(?:createdAt|updatedAt)"\s*:\s*)\d+')

    def normalize(value: object) -> object:
        if isinstance(value, str):
            normalized = value.replace("\r\n", "\n").replace("\r", "\n")
            normalized = uuid_pattern.sub("<uuid>", normalized)
            normalized = goal_timestamp_pattern.sub(r"\1<timestamp>", normalized)
            return isolated_home_pattern.sub("pycodex-native-home-<temp>", normalized)
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        return value

    tools = request.get("tools")
    tool_names = [
        (
            f"{tool.get('type')}:{tool.get('name')}"
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
            else str(tool.get("type"))
        )
        for tool in tools
        if isinstance(tool, dict)
    ] if isinstance(tools, list) else []
    return {
        "model": request.get("model"),
        "instructions": normalize(request.get("instructions")),
        "input": normalize(request.get("input")),
        "reasoning": normalize(request.get("reasoning")),
        "parallel_tool_calls": request.get("parallel_tool_calls"),
        "tool_names": tool_names,
        "tools": normalize(tools),
    }


def _assert_live_multi_turn_shutdown_summary(transcript, *, first: str, second: str) -> None:
    output = transcript.normalized_stdout()
    detail = (
        f"argv={transcript.argv!r}\n"
        f"returncode={transcript.returncode}\n"
        f"stdout={output}\n"
        f"stderr={transcript.normalized_stderr()}"
    )
    assert "OpenAI Codex" in output, detail
    assert first in output, detail
    assert second in output, detail
    assert output.index(first) < output.index(second), detail
    assert "Token usage:" in output, detail
    assert "To continue this session, run codex resume" in output, detail
    assert output.index("Token usage:") < output.index("To continue this session, run codex resume"), detail
    if transcript.returncode == 0:
        return
    # Native Rust Codex can leave the Windows ConPTY capture open after the
    # visible shutdown summary has been rendered. Treat that as a harness
    # limitation only when the source-of-truth shutdown transcript is complete.
    assert "ConPTY command timed out" in transcript.normalized_combined()


def _assert_startup_shell_status_surface(transcript) -> None:
    # Rust source anchors:
    # - codex-tui/src/chatwidget.rs::PLACEHOLDERS and
    #   codex-tui/src/chatwidget/constructor.rs::new_with_op_target select the
    #   startup composer placeholder shown by the bottom pane.
    # - codex-tui/src/history_cell/session.rs::SessionHeaderHistoryCell renders
    #   the startup header with model and directory rows.
    # - codex-tui/src/bottom_pane/footer.rs::passive_footer_status_line renders
    #   the passive footer with model and current directory context.
    # - codex-tui/src/app.rs shutdown handling renders the visible shutdown row.
    output = transcript.normalized_stdout()
    assert ">_ OpenAI Codex" in output
    assert "model:" in output
    assert "/model to change" in output
    assert "directory:" in output
    assert "codex-python" in output
    assert "Context " not in output
    assert "Shutting down" in output
    assert any("gpt-" in line and "codex-python" in line for line in output.splitlines())


def _assert_startup_current_screen_surface(transcript, *, rows: int, cols: int) -> None:
    # Rust source anchors:
    # - codex-tui/src/tui.rs::enter_alt_screen controls whether the interactive
    #   UI is rendered into the current inline viewport or alternate screen.
    # - codex-tui/src/history_cell/session.rs::new_session_info supplies the
    #   startup header rows.
    # - codex-tui/src/chatwidget/constructor.rs::new_with_op_target wires the
    #   startup composer placeholder into BottomPane.
    # This assertion intentionally uses a VT current-screen projection instead
    # of cumulative stdout so it can catch stale/duplicated startup text.
    screen = transcript.screen_stdout(rows=rows, cols=cols)
    assert ">_ OpenAI Codex" in screen
    assert "╭" in screen
    assert "╰" in screen
    assert "│" in screen
    assert "model:" in screen
    assert "/model to change" in screen
    assert "directory:" in screen
    assert "codex-python" in screen
    assert "Context " not in screen
    assert "Shutting down" not in screen
    assert "\u9225?" not in screen


def _assert_startup_yolo_current_screen_surface(transcript, *, rows: int, cols: int) -> None:
    # Rust source/test contract:
    # - codex-tui/src/history_cell/session.rs::new_active_session applies
    #   SessionHeaderHistoryCell::with_yolo_mode when has_yolo_permissions is
    #   true.
    # - codex-tui/src/history_cell/session.rs::has_yolo_permissions accepts
    #   approval=never plus PermissionProfile::Disabled/full access.
    # - history_cell::tests::session_header_indicates_yolo_mode snapshots the
    #   visible `permissions: YOLO mode` startup row.
    screen = transcript.screen_stdout(rows=rows, cols=cols)
    _assert_startup_current_screen_surface(transcript, rows=rows, cols=cols)
    assert "permissions:" in screen
    assert "YOLO mode" in screen


def _assert_post_turn_current_screen_surface(
    transcript,
    *,
    rows: int,
    cols: int,
    answer: str,
    model_marker: str,
) -> None:
    # Rust source/test contract:
    # - codex-tui::status_indicator_widget owns the active
    #   `Working (... esc to interrupt)` row while a turn is running.
    # - codex-tui::bottom_pane::footer owns the passive model/directory footer
    #   after chatwidget::turn_runtime::on_task_complete restores idle state.
    # This assertion uses the current-screen projection so stale active-status
    # rows in cumulative stdout do not masquerade as the post-turn UI.
    screen = transcript.screen_stdout(rows=rows, cols=cols)
    assert answer in screen
    assert model_marker in screen
    assert "codex-python" in screen
    assert "Working" not in screen
    assert "to interrupt" not in screen
    assert "status: Ready" not in screen
    assert "Token usage:" not in screen


def _assert_interrupt_affordance_visible(transcript) -> None:
    # Rust source/test contract:
    # - codex-tui/src/status_indicator_widget.rs::StatusIndicatorWidget renders
    #   `(<elapsed> • <binding> to interrupt)` when an interrupt binding is
    #   available.
    # - status_indicator_widget::tests::renders_with_working_header and
    #   renders_remapped_interrupt_hint cover the deterministic widget shape.
    #
    # Native live prompts can answer before the active-turn `Working` row is
    # captured, while Rust startup/MCP status can still expose the same
    # interrupt affordance. The product-level native guard therefore checks the
    # stable affordance text, and fake-runtime tests own exact active-turn
    # `Working (...)` timing.
    output = transcript.normalized_stdout()
    assert "esc" in output
    assert "to interrupt" in output

# Scenario modules deliberately import this complete test vocabulary.
__all__ = [name for name in globals() if not name.startswith("__")]
