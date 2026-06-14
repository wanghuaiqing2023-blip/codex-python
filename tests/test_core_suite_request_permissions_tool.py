import asyncio
from pathlib import Path

from pycodex.core.tools.handlers.utils import apply_granted_turn_permissions
from pycodex.exec.local_runtime import (
    LocalHttpShellInvocation,
    _local_http_apply_patch_preapproved,
    local_http_shell_tool_permission_request_error,
)
from pycodex.protocol import (
    AdditionalPermissionProfile,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    SandboxPermissions,
)
from pycodex.protocol.approvals import FileChange


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


def _session_with_turn_grant(grant: AdditionalPermissionProfile):
    class Session:
        async def granted_turn_permissions(self):
            return grant

        async def granted_session_permissions(self):
            return None

    return Session()


def test_approved_folder_write_request_permissions_unblocks_later_exec_without_sandbox_args(tmp_path):
    # Rust: codex/codex-rs/core/tests/suite/request_permissions_tool.rs
    # Test: approved_folder_write_request_permissions_unblocks_later_exec_without_sandbox_args.
    requested_dir = tmp_path / "requested"
    requested_dir.mkdir()
    grant = _fs_write(requested_dir)

    effective = asyncio.run(
        apply_granted_turn_permissions(
            _session_with_turn_grant(grant),
            tmp_path,
            SandboxPermissions.USE_DEFAULT,
            None,
        )
    )

    assert effective.sandbox_permissions is SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS
    assert effective.permissions_preapproved is True
    assert (
        local_http_shell_tool_permission_request_error(
            LocalHttpShellInvocation(command="printf ok > allowed-write.txt"),
            granted_permissions=effective.additional_permissions,
            cwd=requested_dir,
            additional_permissions_allowed=True,
        )
        is None
    )


def test_approved_folder_write_request_permissions_unblocks_later_apply_patch(tmp_path):
    # Rust: approved_folder_write_request_permissions_unblocks_later_apply_patch.
    requested_dir = tmp_path / "requested"
    requested_dir.mkdir()
    requested_file = requested_dir / "allowed-patch.txt"
    grant = _fs_write(requested_dir)
    changes = {requested_file: FileChange.add("patched-via-request-permissions\n")}

    assert _local_http_apply_patch_preapproved(changes, tmp_path, grant) is True

    outside_file = tmp_path / "not-granted" / "blocked-patch.txt"
    outside_changes = {outside_file: FileChange.add("blocked\n")}
    assert _local_http_apply_patch_preapproved(outside_changes, tmp_path, grant) is False
