import os
import unittest

from pycodex.shell_command.command_safety import (
    command_might_be_dangerous,
    executable_name_lookup_key,
    find_git_subcommand,
    is_known_safe_command,
    is_safe_git_command,
    is_safe_powershell_words,
    is_safe_to_call_with_exec,
)


class ShellCommandSafetyTests(unittest.TestCase):
    def test_known_safe_exec_examples(self):
        self.assertTrue(is_safe_to_call_with_exec(["ls"]))
        self.assertTrue(is_safe_to_call_with_exec(["git", "status"]))
        self.assertTrue(is_safe_to_call_with_exec(["git", "branch"]))
        self.assertTrue(is_safe_to_call_with_exec(["git", "branch", "--show-current"]))
        self.assertTrue(is_safe_to_call_with_exec(["base64"]))
        self.assertTrue(is_safe_to_call_with_exec(["sed", "-n", "1,5p", "file.txt"]))
        self.assertTrue(is_safe_to_call_with_exec(["find", ".", "-name", "file.txt"]))

    def test_unsafe_exec_examples(self):
        self.assertFalse(is_safe_to_call_with_exec(["cargo", "check"]))
        self.assertFalse(is_safe_to_call_with_exec(["git", "fetch"]))
        self.assertFalse(is_safe_to_call_with_exec(["sed", "-n", "xp", "file.txt"]))
        self.assertFalse(is_safe_to_call_with_exec(["find", ".", "-delete", "-name", "file.txt"]))
        self.assertFalse(is_safe_to_call_with_exec(["find", ".", "-exec", "rm", "{}", ";"]))
        self.assertFalse(is_safe_to_call_with_exec(["base64", "--output=out.bin"]))
        self.assertFalse(is_safe_to_call_with_exec(["base64", "-ob64.txt"]))
        self.assertFalse(is_safe_to_call_with_exec(["rg", "--search-zip", "files"]))
        self.assertFalse(is_safe_to_call_with_exec(["rg", "--pre=cat", "files"]))

    def test_git_global_and_subcommand_safety_rules(self):
        self.assertEqual(find_git_subcommand(["git", "-C", ".", "status"], ["status"]), (3, "status"))
        self.assertFalse(is_safe_git_command(["git", "-C", ".", "status"]))
        self.assertFalse(is_known_safe_command(["git", "--paginate", "log", "-1"]))
        self.assertFalse(is_known_safe_command(["git", "diff", "--output", "/tmp/out"]))
        self.assertTrue(is_known_safe_command(["git", "log", "-p", "-1"]))
        self.assertTrue(is_known_safe_command(["git", "diff", "-p"]))
        self.assertFalse(is_known_safe_command(["git", "branch", "-d", "feature"]))
        self.assertFalse(is_known_safe_command(["git", "branch", "new-branch"]))

    def test_bash_lc_safe_and_unsafe_sequences(self):
        self.assertTrue(is_known_safe_command(["bash", "-lc", "ls"]))
        self.assertTrue(is_known_safe_command(["zsh", "-lc", "ls"]))
        self.assertTrue(is_known_safe_command(["bash", "-lc", "grep -R 'Cargo.toml' -n || true"]))
        self.assertTrue(is_known_safe_command(["bash", "-lc", "ls | wc -l"]))

        self.assertFalse(is_known_safe_command(["bash", "-lc", "git", "status"]))
        self.assertFalse(is_known_safe_command(["bash", "-lc", "'git status'"]))
        self.assertFalse(is_known_safe_command(["bash", "-lc", "find . -name file.txt -delete"]))
        self.assertFalse(is_known_safe_command(["bash", "-lc", "ls && rm -rf /"]))
        self.assertFalse(is_known_safe_command(["bash", "-lc", "(ls)"]))
        self.assertFalse(is_known_safe_command(["bash", "-lc", "ls > out.txt"]))

    def test_dangerous_command_detection(self):
        self.assertTrue(command_might_be_dangerous(["rm", "-rf", "/"]))
        self.assertTrue(command_might_be_dangerous(["sudo", "rm", "-f", "/tmp/file"]))
        self.assertTrue(command_might_be_dangerous(["bash", "-lc", "ls && rm -rf /"]))
        self.assertFalse(command_might_be_dangerous(["rm", "-r", "/tmp/file"]))
        self.assertFalse(command_might_be_dangerous(["git", "status"]))

    def test_windows_dangerous_heuristics_are_platform_independent(self):
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Start-Process 'https://example.com'"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "echo hi&del /f file.txt"]))
        self.assertTrue(command_might_be_dangerous(["msedge.exe", "https://example.com"]))
        self.assertFalse(command_might_be_dangerous(["powershell", "-Command", "Start-Process notepad.exe"]))
        self.assertFalse(command_might_be_dangerous(["cmd", "/c", "echo", "del", "/f"]))

    def test_windows_powershell_safelist_matches_platform_cfg(self):
        expected = os.name == "nt"
        self.assertEqual(is_safe_powershell_words(["Get-Content", "Cargo.toml"]), expected)
        self.assertEqual(
            is_known_safe_command(["powershell.exe", "-NoProfile", "-Command", "Get-ChildItem -Path ."]),
            expected,
        )
        self.assertFalse(is_known_safe_command(["powershell.exe", "-Command", "Remove-Item foo.txt"]))

    def test_executable_name_lookup_key_uses_windows_suffix_rules_on_windows(self):
        if os.name == "nt":
            self.assertEqual(executable_name_lookup_key(r"C:\Program Files\Git\cmd\git.exe"), "git")
        else:
            self.assertEqual(executable_name_lookup_key("/usr/bin/git"), "git")


if __name__ == "__main__":
    unittest.main()
