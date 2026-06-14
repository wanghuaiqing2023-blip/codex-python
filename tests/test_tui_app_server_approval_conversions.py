"""Parity tests for ``codex-tui/src/app_server_approval_conversions.rs``."""

from pathlib import Path

import pytest

from pycodex.protocol.models import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    NetworkPermissions,
)
from pycodex.protocol.request_permissions import RequestPermissionProfile
from pycodex.tui.app_server_approval_conversions import (
    AdditionalNetworkPermissions,
    FileUpdateChange,
    GrantedPermissionProfile,
    PatchChangeKind,
    absolute_path,
    file_update_changes_to_display,
    granted_permission_profile_from_request,
)
from pycodex.tui.diff_model import FileChange


def test_converts_file_update_changes_to_display_add() -> None:
    # Rust: converts_file_update_changes_to_display
    assert file_update_changes_to_display([
        FileUpdateChange(path="foo.txt", kind=PatchChangeKind.ADD, diff="hello\n")
    ]) == {Path("foo.txt"): FileChange.add("hello\n")}


def test_converts_file_update_changes_to_display_delete_and_update() -> None:
    # Rust source: Add/Delete/Update map to FileChange variants.
    changes = [
        FileUpdateChange(path="gone.txt", kind=PatchChangeKind.DELETE, diff="old\n"),
        FileUpdateChange(path="edit.txt", kind={"type": "update", "move_path": "moved.txt"}, diff="@@\n"),
    ]
    assert file_update_changes_to_display(changes) == {
        Path("gone.txt"): FileChange.delete("old\n"),
        Path("edit.txt"): FileChange.update("@@\n", "moved.txt"),
    }


def test_converts_request_permissions_into_granted_permissions() -> None:
    # Rust: converts_request_permissions_into_granted_permissions
    file_system = FileSystemPermissions.from_read_write_roots(
        read=[absolute_path("/tmp/read-only")],
        write=[absolute_path("/tmp/write")],
    )
    request = RequestPermissionProfile(
        network=NetworkPermissions(enabled=True),
        file_system=file_system,
    )

    assert granted_permission_profile_from_request(request) == GrantedPermissionProfile(
        network=AdditionalNetworkPermissions(enabled=True),
        file_system=file_system,
    )


def test_converts_request_permissions_into_canonical_granted_permissions() -> None:
    # Rust: converts_request_permissions_into_canonical_granted_permissions
    root_entry = FileSystemSandboxEntry(
        path=FileSystemPath.special("root"),
        access=FileSystemAccessMode.WRITE,
    )
    file_system = FileSystemPermissions(entries=(root_entry,))
    request = RequestPermissionProfile(network=None, file_system=file_system)

    assert granted_permission_profile_from_request(request) == GrantedPermissionProfile(
        network=None,
        file_system=file_system,
    )


def test_conversions_accept_mapping_payloads() -> None:
    # Source contract: conversion reads only narrow payload fields.
    granted = granted_permission_profile_from_request({"network": {"enabled": False}, "file_system": {"entries": []}})
    assert granted.network == AdditionalNetworkPermissions(enabled=False)
    assert granted.file_system == {"entries": []}

    changes = [{"path": "x.txt", "kind": "update", "diff": "diff"}]
    assert file_update_changes_to_display(changes) == {Path("x.txt"): FileChange.update("diff")}


def test_rejects_unknown_patch_kind_and_relative_absolute_path_helper() -> None:
    # Rust helper absolute_path panics on non-absolute paths; Python raises ValueError.
    with pytest.raises(ValueError):
        absolute_path("relative/path")
    with pytest.raises(ValueError):
        file_update_changes_to_display([FileUpdateChange(path="x", kind="rename", diff="d")])
