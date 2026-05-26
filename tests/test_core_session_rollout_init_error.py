from __future__ import annotations

import errno
from pathlib import Path
import unittest

from pycodex.core.session_rollout_init_error import (
    map_rollout_io_error,
    map_session_init_error,
)
from pycodex.protocol import CodexErr


class SessionRolloutInitErrorTests(unittest.TestCase):
    def test_maps_permission_denied_with_ownership_hint(self) -> None:
        codex_home = Path("C:/codex-home")
        sessions_dir = codex_home / "sessions"
        err = map_rollout_io_error(PermissionError(errno.EACCES, "permission denied"), codex_home)

        self.assertIsNotNone(err)
        self.assertEqual(err.kind, "fatal")
        self.assertIn(f"Codex cannot access session files at {sessions_dir}", err.message or "")
        self.assertIn(f"sudo chown -R $(whoami) {codex_home}", err.message or "")
        self.assertIn("underlying error:", err.message or "")

    def test_maps_missing_existing_invalid_and_type_errors(self) -> None:
        cases = (
            (FileNotFoundError(errno.ENOENT, "not found"), "Session storage missing"),
            (FileExistsError(errno.EEXIST, "exists"), "is blocked by an existing file"),
            (OSError(errno.EINVAL, "invalid data"), "looks corrupt or unreadable"),
            (IsADirectoryError(errno.EISDIR, "is a directory"), "has an unexpected type"),
            (NotADirectoryError(errno.ENOTDIR, "not a directory"), "has an unexpected type"),
        )

        for error, expected in cases:
            with self.subTest(expected=expected):
                codex_home = Path("C:/Users/me/.codex")
                mapped = map_rollout_io_error(error, codex_home)
                self.assertIsNotNone(mapped)
                self.assertEqual(mapped.kind, "fatal")
                self.assertIn(expected, mapped.message or "")
                self.assertIn(str(codex_home), mapped.message or "")

    def test_unrecognized_io_error_returns_none(self) -> None:
        self.assertIsNone(map_rollout_io_error(OSError(errno.EBUSY, "busy"), "/codex-home"))

    def test_map_session_init_error_uses_recognized_cause(self) -> None:
        outer = RuntimeError("session init failed")
        inner = FileNotFoundError(errno.ENOENT, "not found")
        outer.__cause__ = inner

        codex_home = Path("C:/codex-home")
        mapped = map_session_init_error(outer, codex_home)

        self.assertEqual(mapped.kind, "fatal")
        self.assertIn(f"Session storage missing at {codex_home / 'sessions'}", mapped.message or "")
        self.assertNotIn("Failed to initialize session", mapped.message or "")

    def test_map_session_init_error_falls_back_to_generic_fatal(self) -> None:
        outer = RuntimeError("session init failed")
        outer.__cause__ = ValueError("bad metadata")

        mapped = map_session_init_error(outer, "/codex-home")

        self.assertEqual(mapped, CodexErr.fatal("Failed to initialize session: session init failed: bad metadata"))


if __name__ == "__main__":
    unittest.main()
