import unittest

from pycodex.core import (
    CANONICAL_BASH_SCRIPT_PREFIX,
    CANONICAL_POWERSHELL_SCRIPT_PREFIX,
    canonicalize_command_for_approval,
)


class CoreCommandCanonicalizationTests(unittest.TestCase):
    def test_canonicalizes_word_only_shell_scripts_to_inner_command(self):
        # Rust source: codex-rs/core/src/command_canonicalization.rs
        # Rust test: canonicalizes_word_only_shell_scripts_to_inner_command.
        # Behavior anchor: simple shell wrapper scripts canonicalize to the
        # parsed inner command argv so approval-cache keys survive wrapper
        # path and whitespace differences.
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
        # Rust source: codex-rs/core/src/command_canonicalization.rs
        # Rust test: canonicalizes_heredoc_scripts_to_stable_script_key.
        # Behavior anchor: complex bash/zsh scripts that cannot safely be
        # tokenized use a stable shell-script prefix plus shell mode and script.
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
        # Rust source: codex-rs/core/src/command_canonicalization.rs
        # Rust test: canonicalizes_powershell_wrappers_to_stable_script_key.
        # Behavior anchor: PowerShell wrapper variants canonicalize to the
        # same stable script key and preserve the script text.
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
        # Rust source: codex-rs/core/src/command_canonicalization.rs
        # Rust test: preserves_non_shell_commands.
        # Behavior anchor: non-shell argv is preserved exactly.
        command = ["cargo", "fmt"]

        self.assertEqual(canonicalize_command_for_approval(command), command)

    def test_rejects_non_rust_command_shapes(self):
        # Python-only guard: Rust receives typed &[String], while Python must
        # reject ambiguous string and non-string-token inputs at runtime.
        with self.assertRaises(TypeError):
            canonicalize_command_for_approval("cargo fmt")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            canonicalize_command_for_approval(["cargo", 1])  # type: ignore[list-item]
        with self.assertRaises(TypeError):
            canonicalize_command_for_approval(["cargo", True])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
