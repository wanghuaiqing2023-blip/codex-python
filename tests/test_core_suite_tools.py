from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.shell import Shell, ShellType
from pycodex.core.session.turn.runtime import build_user_turn_responses_request_from_session
from pycodex.core.tools import format_exec_output_for_model
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.handlers.shell import ShellCommandHandler
from pycodex.core.tools.parallel import ToolCallRuntime
from pycodex.core.tools.registry import ToolCallSource, ToolInvocation
from pycodex.core.tools.router import ToolRouter, build_tool_call
from pycodex.core.tools.spec_plan import ToolPlanOptions, build_tool_router
from pycodex.protocol import (
    ApplyPatchToolType,
    AskForApproval,
    ContentItem,
    ExecToolCallOutput,
    PermissionProfile,
    ResponseItem,
    StreamOutput,
    ToolName,
    TruncationPolicyConfig,
    TurnEnvironmentSelection,
    UserInput,
)

from test_core_turn_runtime import Session


def _tool_names(body: dict) -> list[str]:
    return [
        tool.get("name") or tool.get("type")
        for tool in body.get("tools", ())
        if tool.get("name") or tool.get("type")
    ]


def _model_info():
    return SimpleNamespace(
        slug="gpt-test",
        supports_reasoning_summaries=False,
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
        apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
        supports_image_detail_original=True,
    )


def _planned_tool_names(environments) -> list[str]:
    turn_context = SimpleNamespace(environments=environments, model_info=_model_info())
    router = build_tool_router(turn_context, SimpleNamespace(), ToolPlanOptions(use_unified_exec=True))
    return _tool_names({"tools": router.model_visible_specs()})


def _shell_invocation(call_id: str, arguments: dict, *, cwd: Path, runner=None) -> ToolInvocation:
    session = SimpleNamespace(
        user_shell=lambda: Shell(ShellType.POWERSHELL, "pwsh"),
        thread_id="00000000-0000-0000-0000-000000000001",
    )
    if runner is not None:
        session.shell_command_runner = runner
    turn = SimpleNamespace(
        cwd=cwd,
        approval_policy=AskForApproval.NEVER,
        permission_profile=PermissionProfile.disabled(),
    )
    return ToolInvocation(
        call_id=call_id,
        tool_name=ToolName.plain("shell_command"),
        payload=ToolPayload.function(json.dumps(arguments, separators=(",", ":"))),
        source=ToolCallSource.direct(),
        session=session,
        turn=turn,
        cancellation_token=None,
        tracker=None,
    )


def test_empty_turn_environments_omits_environment_backed_tools() -> None:
    # Rust: core/tests/suite/tools.rs::empty_turn_environments_omits_environment_backed_tools.
    names = _planned_tool_names(())

    assert "update_plan" in names
    for environment_tool in ("exec_command", "write_stdin", "apply_patch", "view_image"):
        assert environment_tool not in names


def test_turn_environment_selection_keeps_environment_backed_tools() -> None:
    # Rust: core/tests/suite/tools.rs::turn_environment_selection_keeps_environment_backed_tools.
    names = _planned_tool_names((TurnEnvironmentSelection("local", str(Path.cwd())),))

    assert "exec_command" in names


def test_custom_tool_unknown_returns_custom_output_error() -> None:
    # Rust: core/tests/suite/tools.rs::custom_tool_unknown_returns_custom_output_error.
    async def run():
        item = ResponseItem.custom_tool_call("unsupported_tool", '"payload"', "custom-unsupported")
        call = build_tool_call(item)
        assert call is not None
        output = await ToolCallRuntime(ToolRouter.from_parts(())).handle_tool_call(call)
        return output

    output = asyncio.run(run())

    assert output.type == "custom_tool_call_output"
    assert output.call_id == "custom-unsupported"
    assert output.output.to_text() == "unsupported custom tool call: unsupported_tool"


def test_shell_command_escalated_permissions_rejected_then_ok(tmp_path: Path) -> None:
    # Rust: core/tests/suite/tools.rs::shell_command_escalated_permissions_rejected_then_ok.
    handler = ShellCommandHandler(runner=lambda _request: FunctionToolOutput.from_text("shell ok", True))

    with pytest_raises_function_call_error() as error:
        maybe = handler.handle(
            _shell_invocation(
                "shell-command-blocked",
                {"command": "echo shell ok", "login": False, "sandbox_permissions": "require_escalated"},
                cwd=tmp_path,
            )
        )
        if asyncio.iscoroutine(maybe):
            asyncio.run(maybe)

    assert "approval policy is" in str(error.value)
    assert "escalated permissions" in str(error.value)

    ok = handler.handle(
        _shell_invocation(
            "shell-command-success",
            {"command": "echo shell ok", "login": False},
            cwd=tmp_path,
        )
    )
    if asyncio.iscoroutine(ok):
        ok = asyncio.run(ok)
    assert ok.into_text() == "shell ok"


