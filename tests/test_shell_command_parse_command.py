import unittest
from pathlib import Path

from pycodex.protocol import ParsedCommand
from pycodex.shell_command import (
    extract_powershell_command,
    parse_command,
    parse_shell_lc_plain_commands,
    parse_shell_lc_single_command_prefix,
    shlex_join,
)


def split(value: str) -> list[str]:
    import shlex

    return shlex.split(value)


class ShellCommandParseCommandTests(unittest.TestCase):
    def test_shlex_join_and_unknown_commands(self):
        self.assertEqual(shlex_join(["rg", "-n", "BUG|FIXME", "-S"]), "rg -n 'BUG|FIXME' -S")
        self.assertEqual(parse_command(["git", "status"]), [ParsedCommand.unknown("git status")])

    def test_supports_git_grep_and_ls_files(self):
        self.assertEqual(
            parse_command(split("git grep TODO src")),
            [ParsedCommand.search("git grep TODO src", query="TODO", path="src")],
        )
        self.assertEqual(
            parse_command(split("git ls-files --exclude target src")),
            [ParsedCommand.list_files("git ls-files --exclude target src", "src")],
        )

    def test_supports_rg_search_and_file_listing_in_bash(self):
        self.assertEqual(
            parse_command(["bash", "-lc", 'rg -n "navigate-to-route" -S']),
            [ParsedCommand.search("rg -n navigate-to-route -S", query="navigate-to-route")],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "rg --files webview/src | sed -n"]),
            [ParsedCommand.list_files("rg --files webview/src", "webview")],
        )

    def test_bash_falls_back_to_full_script_when_unknown_or_unsupported(self):
        self.assertEqual(
            parse_command(["bash", "-lc", "git status | wc -l"]),
            [ParsedCommand.unknown("git status | wc -l")],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "echo foo > bar"]),
            [ParsedCommand.unknown("echo foo > bar")],
        )

    def test_collapses_mutating_xargs_pipeline_to_unknown(self):
        command = split("rg -l OldName src | xargs perl -pi -e 's/OldName/NewName/g'")
        self.assertEqual(
            parse_command(command),
            [ParsedCommand.unknown(shlex_join(command))],
        )

    def test_read_commands_and_cd_context(self):
        self.assertEqual(
            parse_command(split("cat pycodex/protocol/protocol.py")),
            [ParsedCommand.read("cat pycodex/protocol/protocol.py", "protocol.py", Path("pycodex/protocol/protocol.py"))],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "cd pycodex && sed -n 1,20p protocol/protocol.py"]),
            [ParsedCommand.read("sed -n 1,20p protocol/protocol.py", "protocol.py", Path("pycodex") / "protocol/protocol.py")],
        )

    def test_powershell_wrapper_extracts_script(self):
        self.assertEqual(
            extract_powershell_command(["pwsh", "-NoProfile", "-c", "Write-Host hi"]),
            ("pwsh", "Write-Host hi"),
        )
        self.assertEqual(
            parse_command(["powershell.exe", "-NoProfile", "-Command", "Write-Host hi"]),
            [ParsedCommand.unknown("Write-Host hi")],
        )

    def test_bash_plain_commands_reject_empty_shell_segments(self):
        self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", ""]))
        self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", "  \n\t  "]))
        self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", "ls &&"]))

    def test_bash_single_command_prefix_supports_heredoc(self):
        self.assertEqual(
            parse_shell_lc_single_command_prefix(["zsh", "-lc", "python3 <<'PY'\nprint('hello')\nPY"]),
            ["python3"],
        )
        self.assertEqual(
            parse_shell_lc_single_command_prefix(["zsh", "-lc", "python3 << PY\nprint('hello')\nPY"]),
            ["python3"],
        )

    def test_bash_single_command_prefix_rejects_complex_heredocs(self):
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "python3 <<'PY'\nprint('hello')\nPY\necho done"])
        )
        self.assertIsNone(parse_shell_lc_single_command_prefix(["bash", "-lc", "echo hello > /tmp/out.txt"]))
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "python3 <<'PY' > /tmp/out.txt\nprint('hello')\nPY"])
        )
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "PATH=/tmp/evil:$PATH cat <<'EOF'\nhello\nEOF"])
        )
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "python3 $((1<<2)) <<'PY'\nprint('hello')\nPY"])
        )


if __name__ == "__main__":
    unittest.main()
