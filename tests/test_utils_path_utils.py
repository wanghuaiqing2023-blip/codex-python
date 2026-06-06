from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from pycodex.utils.path_utils import (
    SymlinkWritePaths,
    is_wsl,
    normalize_for_native_workdir_with_flag,
    normalize_for_wsl_with_flag,
    paths_match_after_normalization,
    resolve_symlink_write_paths,
    write_atomically,
)


class PathUtilsTests(unittest.TestCase):
    def test_wsl_mnt_drive_paths_lowercase(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
        # Rust crate: codex-utils-path-utils
        # Rust test: wsl::wsl_mnt_drive_paths_lowercase
        # Contract: WSL mounted Windows drive paths are ASCII-lowercased.
        normalized = normalize_for_wsl_with_flag(Path("/mnt/C/Users/Dev"), True, is_linux=True)

        self.assertEqual(normalized, Path("/mnt/c/users/dev"))

    def test_wsl_non_drive_paths_unchanged(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
        # Rust tests: wsl_non_drive_paths_unchanged, wsl_non_mnt_paths_unchanged
        path = Path("/mnt/cc/Users/Dev")
        self.assertEqual(normalize_for_wsl_with_flag(path, True, is_linux=True), path)
        home = Path("/home/Dev")
        self.assertEqual(normalize_for_wsl_with_flag(home, True, is_linux=True), home)

    def test_non_windows_native_workdir_paths_are_unchanged(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
        # Rust test: native_workdir::non_windows_paths_are_unchanged
        path = Path(r"\\?\D:\c\x\worktrees\2508\swift-base")

        self.assertEqual(normalize_for_native_workdir_with_flag(path, False), path)

    def test_windows_native_workdir_verbatim_paths_are_simplified(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
        # Rust test: native_workdir::windows_verbatim_paths_are_simplified
        path = Path(r"\\?\D:\c\x\worktrees\2508\swift-base")

        self.assertEqual(
            normalize_for_native_workdir_with_flag(path, True),
            Path(r"D:\c\x\worktrees\2508\swift-base"),
        )

    def test_paths_match_identical_existing_paths(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
        # Rust test: path_comparison::matches_identical_existing_paths
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            self.assertTrue(paths_match_after_normalization(path, path))

    def test_paths_match_falls_back_to_raw_equality(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
        # Rust test: path_comparison::falls_back_to_raw_equality_when_paths_cannot_be_normalized
        self.assertTrue(paths_match_after_normalization(Path("missing"), Path("missing")))
        self.assertFalse(paths_match_after_normalization(Path("missing-a"), Path("missing-b")))

    @unittest.skipUnless(os.name == "posix", "Rust symlink cycle test is cfg(unix)")
    def test_symlink_cycles_fall_back_to_root_write_path(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
        # Rust test: symlinks::symlink_cycles_fall_back_to_root_write_path
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            a = root / "a"
            b = root / "b"
            os.symlink(b, a)
            os.symlink(a, b)

            resolved = resolve_symlink_write_paths(a)

        self.assertEqual(resolved, SymlinkWritePaths(read_path=None, write_path=a))

    def test_resolve_symlink_write_paths_returns_missing_path_for_read_and_write(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/lib.rs
        # Contract: missing target returns read_path=Some(current) and write_path=current.
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing.txt"

            resolved = resolve_symlink_write_paths(missing)

        self.assertEqual(resolved, SymlinkWritePaths(read_path=missing, write_path=missing))

    def test_write_atomically_creates_parent_and_replaces_contents(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/lib.rs
        # Contract: write_atomically creates the parent directory and persists contents.
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "file.txt"

            write_atomically(path, "first")
            write_atomically(path, "second")

            self.assertEqual(path.read_text(encoding="utf-8"), "second")

    def test_is_wsl_uses_linux_env_then_proc_version(self) -> None:
        # Source: codex/codex-rs/utils/path-utils/src/env.rs
        # Contract: Linux WSL detection checks WSL_DISTRO_NAME before /proc/version.
        with tempfile.TemporaryDirectory() as tmpdir:
            version = Path(tmpdir) / "version"
            version.write_text("Linux version Microsoft", encoding="utf-8")

            self.assertTrue(is_wsl(env={"WSL_DISTRO_NAME": "Ubuntu"}, platform="linux"))
            self.assertTrue(is_wsl(env={}, proc_version_path=version, platform="linux"))
            self.assertFalse(is_wsl(env={"WSL_DISTRO_NAME": "Ubuntu"}, platform="win32"))


if __name__ == "__main__":
    unittest.main()
