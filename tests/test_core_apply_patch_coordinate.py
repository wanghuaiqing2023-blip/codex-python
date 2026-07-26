from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pycodex.apply_patch import ApplyPatchAction, ApplyPatchFileChange
from pycodex.core.apply_patch import (
    InternalApplyPatchInvocation,
    apply_patch,
    convert_apply_patch_to_protocol,
)
from pycodex.core.safety import SafetyCheck
from pycodex.core.sandbox_tags import SandboxType
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import FileSystemSandboxPolicy, PermissionProfile, WindowsSandboxLevel


def _turn() -> SimpleNamespace:
    return SimpleNamespace(
        approval_policy=SimpleNamespace(value=lambda: "on-request"),
        permission_profile=lambda: PermissionProfile.disabled(),
        windows_sandbox_level=WindowsSandboxLevel.DISABLED,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("check", "expected_type", "auto_approved", "requirement_type"),
    (
        (SafetyCheck.auto_approve(SandboxType.NONE), "delegate_to_runtime", True, "skip"),
        (
            SafetyCheck.auto_approve(SandboxType.NONE, user_explicitly_approved=True),
            "delegate_to_runtime",
            False,
            "skip",
        ),
        (SafetyCheck.ask_user(), "delegate_to_runtime", False, "needs_approval"),
    ),
)
async def test_apply_patch_maps_rust_safety_branches(
    check: SafetyCheck,
    expected_type: str,
    auto_approved: bool,
    requirement_type: str,
) -> None:
    action = ApplyPatchAction({}, Path.cwd())
    with patch("pycodex.core.apply_patch.assess_patch_safety", return_value=check):
        result = await apply_patch(
            _turn(),
            FileSystemSandboxPolicy.default(),
            action,
        )

    assert result.type == expected_type
    assert result.runtime_invocation is not None
    assert result.runtime_invocation.action is action
    assert result.runtime_invocation.auto_approved is auto_approved
    assert result.runtime_invocation.exec_approval_requirement.type == requirement_type


@pytest.mark.asyncio
async def test_apply_patch_reject_returns_model_error_output() -> None:
    action = ApplyPatchAction({}, Path.cwd())
    with patch(
        "pycodex.core.apply_patch.assess_patch_safety",
        return_value=SafetyCheck.reject("outside project"),
    ):
        result = await apply_patch(_turn(), FileSystemSandboxPolicy.default(), action)

    assert result.type == "output"
    assert isinstance(result.output, FunctionCallError)
    assert str(result.output) == "patch rejected: outside project"


def test_convert_apply_patch_to_protocol_is_owned_by_core_module() -> None:
    path = Path("new.txt")
    action = ApplyPatchAction(
        {path: ApplyPatchFileChange.add("hello")},
        Path.cwd(),
    )

    converted = convert_apply_patch_to_protocol(action)

    assert converted[path].type == "add"
    assert converted[path].content == "hello"
    assert InternalApplyPatchInvocation.delegate_to_runtime
