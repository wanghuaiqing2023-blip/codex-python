"""Core-owned apply-patch safety and protocol conversion.

Rust source: ``codex-rs/core/src/apply_patch.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.apply_patch import ApplyPatchAction
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.safety import assess_patch_safety
from pycodex.core.tools.sandboxing import ExecApprovalRequirement
from pycodex.protocol import (
    AskForApproval,
    FileChange,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PermissionProfile,
    WindowsSandboxLevel,
)


@dataclass(frozen=True)
class ApplyPatchRuntimeInvocation:
    action: ApplyPatchAction
    auto_approved: bool
    exec_approval_requirement: ExecApprovalRequirement

    def __post_init__(self) -> None:
        if not isinstance(self.action, ApplyPatchAction):
            raise TypeError("action must be an ApplyPatchAction")
        if not isinstance(self.auto_approved, bool):
            raise TypeError("auto_approved must be a bool")
        if not isinstance(self.exec_approval_requirement, ExecApprovalRequirement):
            raise TypeError("exec_approval_requirement must be an ExecApprovalRequirement")


@dataclass(frozen=True)
class InternalApplyPatchInvocation:
    type: str
    output: str | FunctionCallError | None = None
    runtime_invocation: ApplyPatchRuntimeInvocation | None = None

    def __post_init__(self) -> None:
        if self.type == "output":
            if self.output is None or self.runtime_invocation is not None:
                raise ValueError("output invocation requires only output")
            return
        if self.type == "delegate_to_runtime":
            if self.output is not None or not isinstance(
                self.runtime_invocation,
                ApplyPatchRuntimeInvocation,
            ):
                raise ValueError("runtime invocation requires only runtime_invocation")
            return
        raise ValueError(f"unknown apply-patch invocation type: {self.type}")

    @classmethod
    def output_result(cls, result: str | FunctionCallError) -> "InternalApplyPatchInvocation":
        return cls("output", output=result)

    @classmethod
    def delegate_to_runtime(
        cls,
        invocation: ApplyPatchRuntimeInvocation,
    ) -> "InternalApplyPatchInvocation":
        return cls("delegate_to_runtime", runtime_invocation=invocation)


async def apply_patch(
    turn_context: Any,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    action: ApplyPatchAction,
) -> InternalApplyPatchInvocation:
    """Map the Rust safety decision to a runtime or model-facing result."""

    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    if not isinstance(action, ApplyPatchAction):
        raise TypeError("action must be an ApplyPatchAction")

    check = assess_patch_safety(
        action,
        _approval_policy(turn_context),
        _permission_profile(turn_context),
        file_system_sandbox_policy,
        action.cwd or Path(getattr(turn_context, "cwd", Path.cwd())),
        _windows_sandbox_level(turn_context),
    )
    if check.type == "auto_approve":
        return InternalApplyPatchInvocation.delegate_to_runtime(
            ApplyPatchRuntimeInvocation(
                action=action,
                auto_approved=not check.user_explicitly_approved,
                exec_approval_requirement=ExecApprovalRequirement.skip(
                    bypass_sandbox=False,
                ),
            )
        )
    if check.type == "ask_user":
        return InternalApplyPatchInvocation.delegate_to_runtime(
            ApplyPatchRuntimeInvocation(
                action=action,
                auto_approved=False,
                exec_approval_requirement=ExecApprovalRequirement.needs_approval(),
            )
        )
    if check.type == "reject":
        return InternalApplyPatchInvocation.output_result(
            FunctionCallError.respond_to_model(f"patch rejected: {check.reason}")
        )
    raise ValueError(f"unknown safety check type: {check.type}")


def convert_apply_patch_to_protocol(action: ApplyPatchAction) -> dict[Path, FileChange]:
    if not isinstance(action, ApplyPatchAction):
        raise TypeError("action must be an ApplyPatchAction")
    result: dict[Path, FileChange] = {}
    for path, change in action.changes.items():
        if change.type == "add":
            result[path] = FileChange.add(change.content or "")
        elif change.type == "delete":
            result[path] = FileChange.delete(change.content or "")
        elif change.type == "update":
            result[path] = FileChange.update(
                change.unified_diff or "",
                move_path=change.move_path,
            )
        else:
            raise ValueError(f"unknown apply_patch file change type: {change.type}")
    return result


def _approval_policy(turn_context: Any) -> AskForApproval | GranularApprovalConfig:
    value = getattr(turn_context, "approval_policy", AskForApproval.ON_REQUEST)
    getter = getattr(value, "value", None)
    if callable(getter):
        value = getter()
    if isinstance(value, GranularApprovalConfig):
        return value
    if not isinstance(value, AskForApproval):
        value = AskForApproval.parse(str(value))
    return value


def _permission_profile(turn_context: Any) -> PermissionProfile:
    value = getattr(turn_context, "permission_profile", None)
    if callable(value):
        value = value()
    if not isinstance(value, PermissionProfile):
        raise TypeError("turn_context.permission_profile must resolve to PermissionProfile")
    return value


def _windows_sandbox_level(turn_context: Any) -> WindowsSandboxLevel:
    value = getattr(turn_context, "windows_sandbox_level", WindowsSandboxLevel.DISABLED)
    if not isinstance(value, WindowsSandboxLevel):
        value = WindowsSandboxLevel.parse(str(value))
    return value


__all__ = [
    "ApplyPatchRuntimeInvocation",
    "InternalApplyPatchInvocation",
    "apply_patch",
    "convert_apply_patch_to_protocol",
]
