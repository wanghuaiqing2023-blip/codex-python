"""End-to-end coverage for ``/stop`` and its ``/clean`` alias."""

import base64
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import (
    READY_COMPOSER_PATTERN,
    ConptyInputStep,
    TerminalSize,
    _isolated_codex_home_env_with_config,
    _repo_root,
    _responses_sse,
    _SseFixtureServer,
    build_inline_tui_command,
    interactive_tui_comparison_capability,
    run_windows_conpty_tui_command,
)
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    run_repeated_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def _completed_response(response_id: str, message_id: str, text: str) -> str:
    return _responses_sse(
        {"type": "response.created", "response": {"id": response_id}},
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [],
            },
        },
        {
            "type": "response.output_text.delta",
            "item_id": message_id,
            "output_index": 0,
            "content_index": 0,
            "delta": text,
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )


def _wait_for_test_process_exit(pid: str, *, timeout: float = 5.0) -> bool:
    from tests.support.core_test_support.process import process_is_alive

    deadline = time.monotonic() + timeout
    while process_is_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)
    return True


def _cleanup_managed_test_process(pid_path: Path, release_path: Path) -> None:
    """Release only the uniquely identified process created by this test."""

    release_path.write_text("release\n", encoding="utf-8")
    try:
        pid = pid_path.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if not pid.isascii() or not pid.isdigit() or int(pid) <= 0:
        return
    if _wait_for_test_process_exit(pid):
        return
    subprocess.run(
        ["taskkill", "/PID", pid, "/T", "/F"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert _wait_for_test_process_exit(pid), f"managed E2E process {pid} survived cleanup"


@pytest.mark.parametrize(
    ("process_count", "stop_slash"),
    ((1, "/stop"), (2, "/clean")),
    ids=("one-process-stop", "two-process-clean-alias"),
)
def test_windows_conpty_python_ps_stop_manages_real_unified_exec_processes(
    tmp_path: Path,
    process_count: int,
    stop_slash: str,
) -> None:
    """Exercise Responses -> exec_command -> TUI -> /ps -> /stop end to end.

    Rust contracts:
    - ``core::unified_exec::process_manager`` emits a startup event carrying a
      process id and retains a live session after the turn completes;
    - ``tui::chatwidget::command_lifecycle`` keeps that process in the footer;
    - ``tui::chatwidget::{add_ps_output,clean_background_terminals}`` list it
      and submit ``CleanBackgroundTerminals`` for core-owned termination.
    """

    if os.name != "nt":
        pytest.skip("Windows ConPTY regression only runs on Windows")
    capability = interactive_tui_comparison_capability(conpty_driver_available=True)
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    markers = [f"PYCODEX_MANAGED_PS_STOP_E2E_{index}" for index in range(process_count)]
    final_answer = f"PYCODEX_MANAGED_BACKGROUND_READY_{process_count}"
    pid_paths = [tmp_path / f"managed-background-{index}.pid" for index in range(process_count)]
    release_paths = [
        tmp_path / f"release-managed-background-{index}" for index in range(process_count)
    ]
    commands: list[str] = []
    for marker, pid_path, release_path in zip(markers, pid_paths, release_paths, strict=True):
        escaped_pid_path = pid_path.as_posix().replace("'", "''")
        escaped_release_path = release_path.as_posix().replace("'", "''")
        commands.append(
            f"Write-Output '{marker}'; "
            f"$PID | Set-Content -LiteralPath '{escaped_pid_path}'; "
            f"while (-not (Test-Path -LiteralPath '{escaped_release_path}')) "
            "{ Start-Sleep -Milliseconds 100 }"
        )
    tool_events: list[dict[str, object]] = [
        {"type": "response.created", "response": {"id": "resp-managed-tool"}},
    ]
    for index, command_text in enumerate(commands):
        tool_events.append(
            {
                "type": "response.output_item.done",
                "output_index": index,
                "item": {
                    "id": f"fc-managed-ps-stop-{index}",
                    "type": "function_call",
                    "call_id": f"call-managed-ps-stop-{index}",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {"cmd": command_text, "yield_time_ms": 250},
                        separators=(",", ":"),
                    ),
                },
            }
        )
    tool_events.append(
        {
            "type": "response.completed",
            "response": {
                "id": "resp-managed-tool",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        }
    )
    tool_body = _responses_sse(*tool_events)
    final_body = _completed_response(
        "resp-managed-final",
        "msg-managed-final",
        final_answer,
    )
    config = (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "danger-full-access"\n'
        'suppress_unstable_features_warning = true\n\n'
        "[features]\n"
        "unified_exec = true\n"
        "apps = false\n"
        "plugins = false\n\n"
        "[model_providers.pycodex_mock]\n"
        'name = "Mock provider for managed /ps and /stop E2E"\n'
        f'base_url = "{{base_url}}"\n'
        'wire_api = "responses"\n'
        "request_max_retries = 0\n"
        "stream_max_retries = 0\n"
        "supports_websockets = false\n\n"
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )
    python = build_inline_tui_command(
        "python",
        repo_root=repo_root,
        extra_args=("--enable", "unified_exec", "--disable", "apps", "--disable", "plugins"),
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )

    transcript = None
    request_count = 0
    request_tool_names: list[set[str]] = []
    managed_pids: list[str] = []
    processes_stopped_by_slash: list[bool] = []
    try:
        with _SseFixtureServer((tool_body, final_body)) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                config.format(base_url=server.base_url)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    python,
                    input_steps=(
                        ConptyInputStep(
                            "start one managed background terminal",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="managed background terminal",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(final_answer, "mock-model"),
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                            capture_name="managed-ready",
                        ),
                        ConptyInputStep(
                            "/ps",
                            ready_timeout=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="/ps",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text="Background terminals",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            capture_name="ps-running",
                        ),
                        ConptyInputStep(
                            stop_slash,
                            ready_timeout=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text=stop_slash,
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text="Stopping all background terminals.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            capture_name="stop-confirmed",
                        ),
                        ConptyInputStep(
                            "/ps",
                            ready_timeout=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="/ps",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text="No background terminals running.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            capture_name="ps-empty",
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, atomic_write=True),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=36, cols=140),
                )
            request_count = len(server.request_bodies)
            request_tool_names = [
                {
                    str(tool.get("name"))
                    for tool in json.loads(body.decode("utf-8")).get("tools", ())
                    if isinstance(tool, dict) and isinstance(tool.get("name"), str)
                }
                for body in server.request_bodies
            ]
            from tests.support.core_test_support.process import process_is_alive

            managed_pids = [path.read_text(encoding="utf-8").strip() for path in pid_paths]
            processes_stopped_by_slash = [
                pid.isdigit() and not process_is_alive(pid) for pid in managed_pids
            ]
    finally:
        for pid_path, release_path in zip(pid_paths, release_paths, strict=True):
            _cleanup_managed_test_process(pid_path, release_path)

    assert transcript is not None
    transcript.write_artifacts(tmp_path, prefix="python-managed-ps-stop", rows=36, cols=140)
    running_footer = transcript.checkpoint_screen("managed-ready", rows=36, cols=140)
    running_ps = transcript.checkpoint_screen("ps-running", rows=36, cols=140)
    stopped = transcript.checkpoint_screen("stop-confirmed", rows=36, cols=140)
    empty_ps = transcript.checkpoint_screen("ps-empty", rows=36, cols=140)
    plural = "" if process_count == 1 else "s"
    footer_summary = f"{process_count} background terminal{plural} running"
    assert footer_summary in running_footer
    for marker in markers:
        assert marker in running_ps
    assert "No background terminals running." not in running_ps
    ps_lines = running_ps.splitlines()
    ps_header_index = max(
        index for index, line in enumerate(ps_lines) if line.strip() == "Background terminals"
    )
    ps_tail = ps_lines[ps_header_index + 1 :]
    summary_index = next(
        index for index, line in enumerate(ps_tail) if footer_summary in line
    )
    composer_index = next(
        index for index, line in enumerate(ps_tail) if line.lstrip().startswith("›")
    )
    process_rows = [
        line.strip()
        for line in ps_tail[:summary_index]
        if line.strip().startswith("• ")
    ]
    assert len(process_rows) == process_count, (
        "Rust /ps renders exactly one summary row per managed process without "
        f"a duplicate active exec row: {process_rows!r}"
    )
    assert not any(row.startswith("• Running ") for row in process_rows)
    assert summary_index < composer_index, (
        "Rust bottom_pane renders the unified-exec footer above the composer: "
        f"{ps_tail!r}"
    )
    assert composer_index == summary_index + 2
    assert not ps_tail[summary_index + 1].strip(), (
        "Rust bottom_pane keeps one blank row between the unified-exec footer "
        f"and composer: {ps_tail!r}"
    )
    assert "Stopping all background terminals." in stopped
    assert "background terminal running" not in stopped
    assert "No background terminals running." in empty_ps
    assert request_count == 2, "local slash commands must not create model turns"
    assert request_tool_names and all(
        {"exec_command", "write_stdin"} <= tool_names
        and "shell_command" not in tool_names
        for tool_names in request_tool_names
    ), f"unified-exec E2E must expose only its model-visible shell tools: {request_tool_names!r}"
    assert all(pid.isdigit() for pid in managed_pids)
    assert all(processes_stopped_by_slash), (
        f"{stop_slash} did not terminate every managed process: "
        f"pids={managed_pids!r}, stopped={processes_stopped_by_slash!r}"
    )
    assert "Traceback" not in transcript.normalized_combined()


def test_windows_conpty_detached_start_process_is_outside_ps_stop_boundary(
    tmp_path: Path,
) -> None:
    """A Start-Process child is not a Rust unified-exec managed session."""

    if os.name != "nt":
        pytest.skip("Windows ConPTY regression only runs on Windows")
    capability = interactive_tui_comparison_capability(conpty_driver_available=True)
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    pid_path = tmp_path / "detached-background.pid"
    release_path = tmp_path / "release-detached-background"
    escaped_pid_path = pid_path.as_posix().replace("'", "''")
    escaped_release_path = release_path.as_posix().replace("'", "''")
    child_script = (
        f"while (-not (Test-Path -LiteralPath '{escaped_release_path}')) "
        "{ Start-Sleep -Milliseconds 100 }"
    )
    encoded_child = base64.b64encode(child_script.encode("utf-16le")).decode("ascii")
    marker = "PYCODEX_DETACHED_PS_STOP_BOUNDARY"
    command = (
        "$child = Start-Process -FilePath 'powershell.exe' "
        f"-ArgumentList '-NoProfile','-EncodedCommand','{encoded_child}' "
        "-WindowStyle Hidden -PassThru; "
        f"$child.Id | Set-Content -LiteralPath '{escaped_pid_path}'; "
        f"Write-Output '{marker}'"
    )
    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-detached-tool"}},
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "fc-detached-boundary",
                "type": "function_call",
                "call_id": "call-detached-boundary",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": command, "yield_time_ms": 1_000},
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-detached-tool",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )
    final_answer = "PYCODEX_DETACHED_BOUNDARY_READY"
    final_body = _completed_response(
        "resp-detached-final",
        "msg-detached-final",
        final_answer,
    )
    config = (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "danger-full-access"\n'
        'suppress_unstable_features_warning = true\n\n'
        "[features]\n"
        "unified_exec = true\n"
        "apps = false\n"
        "plugins = false\n\n"
        "[model_providers.pycodex_mock]\n"
        'name = "Mock provider for detached process boundary E2E"\n'
        'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        "request_max_retries = 0\n"
        "stream_max_retries = 0\n"
        "supports_websockets = false\n\n"
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )
    python = build_inline_tui_command(
        "python",
        repo_root=repo_root,
        extra_args=("--enable", "unified_exec", "--disable", "apps", "--disable", "plugins"),
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )

    transcript = None
    request_count = 0
    detached_pid = ""
    detached_alive_after_stop = False
    try:
        with _SseFixtureServer((tool_body, final_body)) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                config.format(base_url=server.base_url)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    python,
                    input_steps=(
                        ConptyInputStep(
                            "start a detached child",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="detached child",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(final_answer, "mock-model"),
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                        ),
                        ConptyInputStep("/ps", ready_timeout=0.2, atomic_write=True),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="/ps",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text="No background terminals running.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            capture_name="detached-ps-empty",
                        ),
                        ConptyInputStep("/stop", ready_timeout=0.2, atomic_write=True),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="/stop",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text="Stopping all background terminals.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            capture_name="detached-stop",
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, atomic_write=True),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=36, cols=140),
                )
            request_count = len(server.request_bodies)
            from tests.support.core_test_support.process import process_is_alive

            detached_pid = pid_path.read_text(encoding="utf-8").strip()
            detached_alive_after_stop = (
                detached_pid.isdigit() and process_is_alive(detached_pid)
            )
    finally:
        _cleanup_managed_test_process(pid_path, release_path)

    assert transcript is not None
    transcript.write_artifacts(tmp_path, prefix="python-detached-ps-stop", rows=36, cols=140)
    empty_ps = transcript.checkpoint_screen("detached-ps-empty", rows=36, cols=140)
    stopped = transcript.checkpoint_screen("detached-stop", rows=36, cols=140)
    assert "No background terminals running." in empty_ps
    assert "background terminal running" not in empty_ps
    assert "Stopping all background terminals." in stopped
    assert detached_pid.isdigit()
    assert detached_alive_after_stop, "/stop must not terminate an unmanaged Start-Process child"
    assert request_count == 2
    assert "Traceback" not in transcript.normalized_combined()


