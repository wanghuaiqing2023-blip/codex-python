import unittest

from pycodex.cli import exit_code_from_returncode


class CliExitStatusTests(unittest.TestCase):
    def test_exit_code_from_returncode_matches_rust_exit_status_mapping(self) -> None:
        # Rust parity: codex-cli/src/exit_status.rs.
        self.assertEqual(exit_code_from_returncode(0), 0)
        self.assertEqual(exit_code_from_returncode(2), 2)
        self.assertEqual(exit_code_from_returncode(-15), 143)
        self.assertEqual(exit_code_from_returncode(None), 1)
        with self.assertRaisesRegex(TypeError, "returncode must be an integer or None"):
            exit_code_from_returncode("1")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
