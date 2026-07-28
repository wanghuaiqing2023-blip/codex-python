"""Rust ``tools::handlers::unified_exec::exec_command`` handler."""

from __future__ import annotations

import inspect
import json
import shlex
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pycodex.core.tools.context import ExecCommandToolOutput, ToolPayload
from pycodex.core.tools.handlers import (
    apply_granted_turn_permissions,
    implicit_granted_permissions,
    normalize_and_validate_additional_permissions,
)
from pycodex.core.tools.handlers.shell_spec import (
    CommandToolOptions,
    create_exec_command_tool_with_environment_id,
)
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.tools.registry import PostToolUsePayload, PreToolUsePayload, ToolInvocation
from pycodex.core.tools.router import FunctionCallError
from pycodex.core.unified_exec import UnifiedExecError
from pycodex.features import Feature
from pycodex.protocol import AskForApproval, PermissionProfile, SandboxPermissions, ToolName

from . import (
    JsonValue,
    ExecCommandArgs,
    ExecCommandRequest,
    ResolvedExecCommandInvocation,
    _allocate_unified_exec_process_id,
    _emit_unified_exec_tty_metric,
    _invocation_allow_login_shell,
    _invocation_approval_policy,
    _invocation_exec_env,
    _invocation_feature_enabled,
    _invocation_optional_unified_exec_manager,
    _invocation_session_shell,
    _invocation_truncation_policy,
    _json_mapping,
    _maybe_emit_implicit_skill_invocation,
    _parse_or_validation_error,
    _release_unified_exec_process_id,
    _sandbox_denied_tool_output,
    _session_with_permission_accessors,
    intercept_exec_apply_patch,
    post_unified_exec_tool_use_payload,
    resolve_exec_command_invocation,
    updated_hook_command,
)


@dataclass(frozen=True)
class ExecCommandHandlerOptions:
    allow_login_shell: bool = False
    exec_permission_approvals_enabled: bool = False
    include_environment_id: bool = False


