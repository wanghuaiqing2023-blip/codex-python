"""Apply-patch tool handler owned by ``core::tools::handlers::apply_patch``."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pycodex.apply_patch import (
    EOF_MARKER,
    ApplyPatchAction,
    ApplyPatchArgs,
    ApplyPatchParseError,
    Hunk,
    StreamingPatchParser,
    UpdateFileChunk,
    apply_patch_action_to_disk,
    parse_patch,
    verify_apply_patch_args,
)
from pycodex.core.apply_patch import convert_apply_patch_to_protocol
from pycodex.core.tools.context import ApplyPatchToolOutput, ToolPayload
from pycodex.core.tools.handlers import apply_patch_spec
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.tools.hosted_spec import ToolSpec
from pycodex.core.tools.registry import CoreToolRuntime, PostToolUsePayload, PreToolUsePayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.features import Feature
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    EventMsg,
    FileChange,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PatchApplyUpdatedEvent,
    ToolName,
    approval_policy_display_value,
)

APPLY_PATCH_ARGUMENT_DIFF_BUFFER_INTERVAL = 0.5


@dataclass
class ApplyPatchHandler(CoreToolRuntime):
    multi_environment: bool = False

    @classmethod
    def new(cls, include_environment_id: bool) -> "ApplyPatchHandler":
        return cls(multi_environment=include_environment_id)

    def tool_name(self) -> ToolName:
        return ToolName.plain(apply_patch_spec.APPLY_PATCH_TOOL_NAME)

    def spec(self) -> ToolSpec:
        return apply_patch_spec.create_apply_patch_freeform_tool(self.multi_environment)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return payload.type == "custom"

    def create_diff_consumer(self) -> "ApplyPatchArgumentDiffConsumer":
        return ApplyPatchArgumentDiffConsumer()

    def pre_tool_use_payload(self, invocation: Any) -> PreToolUsePayload | None:
        command = apply_patch_payload_command(getattr(invocation, "payload", None))
        if command is None:
            return None
        return PreToolUsePayload(HookToolName.apply_patch(), {"command": command})

    def with_updated_hook_input(self, invocation: Any, updated_input: Any) -> Any:
        from pycodex.core.tools.handlers import updated_hook_command

        patch = updated_hook_command(updated_input)
        payload = getattr(invocation, "payload", None)
        if isinstance(payload, ToolPayload) and payload.type == "custom":
            return replace(invocation, payload=ToolPayload.custom(patch))
        return invocation

    def post_tool_use_payload(self, invocation: Any, result: Any) -> PostToolUsePayload | None:
        command = apply_patch_payload_command(getattr(invocation, "payload", None))
        if command is None:
            return None
        response_method = getattr(result, "post_tool_use_response", None)
        tool_response = response_method(invocation.call_id, invocation.payload) if callable(response_method) else None
        if tool_response is None:
            return None
        return PostToolUsePayload(
            HookToolName.apply_patch(),
            invocation.call_id,
            {"command": command},
            tool_response,
        )

    def handle(self, invocation: Any) -> ApplyPatchToolOutput:
        resolved = resolve_apply_patch_invocation(
            invocation,
            multi_environment=self.multi_environment,
        )
        verified = verify_apply_patch_args(resolved.args, resolved.cwd)
        if verified.type == "body":
            assert verified.body is not None
            rejection = _apply_patch_policy_rejection(invocation, verified.body)
            if rejection is None:
                return ApplyPatchToolOutput.from_text(apply_patch_action_to_disk(verified.body))
            if "approval_required" not in rejection:
                raise FunctionCallError.respond_to_model(rejection)
            if getattr(invocation, "session", None) is None or not getattr(invocation, "call_id", None):
                raise FunctionCallError.respond_to_model(rejection)
            return self._handle_approval_required(invocation, resolved, verified.body)
        if verified.type == "correctness_error":
            raise FunctionCallError.respond_to_model(
                f"apply_patch verification failed: {verified.error}"
            )
        raise FunctionCallError.respond_to_model(
            "apply_patch handler received invalid patch input"
        )

    async def _handle_approval_required(
        self,
        invocation: Any,
        resolved: "ResolvedApplyPatchInvocation",
        action: ApplyPatchAction,
    ) -> ApplyPatchToolOutput:
        from pycodex.core.tools.orchestrator import OrchestratorRunResult, ToolOrchestrator
        from pycodex.core.tools.runtimes import ApplyPatchRuntime
        from pycodex.core.tools.sandboxing import ExecApprovalRequirement, ToolCtx, ToolError

        turn = getattr(invocation, "turn", None)
        session = getattr(invocation, "session", None)
        file_system_sandbox_policy = _invocation_file_system_sandbox_policy(invocation)
        if file_system_sandbox_policy is None:
            raise FunctionCallError.respond_to_model("apply_patch is unavailable without a filesystem policy")
        request = build_apply_patch_request(
            turn_environment=resolved.turn_environment,
            action=action,
            file_system_sandbox_policy=file_system_sandbox_policy,
            cwd=resolved.cwd,
            exec_approval_requirement=ExecApprovalRequirement.needs_approval(),
        )
        result = await ToolOrchestrator.new().run(
            ApplyPatchRuntime(),
            request,
            ToolCtx(
                session=session,
                turn=turn,
                call_id=str(getattr(invocation, "call_id")),
                tool_name=getattr(invocation, "tool_name"),
            ),
            turn,
            _invocation_approval_policy(invocation),
        )
        if isinstance(result, ToolError):
            message = result.message if result.type == "rejected" else str(result.error)
            raise FunctionCallError.respond_to_model(message or "apply_patch rejected")
        if not isinstance(result, OrchestratorRunResult):
            raise TypeError("apply_patch orchestrator returned an invalid result")
        return ApplyPatchToolOutput.from_text(result.output.exec_output.aggregated_output.text)


@dataclass
class ApplyPatchArgumentDiffConsumer:
    parser: StreamingPatchParser = field(default_factory=StreamingPatchParser)
    last_sent_at: float | None = None
    pending: PatchApplyUpdatedEvent | None = None

    def consume_diff(self, turn: Any, call_id: str, delta: str) -> EventMsg | None:
        if not _apply_patch_streaming_events_enabled(turn):
            return None
        try:
            hunks = self.parser.push_delta(delta)
        except ApplyPatchParseError:
            return None
        if not hunks:
            return None
        event = PatchApplyUpdatedEvent(call_id, convert_apply_patch_hunks_to_protocol(hunks))
        now = time.monotonic()
        if self.last_sent_at is not None and now - self.last_sent_at < APPLY_PATCH_ARGUMENT_DIFF_BUFFER_INTERVAL:
            self.pending = event
            return None
        self.pending = None
        self.last_sent_at = now
        return EventMsg.with_payload("patch_apply_updated", event)

    def finish(self) -> EventMsg | None:
        try:
            self.parser.finish()
        except ApplyPatchParseError as error:
            raise FunctionCallError.respond_to_model(f"failed to parse apply_patch: {error}") from error
        event = self.pending
        self.pending = None
        if event is not None:
            self.last_sent_at = time.monotonic()
            return EventMsg.with_payload("patch_apply_updated", event)
        return None


def apply_patch_payload_command(payload: Any) -> str | None:
    if isinstance(payload, ToolPayload) and payload.type == "custom":
        return payload.input
    return None


def convert_apply_patch_hunks_to_protocol(hunks: tuple[Hunk, ...] | list[Hunk]) -> dict[Path, FileChange]:
    changes: dict[Path, FileChange] = {}
    for hunk in hunks:
        path = hunk.path
        if hunk.type == "add":
            changes[path] = FileChange.add(hunk.contents or "")
        elif hunk.type == "delete":
            changes[path] = FileChange.delete("")
        elif hunk.type == "update":
            changes[path] = FileChange.update(
                _format_update_chunks_for_progress(hunk.chunks),
                move_path=hunk.move_path,
            )
        else:
            raise ValueError(f"unknown apply_patch hunk type: {hunk.type}")
    return changes


def _format_update_chunks_for_progress(chunks: tuple[UpdateFileChunk, ...]) -> str:
    lines: list[str] = []
    for chunk in chunks:
        lines.append(f"@@ {chunk.change_context}" if chunk.change_context is not None else "@@")
        lines.extend(f"-{line}" for line in chunk.old_lines)
        lines.extend(f"+{line}" for line in chunk.new_lines)
        if chunk.is_end_of_file:
            lines.append(EOF_MARKER)
    return "\n".join(lines) + ("\n" if lines else "")


def _apply_patch_streaming_events_enabled(turn: Any) -> bool:
    features = getattr(turn, "features", None)
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        return bool(enabled(Feature.APPLY_PATCH_STREAMING_EVENTS))
    if isinstance(features, Mapping):
        return bool(
            features.get(Feature.APPLY_PATCH_STREAMING_EVENTS)
            or features.get(Feature.APPLY_PATCH_STREAMING_EVENTS.value)
            or features.get(Feature.APPLY_PATCH_STREAMING_EVENTS.key())
        )
    return False


def _apply_patch_policy_rejection(invocation: Any, action: ApplyPatchAction) -> str | None:
    file_system_sandbox_policy = _invocation_file_system_sandbox_policy(invocation)
    if file_system_sandbox_policy is None:
        return None
    cwd = action.cwd
    write_check_paths = _apply_patch_write_check_paths(action)
    unwritable = tuple(
        path for path in write_check_paths if not file_system_sandbox_policy.can_write_path_with_cwd(path, cwd)
    )
    if not unwritable:
        return None
    granted_permissions = _invocation_granted_permissions(invocation)
    from pycodex.core.tools.handlers import permissions_are_preapproved

    if granted_permissions is not None and permissions_are_preapproved(
        _apply_patch_required_permissions(write_check_paths, cwd),
        granted_permissions,
        cwd,
    ):
        return None
    approval_policy = _invocation_approval_policy(invocation)
    approval = approval_policy_display_value(approval_policy)
    paths = "\n".join(str(path) for path in unwritable)
    if approval_policy is AskForApproval.NEVER or (
        isinstance(approval_policy, GranularApprovalConfig)
        and not approval_policy.allows_sandbox_approval()
    ):
        return (
            "exit_code: forbidden\n"
            f"approval_policy: {approval}\n"
            "stderr:\n"
            "patch rejected: writing outside of the project; rejected by user approval settings\n"
            f"paths:\n{paths}"
        )
    return (
        "exit_code: approval_required\n"
        f"approval_policy: {approval}\n"
        "stderr:\n"
        "patch requires approval before writing outside the current sandbox\n"
        f"paths:\n{paths}"
    )


def _apply_patch_write_check_paths(action: ApplyPatchAction) -> tuple[Path, ...]:
    paths: list[Path] = []
    for path, change in action.changes.items():
        paths.append(_write_check_path(path))
        if change.move_path is not None:
            paths.append(_write_check_path(change.move_path))
    return tuple(dict.fromkeys(paths))


def file_paths_for_action(action: ApplyPatchAction) -> tuple[Path, ...]:
    if not isinstance(action, ApplyPatchAction):
        raise TypeError("action must be ApplyPatchAction")
    paths: list[Path] = []
    for path, change in action.changes.items():
        paths.append(_resolve_action_path(path, action.cwd))
        if change.move_path is not None:
            paths.append(_resolve_action_path(change.move_path, action.cwd))
    return tuple(dict.fromkeys(paths))


def write_permissions_for_paths(
    file_paths: tuple[Path, ...] | list[Path],
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: Path | str,
) -> AdditionalPermissionProfile | None:
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
    cwd = Path(cwd)
    write_roots: list[Path] = []
    for path in file_paths:
        path = Path(path)
        parent = path.parent if str(path.parent) not in {"", "."} else path
        if not file_system_sandbox_policy.can_write_path_with_cwd(parent, cwd):
            write_roots.append(parent)
    if not write_roots:
        return None
    entries = tuple(
        FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.WRITE)
        for path in tuple(dict.fromkeys(write_roots))
    )
    return AdditionalPermissionProfile(file_system=FileSystemPermissions(entries=entries))


def build_apply_patch_request(
    *,
    turn_environment: Any,
    action: ApplyPatchAction,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: Path | str | None = None,
    effective_additional_permissions: Any | None = None,
    exec_approval_requirement: Any | None = None,
) -> Any:
    from pycodex.core.tools.handlers import EffectiveAdditionalPermissions
    from pycodex.core.tools.runtimes import ApplyPatchRequest
    from pycodex.core.tools.sandboxing import ExecApprovalRequirement

    if not isinstance(action, ApplyPatchAction):
        raise TypeError("action must be ApplyPatchAction")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
    request_cwd = Path(cwd) if cwd is not None else action.cwd
    if request_cwd is None:
        request_cwd = Path(getattr(turn_environment, "cwd"))
    file_paths = file_paths_for_action(action)
    if effective_additional_permissions is None:
        effective_additional_permissions = EffectiveAdditionalPermissions(
            sandbox_permissions="use_default",
            additional_permissions=write_permissions_for_paths(
                file_paths,
                file_system_sandbox_policy,
                request_cwd,
            ),
            permissions_preapproved=False,
        )
    if not isinstance(effective_additional_permissions, EffectiveAdditionalPermissions):
        raise TypeError("effective_additional_permissions must be EffectiveAdditionalPermissions")
    if exec_approval_requirement is None:
        exec_approval_requirement = ExecApprovalRequirement.skip()
    if not isinstance(exec_approval_requirement, ExecApprovalRequirement):
        raise TypeError("exec_approval_requirement must be ExecApprovalRequirement")
    return ApplyPatchRequest(
        turn_environment=turn_environment,
        action=action,
        file_paths=file_paths,
        changes=convert_apply_patch_to_protocol(action),
        exec_approval_requirement=exec_approval_requirement,
        additional_permissions=effective_additional_permissions.additional_permissions,
        permissions_preapproved=effective_additional_permissions.permissions_preapproved,
    )


def _resolve_action_path(path: Path, cwd: Path | None) -> Path:
    if path.is_absolute() or cwd is None:
        return path
    return cwd / path


def _write_check_path(path: Path) -> Path:
    parent = path.parent
    return parent if str(parent) not in {"", "."} else path


def _apply_patch_required_permissions(paths: tuple[Path, ...], cwd: Path) -> AdditionalPermissionProfile:
    entries = tuple(
        FileSystemSandboxEntry(
            FileSystemPath.explicit_path(path if path.is_absolute() else cwd / path),
            FileSystemAccessMode.WRITE,
        )
        for path in paths
    )
    return AdditionalPermissionProfile(file_system=FileSystemPermissions(entries=entries))


def _invocation_granted_permissions(invocation: Any) -> AdditionalPermissionProfile | None:
    session = getattr(invocation, "session", None)
    granted_session = _sync_granted_permissions(session, "granted_session_permissions", "_granted_session_permissions")
    granted_turn = _sync_granted_permissions(session, "granted_turn_permissions", "_granted_turn_permissions")
    turn = getattr(invocation, "turn", None)
    from pycodex.core.tools.handlers import merge_permission_profiles

    granted_turn = merge_permission_profiles(
        granted_turn,
        _sync_granted_permissions(turn, "granted_turn_permissions", "_granted_turn_permissions"),
    )
    return merge_permission_profiles(granted_session, granted_turn)


def _sync_granted_permissions(target: Any, method_name: str, attr_name: str) -> AdditionalPermissionProfile | None:
    if target is None:
        return None
    if hasattr(target, attr_name):
        value = getattr(target, attr_name)
        return value if isinstance(value, AdditionalPermissionProfile) else None
    method = getattr(target, method_name, None)
    if callable(method):
        try:
            value = method()
        except TypeError:
            return None
        close = getattr(value, "close", None)
        if callable(close):
            close()
            return None
        if isinstance(value, AdditionalPermissionProfile):
            return value
    return None


def _invocation_file_system_sandbox_policy(invocation: Any) -> Any | None:
    turn = getattr(invocation, "turn", None)
    policy = getattr(turn, "file_system_sandbox_policy", None)
    if policy is not None:
        return policy
    permission_profile = getattr(turn, "permission_profile", None)
    if permission_profile is None:
        permission_profile = getattr(getattr(invocation, "session", None), "permission_profile", None)
    method = getattr(permission_profile, "file_system_sandbox_policy", None)
    return method() if callable(method) else None


def _invocation_approval_policy(invocation: Any) -> AskForApproval | GranularApprovalConfig:
    value = getattr(getattr(invocation, "turn", None), "approval_policy", AskForApproval.ON_REQUEST)
    method = getattr(value, "value", None)
    if callable(method):
        value = method()
    if isinstance(value, GranularApprovalConfig):
        return value
    if not isinstance(value, AskForApproval):
        value = AskForApproval.parse(str(value))
    return value


@dataclass(frozen=True)
class ResolvedApplyPatchInvocation:
    args: ApplyPatchArgs
    selected_environment_id: str | None
    turn_environment: Any
    cwd: Path

    def __post_init__(self) -> None:
        if not isinstance(self.args, ApplyPatchArgs):
            raise TypeError("args must be ApplyPatchArgs")
        if self.selected_environment_id is not None and not isinstance(self.selected_environment_id, str):
            raise TypeError("selected_environment_id must be a string")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))


def resolve_apply_patch_invocation(
    invocation: Any,
    *,
    multi_environment: bool = False,
) -> ResolvedApplyPatchInvocation:
    payload = getattr(invocation, "payload", None)
    if payload is None or getattr(payload, "type", None) != "custom":
        raise FunctionCallError.respond_to_model("apply_patch handler received unsupported payload")
    patch_input = getattr(payload, "input", None)
    if not isinstance(patch_input, str):
        raise FunctionCallError.respond_to_model("apply_patch handler received unsupported payload")
    try:
        args = parse_patch(patch_input)
    except ApplyPatchParseError as parse_error:
        raise FunctionCallError.respond_to_model(
            f"apply_patch verification failed: {parse_error}"
        ) from parse_error
    selected_environment_id = require_apply_patch_environment_id(
        args.environment_id,
        multi_environment,
    )
    from pycodex.core.tools.handlers import resolve_tool_environment

    turn_environment = resolve_tool_environment(
        getattr(invocation, "turn", None),
        selected_environment_id,
    )
    if turn_environment is None:
        raise FunctionCallError.respond_to_model("apply_patch is unavailable in this session")
    return ResolvedApplyPatchInvocation(
        args=args,
        selected_environment_id=selected_environment_id,
        turn_environment=turn_environment,
        cwd=Path(getattr(turn_environment, "cwd")),
    )


def require_apply_patch_environment_id(
    parsed_environment_id: str | None,
    allow_environment_id: bool,
) -> str | None:
    if parsed_environment_id is not None and not allow_environment_id:
        raise FunctionCallError.respond_to_model(
            "apply_patch environment selection is unavailable for this turn"
        )
    return parsed_environment_id


__all__ = [
    "APPLY_PATCH_ARGUMENT_DIFF_BUFFER_INTERVAL",
    "ApplyPatchArgumentDiffConsumer",
    "ApplyPatchHandler",
    "ResolvedApplyPatchInvocation",
    "apply_patch_payload_command",
    "build_apply_patch_request",
    "convert_apply_patch_hunks_to_protocol",
    "file_paths_for_action",
    "require_apply_patch_environment_id",
    "resolve_apply_patch_invocation",
    "write_permissions_for_paths",
]
