import unittest

from pycodex.core import (
    CANONICAL_BASH_SCRIPT_PREFIX,
    CANONICAL_POWERSHELL_SCRIPT_PREFIX,
    canonicalize_command_for_approval,
)


class CoreCommandCanonicalizationTests(unittest.TestCase):
    def test_canonicalizes_word_only_shell_scripts_to_inner_command(self):
        command_a = ["/bin/bash", "-lc", "cargo test -p codex-core"]
        command_b = ["bash", "-lc", "cargo   test   -p codex-core"]

        self.assertEqual(
            canonicalize_command_for_approval(command_a),
            ["cargo", "test", "-p", "codex-core"],
        )
        self.assertEqual(
            canonicalize_command_for_approval(command_a),
            canonicalize_command_for_approval(command_b),
        )

    def test_canonicalizes_heredoc_scripts_to_stable_script_key(self):
        script = "python3 <<'PY'\nprint('hello')\nPY"
        command_a = ["/bin/zsh", "-lc", script]
        command_b = ["zsh", "-lc", script]

        self.assertEqual(
            canonicalize_command_for_approval(command_a),
            [CANONICAL_BASH_SCRIPT_PREFIX, "-lc", script],
        )
        self.assertEqual(
            canonicalize_command_for_approval(command_a),
            canonicalize_command_for_approval(command_b),
        )

    def test_canonicalizes_powershell_wrappers_to_stable_script_key(self):
        script = "Write-Host hi"
        command_a = ["powershell.exe", "-NoProfile", "-Command", script]
        command_b = ["powershell", "-Command", script]

        self.assertEqual(
            canonicalize_command_for_approval(command_a),
            [CANONICAL_POWERSHELL_SCRIPT_PREFIX, script],
        )
        self.assertEqual(
            canonicalize_command_for_approval(command_a),
            canonicalize_command_for_approval(command_b),
        )

    def test_preserves_non_shell_commands(self):
        command = ["cargo", "fmt"]

        self.assertEqual(canonicalize_command_for_approval(command), command)


if __name__ == "__main__":
    unittest.main()
