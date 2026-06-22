from pathlib import Path

from pycodex.linux_sandbox import bwrap
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
)


def test_default_unreadable_glob_scan_has_no_depth_cap() -> None:
    # Rust source: linux-sandbox/src/bwrap.rs
    # default_unreadable_glob_scan_has_no_depth_cap.
    assert bwrap.BwrapOptions().glob_scan_max_depth is None


def test_network_modes_decide_unshare_network() -> None:
    # Rust source: BwrapNetworkMode::should_unshare_network.
    assert bwrap.BwrapNetworkMode.FULL_ACCESS.should_unshare_network() is False
    assert bwrap.BwrapNetworkMode.ISOLATED.should_unshare_network() is True
    assert bwrap.BwrapNetworkMode.PROXY_ONLY.should_unshare_network() is True


def test_full_disk_write_full_network_returns_unwrapped_command() -> None:
    # Rust source: full_disk_write_full_network_returns_unwrapped_command.
    command = ["/bin/true"]
    args = bwrap.create_bwrap_command_args(
        command,
        FileSystemSandboxPolicy.unrestricted(),
        Path("/"),
        Path("/"),
        bwrap.BwrapOptions(network_mode=bwrap.BwrapNetworkMode.FULL_ACCESS),
    )

    assert args.args == tuple(command)
    assert args.preserved_files == ()
    assert args.synthetic_mount_targets == ()
    assert args.protected_create_targets == ()


def test_full_disk_write_proxy_only_keeps_full_filesystem_but_unshares_network() -> None:
    # Rust source: full_disk_write_proxy_only_keeps_full_filesystem_but_unshares_network.
    args = bwrap.create_bwrap_command_args(
        ["/bin/true"],
        FileSystemSandboxPolicy.unrestricted(),
        Path("/"),
        Path("/"),
        bwrap.BwrapOptions(network_mode=bwrap.BwrapNetworkMode.PROXY_ONLY),
    )

    assert args.args == (
        "--new-session",
        "--die-with-parent",
        "--bind",
        "/",
        "/",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-net",
        "--proc",
        "/proc",
        "--",
        "/bin/true",
    )


def test_synthetic_mount_targets_preserve_existing_empty_paths(tmp_path: Path) -> None:
    # Rust source: SyntheticMountTarget constructors and should_remove_after_bwrap.
    existing = tmp_path / ".codex"
    existing.write_text("")

    preserved = bwrap.SyntheticMountTarget.existing_empty_file(existing)
    missing = bwrap.SyntheticMountTarget.missing(tmp_path / "new-file")

    assert preserved.path() == existing
    assert preserved.kind() is bwrap.SyntheticMountTargetKind.EMPTY_FILE
    assert preserved.preserves_pre_existing_path() is True
    assert preserved.should_remove_after_bwrap(existing) is False
    assert missing.preserves_pre_existing_path() is False


def test_protected_create_target_records_missing_path(tmp_path: Path) -> None:
    # Rust source: ProtectedCreateTarget::missing.
    target = bwrap.ProtectedCreateTarget.missing(tmp_path / ".git")

    assert target.path() == tmp_path / ".git"


def test_unclosed_character_classes_are_escaped_for_ripgrep() -> None:
    # Rust source: unclosed_character_classes_are_escaped_for_ripgrep.
    search_root, glob = bwrap.split_pattern_for_ripgrep("/tmp/[*.env", Path("/")) or (None, None)

    assert search_root == Path("/tmp")
    assert glob == r"\[*.env"


def test_root_prefix_unreadable_globs_are_too_broad_for_linux_expansion() -> None:
    # Rust source: root_prefix_unreadable_globs_are_too_broad_for_linux_expansion.
    assert bwrap.split_pattern_for_ripgrep("/**/*.env", Path("/tmp")) is None


def test_full_disk_write_with_unreadable_glob_still_wraps_and_masks_match(tmp_path: Path) -> None:
    # Rust source: full_disk_write_with_unreadable_glob_still_wraps_and_masks_match.
    root_env = tmp_path / ".env"
    root_env.write_text("secret")
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(Path("/")),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.glob_pattern(f"{tmp_path.as_posix()}/**/*.env"),
                FileSystemAccessMode.DENY,
            ),
        ]
    )

    args = bwrap.create_bwrap_command_args(["/bin/true"], policy, tmp_path, tmp_path)

    assert args.args != ("/bin/true",)
    assert _window(args.args, ("--bind", "/", "/"))
    assert _window(args.args, ("--perms", "000", "--ro-bind-data", "0", root_env.as_posix()))


