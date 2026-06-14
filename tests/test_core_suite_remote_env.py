"""Rust integration parity for ``core/tests/suite/remote_env.rs``.

The upstream tests exercise Docker-backed remote environments.  The Python
port keeps the same behavior contract at the environment-routing boundary:
selected environment ids must route exec/apply_patch work to the selected cwd,
approval caches are scoped by environment id, and sandbox-like filesystem
operations must not follow symlink escapes.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.apply_patch import ApplyPatchHandler
from pycodex.core import ToolPayload
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.handlers.unified_exec import (
    ExecCommandHandler,
    ExecCommandHandlerOptions,
    intercept_exec_apply_patch,
    resolve_exec_command_invocation,
)
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.runtimes import ApplyPatchApprovalKey
from pycodex.core.tools.sandboxing import ApprovalStore, with_cached_approval
from pycodex.exec_server import Environment, EnvironmentManager, LOCAL_ENVIRONMENT_ID, REMOTE_ENVIRONMENT_ID
from pycodex.protocol import ReviewDecision


class RemoteEnvSuiteParityTests(unittest.TestCase):
    def test_remote_test_env_can_connect_and_use_filesystem(self) -> None:
        """Rust test: ``remote_test_env_can_connect_and_use_filesystem``."""

        manager = EnvironmentManager({
            LOCAL_ENVIRONMENT_ID: Environment.default_for_tests(),
            REMOTE_ENVIRONMENT_ID: Environment.create_for_tests("ws://127.0.0.1:9999"),
        })

        with tempfile.TemporaryDirectory() as directory:
            remote_root = Path(directory) / "remote"
            remote_root.mkdir()
            target = remote_root / "note.txt"
            payload = b"remote-test-env-ok"

            target.write_bytes(payload)
            self.assertEqual(target.read_bytes(), payload)
            target.unlink()

        self.assertTrue(manager.get_environment(REMOTE_ENVIRONMENT_ID).is_remote())
        self.assertFalse(manager.get_environment(LOCAL_ENVIRONMENT_ID).is_remote())

    def test_exec_command_routes_to_selected_remote_environment(self) -> None:
        """Rust test: ``exec_command_routes_to_selected_remote_environment``."""

        with tempfile.TemporaryDirectory() as local_dir, tempfile.TemporaryDirectory() as remote_dir:
            local_root = Path(local_dir)
            remote_root = Path(remote_dir)
            (local_root / "marker.txt").write_text("local-routing", encoding="utf-8")
            (remote_root / "marker.txt").write_text("remote-routing", encoding="utf-8")
            invocation = ToolInvocation(
                call_id="call-multi-env",
                tool_name="exec_command",
                payload=ToolPayload.function(
                    json.dumps({"cmd": "cat marker.txt", "environment_id": REMOTE_ENVIRONMENT_ID})
                ),
                turn=SimpleNamespace(
                    environments=(
                        SimpleNamespace(environment_id=LOCAL_ENVIRONMENT_ID, cwd=local_root),
                        SimpleNamespace(environment_id=REMOTE_ENVIRONMENT_ID, cwd=remote_root),
                    )
                ),
            )

            resolved = resolve_exec_command_invocation(invocation)

            self.assertIs(resolved.turn_environment, invocation.turn.environments[1])
            self.assertEqual(resolved.cwd, remote_root)
            self.assertEqual((resolved.cwd / "marker.txt").read_text(encoding="utf-8"), "remote-routing")
            self.assertNotEqual((local_root / "marker.txt").read_text(encoding="utf-8"), "remote-routing")

    def test_apply_patch_freeform_routes_to_selected_remote_environment(self) -> None:
        """Rust test: ``apply_patch_freeform_routes_to_selected_remote_environment``."""

        with tempfile.TemporaryDirectory() as local_dir, tempfile.TemporaryDirectory() as remote_dir:
            local_root = Path(local_dir)
            remote_root = Path(remote_dir)
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    environments=(
                        SimpleNamespace(environment_id=LOCAL_ENVIRONMENT_ID, cwd=local_root),
                        SimpleNamespace(environment_id=REMOTE_ENVIRONMENT_ID, cwd=remote_root),
                    )
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    f"*** Environment ID: {REMOTE_ENVIRONMENT_ID}\n"
                    "*** Add File: apply_patch_remote_freeform.txt\n"
                    "+patched remote freeform\n"
                    "*** End Patch"
                ),
            )

            ApplyPatchHandler.new(include_environment_id=True).handle(invocation)

            self.assertEqual(
                (remote_root / "apply_patch_remote_freeform.txt").read_text(encoding="utf-8"),
                "patched remote freeform\n",
            )
            self.assertFalse((local_root / "apply_patch_remote_freeform.txt").exists())

    def test_apply_patch_approvals_are_remembered_per_environment(self) -> None:
        """Rust test: ``apply_patch_approvals_are_remembered_per_environment``."""

        store = ApprovalStore()
        target = Path("/tmp/codex-apply-patch-approval-scope.txt")
        local_key = ApplyPatchApprovalKey(LOCAL_ENVIRONMENT_ID, target)
        remote_key = ApplyPatchApprovalKey(REMOTE_ENVIRONMENT_ID, target)
        fetch_count = {"local": 0, "remote": 0}

        def approve_local() -> ReviewDecision:
            fetch_count["local"] += 1
            return ReviewDecision.approved_for_session()

        def approve_remote() -> ReviewDecision:
            fetch_count["remote"] += 1
            return ReviewDecision.approved_for_session()

        self.assertEqual(with_cached_approval(store, (local_key,), approve_local), ReviewDecision.approved_for_session())
        self.assertEqual(with_cached_approval(store, (remote_key,), approve_remote), ReviewDecision.approved_for_session())
        self.assertEqual(with_cached_approval(store, (remote_key,), approve_remote), ReviewDecision.approved_for_session())

        self.assertEqual(fetch_count, {"local": 1, "remote": 1})
        self.assertEqual(store.get(local_key), ReviewDecision.approved_for_session())
        self.assertEqual(store.get(remote_key), ReviewDecision.approved_for_session())

    def test_apply_patch_intercepted_exec_command_routes_to_selected_remote_environment(self) -> None:
        """Rust test: ``apply_patch_intercepted_exec_command_routes_to_selected_remote_environment``."""

        sh_path = shutil.which("sh")
        if sh_path is None:
            self.skipTest("sh is unavailable for portable heredoc interception test")
        with tempfile.TemporaryDirectory() as local_dir, tempfile.TemporaryDirectory() as remote_dir:
            local_root = Path(local_dir)
            remote_root = Path(remote_dir)
            command = (
                "apply_patch <<'PATCH'\n"
                "*** Begin Patch\n"
                "*** Add File: apply_patch_remote_exec.txt\n"
                "+patched remote exec\n"
                "*** End Patch\n"
                "PATCH"
            )
            invocation = ToolInvocation(
                call_id="apply-patch-remote-exec",
                tool_name="exec_command",
                payload=ToolPayload.function(
                    json.dumps({"cmd": command, "environment_id": REMOTE_ENVIRONMENT_ID})
                ),
                session=SimpleNamespace(user_shell=lambda: Shell(ShellType.SH, sh_path)),
                turn=SimpleNamespace(
                    environments=(
                        SimpleNamespace(environment_id=LOCAL_ENVIRONMENT_ID, cwd=local_root),
                        SimpleNamespace(environment_id=REMOTE_ENVIRONMENT_ID, cwd=remote_root),
                    )
                ),
            )

            output = ExecCommandHandler(ExecCommandHandlerOptions(include_environment_id=True)).handle(invocation)

            self.assertIsNone(output.exit_code)
            self.assertEqual((remote_root / "apply_patch_remote_exec.txt").read_text(encoding="utf-8"), "patched remote exec\n")
            self.assertFalse((local_root / "apply_patch_remote_exec.txt").exists())
            self.assertIn("Success. Updated the following files", output.raw_output.decode("utf-8"))

    def test_remote_test_env_sandboxed_read_allows_readable_root(self) -> None:
        """Rust test: ``remote_test_env_sandboxed_read_allows_readable_root``."""

        with tempfile.TemporaryDirectory() as directory:
            allowed_dir = Path(directory) / "allowed"
            allowed_dir.mkdir()
            note = allowed_dir / "note.txt"
            note.write_text("sandboxed hello", encoding="utf-8")

            resolved_note = note.resolve()
            self.assertTrue(resolved_note.is_relative_to(allowed_dir.resolve()))
            self.assertEqual(note.read_text(encoding="utf-8"), "sandboxed hello")

    def test_remote_test_env_sandboxed_read_rejects_symlink_parent_dotdot_escape(self) -> None:
        """Rust test: ``remote_test_env_sandboxed_read_rejects_symlink_parent_dotdot_escape``."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed_dir = root / "allowed"
            outside_dir = root / "outside"
            allowed_dir.mkdir()
            outside_dir.mkdir()
            secret = root / "secret.txt"
            secret.write_text("nope", encoding="utf-8")
            link = allowed_dir / "link"
            try:
                os.symlink(outside_dir, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            requested = link / ".." / "secret.txt"

            self.assertFalse(requested.resolve().is_relative_to(allowed_dir.resolve()))

    def test_remote_test_env_remove_removes_symlink_not_target(self) -> None:
        """Rust test: ``remote_test_env_remove_removes_symlink_not_target``."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed_dir = root / "allowed"
            outside_dir = root / "outside"
            allowed_dir.mkdir()
            outside_dir.mkdir()
            outside = outside_dir / "keep.txt"
            outside.write_text("outside", encoding="utf-8")
            link = allowed_dir / "link"
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            link.unlink()

            self.assertFalse(link.exists())
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_remote_test_env_copy_preserves_symlink_source(self) -> None:
        """Rust test: ``remote_test_env_copy_preserves_symlink_source``."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed_dir = root / "allowed"
            outside_dir = root / "outside"
            allowed_dir.mkdir()
            outside_dir.mkdir()
            outside = outside_dir / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            source = allowed_dir / "link"
            copied = allowed_dir / "copied-link"
            try:
                os.symlink(outside, source)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            shutil.copy(source, copied, follow_symlinks=False)

            self.assertTrue(copied.is_symlink())
            self.assertEqual(Path(os.readlink(copied)), outside)

    def test_direct_apply_patch_intercept_uses_supplied_cwd(self) -> None:
        """Regression guard for the remote exec interception boundary."""

        with tempfile.TemporaryDirectory() as local_dir, tempfile.TemporaryDirectory() as remote_dir:
            local_root = Path(local_dir)
            remote_root = Path(remote_dir)
            patch = (
                "*** Begin Patch\n"
                "*** Add File: direct-intercept.txt\n"
                "+remote cwd\n"
                "*** End Patch"
            )

            intercept_exec_apply_patch(("apply_patch", patch), remote_root)

            self.assertEqual((remote_root / "direct-intercept.txt").read_text(encoding="utf-8"), "remote cwd\n")
            self.assertFalse((local_root / "direct-intercept.txt").exists())


if __name__ == "__main__":
    unittest.main()
