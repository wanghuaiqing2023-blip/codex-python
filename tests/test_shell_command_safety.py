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
from pycodex.shell_command.powershell_parser import (
    PowershellParseKind,
    PowershellParserResponse,
    encode_powershell_base64,
    parse_with_powershell_ast,
    try_parse_powershell_ast_commands,
)


class ShellCommandSafetyTests(unittest.TestCase):
    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/is_safe_command.rs
    # Rust test: tests::known_safe_examples
    # Contract: shell.command_safety
    def test_known_safe_exec_examples(self):
        self.assertTrue(is_safe_to_call_with_exec(["ls"]))
        self.assertTrue(is_safe_to_call_with_exec(["git", "status"]))
        self.assertTrue(is_safe_to_call_with_exec(["git", "branch"]))
        self.assertTrue(is_safe_to_call_with_exec(["git", "branch", "--show-current"]))
        self.assertTrue(is_safe_to_call_with_exec(["base64"]))
        self.assertTrue(is_safe_to_call_with_exec(["sed", "-n", "1,5p", "file.txt"]))
        self.assertTrue(is_safe_to_call_with_exec(["nl", "-nrz", "Cargo.toml"]))
        self.assertTrue(is_safe_to_call_with_exec(["find", ".", "-name", "file.txt"]))
        self.assertEqual(is_safe_to_call_with_exec(["numfmt", "1000"]), os.name == "posix")
        self.assertEqual(is_safe_to_call_with_exec(["tac", "Cargo.toml"]), os.name == "posix")

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/is_safe_command.rs
    # Rust tests: tests::cargo_check_is_not_safe; tests::unknown_or_partial; tests::base64_output_options_are_unsafe; tests::ripgrep_rules
    # Contract: shell.command_safety
    def test_unsafe_exec_examples(self):
        self.assertFalse(is_safe_to_call_with_exec(["cargo", "check"]))
        self.assertFalse(is_safe_to_call_with_exec(["git", "fetch"]))
        self.assertFalse(is_safe_to_call_with_exec(["sed", "-n", "xp", "file.txt"]))
        self.assertFalse(is_safe_to_call_with_exec(["find", ".", "-delete", "-name", "file.txt"]))
        self.assertFalse(is_safe_to_call_with_exec(["find", ".", "-exec", "rm", "{}", ";"]))
        self.assertFalse(is_safe_to_call_with_exec(["base64", "-o", "out.bin"]))
        self.assertFalse(is_safe_to_call_with_exec(["base64", "--output", "out.bin"]))
        self.assertFalse(is_safe_to_call_with_exec(["base64", "--output=out.bin"]))
        self.assertFalse(is_safe_to_call_with_exec(["base64", "-ob64.txt"]))
        self.assertFalse(is_safe_to_call_with_exec(["rg", "--search-zip", "files"]))
        self.assertFalse(is_safe_to_call_with_exec(["rg", "--pre", "cat", "files"]))
        self.assertFalse(is_safe_to_call_with_exec(["rg", "--pre=cat", "files"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/is_safe_command.rs
    # Rust tests: tests::git_branch_mutating_flags_are_not_safe; tests::git_first_positional_is_the_subcommand; tests::git_output_flags_are_not_safe; tests::git_global_pagination_flags_are_not_safe; tests::git_subcommand_patch_flags_remain_safe; tests::git_global_override_flags_are_not_safe
    # Contract: shell.command_safety
    def test_git_global_and_subcommand_safety_rules(self):
        self.assertEqual(find_git_subcommand(["git", "-C", ".", "status"], ["status"]), (3, "status"))
        self.assertFalse(is_safe_git_command(["git", "-C", ".", "status"]))
        self.assertFalse(is_known_safe_command(["git", "--paginate", "log", "-1"]))
        self.assertFalse(is_known_safe_command(["git", "checkout", "status"]))
        self.assertFalse(is_known_safe_command(["git", "diff", "--output", "/tmp/out"]))
        self.assertFalse(is_known_safe_command(["git", "--config-env=core.pager=PAGER", "show", "HEAD"]))
        self.assertFalse(is_known_safe_command(["git", "--git-dir=.evil-git", "diff", "HEAD~1..HEAD"]))
        self.assertTrue(is_known_safe_command(["git", "log", "-p", "-1"]))
        self.assertTrue(is_known_safe_command(["git", "diff", "-p"]))
        self.assertFalse(is_known_safe_command(["git", "branch", "-d", "feature"]))
        self.assertFalse(is_known_safe_command(["git", "branch", "new-branch"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/is_safe_command.rs
    # Rust tests: tests::bash_lc_safe_examples; tests::bash_lc_safe_examples_with_operators; tests::bash_lc_unsafe_examples
    # Contract: shell.command_safety
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

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/is_dangerous_command.rs
    # Rust tests: tests::rm_rf_is_dangerous; tests::rm_f_is_dangerous
    # Contract: shell.dangerous_command
    def test_dangerous_command_detection(self):
        self.assertTrue(command_might_be_dangerous(["rm", "-rf", "/"]))
        self.assertTrue(command_might_be_dangerous(["rm", "-f", "/"]))
        self.assertTrue(command_might_be_dangerous(["sudo", "rm", "-f", "/tmp/file"]))
        self.assertTrue(command_might_be_dangerous(["bash", "-lc", "ls && rm -rf /"]))
        self.assertFalse(command_might_be_dangerous(["rm", "-r", "/tmp/file"]))
        self.assertFalse(command_might_be_dangerous(["git", "status"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_dangerous_commands.rs
    # Rust tests: tests::powershell_start_process_url_is_dangerous; tests::powershell_start_process_url_with_trailing_semicolon_is_dangerous; tests::cmd_start_with_url_is_dangerous; tests::msedge_with_url_is_dangerous; tests::explorer_with_directory_is_not_flagged; tests::powershell_start_process_local_is_not_flagged; tests::cmd_echo_del_is_not_dangerous
    # Contract: shell.powershell_safety
    def test_windows_dangerous_heuristics_are_platform_independent(self):
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Start-Process 'https://example.com'"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Start-Process('https://example.com');"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "start", "https://example.com"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "echo hi&del /f file.txt"]))
        self.assertTrue(command_might_be_dangerous(["msedge.exe", "https://example.com"]))
        self.assertTrue(command_might_be_dangerous(["chrome.exe", "https://example.com"]))
        self.assertTrue(command_might_be_dangerous(["firefox.exe", "https://example.com"]))
        self.assertTrue(command_might_be_dangerous(["explorer.exe", "https://example.com"]))
        self.assertTrue(command_might_be_dangerous(["mshta.exe", "https://example.com"]))
        self.assertTrue(command_might_be_dangerous(["rundll32.exe", "url.dll,FileProtocolHandler", "https://example.com"]))
        self.assertFalse(command_might_be_dangerous(["explorer.exe", "."]))
        self.assertFalse(command_might_be_dangerous(["powershell", "-Command", "Start-Process notepad.exe"]))
        self.assertFalse(command_might_be_dangerous(["cmd", "/c", "echo", "del", "/f"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_dangerous_commands.rs
    # Rust tests: tests::cmd_start_url_single_string_is_dangerous; tests::cmd_start_quoted_url_single_string_is_dangerous; tests::cmd_start_title_then_url_is_dangerous
    # Contract: shell.powershell_safety
    def test_windows_cmd_start_url_string_variants_are_dangerous(self):
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "start https://example.com"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", 'start "https://example.com"']))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", 'start "" https://example.com']))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_dangerous_commands.rs
    # Rust tests: selected PowerShell/CMD force-delete dangerous-command tests
    # Contract: shell.powershell_safety
    def test_windows_force_delete_heuristics_are_platform_independent(self):
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Remove-Item test -Force"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Remove-Item test -Recurse -Force"]))
        self.assertTrue(command_might_be_dangerous(["pwsh", "-Command", "ri test -Force"]))
        self.assertFalse(command_might_be_dangerous(["powershell", "-Command", "Remove-Item test"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "del", "/f", "test.txt"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "erase", "/f", "test.txt"]))
        self.assertFalse(command_might_be_dangerous(["cmd", "/c", "del", "test.txt"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "rd", "/s", "/q", "test"]))
        self.assertFalse(command_might_be_dangerous(["cmd", "/c", "rd", "/s", "test"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "rmdir", "/s", "/q", "test"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Remove-Item -Path 'test' -Recurse -Force"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Remove-Item test -Force; Write-Host done"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "if ($true) { Remove-Item test -Force}"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "[void]( Remove-Item test -Force)]"]))
        self.assertFalse(command_might_be_dangerous(["cmd", "/c", "del", "C:/foo/bar.txt"]))
        self.assertFalse(command_might_be_dangerous(["cmd", "/c", "rd", "C:/source"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_dangerous_commands.rs
    # Rust tests: tests::powershell_rm_alias_force_is_dangerous; tests::powershell_benign_force_separate_command_is_not_dangerous
    # Contract: shell.powershell_safety
    def test_windows_powershell_rm_alias_force_and_benign_force_segment(self):
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "rm test -Force"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "rm -rf /important/data"]))
        self.assertFalse(command_might_be_dangerous(["powershell", "-Command", "Get-ChildItem -Force; Remove-Item test"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_dangerous_commands.rs
    # Rust tests: selected CMD/PowerShell chained delete dangerous-command tests
    # Contract: shell.powershell_safety
    def test_windows_chained_delete_heuristics_are_platform_independent(self):
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "echo hi&del /f file.txt"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "echo hi&&del /f file.txt"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "echo hi||del /f file.txt"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "del /f file.txt"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "echo hello & del /f file.txt"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "rmdir /s /q test"]))
        self.assertTrue(command_might_be_dangerous(["cmd", "/c", "echo hi&rmdir /s /q test"]))
        self.assertTrue(command_might_be_dangerous(["cmd.exe", "/r", "del", "/F", "test.txt"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Write-Host hi; Remove-Item test -Force"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Write-Host hi;Remove-Item test -Force"]))
        self.assertTrue(command_might_be_dangerous(["powershell", "-Command", "Write-Host hi, Remove-Item test -Force"]))
        self.assertFalse(command_might_be_dangerous(["powershell", "-Command", "Write-Host -Force; Remove-Item test"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust modules: src/command_safety/is_safe_command.rs; src/command_safety/windows_safe_commands.rs
    # Rust tests: tests::direct_powershell_words_use_windows_safelist; windows_safe_commands::tests::recognizes_safe_powershell_wrappers; windows_safe_commands::tests::rejects_powershell_commands_with_side_effects
    # Contract: shell.powershell_safety
    def test_windows_powershell_safelist_matches_platform_cfg(self):
        expected = os.name == "nt"
        self.assertEqual(is_safe_powershell_words(["Get-Content", "Cargo.toml"]), expected)
        self.assertEqual(
            is_known_safe_command(["powershell.exe", "-NoProfile", "-Command", "Get-ChildItem -Path ."]),
            expected,
        )
        self.assertFalse(is_known_safe_command(["powershell.exe", "-Command", "Remove-Item foo.txt"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_safe_commands.rs
    # Rust tests: tests::recognizes_safe_powershell_wrappers; tests::accepts_full_path_powershell_invocations
    # Contract: shell.powershell_safety
    def test_windows_powershell_wrapper_forms_follow_platform_cfg(self):
        expected = os.name == "nt"
        self.assertEqual(
            is_known_safe_command(
                [
                    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                    "-Command",
                    "Get-Content Cargo.toml",
                ]
            ),
            expected,
        )
        self.assertEqual(
            is_known_safe_command(
                [
                    "/usr/local/bin/pwsh.exe",
                    "-NoProfile",
                    "-Command",
                    "Get-ChildItem -Path .",
                ]
            ),
            expected,
        )
        self.assertEqual(
            is_known_safe_command(["powershell.exe", "Get-Content", "foo bar"]),
            expected,
        )
        self.assertEqual(
            is_known_safe_command(["powershell.exe", "-Command:Get-Content Cargo.toml"]),
            expected,
        )
        self.assertEqual(
            is_known_safe_command(["powershell.exe", "/Command:Get-ChildItem"]),
            expected,
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_safe_commands.rs
    # Rust tests: tests::recognizes_safe_powershell_wrappers; tests::rejects_powershell_commands_with_side_effects
    # Contract: shell.powershell_safety
    def test_windows_powershell_wrapper_rejections(self):
        unsafe_commands = (
            ["powershell.exe"],
            ["powershell.exe", "-NoLogo"],
            ["powershell.exe", "-NoProfile", "-Command", "Get-Content", "Cargo.toml"],
            ["powershell.exe", "-Command:Get-Content", "Cargo.toml"],
            ["powershell.exe", "-UnknownFlag"],
            ["powershell.exe", "-EncodedCommand", "AAAA"],
            ["powershell.exe", "-File", "script.ps1"],
            ["powershell.exe", "-WindowStyle", "Hidden", "-Command", "Get-Content Cargo.toml"],
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", "Get-Content Cargo.toml"],
            ["powershell.exe", "-WorkingDirectory", ".", "-Command", "Get-Content Cargo.toml"],
        )
        for command in unsafe_commands:
            with self.subTest(command=command):
                self.assertFalse(is_known_safe_command(command))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_safe_commands.rs
    # Rust test: tests::allows_read_only_pipelines_and_git_usage
    # Contract: shell.powershell_safety
    def test_windows_powershell_read_only_pipelines_and_git_usage_follow_platform_cfg(self):
        expected = os.name == "nt"
        self.assertEqual(
            is_known_safe_command(
                [
                    "pwsh",
                    "-NoLogo",
                    "-NoProfile",
                    "-Command",
                    "rg --files-with-matches foo | Measure-Object | Select-Object -ExpandProperty Count",
                ]
            ),
            expected,
        )
        self.assertEqual(
            is_known_safe_command(
                [
                    "pwsh",
                    "-NoLogo",
                    "-NoProfile",
                    "-Command",
                    "Get-Content foo.rs | Select-Object -Skip 200",
                ]
            ),
            expected,
        )
        self.assertEqual(is_known_safe_command(["pwsh", "-Command", "git show HEAD:foo.rs"]), expected)
        self.assertEqual(is_known_safe_command(["pwsh", "-Command", "(Get-Content foo.rs -Raw)"]), expected)
        self.assertEqual(is_known_safe_command(["pwsh", "-Command", "Get-Item foo.rs | Select-Object Length"]), expected)

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_safe_commands.rs
    # Rust test: tests::rejects_git_global_override_options
    # Contract: shell.powershell_safety
    def test_windows_powershell_rejects_git_global_override_options(self):
        unsafe_scripts = (
            "git -c core.pager=cat show HEAD:foo.rs",
            "git --config-env core.pager=PAGER show HEAD:foo.rs",
            "git --config-env=core.pager=PAGER show HEAD:foo.rs",
            "git --git-dir .evil-git diff HEAD~1..HEAD",
            "git --git-dir=.evil-git diff HEAD~1..HEAD",
            "git --work-tree . status",
            "git --work-tree=. status",
            "git --exec-path .git/helpers show HEAD:foo.rs",
            "git --exec-path=.git/helpers show HEAD:foo.rs",
            "git --namespace attacker show HEAD:foo.rs",
            "git --namespace=attacker show HEAD:foo.rs",
            "git --super-prefix attacker/ show HEAD:foo.rs",
            "git --super-prefix=attacker/ show HEAD:foo.rs",
        )
        for script in unsafe_scripts:
            with self.subTest(script=script):
                self.assertFalse(is_known_safe_command(["pwsh", "-NoLogo", "-NoProfile", "-Command", script]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_safe_commands.rs
    # Rust test: tests::rejects_git_subcommand_options_with_side_effects
    # Contract: shell.powershell_safety
    def test_windows_powershell_rejects_git_subcommand_options_with_side_effects(self):
        unsafe_scripts = (
            "git diff --output codex_poc.txt",
            "git diff --ext-diff HEAD",
            "git log --textconv -1",
            "git show --output=codex_poc.txt HEAD",
            "git cat-file --filters HEAD:a.txt",
        )
        for script in unsafe_scripts:
            with self.subTest(script=script):
                self.assertFalse(is_known_safe_command(["powershell.exe", "-NoProfile", "-Command", script]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/windows_safe_commands.rs
    # Rust tests: tests::accepts_constant_expression_arguments; tests::rejects_dynamic_arguments
    # Contract: shell.powershell_safety
    def test_windows_powershell_constant_arguments_and_dynamic_rejection_follow_platform_cfg(self):
        expected = os.name == "nt"
        self.assertEqual(is_known_safe_command(["powershell.exe", "-Command", "Get-Content 'foo bar'"]), expected)
        self.assertEqual(is_known_safe_command(["powershell.exe", "-Command", 'Get-Content "foo bar"']), expected)
        self.assertFalse(is_known_safe_command(["powershell.exe", "-Command", "Get-Content $foo"]))
        self.assertFalse(is_known_safe_command(["powershell.exe", "-Command", 'Write-Output "foo $bar"']))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/is_safe_command.rs
    # Rust tests: tests::windows_git_full_path_is_safe; tests::windows_powershell_full_path_is_safe
    # Contract: shell.command_safety
    def test_executable_name_lookup_key_uses_windows_suffix_rules_on_windows(self):
        if os.name == "nt":
            self.assertEqual(executable_name_lookup_key(r"C:\Program Files\Git\cmd\git.exe"), "git")
        else:
            self.assertEqual(executable_name_lookup_key("/usr/bin/git"), "git")

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/powershell_parser.rs
    # Rust test: tests::parser_process_handles_multiple_requests
    # Contract: shell.powershell_parser
    def test_powershell_parser_handles_simple_command_requests(self):
        self.assertEqual(
            try_parse_powershell_ast_commands("powershell.exe", "Get-Content 'foo bar'"),
            [["Get-Content", "foo bar"]],
        )
        self.assertEqual(
            try_parse_powershell_ast_commands("powershell.exe", "Write-Output foo | Measure-Object"),
            [["Write-Output", "foo"], ["Measure-Object"]],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/powershell_parser.rs
    # Rust test: tests::parser_process_rejects_stop_parsing_forms
    # Contract: shell.powershell_parser
    def test_powershell_parser_rejects_stop_parsing_forms(self):
        outcome = parse_with_powershell_ast("powershell.exe", "git log --% HEAD --output=codex_poc.txt")
        self.assertEqual(outcome.kind, PowershellParseKind.UNSUPPORTED)
        self.assertIsNone(
            try_parse_powershell_ast_commands("powershell.exe", "git log --% HEAD --output=codex_poc.txt")
        )

    # Source: rust_source_inferred
    # Rust crate: codex-shell-command
    # Rust module: src/command_safety/powershell_parser.rs
    # Rust items: encode_powershell_base64; PowershellParserResponse::into_outcome
    # Contract: shell.powershell_parser
    def test_powershell_parser_encoding_and_response_validation(self):
        self.assertEqual(encode_powershell_base64("ok"), "bwBrAA==")
        self.assertEqual(
            PowershellParserResponse(1, "ok", (("echo", "hi"),)).into_outcome().kind,
            PowershellParseKind.COMMANDS,
        )
        self.assertEqual(
            PowershellParserResponse(1, "ok", ()).into_outcome().kind,
            PowershellParseKind.UNSUPPORTED,
        )
        self.assertEqual(
            PowershellParserResponse(1, "unsupported").into_outcome().kind,
            PowershellParseKind.UNSUPPORTED,
        )
        self.assertEqual(
            PowershellParserResponse(1, "bad-status").into_outcome().kind,
            PowershellParseKind.FAILED,
        )


if __name__ == "__main__":
    unittest.main()