def test_missing_read_only_subpath_uses_empty_file_bind_data(tmp_path: Path) -> None:
    # Rust source: missing_read_only_subpath_uses_empty_file_bind_data.
    workspace = tmp_path / "workspace"
    blocked = workspace / "blocked"
    workspace.mkdir()
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(workspace), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(blocked), FileSystemAccessMode.READ),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert _window(args.args, ("--ro-bind-data", "0", blocked.as_posix()))
    assert blocked in [target.path() for target in args.synthetic_mount_targets]
    for name in (".git", ".agents", ".codex"):
        metadata_path = workspace / name
        assert _window(
            args.args,
            ("--perms", "555", "--tmpfs", metadata_path.as_posix(), "--remount-ro", metadata_path.as_posix()),
        )


def test_transient_empty_preserved_file_uses_empty_file_bind_data(tmp_path: Path) -> None:
    # Rust source: transient_empty_preserved_file_uses_empty_file_bind_data.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dot_git = workspace / ".git"
    dot_git.write_text("")
    policy = FileSystemSandboxPolicy.restricted(
        [FileSystemSandboxEntry(FileSystemPath.explicit_path(workspace), FileSystemAccessMode.WRITE)]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert _window(args.args, ("--ro-bind-data", "0", dot_git.as_posix()))
    targets = {target.path(): target for target in args.synthetic_mount_targets}
    assert targets[dot_git].preserves_pre_existing_path() is True
    assert targets[dot_git].should_remove_after_bwrap(dot_git) is False


def test_ignores_missing_writable_roots(tmp_path: Path) -> None:
    # Rust source: ignores_missing_writable_roots.
    existing_root = tmp_path / "existing"
    missing_root = tmp_path / "missing"
    existing_root.mkdir()
    policy = FileSystemSandboxPolicy.workspace_write(
        [existing_root, missing_root],
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert _window(args.args, ("--bind", existing_root.as_posix(), existing_root.as_posix()))
    assert missing_root.as_posix() not in args.args


def test_restricted_read_only_uses_scoped_read_roots_instead_of_erroring(tmp_path: Path) -> None:
    # Rust source: restricted_read_only_uses_scoped_read_roots_instead_of_erroring.
    readable_root = tmp_path / "readable"
    readable_root.mkdir()
    policy = FileSystemSandboxPolicy.restricted(
        [FileSystemSandboxEntry(FileSystemPath.explicit_path(readable_root), FileSystemAccessMode.READ)]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert args.args[:4] == ("--tmpfs", "/", "--dev", "/dev")
    assert _window(args.args, ("--ro-bind", readable_root.as_posix(), readable_root.as_posix()))


def test_mounts_dev_before_writable_dev_binds() -> None:
    # Rust source: mounts_dev_before_writable_dev_binds.
    policy = FileSystemSandboxPolicy.workspace_write(
        [Path("/dev")],
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )

    args = bwrap.create_filesystem_args(policy, Path("/"))

    assert args.args[:5] == ("--ro-bind", "/", "/", "--dev", "/dev")
    assert args.args.index("--dev") < _window_index(args.args, ("--bind", "/dev", "/dev"))


def test_restricted_read_only_with_platform_defaults_includes_usr_when_present(tmp_path: Path) -> None:
    # Rust source: restricted_read_only_with_platform_defaults_includes_usr_when_present.
    policy = FileSystemSandboxPolicy.restricted(
        [FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.minimal()), FileSystemAccessMode.READ)]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert args.args[:2] == ("--tmpfs", "/")
    if Path("/usr").exists():
        assert _window(args.args, ("--ro-bind", "/usr", "/usr"))


def test_split_policy_reenables_writable_subpaths_after_unreadable_parent(tmp_path: Path) -> None:
    # Rust source: split_policy_reenables_writable_subpaths_after_unreadable_parent.
    blocked = tmp_path / "blocked"
    allowed = blocked / "allowed"
    allowed.mkdir(parents=True)
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(Path("/")), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(blocked), FileSystemAccessMode.DENY),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(allowed), FileSystemAccessMode.WRITE),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    blocked_mask = _window_index(args.args, ("--perms", "111", "--tmpfs", blocked.as_posix()))
    allowed_dir = _window_index(args.args, ("--dir", allowed.as_posix()))
    blocked_remount = _window_index(args.args, ("--remount-ro", blocked.as_posix()))
    allowed_bind = _window_index(args.args, ("--bind", allowed.as_posix(), allowed.as_posix()))
    assert -1 not in (blocked_mask, allowed_dir, blocked_remount, allowed_bind)
    assert blocked_mask < allowed_dir < blocked_remount < allowed_bind


