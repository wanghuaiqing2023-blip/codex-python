import asyncio
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pycodex.file_system import (
    CopyOptions,
    CreateDirectoryOptions,
    FileMetadata,
    FileSystemSandboxContext,
    LocalExecutorFileSystem,
    ReadDirectoryEntry,
    RemoveOptions,
    file_system_policy_has_cwd_dependent_entries,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    PermissionProfile,
    SandboxPolicy,
    WindowsSandboxLevel,
)


def test_option_and_metadata_records_are_value_types() -> None:
    # Rust: codex-file-system/src/lib.rs derives Clone/Copy/Debug/Eq/PartialEq
    # for operation options and Clone/Debug/Eq/PartialEq for metadata records.
    assert CreateDirectoryOptions(recursive=True) == CreateDirectoryOptions(recursive=True)
    assert RemoveOptions(recursive=True, force=False) != RemoveOptions(recursive=False, force=False)
    assert CopyOptions(recursive=False) == CopyOptions(recursive=False)
    assert FileMetadata(False, True, False, 1, 2).modified_at_ms == 2
    assert ReadDirectoryEntry("a.txt", False, True).file_name == "a.txt"

    with pytest.raises(FrozenInstanceError):
        CreateDirectoryOptions(recursive=True).recursive = False  # type: ignore[misc]


def test_file_system_sandbox_context_permission_profile_constructors(tmp_path: Path) -> None:
    # Rust: FileSystemSandboxContext::from_permission_profile,
    # from_permission_profile_with_cwd, should_run_in_sandbox, and drop_cwd_if_unused.
    read_only_context = FileSystemSandboxContext.from_permission_profile_with_cwd(
        PermissionProfile.read_only(),
        tmp_path,
    )
    assert read_only_context.cwd == tmp_path
    assert read_only_context.windows_sandbox_level is WindowsSandboxLevel.DISABLED
    assert read_only_context.should_run_in_sandbox()
    assert not read_only_context.has_cwd_dependent_permissions()
    assert read_only_context.drop_cwd_if_unused().cwd is None

    workspace_context = FileSystemSandboxContext.from_permission_profile_with_cwd(
        PermissionProfile.workspace_write(),
        tmp_path,
    )
    assert workspace_context.should_run_in_sandbox()
    assert workspace_context.has_cwd_dependent_permissions()
    assert workspace_context.drop_cwd_if_unused().cwd == tmp_path

    disabled_context = FileSystemSandboxContext.from_permission_profile(PermissionProfile.disabled())
    assert not disabled_context.should_run_in_sandbox()
    assert disabled_context.cwd is None


def test_from_legacy_sandbox_policy_uses_cwd_materialized_permissions(tmp_path: Path) -> None:
    # Rust: FileSystemSandboxContext::from_legacy_sandbox_policy builds a
    # FileSystemSandboxPolicy for cwd, then wraps it as a PermissionProfile.
    sandbox_policy = SandboxPolicy.workspace_write(
        [tmp_path / "extra"],
        network_access=True,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )

    context = FileSystemSandboxContext.from_legacy_sandbox_policy(sandbox_policy, tmp_path)

    assert context.cwd == tmp_path
    assert context.windows_sandbox_level is WindowsSandboxLevel.DISABLED
    assert context.permissions == PermissionProfile.from_legacy_sandbox_policy_for_cwd(
        sandbox_policy,
        tmp_path,
    )
    assert context.should_run_in_sandbox()
    assert context.has_cwd_dependent_permissions()


def test_cwd_dependent_entries_match_rust_predicate(tmp_path: Path) -> None:
    # Rust: file_system_policy_has_cwd_dependent_entries returns true for
    # relative glob patterns and ProjectRoots special paths only.
    relative_glob = FileSystemSandboxEntry(
        FileSystemPath.glob_pattern("**/*.env"),
        FileSystemAccessMode.DENY,
    )
    absolute_glob = FileSystemSandboxEntry(
        FileSystemPath.glob_pattern(str(tmp_path / "**" / "*.env")),
        FileSystemAccessMode.DENY,
    )
    project_roots = FileSystemSandboxEntry(
        FileSystemPath.special(FileSystemSpecialPath.project_roots()),
        FileSystemAccessMode.WRITE,
    )
    explicit_path = FileSystemSandboxEntry(
        FileSystemPath.explicit_path(tmp_path / "file.txt"),
        FileSystemAccessMode.WRITE,
    )

    assert file_system_policy_has_cwd_dependent_entries(
        FileSystemSandboxPolicy.restricted((relative_glob,))
    )
    assert not file_system_policy_has_cwd_dependent_entries(
        FileSystemSandboxPolicy.restricted((absolute_glob, explicit_path))
    )
    assert file_system_policy_has_cwd_dependent_entries(
        FileSystemSandboxPolicy.restricted((project_roots,))
    )


def test_executor_read_file_text_decodes_read_bytes(tmp_path: Path) -> None:
    # Rust: ExecutorFileSystem::read_file_text default method delegates to
    # read_file and decodes UTF-8 text.
    path = tmp_path / "message.txt"
    path.write_text("hello", encoding="utf-8")

    assert asyncio.run(LocalExecutorFileSystem().read_file_text(path)) == "hello"


def test_local_executor_file_system_operations(tmp_path: Path) -> None:
    fs = LocalExecutorFileSystem()
    root = tmp_path / "root"
    nested = root / "nested"
    source = nested / "a.txt"
    copied = tmp_path / "copy.txt"

    asyncio.run(fs.create_directory(nested, CreateDirectoryOptions(recursive=True)))
    asyncio.run(fs.write_file(source, b"abc"))

    assert asyncio.run(fs.read_file(source)) == b"abc"
    entries = asyncio.run(fs.read_directory(nested))
    assert entries == [ReadDirectoryEntry("a.txt", is_directory=False, is_file=True)]

    metadata = asyncio.run(fs.get_metadata(source))
    assert metadata.is_file
    assert not metadata.is_directory
    assert metadata.modified_at_ms >= metadata.created_at_ms or metadata.created_at_ms >= 0

    asyncio.run(fs.copy(source, copied, CopyOptions(recursive=False)))
    assert copied.read_bytes() == b"abc"

    asyncio.run(fs.remove(copied, RemoveOptions(recursive=False, force=False)))
    assert not copied.exists()
    asyncio.run(fs.remove(copied, RemoveOptions(recursive=False, force=True)))
