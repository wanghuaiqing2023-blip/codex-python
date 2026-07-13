from pathlib import Path
from unittest.mock import patch

from pycodex.windows_sandbox.deny_read_state import (
    apply_deny_read_acls,
    plan_deny_read_acl_paths,
    sync_persistent_deny_read_acls,
)


def test_plan_preserves_missing_policy_path(tmp_path: Path) -> None:
    # Rust source: windows-sandbox-rs/src/deny_read_acl.rs
    missing = tmp_path / "future-secret"

    assert plan_deny_read_acl_paths((missing,)) == (missing,)


def test_apply_materializes_missing_path_before_adding_ace(tmp_path: Path) -> None:
    # Rust source: deny_read_acl::apply_deny_read_acls.
    missing = tmp_path / "future-secret"
    with patch("pycodex.windows_sandbox.deny_read_state.add_deny_read_ace", return_value=True) as add:
        applied = apply_deny_read_acls((missing,), 123)

    assert missing.is_dir()
    assert applied == (missing,)
    add.assert_called_once_with(missing, 123)


def test_sync_revokes_stale_paths_for_same_principal(tmp_path: Path) -> None:
    # Rust source: windows-sandbox-rs/src/deny_read_state.rs.
    old = tmp_path / "old-secret"
    new = tmp_path / "new-secret"
    with (
        patch("pycodex.windows_sandbox.deny_read_state.add_deny_read_ace", return_value=True),
        patch("pycodex.windows_sandbox.deny_read_state.revoke_ace", return_value=True) as revoke,
    ):
        sync_persistent_deny_read_acls(tmp_path, "S-1-test", (old,), 123)
        sync_persistent_deny_read_acls(tmp_path, "S-1-test", (new,), 123)

    revoke.assert_called_with(old, 123)
