"""End-to-end coverage for the ``/init`` slash command."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import (
    READY_COMPOSER_PATTERN,
    ConptyInputStep,
    TerminalSize,
    _SseFixtureServer,
    _completed_text_response,
    _isolated_codex_home_env_with_config,
    _repo_root,
    _responses_sse,
    build_inline_tui_command,
    build_rust_python_inline_pair,
    interactive_tui_comparison_capability,
    run_windows_conpty_tui_command,
)
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e

_INIT_PROMPT_FIXTURE = _repo_root() / "tests" / "fixtures" / "tui" / "init_prompt.md"
_AGENTS_BODY = "# Repository Guidelines\n\nDeterministic /init E2E fixture.\n"
_FINAL_ANSWER = "PYCODEX_INIT_E2E_COMPLETE"
_EXISTING_NOTICE = "AGENTS.md already exists here. Skipping /init to avoid overwriting it."


def _expected_init_prompt() -> str:
    # The fixed Windows Rust reference was compiled from the CRLF checkout of
    # prompt_for_init_command.md; pin those exact bytes for native comparison.
    return _INIT_PROMPT_FIXTURE.read_text(encoding="utf-8").replace("\n", "\r\n")


def _request_user_text(request: bytes) -> str:
    payload = json.loads(request.decode("utf-8"))
    for item in reversed(payload.get("input", [])):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content", [])
        if isinstance(content, str):
            return content
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in {"input_text", "text"}
        )
    return ""


def _init_tool_response(label: str) -> bytes:
    patch = (
        "*** Begin Patch\n"
        "*** Add File: AGENTS.md\n"
        + "".join(f"+{line}\n" for line in _AGENTS_BODY.splitlines())
        + "*** End Patch\n"
    )
    return _responses_sse(
        {"type": "response.created", "response": {"id": f"resp-{label}-init-tool"}},
        {
            "type": "response.output_item.added",
            "item": {
                "id": f"ctc-{label}-init",
                "type": "custom_tool_call",
                "call_id": f"call-{label}-init",
                "name": "apply_patch",
                "input": "",
            },
            "output_index": 0,
        },
        {
            "type": "response.custom_tool_call_input.delta",
            "item_id": f"ctc-{label}-init",
            "call_id": f"call-{label}-init",
            "output_index": 0,
            "delta": patch,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "id": f"ctc-{label}-init",
                "type": "custom_tool_call",
                "call_id": f"call-{label}-init",
                "name": "apply_patch",
                "input": patch,
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": f"resp-{label}-init-tool",
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


def _init_config(repo: Path, base_url: str) -> str:
    return (
        # Use a fixed catalog model whose Rust metadata enables the custom
        # apply_patch handler as well as exposing its tool specification.
        'model = "gpt-5.4"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "danger-full-access"\n'
        'suppress_unstable_features_warning = true\n\n'
        "[features]\n"
        "apps = false\n"
        "plugins = false\n\n"
        "[model_providers.pycodex_mock]\n"
        'name = "Mock provider for /init E2E"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        f"[projects.'{str(repo.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )


def _new_git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--quiet", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    (path / "README.md").write_text("# Init E2E repository\n", encoding="utf-8")
    return path


def _run_init_success_candidate(command, *, label: str, repo: Path, artifact_dir: Path):
    tool_body = _init_tool_response(label)
    final_body = _completed_text_response(
        f"resp-{label}-init-final",
        f"msg-{label}-init-final",
        _FINAL_ANSWER,
    )
    observed_hashes: list[str] = []

    def capture_agents_hash() -> None:
        observed_hashes.append(
            hashlib.sha256((repo / "AGENTS.md").read_bytes()).hexdigest()
        )

    with _SseFixtureServer((tool_body, final_body)) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _init_config(repo, server.base_url)
        )
        if command.kind == "python":
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [str(_repo_root()), env.get("PYTHONPATH", "")])
            )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/init",
                        ready_pattern=READY_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.3,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/init",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_text=_FINAL_ANSWER,
                        ready_timeout=40.0,
                        ready_quiet_period=0.3,
                        capture_name="init-complete",
                        after_ready=capture_agents_hash,
                    ),
                    ConptyInputStep(
                        "\x1b[A",
                        ready_text=_FINAL_ANSWER,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text="/init",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        capture_name="init-recalled",
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/init",
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text=_EXISTING_NOTICE,
                        ready_timeout=15.0,
                        ready_quiet_period=0.3,
                        capture_name="init-guarded",
                        after_ready=capture_agents_hash,
                    ),
                    ConptyInputStep("/quit\r", ready_timeout=0.2, atomic_write=True),
                ),
                env=env,
                timeout=55,
                size=TerminalSize(rows=38, cols=140),
            )
        requests = tuple(server.request_bodies)

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-init-success",
        rows=38,
        cols=140,
    )
    for index, request in enumerate(requests):
        (artifact_dir / f"{label}-init-request-{index}.json").write_bytes(request)
    agents_path = repo / "AGENTS.md"
    assert agents_path.is_file(), transcript.normalized_combined()
    file_bytes = agents_path.read_bytes()
    assert file_bytes.decode("utf-8") == _AGENTS_BODY
    assert len(requests) == 2, transcript.normalized_combined()
    assert _request_user_text(requests[0]) == _expected_init_prompt()
    assert _request_user_text(requests[0]) != "/init"
    assert "/init" not in _request_user_text(requests[0])
    assert observed_hashes == [
        hashlib.sha256(file_bytes).hexdigest(),
        hashlib.sha256(file_bytes).hexdigest(),
    ]
    assert "/init" in transcript.checkpoint_screen("init-recalled", rows=38, cols=140)
    assert _EXISTING_NOTICE in transcript.checkpoint_screen("init-guarded", rows=38, cols=140)
    assert "Traceback" not in transcript.normalized_combined()
    return {
        "request_count": len(requests),
        "prompt": _request_user_text(requests[0]),
        "file_bytes": file_bytes,
        "file_hash": hashlib.sha256(file_bytes).hexdigest(),
        "relative_path": agents_path.relative_to(repo).as_posix(),
        "recalled": "/init",
        "guard_notice": _EXISTING_NOTICE,
        "tool_name": "apply_patch",
        "tool_target": "AGENTS.md",
    }


def test_init_slash_command_uses_local_effect_route() -> None:
    assert terminal_slash_command_routes()[SlashCommand.INIT].outcome == "effect"


def test_init_dispatch_works_from_isolated_python_package_without_rust_tree(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "isolated-artifact"
    shutil.copytree(_repo_root() / "pycodex", artifact / "pycodex")
    assert not (artifact / "codex").exists()
    script = """
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

