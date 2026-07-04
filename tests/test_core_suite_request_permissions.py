import asyncio
import json
import subprocess
from pathlib import Path

from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.core.tools.handlers.utils import (
    apply_granted_turn_permissions,
    normalize_and_validate_additional_permissions,
    permissions_are_preapproved,
)
from pycodex.exec.local_runtime import (
    ExecSessionConfig,
    LocalHttpShellInvocation,
    _materialize_local_http_additional_permissions,
    local_http_shell_tool_additional_permissions_allowed,
    local_http_shell_tool_approval_required_output,
    shell_tool_outputs_from_local_http_exec_result,
    local_http_shell_tool_permission_request_error,
)
from pycodex.core.session.turn.runtime import UserTurnSamplingResult
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    GranularApprovalConfig,
    NetworkPermissions,
    PermissionProfile,
    ReviewDecision,
    SandboxPermissions,
)
from pycodex.protocol.request_permissions import RequestPermissionProfile, RequestPermissionsArgs, RequestPermissionsResponse


def _fs_write(path: Path | str) -> AdditionalPermissionProfile:
    return AdditionalPermissionProfile(
        file_system=FileSystemPermissions(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(Path(path)),
                    FileSystemAccessMode.WRITE,
                ),
            )
        )
    )


def _fs_read(path: Path | str) -> AdditionalPermissionProfile:
    return AdditionalPermissionProfile(
        file_system=FileSystemPermissions(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(Path(path)),
                    FileSystemAccessMode.READ,
                ),
            )
        )
    )


def _network() -> AdditionalPermissionProfile:
    return AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))


def _shell_invocation(profile: AdditionalPermissionProfile, *, workdir: Path | None = None) -> LocalHttpShellInvocation:
    return LocalHttpShellInvocation(
        command="pwd",
        workdir=workdir,
        sandbox_permissions="with_additional_permissions",
        additional_permissions=profile.to_mapping(),
    )


def _session(*, turn=None, session=None):
    class Grants:
        async def granted_turn_permissions(self):
            return turn

        async def granted_session_permissions(self):
            return session

    return Grants()


def test_with_additional_permissions_requires_approval_under_on_request(tmp_path):
    # Rust: codex/codex-rs/core/tests/suite/request_permissions.rs
    # Test: with_additional_permissions_requires_approval_under_on_request.
    requested = _fs_write(tmp_path / "requested-dir")
    normalize_and_validate_additional_permissions(
        True,
        AskForApproval.ON_REQUEST,
        SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
        requested,
        False,
        tmp_path,
    )
    output = local_http_shell_tool_approval_required_output(
        _shell_invocation(requested),
        ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=tmp_path,
            approval_policy=AskForApproval.ON_REQUEST,
            exec_permission_approvals_enabled=True,
        ),
    )
    assert "exit_code: approval_required" in output
    assert "sandbox_permissions: with_additional_permissions" in output


def test_default_permissions_shell_approval_callback_runs_approved_command(tmp_path):
    # Rust-derived contract:
    # - codex-core::tools::orchestrator sees ExecApprovalRequirement::NeedsApproval,
    #   emits an approval request, waits for ReviewDecision, then runs the shell
    #   command when approved.
    # - A Default/workspace-write profile may write in the workspace, but a
    #   command such as `Get-Command gcc` still crosses the shell approval
    #   boundary instead of being returned to the model as `approval_required`.
    approvals: list[tuple[str, str]] = []
    ran: list[str] = []

    def approve(invocation, _config, requirement, meta):
        approvals.append((str(meta["call_id"]), invocation.command))
        assert requirement.type == "needs_approval"
        return ReviewDecision.approved()

    def runner(command, **_kwargs):
        ran.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="gcc exists\n", stderr="")

    result = UserTurnSamplingResult(
        request_plan=None,
        response_items=(),
        raw_result={
            "output": [
                {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-gcc",
                    "arguments": json.dumps(
                        {
                            "cmd": "Get-Command gcc -ErrorAction SilentlyContinue",
                            "sandbox_permissions": "require_escalated",
                        }
                    ),
                }
            ]
        },
    )
    config = ExecSessionConfig(
        model=None,
        model_provider_id=None,
        cwd=tmp_path,
        approval_policy=AskForApproval.ON_REQUEST,
        permission_profile=PermissionProfile.workspace_write((tmp_path,)),
        exec_approval_callback=approve,
    )

    outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=runner)

    assert approvals == [("call-gcc", "Get-Command gcc -ErrorAction SilentlyContinue")]
    assert ran == ["Get-Command gcc -ErrorAction SilentlyContinue"]
    assert len(outputs) == 1
    assert outputs[0]["success"] is True
    assert "approval_required" not in outputs[0]["output"]
    assert "gcc exists" in outputs[0]["output"]


