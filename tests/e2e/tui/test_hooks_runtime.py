"""End-to-end coverage for lifecycle hooks executed by real TUI turns."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from tests.e2e.tui._common import (
    READY_COMPOSER_PATTERN,
    ConptyInputStep,
    TerminalSize,
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


def _runtime_config(base_url: str, project: Path) -> str:
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
        'name = "Mock provider for hook runtime E2E"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        f"[projects.'{str(project.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n\n'
    )


def test_windows_conpty_python_user_prompt_submit_hook_executes_before_model_request(
    tmp_path: Path,
) -> None:
    """A real user turn executes the configured hook and applies its context.

    Rust owners and acceptance evidence:
    - ``codex-core/src/session/session.rs`` installs ``Hooks`` in
      ``SessionServices``.
    - ``codex-core/src/hook_runtime.rs::run_user_prompt_submit_hooks`` runs the
      hook before the first model request.
    - ``codex-core/tests/suite/hooks.rs`` asserts real command-hook inputs and
      context injection rather than discovery metadata alone.
    """

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

    repo_root = _repo_root()
    prompt = "verify user prompt submit hook"
    answer = "USER_PROMPT_HOOK_E2E_OK"
    context_marker = "USER_PROMPT_HOOK_CONTEXT_APPLIED"
    project = tmp_path / "hook-project"
    hooks_dir = project / ".codex" / "hooks"
    hooks_dir.mkdir(parents=True)
    (project / ".git").mkdir()
    audit_log = project / ".tmp" / "user-prompt-submit-audit.jsonl"
    hook_script = hooks_dir / "user_prompt_submit_audit_hook.py"
    hook_script.write_text(
        "from pathlib import Path\n"
        "import json\n"
        "import sys\n\n"
        "payload = json.load(sys.stdin)\n"
        "log_path = Path(payload['cwd']) / '.tmp' / "
        "'user-prompt-submit-audit.jsonl'\n"
        "log_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "with log_path.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(payload, ensure_ascii=False) + '\\n')\n"
        "print(json.dumps({\n"
        "    'hookSpecificOutput': {\n"
        "        'hookEventName': 'UserPromptSubmit',\n"
        f"        'additionalContext': {context_marker!r},\n"
        "    }\n"
        "}))\n",
        encoding="utf-8",
    )
    hook_command = "python -B .codex/hooks/user_prompt_submit_audit_hook.py"
    encoded_command = json.dumps(hook_command)
    (project / ".codex" / "config.toml").write_text(
        "[[hooks.UserPromptSubmit]]\n\n"
        "[[hooks.UserPromptSubmit.hooks]]\n"
        'type = "command"\n'
        f"command = {encoded_command}\n"
        f"commandWindows = {encoded_command}\n"
        "timeout = 5\n"
        'statusMessage = "Executing prompt audit hook"\n',
        encoding="utf-8",
    )
    command = build_inline_tui_command(
        "python",
        repo_root=repo_root,
        python_executable=sys.executable,
        extra_args=(
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "-C",
            str(project),
            "--dangerously-bypass-hook-trust",
        ),
    )
    fixture_body = _completed_text_response(
        "resp-python-user-prompt-hook",
        "msg-python-user-prompt-hook",
        answer,
    )

    with _SseFixtureServer(fixture_body) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _runtime_config(server.base_url, project)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        prompt,
                        ready_pattern=READY_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text=prompt,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_text=answer,
                        ready_timeout=35.0,
                        ready_quiet_period=0.2,
                    ),
                ),
                env=env,
                timeout=10,
                stop_pattern=answer,
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        request_bodies = list(server.request_bodies)

    transcript.write_artifacts(
        tmp_path,
        prefix="python-user-prompt-submit-hook-runtime",
        rows=ROWS,
        cols=COLS,
    )
    combined = transcript.normalized_combined()
    assert answer in transcript.normalized_stdout(), combined
    assert "Traceback" not in combined
    assert len(request_bodies) == 1, combined
    assert audit_log.exists(), (
        "the real TUI completed a model turn, but UserPromptSubmit did not "
        f"execute its command hook; expected audit log at {audit_log}\n{combined}"
    )

    records = [
        json.loads(line)
        for line in audit_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1, records
    record = records[0]
    assert record["hook_event_name"] == "UserPromptSubmit"
    assert record["prompt"] == prompt
    assert Path(str(record["cwd"])).resolve() == project.resolve()
    assert isinstance(record.get("session_id"), str) and record["session_id"]
    assert isinstance(record.get("turn_id"), str) and record["turn_id"]
    assert context_marker in request_bodies[0].decode("utf-8"), (
        "the hook command ran, but its additionalContext was not applied "
        "before the model request"
    )