def test_split_policy_reapplies_unreadable_carveouts_after_writable_binds(tmp_path: Path) -> None:
    # Rust source: split_policy_reapplies_unreadable_carveouts_after_writable_binds.
    writable_root = tmp_path / "workspace"
    blocked = writable_root / "blocked"
    blocked.mkdir(parents=True)
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(writable_root), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(blocked), FileSystemAccessMode.DENY),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    writable_bind = _window_index(args.args, ("--bind", writable_root.as_posix(), writable_root.as_posix()))
    blocked_mask = _window_index(
        args.args,
        ("--perms", "000", "--tmpfs", blocked.as_posix(), "--remount-ro", blocked.as_posix()),
    )
    assert -1 not in (writable_bind, blocked_mask)
    assert writable_bind < blocked_mask


def test_split_policy_reenables_nested_writable_subpaths_after_read_only_parent(tmp_path: Path) -> None:
    # Rust source: split_policy_reenables_nested_writable_subpaths_after_read_only_parent.
    writable_root = tmp_path / "workspace"
    docs = writable_root / "docs"
    docs_public = docs / "public"
    docs_public.mkdir(parents=True)
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(writable_root), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(docs), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(docs_public), FileSystemAccessMode.WRITE),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    docs_ro = _window_index(args.args, ("--ro-bind", docs.as_posix(), docs.as_posix()))
    docs_public_rw = _window_index(args.args, ("--bind", docs_public.as_posix(), docs_public.as_posix()))
    assert -1 not in (docs_ro, docs_public_rw)
    assert docs_ro < docs_public_rw


def test_missing_child_git_under_parent_repo_uses_protected_create_target(tmp_path: Path) -> None:
    # Rust source: missing_child_git_under_parent_repo_uses_protected_create_target.
    repo = tmp_path / "repo"
    workspace = repo / "workspace"
    dot_git = workspace / ".git"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    workspace.mkdir()
    policy = FileSystemSandboxPolicy.restricted(
        [FileSystemSandboxEntry(FileSystemPath.explicit_path(workspace), FileSystemAccessMode.WRITE)]
    )

    args = bwrap.create_filesystem_args(policy, workspace)

    assert not _window(args.args, ("--perms", "555", "--tmpfs", dot_git.as_posix()))
    assert dot_git not in [target.path() for target in args.synthetic_mount_targets]
    assert [target.path() for target in args.protected_create_targets] == [dot_git]


def test_symlinked_missing_child_git_under_parent_repo_uses_effective_mount_root(tmp_path: Path) -> None:
    # Rust source: symlinked_missing_child_git_under_parent_repo_uses_effective_mount_root.
    repo = tmp_path / "repo"
    workspace = repo / "workspace"
    link_repo = tmp_path / "link-repo"
    link_workspace = link_repo / "workspace"
    dot_git = workspace / ".git"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    workspace.mkdir()
    try:
        link_repo.symlink_to(repo, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    policy = FileSystemSandboxPolicy.restricted(
        [FileSystemSandboxEntry(FileSystemPath.explicit_path(link_workspace), FileSystemAccessMode.WRITE)]
    )

    args = bwrap.create_filesystem_args(policy, link_workspace)

    assert not _window(args.args, ("--perms", "555", "--tmpfs", dot_git.as_posix()))
    assert dot_git not in [target.path() for target in args.synthetic_mount_targets]
    assert [target.path() for target in args.protected_create_targets] == [dot_git]


def test_missing_project_root_metadata_carveouts_use_metadata_path_masks(tmp_path: Path) -> None:
    # Rust source: missing_project_root_metadata_carveouts_use_metadata_path_masks.
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots(".git")),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots(".agents")),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots(".codex")),
                FileSystemAccessMode.READ,
            ),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    synthetic_paths = [target.path() for target in args.synthetic_mount_targets]
    for name in (".git", ".agents", ".codex"):
        metadata_path = tmp_path / name
        assert _window(
            args.args,
            ("--perms", "555", "--tmpfs", metadata_path.as_posix(), "--remount-ro", metadata_path.as_posix()),
        )
        assert metadata_path in synthetic_paths
    assert args.preserved_files == ()
    assert args.protected_create_targets == ()