def test_request_permissions_tool_is_auto_denied_when_granular_request_permissions_is_disabled(tmp_path):
    # Rust: request_permissions_tool_is_auto_denied_when_granular_request_permissions_is_disabled.
    called = False

    def callback(_parent_ctx, _call_id, _args, _cwd, _cancel_token):
        nonlocal called
        called = True
        return RequestPermissionsResponse(RequestPermissionProfile(network=NetworkPermissions(enabled=True)))

    session = InMemoryCodexSession(
        cwd=tmp_path,
        approval_policy=GranularApprovalConfig(
            sandbox_approval=True,
            rules=True,
            mcp_elicitations=True,
            request_permissions=False,
        ),
        request_permissions_callback=callback,
    )
    response = asyncio.run(
        session.request_permissions_for_cwd(
            None,
            "call-1",
            RequestPermissionsArgs(RequestPermissionProfile(network=NetworkPermissions(enabled=True))),
            tmp_path,
            None,
        )
    )
    assert response == RequestPermissionsResponse(RequestPermissionProfile())
    assert called is False


def test_relative_additional_permissions_resolve_against_tool_workdir(tmp_path):
    # Rust: relative_additional_permissions_resolve_against_tool_workdir.
    nested = tmp_path / "nested"
    nested.mkdir()
    requested = _fs_write(Path("nested"))
    materialized = _materialize_local_http_additional_permissions(requested, tmp_path)
    assert materialized.to_mapping()["file_system"]["write"] == [str(nested)]


def test_read_only_with_additional_permissions_does_not_widen_to_unrequested_cwd_write(tmp_path):
    # Rust: read_only_with_additional_permissions_does_not_widen_to_unrequested_cwd_write.
    requested = _fs_read(tmp_path / "requested-dir")
    assert permissions_are_preapproved(_fs_write(tmp_path), requested, tmp_path) is False


def test_read_only_with_additional_permissions_does_not_widen_to_unrequested_tmp_write(tmp_path):
    # Rust: read_only_with_additional_permissions_does_not_widen_to_unrequested_tmp_write.
    requested = _fs_read(tmp_path / "requested-dir")
    assert permissions_are_preapproved(_fs_write(tmp_path / "tmp"), requested, tmp_path) is False


def test_workspace_write_with_additional_permissions_can_write_outside_cwd(tmp_path):
    # Rust: workspace_write_with_additional_permissions_can_write_outside_cwd.
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    requested = _fs_write(outside)
    assert permissions_are_preapproved(requested, requested, tmp_path) is True


def test_with_additional_permissions_denied_approval_blocks_execution(tmp_path):
    # Rust: with_additional_permissions_denied_approval_blocks_execution.
    output = local_http_shell_tool_permission_request_error(
        _shell_invocation(_fs_write(tmp_path / "requested-dir")),
        cwd=tmp_path,
        additional_permissions_allowed=True,
        allow_pending_approval=False,
    )
    assert output is not None
    assert "permission_request_unsupported" in output


def test_request_permissions_grants_apply_to_later_exec_command_calls(tmp_path):
    # Rust: request_permissions_grants_apply_to_later_exec_command_calls.
    granted = _fs_write(tmp_path / "outside")
    effective = asyncio.run(
        apply_granted_turn_permissions(
            _session(turn=granted),
            tmp_path,
            SandboxPermissions.USE_DEFAULT,
            None,
        )
    )
    assert effective.sandbox_permissions is SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS
    assert effective.permissions_preapproved is True
    assert permissions_are_preapproved(granted, effective.additional_permissions, tmp_path)


