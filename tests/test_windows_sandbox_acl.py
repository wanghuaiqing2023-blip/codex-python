from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from pycodex.windows_sandbox import (
    LocalSid,
    add_deny_write_ace,
    create_process_as_user_capture,
    create_workspace_write_token_with_caps_from,
    ensure_allow_write_aces,
    get_current_token_for_restriction,
    load_or_create_cap_sids,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows ACL APIs")


def test_workspace_capability_allows_only_granted_root_write() -> None:
    # Rust owners: codex-windows-sandbox::acl::ensure_allow_write_aces and
    # token::create_workspace_write_token_with_caps_from.
    test_root = Path.cwd() / ".tmp"
    test_root.mkdir(exist_ok=True)
    codex_home = Path.home() / ".codex"
    key = str(Path.cwd().resolve()).replace("\\", "/").lower()
    capability_sid = load_or_create_cap_sids(codex_home).workspace_by_cwd.get(key)
    if capability_sid is None:
        pytest.skip("fixed-Rust workspace capability setup is not present")

    root = test_root / f"native-sandbox-acl-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix="native-sandbox-outside-") as outside_dir:
            workspace = root / "workspace"
            outside = Path(outside_dir)
            workspace.mkdir()
            allowed_target = workspace / "allowed.txt"
            denied_target = outside / "denied.txt"

            with LocalSid(capability_sid) as capability:
                # The full setup may already have installed an inherited ACE;
                # ensure_allow_write_aces reports whether it changed the DACL,
                # while the real child below proves effective access.
                ensure_allow_write_aces(workspace, [capability])
                with get_current_token_for_restriction() as base:
                    with create_workspace_write_token_with_caps_from(base, [capability]) as restricted:
                        allowed = create_process_as_user_capture(
                            restricted,
                            ["cmd.exe", "/d", "/c", "echo allowed> allowed.txt"],
                            workspace,
                            os.environ,
                            10_000,
                        )
                        denied = create_process_as_user_capture(
                            restricted,
                            ["cmd.exe", "/d", "/c", f"echo denied> {denied_target}"],
                            workspace,
                            os.environ,
                            10_000,
                        )

            assert allowed.exit_code == 0
            assert allowed_target.read_text(encoding="utf-8").strip() == "allowed"
            assert denied.exit_code != 0
            assert not denied_target.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_deny_write_ace_wins_and_is_not_duplicated() -> None:
    # Rust owner: codex-windows-sandbox::acl::add_deny_write_ace.
    test_root = Path.cwd() / ".tmp"
    test_root.mkdir(exist_ok=True)
    key = str(Path.cwd().resolve()).replace("\\", "/").lower()
    capability_sid = load_or_create_cap_sids(Path.home() / ".codex").workspace_by_cwd.get(key)
    if capability_sid is None:
        pytest.skip("fixed-Rust workspace capability setup is not present")

    root = test_root / f"native-sandbox-deny-{uuid.uuid4().hex}"
    protected = root / "protected"
    root.mkdir()
    protected.mkdir()
    allowed_target = root / "allowed.txt"
    denied_target = protected / "denied.txt"
    try:
        with LocalSid(capability_sid) as capability:
            assert add_deny_write_ace(protected, capability)
            assert not add_deny_write_ace(protected, capability)
            with get_current_token_for_restriction() as base:
                with create_workspace_write_token_with_caps_from(base, [capability]) as restricted:
                    allowed = create_process_as_user_capture(
                        restricted,
                        ["cmd.exe", "/d", "/c", f"echo allowed> {allowed_target}"],
                        root,
                        os.environ,
                        10_000,
                    )
                    denied = create_process_as_user_capture(
                        restricted,
                        ["cmd.exe", "/d", "/c", f"echo denied> {denied_target}"],
                        root,
                        os.environ,
                        10_000,
                    )
        assert allowed.exit_code == 0
        assert allowed_target.exists()
        assert denied.exit_code != 0
        assert not denied_target.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)