def test_sandbox_denied_shell_command_returns_original_output(tmp_path: Path) -> None:
    # Rust: core/tests/suite/tools.rs::sandbox_denied_shell_command_returns_original_output.
    sentinel = "sandbox-denied sentinel output"
    denied_path = tmp_path / "sandbox-denied.txt"

    def runner(_request):
        return {
            "text": f"Exit code: 1\nWall time: 0.01 seconds\nOutput:\n{sentinel}\npermission denied: {denied_path}",
            "success": True,
        }

    output = ShellCommandHandler(runner=runner).handle(
        _shell_invocation("sandbox-denied-shell-command", {"command": "write denied"}, cwd=tmp_path)
    )
    if asyncio.iscoroutine(output):
        output = asyncio.run(output)
    body = output.into_text()

    assert "Exit code: 1" in body
    assert sentinel in body
    assert str(denied_path) in body
    assert "permission denied" in body.lower()
    assert "failed in sandbox" not in body.lower()


def test_shell_command_enforces_glob_deny_read_policy(tmp_path: Path) -> None:
    # Rust: core/tests/suite/tools.rs::shell_command_enforces_glob_deny_read_policy.
    allowed = "shell glob deny-read allowed"
    secret = "shell glob deny-read secret"

    def runner(_request):
        return {
            "text": f"Exit code: 1\nWall time: 0.01 seconds\nOutput:\npermission denied: secret.env\n{allowed}\n",
            "success": True,
        }

    output = ShellCommandHandler(runner=runner).handle(
        _shell_invocation("shell-command-glob-deny-read", {"command": "cat files"}, cwd=tmp_path)
    )
    if asyncio.iscoroutine(output):
        output = asyncio.run(output)
    body = output.into_text()

    assert "Exit code: 1" in body
    assert allowed in body
    assert secret not in body
    assert "permission denied" in body.lower()


def test_unified_exec_spec_toggle_end_to_end() -> None:
    # Rust: core/tests/suite/tools.rs::unified_exec_spec_toggle_end_to_end.
    turn_context = SimpleNamespace(environments=(TurnEnvironmentSelection("local", str(Path.cwd())),))

    disabled = build_tool_router(
        turn_context,
        SimpleNamespace(),
        ToolPlanOptions(use_unified_exec=False),
    ).model_visible_specs()
    enabled = build_tool_router(
        turn_context,
        SimpleNamespace(),
        ToolPlanOptions(use_unified_exec=True),
    ).model_visible_specs()

    disabled_names = _tool_names({"tools": disabled})
    enabled_names = _tool_names({"tools": enabled})
    assert "exec_command" not in disabled_names
    assert "write_stdin" not in disabled_names
    assert "exec_command" in enabled_names
    assert "write_stdin" in enabled_names


def test_shell_command_timeout_includes_timeout_prefix_and_metadata() -> None:
    # Rust: core/tests/suite/tools.rs::shell_command_timeout_includes_timeout_prefix_and_metadata.
    output = ExecToolCallOutput(
        exit_code=124,
        aggregated_output=StreamOutput.new("line\n"),
        duration=timedelta(milliseconds=50),
        timed_out=True,
    )

    text = format_exec_output_for_model(output, TruncationPolicyConfig.bytes(4096))

    assert text.startswith("Exit code: 124\nWall time:")
    assert "Output:\ncommand timed out after 50 milliseconds\nline\n" in text


def test_shell_command_timeout_handles_background_grandchild_stdout(tmp_path: Path) -> None:
    # Rust: core/tests/suite/tools.rs::shell_command_timeout_handles_background_grandchild_stdout.
    def runner(_request):
        return "Exit code: 124\nWall time: 0.20 seconds\nOutput:\ncommand timed out after 200 milliseconds\n"

    start = time.monotonic()
    output = ShellCommandHandler(runner=runner).handle(
        _shell_invocation(
            "shell-command-grandchild-timeout",
            {"command": "spawn detached grandchild", "login": False, "timeout_ms": 200},
            cwd=tmp_path,
        )
    )
    if asyncio.iscoroutine(output):
        output = asyncio.run(output)
    elapsed = time.monotonic() - start

    assert "Exit code: 124" in output.into_text()
    assert "command timed out" in output.into_text()
    assert elapsed < 1.0


class pytest_raises_function_call_error:
    def __enter__(self):
        import pytest

        self._ctx = pytest.raises(FunctionCallError)
        return self._ctx.__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._ctx.__exit__(exc_type, exc, tb)
