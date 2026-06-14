"""Parity tests for Rust ``codex-tui::additional_dirs``.

Rust source: ``codex/codex-rs/tui/src/additional_dirs.rs``.
"""

from pycodex.tui.additional_dirs import PermissionProfile, add_dir_warning_message


def test_returns_none_for_workspace_write() -> None:
    profile = PermissionProfile.workspace_write()
    assert add_dir_warning_message(["/tmp/example"], profile, "/tmp/project") is None


def test_returns_none_for_danger_full_access() -> None:
    profile = PermissionProfile.disabled()
    assert add_dir_warning_message(["/tmp/example"], profile, "/tmp/project") is None


def test_returns_none_for_managed_full_disk_write_policy() -> None:
    profile = PermissionProfile.managed(full_disk_write=True)
    assert add_dir_warning_message(["/tmp/example"], profile, "/tmp/project") is None


def test_returns_none_for_external_sandbox() -> None:
    profile = PermissionProfile.external()
    assert add_dir_warning_message(["/tmp/example"], profile, "/tmp/project") is None


def test_warns_for_read_only() -> None:
    profile = PermissionProfile.read_only()
    assert add_dir_warning_message(["relative", "/abs"], profile, "/tmp/project") == (
        "Ignoring --add-dir (relative, /abs) because the effective permissions do not allow "
        "additional writable roots. Switch to workspace-write or danger-full-access to allow them."
    )


def test_warns_when_profile_can_write_elsewhere_but_not_cwd() -> None:
    profile = PermissionProfile.managed(writable_paths=["/tmp/writable"])
    assert add_dir_warning_message(["/tmp/extra"], profile, "/tmp/project") == (
        "Ignoring --add-dir (/tmp/extra) because the effective permissions do not allow "
        "additional writable roots. Switch to workspace-write or danger-full-access to allow them."
    )


def test_returns_none_when_profile_can_write_parent_of_cwd() -> None:
    profile = PermissionProfile.managed(writable_paths=["/tmp"])
    assert add_dir_warning_message(["/tmp/extra"], profile, "/tmp/project") is None


def test_returns_none_when_no_additional_dirs() -> None:
    profile = PermissionProfile.read_only()
    assert add_dir_warning_message([], profile, "/tmp/project") is None