def test_split_policy_masks_root_read_directory_carveouts(tmp_path: Path) -> None:
    # Rust source: split_policy_masks_root_read_directory_carveouts.
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(Path("/")), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(blocked), FileSystemAccessMode.DENY),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert _window(args.args, ("--ro-bind", "/", "/"))
    assert _window(args.args, ("--perms", "000", "--tmpfs", blocked.as_posix()))
    assert _window(args.args, ("--remount-ro", blocked.as_posix()))


def test_split_policy_masks_root_read_file_carveouts(tmp_path: Path) -> None:
    # Rust source: split_policy_masks_root_read_file_carveouts.
    blocked_file = tmp_path / "blocked.txt"
    blocked_file.write_text("secret")
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(Path("/")), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(blocked_file), FileSystemAccessMode.DENY),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert len(args.preserved_files) == 1
    assert args.synthetic_mount_targets == ()
    assert _window(args.args, ("--perms", "000", "--ro-bind-data", "0", blocked_file.as_posix()))


def test_unreadable_globs_expand_existing_matches_with_configured_depth(tmp_path: Path) -> None:
    # Rust source: unreadable_globs_expand_existing_matches_with_configured_depth.
    root_env = tmp_path / ".env"
    nested_env = tmp_path / "app" / ".env"
    too_deep_env = tmp_path / "app" / "deep" / ".env"
    too_deep_env.parent.mkdir(parents=True)
    root_env.write_text("secret")
    nested_env.write_text("secret")
    too_deep_env.write_text("secret")
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(Path("/")), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(
                FileSystemPath.glob_pattern(f"{tmp_path.as_posix()}/**/*.env"),
                FileSystemAccessMode.DENY,
            ),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path, glob_scan_max_depth=2)

    assert _window(args.args, ("--perms", "000", "--ro-bind-data", "0", root_env.as_posix()))
    assert _window(args.args, ("--perms", "000", "--ro-bind-data", "1", nested_env.as_posix()))
    assert too_deep_env.as_posix() not in args.args


def test_unreadable_globs_add_canonical_targets_for_symlink_matches(tmp_path: Path) -> None:
    # Rust source: unreadable_globs_add_canonical_targets_for_symlink_matches.
    real_root = tmp_path / "real"
    link_root = tmp_path / "link"
    real_secret = real_root / "secret.env"
    real_root.mkdir()
    real_secret.write_text("secret")
    try:
        link_root.symlink_to(real_root, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(Path("/")), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(
                FileSystemPath.glob_pattern(f"{link_root.as_posix()}/**/*.env"),
                FileSystemAccessMode.DENY,
            ),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path, glob_scan_max_depth=2)

    assert real_secret.as_posix() in args.args


def test_symlinked_writable_roots_bind_real_target_and_remap_carveouts(tmp_path: Path) -> None:
    # Rust source: symlinked_writable_roots_bind_real_target_and_remap_carveouts.
    real_root = tmp_path / "real"
    link_root = tmp_path / "link"
    blocked = real_root / "blocked"
    blocked.mkdir(parents=True)
    try:
        link_root.symlink_to(real_root, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(link_root), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(link_root / "blocked"), FileSystemAccessMode.DENY),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert _window(args.args, ("--bind", real_root.as_posix(), real_root.as_posix()))
    assert _window(
        args.args,
        ("--perms", "000", "--tmpfs", blocked.as_posix(), "--remount-ro", blocked.as_posix()),
    )