# Import the owned module from the isolated package artifact without executing
# the broad pycodex.tui facade, whose unrelated neighboring modules have their
# own installation contracts. This still loads slash_dispatch and all of its
# declared relative dependencies from the artifact.
package_root = Path.cwd() / "pycodex"
tui_package = types.ModuleType("pycodex.tui")
tui_package.__path__ = [str(package_root / "tui")]
sys.modules["pycodex.tui"] = tui_package
chatwidget_package = types.ModuleType("pycodex.tui.chatwidget")
chatwidget_package.__path__ = [str(package_root / "tui" / "chatwidget")]
sys.modules["pycodex.tui.chatwidget"] = chatwidget_package
collaboration_modes = types.ModuleType("pycodex.tui.collaboration_modes")
collaboration_modes.plan_mask = lambda _catalog: None
sys.modules["pycodex.tui.collaboration_modes"] = collaboration_modes
settings = types.ModuleType("pycodex.tui.chatwidget.settings")
settings.collaboration_modes_enabled = lambda _widget: False
sys.modules["pycodex.tui.chatwidget.settings"] = settings

from pycodex.tui.chatwidget.slash_dispatch import TerminalSlashCommandEffectDispatcher
from pycodex.tui.slash_command import SlashCommand

runtime = SimpleNamespace(
    active_thread_runtime=SimpleNamespace(
        session_config=SimpleNamespace(cwd=Path.cwd())
    ),
    insert_info_history_message=lambda *_args: None,
    insert_history_cell=lambda *_args: None,
)
result = TerminalSlashCommandEffectDispatcher(runtime).dispatch(SlashCommand.INIT)
print(json.dumps({"action": result.action, "prompt": result.prompt}, ensure_ascii=False))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(artifact)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=artifact,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)
    assert result == {"action": "submit", "prompt": _expected_init_prompt()}
    assert "FileNotFoundError" not in completed.stderr


def test_windows_conpty_python_init_success_path_without_native_rust(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows ConPTY regression only runs on Windows")
    for variable in (
        "PYCODEX_RUN_EXPERIMENTAL_CONPTY_TUI",
        "PYCODEX_CONPTY_DRIVER_VERIFIED",
        "PYCODEX_CONPTY_TUI_INPUT_VERIFIED",
    ):
        if os.environ.get(variable) != "1":
            pytest.skip(f"set {variable}=1 to run Python ConPTY /init E2E")
    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    repo = _new_git_repo(tmp_path / "python-init-repo")
    python = build_inline_tui_command(
        "python",
        repo_root=repo,
        extra_args=("--disable", "apps", "--disable", "plugins"),
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )

    result = _run_init_success_candidate(
        python,
        label="python",
        repo=repo,
        artifact_dir=tmp_path,
    )

    assert result["request_count"] == 2
    assert result["relative_path"] == "AGENTS.md"


def test_windows_conpty_native_and_python_init_success_path_when_enabled(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust_repo = _new_git_repo(tmp_path / "rust-init-repo")
    python_repo = _new_git_repo(tmp_path / "python-init-repo")
    rust, _ = build_rust_python_inline_pair(
        repo_root=rust_repo,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )
    python = build_inline_tui_command(
        "python",
        repo_root=python_repo,
        extra_args=("--disable", "apps", "--disable", "plugins"),
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )

    rust_result = _run_init_success_candidate(
        rust,
        label="rust",
        repo=rust_repo,
        artifact_dir=tmp_path,
    )
    python_result = _run_init_success_candidate(
        python,
        label="python-native-comparison",
        repo=python_repo,
        artifact_dir=tmp_path,
    )

    assert python_result == rust_result


def test_windows_conpty_native_and_python_init_existing_file_guard_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust test contract:
    # chatwidget/tests/slash_commands.rs::init_command_when_agents_md_exists
    # keeps the existing file intact, shows the skip notice, and records the
    # local command without creating a model turn.
    native_exe = require_native_slash_comparison()
    assert (_repo_root() / "AGENTS.md").is_file()
    rust, python = slash_candidate_pair(native_exe)
    notice = "AGENTS.md already exists here. Skipping /init to avoid overwriting it."

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text="/init",
                stop_pattern=re.escape(notice),
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        assert notice in transcript.normalized_stdout()