class ExecCommandHandler:
    def __init__(self, options: ExecCommandHandlerOptions | None = None) -> None:
        self.options = options or ExecCommandHandlerOptions()

    def tool_name(self) -> ToolName:
        return ToolName.plain("exec_command")

    def spec(self) -> dict[str, JsonValue]:
        return create_exec_command_tool_with_environment_id(
            CommandToolOptions(
                self.options.allow_login_shell,
                self.options.exec_permission_approvals_enabled,
            ),
            self.options.include_environment_id,
        )

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def pre_tool_use_payload(self, invocation: ToolInvocation) -> PreToolUsePayload | None:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            return None
        try:
            args = ExecCommandArgs.from_json(invocation.payload.arguments or "")
        except Exception:
            return None
        return PreToolUsePayload(HookToolName.bash(), {"command": args.cmd})

    def with_updated_hook_input(
        self,
        invocation: ToolInvocation,
        updated_input: JsonValue,
    ) -> ToolInvocation:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            raise ValueError("hook input rewrite received unsupported exec_command payload")
        arguments = _json_mapping(
            invocation.payload.arguments or "",
            "exec_command arguments",
        )
        arguments["cmd"] = updated_hook_command(updated_input)
        return replace(
            invocation,
            payload=ToolPayload.function(
                json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
            ),
        )

    def post_tool_use_payload(
        self,
        invocation: ToolInvocation,
        result: JsonValue,
    ) -> PostToolUsePayload | None:
        return post_unified_exec_tool_use_payload(invocation, result)

    def handle(self, invocation: ToolInvocation) -> ExecCommandToolOutput | Any:
        try:
            resolved = resolve_exec_command_invocation(
                invocation,
                session_shell=_invocation_session_shell(invocation),
                allow_login_shell=_invocation_allow_login_shell(
                    invocation,
                    self.options.allow_login_shell,
                ),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise _parse_or_validation_error(error) from error
        return self._handle_after_skill_invocation(invocation, resolved)

    def _handle_after_skill_invocation(
        self,
        invocation: ToolInvocation,
        resolved: ResolvedExecCommandInvocation,
    ) -> ExecCommandToolOutput | Any:
        manager = _invocation_optional_unified_exec_manager(invocation)
        exec_command = getattr(manager, "exec_command", None) if manager is not None else None
        if callable(exec_command):
            return self._handle_with_unified_exec_manager(invocation, resolved, exec_command)
        raise FunctionCallError.respond_to_model(
            "unified exec is unavailable in this session; refusing unrestricted fallback"
        )

    async def _handle_with_unified_exec_manager(
        self,
        invocation: ToolInvocation,
        resolved: ResolvedExecCommandInvocation,
        exec_command: Any,
    ) -> ExecCommandToolOutput:
        manager = _invocation_optional_unified_exec_manager(invocation)
        turn = invocation.turn
        approval_policy = _invocation_approval_policy(invocation)
        maybe_emitted = _maybe_emit_implicit_skill_invocation(
            invocation.session,
            turn,
            resolved.args.cmd,
            resolved.cwd,
        )
        if inspect.isawaitable(maybe_emitted):
            await maybe_emitted
        process_id = await _allocate_unified_exec_process_id(manager)
        requested_additional_permissions = resolved.args.additional_permissions
        effective_additional_permissions = await apply_granted_turn_permissions(
            _session_with_permission_accessors(invocation.session),
            resolved.cwd,
            resolved.args.sandbox_permissions,
            resolved.args.additional_permissions,
        )
        additional_permissions_allowed = (
            _invocation_feature_enabled(invocation, Feature.EXEC_PERMISSION_APPROVALS)
            or (
                _invocation_feature_enabled(invocation, Feature.REQUEST_PERMISSIONS_TOOL)
                and effective_additional_permissions.permissions_preapproved
            )
        )

        if (
            effective_additional_permissions.sandbox_permissions.requests_sandbox_override()
            and not effective_additional_permissions.permissions_preapproved
            and approval_policy is not AskForApproval.ON_REQUEST
        ):
            await _release_unified_exec_process_id(manager, process_id)
            raise FunctionCallError.respond_to_model(
                f"approval policy is {approval_policy!r}; reject command - "
                f"you cannot ask for escalated permissions if the approval policy is {approval_policy!r}"
            )

        try:
            normalized_additional_permissions = implicit_granted_permissions(
                resolved.args.sandbox_permissions,
                requested_additional_permissions,
                effective_additional_permissions,
            )
            if normalized_additional_permissions is None:
                normalized_additional_permissions = normalize_and_validate_additional_permissions(
                    additional_permissions_allowed,
                    approval_policy,
                    effective_additional_permissions.sandbox_permissions,
                    effective_additional_permissions.additional_permissions,
                    effective_additional_permissions.permissions_preapproved,
                    resolved.cwd,
                )
        except (TypeError, ValueError) as error:
            await _release_unified_exec_process_id(manager, process_id)
            raise FunctionCallError.respond_to_model(str(error)) from error

        intercepted = intercept_exec_apply_patch(
            resolved.resolved_command.command,
            resolved.cwd,
        )
        if intercepted is not None:
            await _release_unified_exec_process_id(manager, process_id)
            return ExecCommandToolOutput(
                event_call_id="",
                chunk_id="",
                wall_time_seconds=0.0,
                raw_output=intercepted.encode("utf-8"),
                truncation_policy=_invocation_truncation_policy(invocation),
                max_output_tokens=resolved.args.max_output_tokens,
                process_id=None,
                exit_code=None,
                hook_command=None,
            )
        _emit_unified_exec_tty_metric(turn, resolved.args.tty)
        request = ExecCommandRequest(
            call_id=invocation.call_id,
            command=resolved.resolved_command.command,
            shell_type=resolved.resolved_command.shell_type,
            hook_command=resolved.args.cmd,
            process_id=process_id,
            yield_time_ms=resolved.args.yield_time_ms,
            max_output_tokens=resolved.args.max_output_tokens,
            cwd=resolved.cwd,
            sandbox_cwd=Path(getattr(resolved.turn_environment, "cwd")),
            environment=_invocation_exec_env(invocation),
            environment_is_complete=True,
            network=getattr(turn, "network", None),
            tty=resolved.args.tty,
            sandbox_permissions=effective_additional_permissions.sandbox_permissions,
            additional_permissions=normalized_additional_permissions,
            additional_permissions_preapproved=effective_additional_permissions.permissions_preapproved,
            justification=resolved.args.justification,
            prefix_rule=resolved.args.prefix_rule,
            truncation_policy=_invocation_truncation_policy(invocation),
        )
        try:
            from pycodex.core.tools.orchestrator import OrchestratorRunResult, ToolOrchestrator
            from pycodex.core.tools.runtimes import UnifiedExecRequest, UnifiedExecRuntime
            from pycodex.core.tools.sandboxing import ToolCtx, ToolError
            from pycodex.core.exec_policy import (
                ExecApprovalRequest,
                create_exec_approval_requirement_for_command,
            )

            permission_profile = getattr(turn, "permission_profile", None)
            if permission_profile is None:
                permission_profile = getattr(invocation.session, "permission_profile", None)
            if permission_profile is None:
                permission_profile = PermissionProfile.disabled()
            file_system_sandbox_policy = getattr(turn, "file_system_sandbox_policy", None)
            if callable(file_system_sandbox_policy):
                file_system_sandbox_policy = file_system_sandbox_policy()
            if file_system_sandbox_policy is None:
                file_system_sandbox_policy = permission_profile.file_system_sandbox_policy()
            approval_sandbox_permissions = (
                SandboxPermissions.USE_DEFAULT
                if effective_additional_permissions.permissions_preapproved
                else effective_additional_permissions.sandbox_permissions
            )
            exec_approval_requirement = create_exec_approval_requirement_for_command(
                ExecApprovalRequest(
                    command=resolved.resolved_command.command,
                    approval_policy=approval_policy,
                    permission_profile=permission_profile,
                    file_system_sandbox_policy=file_system_sandbox_policy,
                    sandbox_cwd=Path(getattr(resolved.turn_environment, "cwd")),
                    sandbox_permissions=approval_sandbox_permissions,
                    prefix_rule=resolved.args.prefix_rule,
                )
            )
            runtime_request = UnifiedExecRequest(
                command=resolved.resolved_command.command,
                shell_type=resolved.resolved_command.shell_type,
                hook_command=resolved.args.cmd,
                process_id=process_id,
                cwd=resolved.cwd,
                sandbox_cwd=Path(getattr(resolved.turn_environment, "cwd")),
                environment=getattr(resolved.turn_environment, "environment", None),
                env=_invocation_exec_env(invocation),
                exec_server_env_config=None,
                explicit_env_overrides={},
                network=getattr(turn, "network", None),
                tty=resolved.args.tty,
                sandbox_permissions=effective_additional_permissions.sandbox_permissions,
                additional_permissions=normalized_additional_permissions,
                additional_permissions_preapproved=effective_additional_permissions.permissions_preapproved,
                justification=resolved.args.justification,
                exec_approval_requirement=exec_approval_requirement,
            )
            runtime = UnifiedExecRuntime(manager, request)
            tool_ctx = ToolCtx(
                session=invocation.session,
                turn=turn,
                call_id=invocation.call_id,
                tool_name=ToolName.plain("exec_command"),
            )
            orchestrator_turn = {
                "permission_profile": permission_profile,
                "file_system_sandbox_policy": file_system_sandbox_policy,
                "network_sandbox_policy": permission_profile.network_sandbox_policy(),
                "network": getattr(turn, "network", None),
                "cwd": Path(getattr(resolved.turn_environment, "cwd")),
                "features": getattr(turn, "features", None),
                "config": getattr(turn, "config", None),
                "windows_sandbox_level": getattr(turn, "windows_sandbox_level", None),
                "codex_linux_sandbox_exe": getattr(turn, "codex_linux_sandbox_exe", None),
                "session_telemetry": getattr(turn, "session_telemetry", None),
                "routes_approval_to_guardian": getattr(turn, "routes_approval_to_guardian", False),
            }
            result = await ToolOrchestrator.new().run(
                runtime,
                runtime_request,
                tool_ctx,
                orchestrator_turn,
                approval_policy,
            )
            if isinstance(result, ToolError):
                message = result.message if result.type == "rejected" else str(result.error)
                raise FunctionCallError.respond_to_model(
                    message or "command execution rejected"
                )
            if not isinstance(result, OrchestratorRunResult):
                raise TypeError("unified exec orchestrator returned an invalid result")
            return result.output
        except UnifiedExecError as error:
            if error.kind == UnifiedExecError.SANDBOX_DENIED and error.output is not None:
                return _sandbox_denied_tool_output(
                    error,
                    invocation,
                    resolved.args,
                    _invocation_truncation_policy(invocation),
                )
            await _release_unified_exec_process_id(manager, process_id)
            command_for_display = shlex.join(resolved.resolved_command.command)
            raise FunctionCallError.respond_to_model(
                f"exec_command failed for `{command_for_display}`: {error}"
            ) from error
        except Exception as error:
            await _release_unified_exec_process_id(manager, process_id)
            command_for_display = shlex.join(resolved.resolved_command.command)
            raise FunctionCallError.respond_to_model(
                f"exec_command failed for `{command_for_display}`: {error}"
            ) from error


__all__ = ["ExecCommandHandler", "ExecCommandHandlerOptions"]
