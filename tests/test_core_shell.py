from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pycodex.core.shell import (
    Shell,
    ShellType,
    default_user_shell_from_path,
    detect_shell_type,
    get_shell,
    get_shell_by_model_provided_path,
    get_shell_path,
    ultimate_fallback_shell,
)


class ShellTest(unittest.TestCase):
    def test_detect_shell_type_matches_upstream_names_and_stems(self) -> None:
        cases = {
            "zsh": ShellType.ZSH,
            "bash": ShellType.BASH,
            "pwsh": ShellType.POWERSHELL,
            "powershell": ShellType.POWERSHELL,
            "powershell.exe": ShellType.POWERSHELL,
            "pwsh.exe": ShellType.POWERSHELL,
            "/usr/local/bin/pwsh": ShellType.POWERSHELL,
            r"C:\windows\System32\WindowsPowerShell\v1.0\powershell.exe": ShellType.POWERSHELL,
            "/bin/sh": ShellType.SH,
            "sh": ShellType.SH,
            "cmd": ShellType.CMD,
            "cmd.exe": ShellType.CMD,
        }
        for path, shell_type in cases.items():
            with self.subTest(path=path):
                self.assertEqual(detect_shell_type(Path(path)), shell_type)

        self.assertIsNone(detect_shell_type(Path("fish")))
        self.assertIsNone(detect_shell_type(Path("other")))
        self.assertIsNone(detect_shell_type(Path("Bash")))

    def test_shell_names_match_upstream_serialized_names(self) -> None:
        self.assertEqual(Shell(ShellType.ZSH, Path("/bin/zsh")).name(), "zsh")
        self.assertEqual(Shell(ShellType.BASH, Path("/bin/bash")).name(), "bash")
        self.assertEqual(Shell(ShellType.POWERSHELL, Path("pwsh.exe")).name(), "powershell")
        self.assertEqual(Shell(ShellType.SH, Path("/bin/sh")).name(), "sh")
        self.assertEqual(Shell(ShellType.CMD, Path("cmd.exe")).name(), "cmd")

    def test_derive_exec_args(self) -> None:
        bash = Shell(ShellType.BASH, Path("/bin/bash"))
        self.assertEqual(bash.derive_exec_args("echo hello", False), ["/bin/bash", "-c", "echo hello"])
        self.assertEqual(bash.derive_exec_args("echo hello", True), ["/bin/bash", "-lc", "echo hello"])

        zsh = Shell(ShellType.ZSH, Path("/bin/zsh"))
        self.assertEqual(zsh.derive_exec_args("echo hello", False), ["/bin/zsh", "-c", "echo hello"])
        self.assertEqual(zsh.derive_exec_args("echo hello", True), ["/bin/zsh", "-lc", "echo hello"])

        sh = Shell(ShellType.SH, Path("/bin/sh"))
        self.assertEqual(sh.derive_exec_args("echo hello", False), ["/bin/sh", "-c", "echo hello"])
        self.assertEqual(sh.derive_exec_args("echo hello", True), ["/bin/sh", "-lc", "echo hello"])

        powershell = Shell(ShellType.POWERSHELL, Path("pwsh.exe"))
        self.assertEqual(
            powershell.derive_exec_args("echo hello", False),
            ["pwsh.exe", "-NoProfile", "-Command", "echo hello"],
        )
        self.assertEqual(
            powershell.derive_exec_args("echo hello", True),
            ["pwsh.exe", "-Command", "echo hello"],
        )

        cmd = Shell(ShellType.CMD, Path("cmd.exe"))
        self.assertEqual(cmd.derive_exec_args("echo hello", False), ["cmd.exe", "/c", "echo hello"])
        self.assertEqual(cmd.derive_exec_args("echo hello", True), ["cmd.exe", "/c", "echo hello"])

    def test_provided_existing_path_wins_without_executable_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ("custom-shell.exe" if sys.platform == "win32" else "custom-shell")
            path.write_text("", encoding="utf-8")

            self.assertEqual(get_shell_path(ShellType.BASH, path, "definitely-not-a-shell", ()), path)
            shell = get_shell(ShellType.BASH, path)
            self.assertIsNotNone(shell)
            self.assertEqual(shell.shell_path, path)
            self.assertEqual(shell.shell_type, ShellType.BASH)

    def test_model_provided_path_uses_detected_type_or_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bash.exe"
            path.write_text("", encoding="utf-8")

            shell = get_shell_by_model_provided_path(path)
            self.assertEqual(shell.shell_type, ShellType.BASH)
            self.assertEqual(shell.shell_path, path)

        fallback = get_shell_by_model_provided_path(Path("fish"))
        self.assertEqual(fallback, ultimate_fallback_shell())

    def test_default_user_shell_from_path_falls_back_for_unknown_shell(self) -> None:
        shell = default_user_shell_from_path(Path("/bin/fish"))
        if sys.platform == "win32":
            self.assertIn(shell.shell_type, {ShellType.POWERSHELL, ShellType.CMD})
        else:
            self.assertIn(shell.shell_type, {ShellType.BASH, ShellType.ZSH, ShellType.SH})

    def test_ultimate_fallback_shell_can_run_command(self) -> None:
        shell = ultimate_fallback_shell()
        args = shell.derive_exec_args("echo Works", False)
        if shutil.which(args[0]) is None and not Path(args[0]).is_file():
            self.skipTest(f"fallback shell is not executable in this environment: {args[0]}")

        output = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn("Works", output.stdout)


if __name__ == "__main__":
    unittest.main()
