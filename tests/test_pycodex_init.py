"""Tests for top-level pycodex package compatibility."""

from __future__ import annotations

import unittest


class TopLevelPackageImportTests(unittest.TestCase):
    def test_top_level_modules_are_lazily_importable(self) -> None:
        import pycodex

        self.assertEqual(pycodex.__version__, "0.1.0")
        self.assertTrue(hasattr(pycodex, "cli"))
        self.assertTrue(hasattr(pycodex, "core"))
        self.assertTrue(hasattr(pycodex, "protocol"))
        self.assertTrue(hasattr(pycodex, "login"))
        self.assertTrue(hasattr(pycodex, "tui"))
        self.assertTrue(hasattr(pycodex, "sandboxing"))

    def test_top_level_directory_exports_expected_names(self) -> None:
        import pycodex

        expected = {
            "__version__",
            "cli",
            "core",
            "protocol",
            "login",
            "tui",
            "sandboxing",
        }
        self.assertTrue(expected.issubset(set(pycodex.__all__)))

    def test_tui_compatibility_exports(self) -> None:
        import io

        from pycodex import tui

        self.assertTrue(callable(getattr(tui, "run_tui", None)))
        self.assertNotIn("run_terminal_tui", getattr(tui, "__all__", ()))
        self.assertNotIn("TUIUnavailableError", getattr(tui, "__all__", ()))
        self.assertFalse(hasattr(tui, "run_terminal_tui"))
        self.assertFalse(hasattr(tui, "TUIUnavailableError"))

        stderr = io.StringIO()
        self.assertEqual(tui.run_tui(stderr=stderr), 64)
        self.assertIn("requires an active thread runtime", stderr.getvalue())
        self.assertNotIn("disabled in this Python port", stderr.getvalue())

    def test_sandboxing_compatibility_exports(self) -> None:
        from pycodex import sandboxing

        self.assertTrue(hasattr(sandboxing, "ReviewDecision"))
        self.assertTrue(hasattr(sandboxing, "SandboxPermissions"))
        self.assertTrue(hasattr(sandboxing, "with_cached_approval"))
    def test_login_compatibility_exports(self) -> None:
        import pycodex.login as login

        self.assertTrue(hasattr(login, "read_auth_json"))
        self.assertTrue(hasattr(login, "write_auth_json"))
        self.assertTrue(hasattr(login, "run_chatgpt_login"))
        compatibility_exports = {
            "AUTH_FILE",
            "AUTH_MODE_API_KEY",
            "AUTH_MODE_CHATGPT",
            "AUTH_MODE_CHATGPT_AUTH_TOKENS",
            "AUTH_MODE_AGENT_IDENTITY",
            "AuthDotJson",
            "auth_file_path",
            "delete_auth_file",
            "read_auth_json",
            "resolve_auth_mode",
            "run_chatgpt_login",
            "safe_format_key",
            "write_auth_json",
        }
        self.assertTrue(compatibility_exports.issubset(login.__all__))
        # Rust `codex-login::lib` also re-exports its auth/device/server owners.
        self.assertTrue({"AuthManager", "DeviceCode", "LoginServer"}.issubset(login.__all__))

    def test_python_m_entrypoint_rejects_non_tty_tui_startup(self) -> None:
        """Rust codex-cli refuses interactive TUI startup without a terminal.

        Rust anchor: codex-rs/cli/src/main.rs::run_interactive_tui and
        codex-rs/tui/src/tui.rs::init.  Python must not fall back to the
        deleted legacy terminal projection for piped stdin.
        """

        import subprocess
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "pycodex"],
            cwd=str(repo_root),
            input="/quit\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Refusing to start the interactive TUI", result.stderr)

    def test_python_m_entrypoint_prints_help(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "pycodex", "--help"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Codex CLI", result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertIn("codex [OPTIONS] [PROMPT]", result.stdout)
        self.assertIn("Print version.", result.stdout)

    def test_python_m_entrypoint_prints_version(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        from pycodex import __version__

        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "pycodex", "--version"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(f"codex {__version__}", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