def test_request_permissions_preapprove_explicit_exec_permissions_outside_on_request(tmp_path):
    # Rust: request_permissions_preapprove_explicit_exec_permissions_outside_on_request.
    requested = _fs_write(tmp_path / "outside")
    effective = normalize_and_validate_additional_permissions(
        True,
        AskForApproval.NEVER,
        SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
        requested,
        True,
        tmp_path,
    )
    assert effective == requested
    assert local_http_shell_tool_permission_request_error(
        _shell_invocation(requested),
        granted_permissions=requested,
        cwd=tmp_path,
        additional_permissions_allowed=True,
    ) is None


def test_request_permissions_grants_apply_to_later_shell_command_calls(tmp_path):
    # Rust: request_permissions_grants_apply_to_later_shell_command_calls.
    assert (
        local_http_shell_tool_permission_request_error(
            _shell_invocation(_network()),
            granted_permissions=_network(),
            cwd=tmp_path,
            additional_permissions_allowed=True,
        )
        is None
    )


def test_request_permissions_grants_apply_to_later_shell_command_calls_without_inline_permission_feature(tmp_path):
    # Rust: request_permissions_grants_apply_to_later_shell_command_calls_without_inline_permission_feature.
    config = ExecSessionConfig(
        model=None,
        model_provider_id=None,
        cwd=tmp_path,
        approval_policy=AskForApproval.NEVER,
        exec_permission_approvals_enabled=False,
        request_permissions_tool_enabled=True,
    )
    assert local_http_shell_tool_additional_permissions_allowed(config, permissions_preapproved=True) is True
    assert (
        local_http_shell_tool_permission_request_error(
            _shell_invocation(_network()),
            granted_permissions=_network(),
            cwd=tmp_path,
            additional_permissions_allowed=True,
        )
        is None
    )


def test_partial_request_permissions_grants_do_not_preapprove_new_permissions(tmp_path):
    # Rust: partial_request_permissions_grants_do_not_preapprove_new_permissions.
    granted = _fs_write(tmp_path / "first")
    requested = _fs_write(tmp_path / "second")
    assert permissions_are_preapproved(requested, granted, tmp_path) is False
    output = local_http_shell_tool_approval_required_output(
        _shell_invocation(requested),
        ExecSessionConfig(model=None, model_provider_id=None, cwd=tmp_path, approval_policy=AskForApproval.ON_REQUEST),
        granted_permissions=granted,
    )
    match = output.split("additional_permissions: ", 1)[1].splitlines()[0]
    assert sorted(json.loads(match)["file_system"]["write"]) == sorted(
        [str(tmp_path / "first"), str(tmp_path / "second")]
    )


def test_request_permissions_grants_do_not_carry_across_turns(tmp_path):
    # Rust: request_permissions_grants_do_not_carry_across_turns.
    granted = _fs_write(tmp_path / "outside")
    first_turn = asyncio.run(
        apply_granted_turn_permissions(_session(turn=granted), tmp_path, SandboxPermissions.USE_DEFAULT, None)
    )
    next_turn = asyncio.run(
        apply_granted_turn_permissions(_session(turn=None), tmp_path, SandboxPermissions.USE_DEFAULT, None)
    )
    assert first_turn.permissions_preapproved is True
    assert next_turn.additional_permissions is None
    assert next_turn.permissions_preapproved is False


def test_request_permissions_session_grants_carry_across_turns(tmp_path):
    # Rust: request_permissions_session_grants_carry_across_turns.
    granted = _fs_write(tmp_path / "outside")
    first_turn = asyncio.run(
        apply_granted_turn_permissions(_session(session=granted), tmp_path, SandboxPermissions.USE_DEFAULT, None)
    )
    next_turn = asyncio.run(
        apply_granted_turn_permissions(_session(session=granted), tmp_path, SandboxPermissions.USE_DEFAULT, None)
    )
    assert first_turn.permissions_preapproved is True
    assert next_turn.permissions_preapproved is True
    assert next_turn.additional_permissions == granted
