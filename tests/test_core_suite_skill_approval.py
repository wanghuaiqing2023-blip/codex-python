from pathlib import Path

from pycodex.core.tools.sandboxing import (
    ExecApprovalRequirement,
    default_exec_approval_requirement,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemPath,
    GranularApprovalConfig,
)


def _restrictive_workspace_write_policy(cwd: Path) -> FileSystemSandboxPolicy:
    return FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(cwd),
                FileSystemAccessMode.WRITE,
            ),
        )
    )


def test_shell_zsh_fork_skill_scripts_ignore_declared_permissions(tmp_path):
    # Rust: core/tests/suite/skill_approval.rs
    # test `shell_zsh_fork_skill_scripts_ignore_declared_permissions`.
    approval_policy = GranularApprovalConfig(
        sandbox_approval=True,
        rules=True,
        skill_approval=False,
        request_permissions=True,
        mcp_elicitations=True,
    )
    turn_sandbox = _restrictive_workspace_write_policy(tmp_path / "workspace")
    declared_skill_write_dir = tmp_path / "declared-by-skill-metadata"
    declared_skill_output = declared_skill_write_dir / "allowed.txt"

    assert approval_policy.allows_skill_approval() is False
    assert default_exec_approval_requirement(
        approval_policy,
        FileSystemSandboxPolicy.external_sandbox(),
    ) == ExecApprovalRequirement.skip()
    assert not turn_sandbox.can_write_path_with_cwd(declared_skill_output, tmp_path / "workspace")
    assert not declared_skill_output.exists()


def test_shell_zsh_fork_still_enforces_workspace_write_sandbox(tmp_path):
    # Rust: core/tests/suite/skill_approval.rs
    # test `shell_zsh_fork_still_enforces_workspace_write_sandbox`.
    cwd = tmp_path / "workspace"
    outside_path = tmp_path / "codex-zsh-fork-workspace-write-deny.txt"
    sandbox = _restrictive_workspace_write_policy(cwd)

    assert sandbox.can_write_path_with_cwd(cwd / "inside.txt", cwd)
    assert not sandbox.can_write_path_with_cwd(outside_path, cwd)
    assert not outside_path.exists()
