from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest

from pycodex.core.exec import ExecParams, ExecRequest
from pycodex.core.client import ModelClient
from pycodex.core.sandbox_tags import SandboxType
from pycodex.core.sandboxing import execute_env, process_exec_tool_call
from pycodex.exec.local_runtime import (
    LocalHttpModelInfo,
    LocalHttpProvider,
    run_exec_user_turn_core_sampling,
)
from pycodex.exec.run import ExecRunPlan, InitialOperation
from pycodex.exec.session import ExecSessionConfig
from pycodex.protocol import (
    AskForApproval,
    ContentItem,
    NetworkSandboxPolicy,
    PermissionProfile,
    ResponseItem,
    UserInput,
    WindowsSandboxLevel,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires native Windows sandbox APIs")


def _request(
    command: tuple[str, ...],
    profile: PermissionProfile,
    cwd: Path,
    *,
    level: WindowsSandboxLevel = WindowsSandboxLevel.RESTRICTED_TOKEN,
) -> ExecRequest:
    file_system, network = profile.to_runtime_permissions()
    return ExecRequest(
        command=command,
        cwd=cwd,
        sandbox=SandboxType.WINDOWS_RESTRICTED_TOKEN,
        windows_sandbox_policy_cwd=cwd,
        windows_sandbox_level=level,
        windows_sandbox_private_desktop=True,
        permission_profile=profile,
        file_system_sandbox_policy=file_system,
        network_sandbox_policy=network,
    )


def test_core_dispatch_read_only_is_os_enforced(tmp_path: Path, monkeypatch) -> None:
    # Rust owner: codex-core::exec::get_raw_output_result -> exec_windows_sandbox.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = Path.cwd()
    target = workspace / ".tmp" / f"core-readonly-{uuid.uuid4().hex}.txt"
    target.parent.mkdir(exist_ok=True)

    result = asyncio.run(
        execute_env(
            _request(
                ("cmd.exe", "/d", "/c", f"echo unsafe> {target}"),
                PermissionProfile.read_only(),
                workspace,
            )
        )
    )
    assert result.exit_code != 0
    assert not target.exists()


def test_core_dispatch_workspace_write_uses_native_backend(monkeypatch) -> None:
    workspace = Path.cwd()
    monkeypatch.setenv("CODEX_HOME", str(Path.home() / ".codex"))
    target = workspace / ".tmp" / f"core-workspace-{uuid.uuid4().hex}.txt"
    target.parent.mkdir(exist_ok=True)
    profile = PermissionProfile.workspace_write(
        network=NetworkSandboxPolicy.ENABLED,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    try:
        result = asyncio.run(
            execute_env(
                _request(
                    ("cmd.exe", "/d", "/c", f"echo native> {target}"),
                    profile,
                    workspace,
                )
            )
        )
        assert result.exit_code == 0
        assert target.read_text(encoding="utf-8").strip() == "native"
    finally:
        target.unlink(missing_ok=True)


def test_core_dispatch_elevated_routes_to_native_capture(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    from pycodex.windows_sandbox import elevated
    from pycodex.windows_sandbox.process import ProcessCaptureResult

    observed: dict[str, object] = {}

    def fake_capture(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return ProcessCaptureResult(0, b"elevated-native", b"")

    monkeypatch.setattr(elevated, "run_elevated_capture", fake_capture)
    result = asyncio.run(
        execute_env(
            _request(
                ("cmd.exe", "/d", "/c", "echo must-not-run"),
                PermissionProfile.read_only(),
                Path.cwd(),
                level=WindowsSandboxLevel.ELEVATED,
            )
        )
    )
    assert result.stdout.text == "elevated-native"
    assert observed["kwargs"]["proxy_enforced"] is False


def test_core_dispatch_spawn_failure_does_not_fallback(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    with pytest.raises(OSError, match="windows sandbox:.*CreateProcessAsUserW failed"):
        asyncio.run(
            execute_env(
                _request(
                    ("definitely-not-a-real-executable-pycodex.exe",),
                    PermissionProfile.read_only(),
                    Path.cwd(),
                )
            )
        )


def test_process_exec_tool_call_routes_read_only_to_native_backend(tmp_path: Path, monkeypatch) -> None:
    # Product dynamic anchor: process_exec_tool_call -> build_exec_request -> native capture.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = Path.cwd()
    target = workspace / ".tmp" / f"tool-readonly-{uuid.uuid4().hex}.txt"
    target.parent.mkdir(exist_ok=True)

    result = asyncio.run(
        process_exec_tool_call(
            ExecParams(
                command=("cmd.exe", "/d", "/c", f"echo unsafe> {target}"),
                cwd=workspace,
                windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
                windows_sandbox_private_desktop=True,
            ),
            PermissionProfile.read_only(),
            workspace,
        )
    )

    assert result.exit_code != 0
    assert not target.exists()


def test_core_session_workspace_profile_blocks_write_outside_workspace(tmp_path: Path, monkeypatch) -> None:
    # Fixed Rust runtime path:
    # Session.windows_sandbox_level -> TurnContext.windows_sandbox_level ->
    # tools::orchestrator::ToolOrchestrator -> native Windows sandbox.
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "workspace"
    codex_home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    target = Path.home() / f"pycodex-session-outside-{uuid.uuid4().hex}.txt"
    target.unlink(missing_ok=True)

    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=workspace,
        workspace_roots=(workspace,),
        approval_policy=AskForApproval.NEVER,
        permission_profile=PermissionProfile.workspace_write((workspace,)),
        windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
    )
    plan = ExecRunPlan(
        InitialOperation.user_turn((UserInput.text_input("write outside workspace"),)),
        "write outside workspace",
    )
    provider = LocalHttpProvider()
    model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
    client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
        provider=provider,
    )
    command = (
        f"$target = '{str(target).replace(chr(39), chr(39) * 2)}'; "
        "Set-Content -LiteralPath $target -Value 'OUTSIDE_WRITE_SHOULD_FAIL'"
    )
    requests = 0

    async def sampler(_request):
        nonlocal requests
        requests += 1
        if requests == 1:
            return [
                ResponseItem.function_call(
                    "exec_command",
                    json.dumps({"cmd": command, "yield_time_ms": 1_000}),
                    "call-outside-write",
                )
            ]
        return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

    try:
        result = asyncio.run(
            run_exec_user_turn_core_sampling(
                config,
                plan,
                client,
                provider,
                model_info,
                sampler,
            )
        )
        assert not target.exists()
        tool_output = result.tool_response_items[0].output.body.text
        assert "Process exited with code 0" not in tool_output
    finally:
        target.unlink(missing_ok=True)
