import unittest

from pycodex.cli import normalize_for_wsl, win_path_to_wsl


class CliWslPathsTests(unittest.TestCase):
    def test_win_path_to_wsl_basic(self) -> None:
        # Rust parity: codex-cli/src/wsl_paths.rs win_to_wsl_basic.
        self.assertEqual(win_path_to_wsl(r"C:\Temp\codex.zip"), "/mnt/c/Temp/codex.zip")
        self.assertEqual(win_path_to_wsl("D:/Work/codex.tgz"), "/mnt/d/Work/codex.tgz")
        self.assertEqual(win_path_to_wsl("D:\\"), "/mnt/d")
        self.assertIsNone(win_path_to_wsl("/home/user/codex"))
        self.assertIsNone(win_path_to_wsl(r"\\server\share\folder"))
        with self.assertRaisesRegex(TypeError, "path must be a string"):
            win_path_to_wsl(123)  # type: ignore[arg-type]

    def test_normalize_for_wsl_maps_only_when_wsl(self) -> None:
        # Rust parity: codex-cli/src/wsl_paths.rs normalize_for_wsl.
        self.assertEqual(normalize_for_wsl("/home/u/x", wsl=False), "/home/u/x")
        self.assertEqual(normalize_for_wsl(r"C:\Temp\codex.zip", wsl=False), r"C:\Temp\codex.zip")
        self.assertEqual(normalize_for_wsl(r"C:\Temp\codex.zip", wsl=True), "/mnt/c/Temp/codex.zip")
        self.assertEqual(normalize_for_wsl("/home/u/x", wsl=True), "/home/u/x")


if __name__ == "__main__":
    unittest.main()
