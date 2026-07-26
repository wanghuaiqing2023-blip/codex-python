import unittest

from pycodex.cli.exit_status import handle_exit_status


class CliExitStatusTests(unittest.TestCase):
    def test_handle_exit_status_matches_rust_exit_status_mapping(self) -> None:
        # Rust parity: codex-cli/src/exit_status.rs.
        self.assertEqual(handle_exit_status(0), 0)
        self.assertEqual(handle_exit_status(2), 2)
        self.assertEqual(handle_exit_status(-15), 143)
        self.assertEqual(handle_exit_status(None), 1)
        with self.assertRaisesRegex(TypeError, "returncode must be an integer or None"):
            handle_exit_status("1")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
