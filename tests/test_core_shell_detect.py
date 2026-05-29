import unittest
from pathlib import PurePosixPath, PureWindowsPath

from pycodex.core.shell import ShellType
from pycodex.core.shell_detect import detect_shell_type


class ShellDetectTests(unittest.TestCase):
    def test_detects_bare_shell_names(self) -> None:
        self.assertEqual(detect_shell_type("zsh"), ShellType.ZSH)
        self.assertEqual(detect_shell_type("sh"), ShellType.SH)
        self.assertEqual(detect_shell_type("cmd"), ShellType.CMD)
        self.assertEqual(detect_shell_type("bash"), ShellType.BASH)
        self.assertEqual(detect_shell_type("pwsh"), ShellType.POWERSHELL)
        self.assertEqual(detect_shell_type("powershell"), ShellType.POWERSHELL)

    def test_detects_shells_from_paths_and_extensions(self) -> None:
        self.assertEqual(detect_shell_type(PurePosixPath("/bin/bash")), ShellType.BASH)
        self.assertEqual(detect_shell_type(PurePosixPath("/usr/local/bin/zsh")), ShellType.ZSH)
        self.assertEqual(detect_shell_type(PureWindowsPath(r"C:\Windows\System32\cmd.exe")), ShellType.CMD)
        self.assertEqual(detect_shell_type(PureWindowsPath(r"C:\Program Files\PowerShell\7\pwsh.exe")), ShellType.POWERSHELL)
        self.assertEqual(detect_shell_type("powershell.exe"), ShellType.POWERSHELL)

    def test_unknown_shell_returns_none(self) -> None:
        self.assertIsNone(detect_shell_type("fish"))
        self.assertIsNone(detect_shell_type(PurePosixPath("/usr/bin/python3")))

    def test_rejects_non_path_inputs(self) -> None:
        with self.assertRaises(TypeError):
            detect_shell_type(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
