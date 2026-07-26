from __future__ import annotations

from pathlib import Path

from pycodex.windows_sandbox import helper_materialization
from pycodex.windows_sandbox import hide_users
from pycodex.windows_sandbox import sandbox_utils
from pycodex.windows_sandbox import ssh_config_dependencies
from pycodex.windows_sandbox import winutil
from pycodex.windows_sandbox import workspace_acl


def test_sandbox_utils_injects_git_worktree_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    nested = repo / "nested"
    (repo / ".git").mkdir(parents=True)
    nested.mkdir()
    env: dict[str, str] = {}

    sandbox_utils.inject_git_safe_directory(env, nested)

    assert env == {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": str(repo.resolve()).replace("\\\\", "/"),
    }


def test_sandbox_utils_appends_to_existing_git_config(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    env = {"GIT_CONFIG_COUNT": "2"}

    sandbox_utils.inject_git_safe_directory(env, tmp_path)

    assert env["GIT_CONFIG_KEY_2"] == "safe.directory"
    assert env["GIT_CONFIG_COUNT"] == "3"


def test_ssh_config_dependencies_collects_includes_and_profile_paths(
    tmp_path: Path,
) -> None:
    ssh_dir = tmp_path / ".ssh"
    included = ssh_dir / "conf.d" / "dev.conf"
    included.parent.mkdir(parents=True)
    (ssh_dir / "config").write_text(
        "Include conf.d/*.conf\nIdentityFile '~/.keys/quoted key'\n",
        encoding="utf-8",
    )
    included.write_text(
        "CertificateFile %d/.certs/dev.pub\n",
        encoding="utf-8",
    )

    assert ssh_config_dependencies.ssh_config_dependency_paths(tmp_path) == [
        ssh_dir / "config",
        included,
        tmp_path / ".certs" / "dev.pub",
        tmp_path / ".keys" / "quoted key",
    ]


def test_winutil_builds_rust_compatible_windows_command_line() -> None:
    assert winutil.argv_to_command_line(
        [
            "pwsh.exe",
            "-Command",
            'Write-Output "hello world"',
        ]
    ) == 'pwsh.exe -Command "Write-Output \\"hello world\\""'


def test_workspace_acl_matches_canonical_command_cwd(tmp_path: Path) -> None:
    cwd = tmp_path / "workspace"
    cwd.mkdir()

    assert workspace_acl.is_command_cwd_root(cwd / ".", cwd.resolve())
    assert not workspace_acl.is_command_cwd_root(tmp_path, cwd.resolve())


def test_helper_materialization_finds_packaged_resource(tmp_path: Path) -> None:
    package_bin = tmp_path / "bin"
    resources = tmp_path / "codex-resources"
    package_bin.mkdir()
    resources.mkdir()
    executable = package_bin / "codex.exe"
    executable.write_bytes(b"codex")
    helper = resources / "codex-command-runner.exe"
    helper.write_bytes(b"runner")

    assert (
        helper_materialization.bundled_executable_path_for_exe(
            executable,
            helper.name,
        )
        == helper
    )


def test_hide_current_user_profile_dir_is_best_effort(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed: list[Path] = []
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(
        hide_users,
        "_hide_directory",
        lambda path: observed.append(path) or True,
    )

    hide_users.hide_current_user_profile_dir(tmp_path)

    assert observed == [tmp_path]
