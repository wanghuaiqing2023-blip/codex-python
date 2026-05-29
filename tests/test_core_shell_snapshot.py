from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from pycodex.core import (
    EXCLUDED_EXPORT_VARS,
    SNAPSHOT_DIR,
    SNAPSHOT_RETENTION_SECONDS,
    ShellSnapshot,
    ShellSnapshotError,
    ShellType,
    bash_snapshot_script,
    cleanup_stale_snapshots,
    excluded_exports_regex,
    powershell_snapshot_script,
    sh_snapshot_script,
    shell_snapshot_extension,
    shell_snapshot_paths,
    snapshot_session_id_from_file_name,
    strip_snapshot_preamble,
    write_shell_snapshot,
    zsh_snapshot_script,
)


class ShellSnapshotTests(unittest.TestCase):
    def test_strip_snapshot_preamble_removes_leading_output(self) -> None:
        snapshot = "noise\n# Snapshot file\nexport PATH=/bin\n"

        cleaned = strip_snapshot_preamble(snapshot)

        self.assertEqual(cleaned, "# Snapshot file\nexport PATH=/bin\n")

    def test_strip_snapshot_preamble_requires_marker(self) -> None:
        with self.assertRaisesRegex(ShellSnapshotError, "missing marker # Snapshot file"):
            strip_snapshot_preamble("missing header")

    def test_snapshot_file_name_parser_supports_legacy_and_suffixed_names(self) -> None:
        session_id = "019cf82b-6a62-7700-bbbd-46909794ef89"

        self.assertEqual(snapshot_session_id_from_file_name(f"{session_id}.sh"), session_id)
        self.assertEqual(snapshot_session_id_from_file_name(f"{session_id}.123.sh"), session_id)
        self.assertEqual(snapshot_session_id_from_file_name(f"{session_id}.ps1"), session_id)
        self.assertEqual(snapshot_session_id_from_file_name(f"{session_id}.tmp-123"), session_id)
        self.assertIsNone(snapshot_session_id_from_file_name("not-a-snapshot.txt"))
        self.assertIsNone(snapshot_session_id_from_file_name("missing-extension"))

    def test_shell_snapshot_paths_use_upstream_directory_and_extension(self) -> None:
        final, temp = shell_snapshot_paths(Path("/codex-home"), "thread-1", ShellType.BASH, nonce=123)

        self.assertEqual(final, Path("/codex-home") / SNAPSHOT_DIR / "thread-1.123.sh")
        self.assertEqual(temp, Path("/codex-home") / SNAPSHOT_DIR / "thread-1.tmp-123")
        self.assertEqual(shell_snapshot_extension(ShellType.POWERSHELL), "ps1")
        self.assertEqual(shell_snapshot_extension(ShellType.CMD), "sh")

    def test_snapshot_scripts_replace_excluded_exports_placeholder(self) -> None:
        expected = "|".join(EXCLUDED_EXPORT_VARS)

        self.assertEqual(excluded_exports_regex(), expected)
        for script in (zsh_snapshot_script(), bash_snapshot_script(), sh_snapshot_script()):
            with self.subTest(script=script[:20]):
                self.assertIn(expected, script)
                self.assertNotIn("EXCLUDED_EXPORTS", script)
                self.assertIn("# Snapshot file", script)
                self.assertIn("# exports", script)

    def test_bash_script_preserves_upstream_export_filtering_shape(self) -> None:
        script = bash_snapshot_script()

        self.assertIn('declare -xp "$name" 2>/dev/null || true', script)
        self.assertIn(r'[[ "$name" =~ ^(PWD|OLDPWD)$ ]]', script)
        self.assertIn(r'[[ ! "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]', script)

    def test_powershell_script_matches_upstream_sections(self) -> None:
        script = powershell_snapshot_script()

        self.assertIn("$ErrorActionPreference = 'Stop'", script)
        self.assertIn("Remove-Item Alias:* -ErrorAction SilentlyContinue", script)
        self.assertIn("Get-ChildItem Function:", script)
        self.assertIn("Get-ChildItem Env:", script)

    def test_write_shell_snapshot_rejects_unsupported_shell_types_like_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "snapshot.ps1"
            with self.assertRaisesRegex(ShellSnapshotError, "not supported yet"):
                write_shell_snapshot(ShellType.POWERSHELL, output_path, Path(tmpdir))
            with self.assertRaisesRegex(ShellSnapshotError, "not supported yet"):
                write_shell_snapshot(ShellType.CMD, output_path, Path(tmpdir))

    def test_shell_snapshot_close_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.sh"
            path.write_text("snapshot", encoding="utf-8")
            snapshot = ShellSnapshot(path=path, cwd=Path(tmpdir))

            snapshot.close()

            self.assertFalse(path.exists())


    def test_shell_snapshot_helpers_reject_implicit_coercions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.sh"
            with self.assertRaises(TypeError):
                ShellSnapshot(path=str(path), cwd=Path(tmpdir))
            with self.assertRaises(TypeError):
                shell_snapshot_extension("bash")
            with self.assertRaises(TypeError):
                shell_snapshot_paths(str(Path(tmpdir)), "thread-1", ShellType.BASH, nonce=1)
            with self.assertRaises(TypeError):
                shell_snapshot_paths(Path(tmpdir), 123, ShellType.BASH, nonce=1)
            with self.assertRaises(TypeError):
                shell_snapshot_paths(Path(tmpdir), "thread-1", ShellType.BASH, nonce=True)
            with self.assertRaises(TypeError):
                strip_snapshot_preamble(123)
            with self.assertRaises(TypeError):
                snapshot_session_id_from_file_name(path)
            with self.assertRaises(TypeError):
                cleanup_stale_snapshots(str(Path(tmpdir)), "active")
            with self.assertRaises(TypeError):
                remove_snapshot_file(str(path))

    def test_cleanup_stale_snapshots_removes_orphans_invalid_and_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            snapshot_dir = codex_home / SNAPSHOT_DIR
            snapshot_dir.mkdir()
            now = time.time()
            active_id = str(uuid.uuid4())
            live_id = str(uuid.uuid4())
            orphan_id = str(uuid.uuid4())
            stale_id = str(uuid.uuid4())

            active_snapshot = snapshot_dir / f"{active_id}.123.sh"
            live_snapshot = snapshot_dir / f"{live_id}.123.sh"
            orphan_snapshot = snapshot_dir / f"{orphan_id}.123.sh"
            stale_snapshot = snapshot_dir / f"{stale_id}.123.sh"
            invalid_snapshot = snapshot_dir / "not-a-snapshot.txt"
            for path in (
                active_snapshot,
                live_snapshot,
                orphan_snapshot,
                stale_snapshot,
                invalid_snapshot,
            ):
                path.write_text("snapshot", encoding="utf-8")

            live_rollout = codex_home / "sessions" / "2026" / "05" / "25" / f"rollout-2026-05-25T00-00-00-{live_id}.jsonl"
            stale_rollout = codex_home / "sessions" / "2026" / "05" / "24" / f"rollout-2026-05-24T00-00-00-{stale_id}.jsonl"
            live_rollout.parent.mkdir(parents=True)
            stale_rollout.parent.mkdir(parents=True)
            live_rollout.write_text("", encoding="utf-8")
            stale_rollout.write_text("", encoding="utf-8")
            os.utime(stale_rollout, (now - SNAPSHOT_RETENTION_SECONDS - 60, now - SNAPSHOT_RETENTION_SECONDS - 60))

            rollouts = {live_id: live_rollout, stale_id: stale_rollout}
            removed = cleanup_stale_snapshots(
                codex_home,
                active_id,
                rollout_finder=lambda _home, session_id: rollouts.get(session_id),
                now=now,
            )

            self.assertEqual(set(removed), {orphan_snapshot, stale_snapshot, invalid_snapshot})
            self.assertTrue(active_snapshot.exists())
            self.assertTrue(live_snapshot.exists())
            self.assertFalse(orphan_snapshot.exists())
            self.assertFalse(stale_snapshot.exists())
            self.assertFalse(invalid_snapshot.exists())

    def test_cleanup_stale_snapshots_ignores_missing_snapshot_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            removed = cleanup_stale_snapshots(Path(tmpdir), str(uuid.uuid4()))

            self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
