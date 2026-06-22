"""Rust-derived tests for codex-exec-server/src/local_file_system.rs."""

from __future__ import annotations

import asyncio
import os

import pytest

from pycodex.exec_server import (
    CopyOptions,
    CreateDirectoryOptions,
    DirectFileSystem,
    FileMetadata,
    LocalFileSystem,
    ReadDirectoryEntry,
    RemoveOptions,
    UnsandboxedFileSystem,
    current_sandbox_cwd,
    resolve_existing_path,
)


def test_resolve_existing_path_handles_missing_suffix(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::resolve_existing_path
    # Contract: canonicalize the deepest existing parent, then append the
    # unresolved suffix back in order.
    existing = tmp_path / "existing"
    existing.mkdir()

    assert resolve_existing_path(existing / "missing" / "file.txt") == existing.resolve() / "missing" / "file.txt"


def test_resolve_existing_path_handles_symlink_parent_dotdot_escape(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs
    # Test: resolve_existing_path_handles_symlink_parent_dotdot_escape
    # Contract: symlink parents are canonicalized before appending unresolved
    # suffixes, so link/../secret escapes relative to the link target.
    allowed_dir = tmp_path / "allowed"
    outside_dir = tmp_path / "outside"
    allowed_dir.mkdir()
    outside_dir.mkdir()
    link = allowed_dir / "link"
    try:
        os.symlink(outside_dir, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    resolved = resolve_existing_path(link / ".." / "secret.txt")

    assert resolved == resolve_existing_path(tmp_path) / "secret.txt"


def test_direct_file_system_read_write_metadata_and_directory(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::DirectFileSystem
    # Contract: direct filesystem operations reject sandbox contexts and expose
    # read/write/metadata/readDirectory using local filesystem semantics.
    fs = DirectFileSystem()
    target = tmp_path / "dir" / "file.txt"

    asyncio.run(fs.create_directory(target.parent, CreateDirectoryOptions(recursive=True)))
    asyncio.run(fs.write_file(target, b"hello"))

    assert asyncio.run(fs.read_file(target)) == b"hello"
    metadata = asyncio.run(fs.get_metadata(target))
    assert isinstance(metadata, FileMetadata)
    assert metadata.is_file is True
    assert metadata.is_directory is False
    assert metadata.modified_at_ms >= 0
    assert asyncio.run(fs.read_directory(target.parent)) == [
        ReadDirectoryEntry(file_name="file.txt", is_directory=False, is_file=True)
    ]


def test_direct_file_system_create_directory_recursive_matches_rust(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::DirectFileSystem::create_directory
    # Contract: recursive create_dir_all succeeds for already existing
    # directories, while non-recursive create_dir errors if parents are missing.
    fs = DirectFileSystem()
    nested = tmp_path / "a" / "b"

    asyncio.run(fs.create_directory(nested, CreateDirectoryOptions(recursive=True)))
    asyncio.run(fs.create_directory(nested, CreateDirectoryOptions(recursive=True)))
    with pytest.raises(OSError):
        asyncio.run(fs.create_directory(tmp_path / "x" / "y", CreateDirectoryOptions(recursive=False)))


def test_direct_file_system_remove_defaults_are_caller_owned(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::DirectFileSystem::remove
    # Contract: remove honors recursive and force options supplied by callers.
    fs = DirectFileSystem()
    missing = tmp_path / "missing"
    directory = tmp_path / "dir"
    child = directory / "child.txt"
    directory.mkdir()
    child.write_text("x", encoding="utf-8")

    asyncio.run(fs.remove(missing, RemoveOptions(recursive=True, force=True)))
    with pytest.raises(FileNotFoundError):
        asyncio.run(fs.remove(missing, RemoveOptions(recursive=True, force=False)))
    with pytest.raises(OSError):
        asyncio.run(fs.remove(directory, RemoveOptions(recursive=False, force=True)))
    asyncio.run(fs.remove(directory, RemoveOptions(recursive=True, force=True)))
    assert not directory.exists()


def test_direct_file_system_copy_rejects_directory_without_recursive(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::DirectFileSystem::copy
    # Contract: copying a directory requires recursive: true.
    fs = DirectFileSystem()
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError, match="fs/copy requires recursive: true"):
        asyncio.run(fs.copy(source, tmp_path / "target", CopyOptions(recursive=False)))


def test_direct_file_system_copy_rejects_descendant_destination(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::destination_is_same_or_descendant_of_source
    # Contract: recursive directory copies reject copying into the source or a
    # descendant of the source.
    fs = DirectFileSystem()
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError, match="cannot copy a directory to itself"):
        asyncio.run(fs.copy(source, source / "child", CopyOptions(recursive=True)))


def test_unsandboxed_file_system_rejects_platform_sandbox_context(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::reject_platform_sandbox_context
    # Contract: unsandboxed fallback rejects contexts that should run in a
    # configured platform sandbox.
    class Sandbox:
        def should_run_in_sandbox(self) -> bool:
            return True

    fs = UnsandboxedFileSystem()

    with pytest.raises(ValueError, match="sandboxed filesystem operations require configured runtime paths"):
        asyncio.run(fs.read_file(tmp_path / "file", Sandbox()))


def test_local_file_system_delegates_to_unsandboxed_without_sandbox(tmp_path):
    # Rust: codex-exec-server/src/local_file_system.rs::LocalFileSystem::file_system_for
    # Contract: absent a sandbox context, LocalFileSystem delegates to the
    # unsandboxed filesystem.
    fs = LocalFileSystem.unsandboxed()
    target = tmp_path / "file.txt"

    asyncio.run(fs.write_file(target, b"ok"))

    assert asyncio.run(fs.read_file(target)) == b"ok"


def test_current_sandbox_cwd_resolves_existing_cwd():
    # Rust: codex-exec-server/src/local_file_system.rs::current_sandbox_cwd
    # Contract: current cwd is resolved through resolve_existing_path.
    assert current_sandbox_cwd() == resolve_existing_path(os.getcwd())