def test_writable_roots_under_symlinked_ancestors_bind_real_target(tmp_path: Path) -> None:
    # Rust source: writable_roots_under_symlinked_ancestors_bind_real_target.
    logical_home = tmp_path / "home"
    real_codex = tmp_path / "real-codex"
    logical_codex = logical_home / ".codex"
    real_memories = real_codex / "memories"
    logical_memories = logical_codex / "memories"
    logical_home.mkdir()
    real_memories.mkdir(parents=True)
    try:
        logical_codex.symlink_to(real_codex, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    policy = FileSystemSandboxPolicy.restricted(
        [FileSystemSandboxEntry(FileSystemPath.explicit_path(logical_memories), FileSystemAccessMode.WRITE)]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert _window(args.args, ("--bind", real_memories.as_posix(), real_memories.as_posix()))
    assert not _window(args.args, ("--bind", logical_memories.as_posix(), logical_memories.as_posix()))


def test_protected_symlinked_directory_subpaths_fail_closed(tmp_path: Path) -> None:
    # Rust source: protected_symlinked_directory_subpaths_fail_closed.
    root = tmp_path / "root"
    agents_target = root / "agents-target"
    agents_link = root / ".agents"
    agents_target.mkdir(parents=True)
    try:
        agents_link.symlink_to(agents_target, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    policy = FileSystemSandboxPolicy.restricted(
        [FileSystemSandboxEntry(FileSystemPath.explicit_path(root), FileSystemAccessMode.WRITE)]
    )

    try:
        bwrap.create_filesystem_args(policy, tmp_path)
    except RuntimeError as exc:
        assert "cannot enforce sandbox read-only path" in str(exc)
        assert agents_link.as_posix() in str(exc)
    else:
        raise AssertionError("protected symlinked subpath should fail closed")


def test_symlinked_writable_roots_nested_symlink_escape_paths_fail_closed(tmp_path: Path) -> None:
    # Rust source: symlinked_writable_roots_nested_symlink_escape_paths_fail_closed.
    real_root = tmp_path / "real"
    link_root = tmp_path / "link"
    outside = tmp_path / "outside-private"
    linked_private = real_root / "linked-private"
    real_root.mkdir()
    outside.mkdir()
    try:
        link_root.symlink_to(real_root, target_is_directory=True)
        linked_private.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(link_root), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(link_root / "linked-private"), FileSystemAccessMode.DENY),
        ]
    )

    try:
        bwrap.create_filesystem_args(policy, tmp_path)
    except RuntimeError as exc:
        assert "cannot enforce sandbox deny-read path" in str(exc)
        assert linked_private.as_posix() in str(exc)
    else:
        raise AssertionError("deny-read path crossing writable symlink should fail closed")


def test_split_policy_reenables_writable_files_after_unreadable_parent(tmp_path: Path) -> None:
    # Rust source: split_policy_reenables_writable_files_after_unreadable_parent.
    blocked = tmp_path / "blocked"
    allowed_dir = blocked / "allowed"
    allowed_file = allowed_dir / "note.txt"
    allowed_dir.mkdir(parents=True)
    allowed_file.write_text("ok")
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(Path("/")), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(blocked), FileSystemAccessMode.DENY),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(allowed_file), FileSystemAccessMode.WRITE),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    blocked_mask = _window_index(args.args, ("--perms", "111", "--tmpfs", blocked.as_posix()))
    allowed_dir_target = _window_index(args.args, ("--dir", allowed_dir.as_posix()))
    allowed_file_dir_target = _window_index(args.args, ("--dir", allowed_file.as_posix()))
    allowed_bind = _window_index(args.args, ("--bind", allowed_file.as_posix(), allowed_file.as_posix()))
    assert -1 not in (blocked_mask, allowed_dir_target, allowed_bind)
    assert allowed_file_dir_target == -1
    assert blocked_mask < allowed_dir_target < allowed_bind


def test_split_policy_reenables_nested_writable_roots_after_unreadable_parent(tmp_path: Path) -> None:
    # Rust source: split_policy_reenables_nested_writable_roots_after_unreadable_parent.
    writable_root = tmp_path / "workspace"
    blocked = writable_root / "blocked"
    allowed = blocked / "allowed"
    allowed.mkdir(parents=True)
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(FileSystemPath.explicit_path(writable_root), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(blocked), FileSystemAccessMode.DENY),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(allowed), FileSystemAccessMode.WRITE),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    blocked_mask = _window_index(args.args, ("--perms", "111", "--tmpfs", blocked.as_posix()))
    allowed_dir = _window_index(args.args, ("--dir", allowed.as_posix()))
    allowed_bind = _window_index(args.args, ("--bind", allowed.as_posix(), allowed.as_posix()))
    assert -1 not in (blocked_mask, allowed_dir, allowed_bind)
    assert blocked_mask < allowed_dir < allowed_bind


def test_missing_user_project_root_subpath_rules_are_still_enforced(tmp_path: Path) -> None:
    # Rust source: missing_user_project_root_subpath_rules_are_still_enforced.
    policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots(".vscode")),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots(".secrets")),
                FileSystemAccessMode.DENY,
            ),
        ]
    )

    args = bwrap.create_filesystem_args(policy, tmp_path)

    assert _window(args.args, ("--ro-bind-data", "0", (tmp_path / ".vscode").as_posix()))
    assert _window(args.args, ("--ro-bind-data", "1", (tmp_path / ".secrets").as_posix()))


def _window(values: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    return _window_index(values, expected) != -1


def _window_index(values: tuple[str, ...], expected: tuple[str, ...]) -> int:
    width = len(expected)
    for index in range(0, len(values) - width + 1):
        if values[index : index + width] == expected:
            return index
    return -1
