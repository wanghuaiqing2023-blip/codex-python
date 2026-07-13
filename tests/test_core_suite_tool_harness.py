from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.apply_patch import ApplyPatchHandler
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.handlers.shell import ShellCommandHandler
from pycodex.core.tools.registry import ToolCallSource, ToolInvocation
from pycodex.protocol import StepStatus, ToolName, UpdatePlanArgs


def _function_invocation(call_id: str, tool_name: str, arguments: str, *, cwd: Path) -> ToolInvocation:
    session = SimpleNamespace(
        user_shell=lambda: Shell(ShellType.POWERSHELL, "pwsh"),
        thread_id="00000000-0000-0000-0000-000000000001",
    )
    turn = SimpleNamespace(cwd=cwd)
    return ToolInvocation(
        call_id=call_id,
        tool_name=ToolName.plain(tool_name),
        payload=ToolPayload.function(arguments),
        source=ToolCallSource.direct(),
        session=session,
        turn=turn,
        cancellation_token=None,
        tracker=None,
    )


def _custom_invocation(call_id: str, patch: str, *, cwd: Path) -> ToolInvocation:
    return ToolInvocation(
        call_id=call_id,
        tool_name=ToolName.plain("apply_patch"),
        payload=ToolPayload.custom(patch),
        source=ToolCallSource.direct(),
        session=SimpleNamespace(),
        turn=SimpleNamespace(cwd=cwd, environments=(SimpleNamespace(environment_id="local", cwd=cwd),)),
        cancellation_token=None,
        tracker=None,
    )


def test_shell_command_tool_executes_command_and_streams_output(tmp_path):
    # Rust: core/tests/suite/tool_harness.rs
    # test `shell_command_tool_executes_command_and_streams_output`.
    seen = []

    def runner(request):
        seen.append(request)
        return FunctionToolOutput.from_text(
            "Exit code: 0\nWall time: 0.01 seconds\nOutput:\ntool harness\n",
            True,
        )

    handler = ShellCommandHandler(runner=runner)
    output = asyncio.run(handler.handle(
        _function_invocation(
            "shell-command-tool-call",
            "shell_command",
            '{"command":"echo tool harness","login":false}',
            cwd=tmp_path,
        )
    ))
    item = output.to_response_item("shell-command-tool-call", ToolPayload.function("{}"))

    assert seen[0].params.command == "echo tool harness"
    assert seen[0].hook_command == "echo tool harness"
    assert output.success_for_logging() is True
    assert item.call_id == "shell-command-tool-call"
    assert item.output.to_text().startswith("Exit code: 0\nWall time:")
    assert "tool harness" in item.output.to_text()


def test_update_plan_tool_emits_plan_update_event():
    # Rust: core/tests/suite/tool_harness.rs
    # test `update_plan_tool_emits_plan_update_event`.
    args = UpdatePlanArgs.from_mapping(
        {
            "explanation": "Tool harness check",
            "plan": [
                {"step": "Inspect workspace", "status": "in_progress"},
                {"step": "Report results", "status": "pending"},
            ],
        }
    )
    output = FunctionToolOutput.from_text("Plan updated", True)

    assert args.explanation == "Tool harness check"
    assert args.plan[0].step == "Inspect workspace"
    assert args.plan[0].status is StepStatus.IN_PROGRESS
    assert args.plan[1].step == "Report results"
    assert args.plan[1].status is StepStatus.PENDING
    assert output.to_response_item("plan-tool-call", ToolPayload.function("{}")).output.to_text() == "Plan updated"


def test_update_plan_tool_rejects_malformed_payload():
    # Rust: core/tests/suite/tool_harness.rs
    # test `update_plan_tool_rejects_malformed_payload`.
    # Rust serde reports a missing required `plan` field; the Python DTO
    # boundary represents required-field absence as KeyError.
    with pytest.raises(KeyError, match="plan"):
        UpdatePlanArgs.from_mapping({"explanation": "Missing plan data"})

    output = FunctionToolOutput.from_text(
        "failed to parse function arguments: plan must be a list",
        False,
    )
    item = output.to_response_item("plan-tool-invalid", ToolPayload.function("{}"))

    assert "failed to parse function arguments" in item.output.to_text()
    assert item.output.success is False


def test_apply_patch_tool_executes_and_emits_patch_events(tmp_path):
    # Rust: core/tests/suite/tool_harness.rs
    # test `apply_patch_tool_executes_and_emits_patch_events`.
    patch = """*** Begin Patch
*** Add File: notes.txt
+Tool harness apply patch
*** End Patch"""
    handler = ApplyPatchHandler.new(False)
    output = handler.handle(_custom_invocation("apply-patch-call", patch, cwd=tmp_path))
    item = output.to_response_item("apply-patch-call", ToolPayload.custom(patch))

    assert item.call_id == "apply-patch-call"
    assert item.output.success is True
    assert "Success. Updated the following files:" in item.output.to_text()
    assert "notes.txt" in item.output.to_text()
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "Tool harness apply patch\n"


def test_apply_patch_reports_parse_diagnostics(tmp_path):
    # Rust: core/tests/suite/tool_harness.rs
    # test `apply_patch_reports_parse_diagnostics`.
    patch = """*** Begin Patch
*** Update File: broken.txt
*** End Patch"""
    handler = ApplyPatchHandler.new(False)

    with pytest.raises(FunctionCallError) as error:
        handler.handle(_custom_invocation("apply-patch-parse-error", patch, cwd=tmp_path))

    message = str(error.value)
    assert "apply_patch verification failed" in message
    assert "invalid hunk" in message