def test_stop_slash_command_and_clean_alias_use_cleanup_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.STOP]

    assert SlashCommand.STOP.command() == "stop"
    assert SlashCommand.parse("clean") is SlashCommand.STOP
    assert SlashCommand.STOP.supports_inline_args() is False
    assert SlashCommand.STOP.available_during_task() is True
    assert SlashCommand.STOP.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"


def test_windows_conpty_python_stop_empty_state_is_idempotent_and_local(
    tmp_path: Path,
) -> None:
    """Repeated empty cleanup remains local and leaves /ps in its Rust state."""

    if os.name != "nt":
        pytest.skip("Windows ConPTY regression only runs on Windows")
    capability = interactive_tui_comparison_capability(conpty_driver_available=True)
    if not capability.available:
        pytest.skip(capability.reason)
    python = build_inline_tui_command(
        "python",
        repo_root=_repo_root(),
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    transcript, request_count = run_repeated_local_slash_candidate(
        python,
        label="python-stop-empty-idempotent",
        commands_and_effects=(
            ("/stop", "Stopping all background terminals."),
            ("/stop", "Stopping all background terminals."),
            ("/clean", "Stopping all background terminals."),
            ("/ps", "No background terminals running."),
        ),
        artifact_dir=tmp_path,
    )

    output = transcript.normalized_stdout()
    assert output.count("Stopping all background terminals.") >= 3
    assert "Background terminals" in output
    assert "No background terminals running." in output
    assert request_count == 0
    assert "Traceback" not in output


@pytest.mark.parametrize("slash_text", ["/stop", "/clean"])
def test_windows_conpty_native_and_python_stop_forms_are_local(
    tmp_path: Path,
    slash_text: str,
) -> None:
    # Rust chatwidget::clean_background_terminals submits the cleanup op,
    # clears the tracked processes/footer, and emits this confirmation.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text=slash_text,
            stop_pattern="Stopping all background terminals.",
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "Stopping all background terminals." in output
        assert "Traceback" not in output
