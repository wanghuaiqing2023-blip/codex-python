import unittest

from pathlib import Path

from pycodex.cli import (
    is_state_db_locked,
    state_db_confirm_repair,
    state_db_backup_path,
    state_db_print_diagnostic_guidance,
    state_db_print_locked_guidance,
    state_db_print_repair_backups,
    state_db_repair_files,
    state_db_startup_error,
    state_db_sqlite_paths,
)
from pycodex.state import goals_db_path, logs_db_path, state_db_path
from pycodex.tui.startup_error import LocalStateDbStartupError


class CliStateDbRecoveryTests(unittest.TestCase):
    def test_startup_error_extracts_embedded_local_state_db_error(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs startup_error.
        startup_error = LocalStateDbStartupError.new("/tmp/codex/state_5.sqlite", "corrupt")
        wrapper = OSError("startup failed")
        wrapper.__cause__ = startup_error

        self.assertIs(state_db_startup_error(wrapper), startup_error)
        self.assertIs(state_db_startup_error(RuntimeError("other")), None)

    def test_is_locked_matches_rust_lock_contention_detection(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs lock_failures_skip_repair.
        self.assertTrue(is_state_db_locked("database is locked"))
        self.assertTrue(is_state_db_locked("DATABASE IS BUSY"))
        self.assertFalse(is_state_db_locked("database disk image is malformed"))
        with self.assertRaisesRegex(TypeError, "detail must be a string"):
            is_state_db_locked(None)  # type: ignore[arg-type]

    def test_sqlite_paths_match_rust_sidecar_contract(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs sqlite_paths.
        db_path = Path("/tmp/codex/state_5.sqlite")

        self.assertEqual(
            state_db_sqlite_paths(db_path),
            (
                db_path,
                Path("/tmp/codex/state_5.sqlite-wal"),
                Path("/tmp/codex/state_5.sqlite-shm"),
            ),
        )

    def test_backup_path_uses_first_available_repair_sequence(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs backup_path.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.sqlite"
            db_path.write_text("state", encoding="utf-8")
            existing_backup = Path(tmp) / "state.sqlite.codex-repair-123.0.bak"
            existing_backup.write_text("existing", encoding="utf-8")

            backup = state_db_backup_path(db_path, "codex-repair-123")

            self.assertEqual(backup, Path(tmp) / "state.sqlite.codex-repair-123.1.bak")
            self.assertFalse(db_path.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), "state")
            self.assertEqual(existing_backup.read_text(encoding="utf-8"), "existing")

    def test_repair_replaces_blocking_sqlite_home_file(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs repair_replaces_blocking_sqlite_home_file.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_home = Path(tmp) / "sqlite-home"
            sqlite_home.write_text("not-a-directory", encoding="utf-8")
            startup_error = LocalStateDbStartupError.new(state_db_path(sqlite_home), "File exists")

            backups = state_db_repair_files(startup_error, repair_suffix="codex-repair-123")

            self.assertEqual(backups, [Path(tmp) / "sqlite-home.codex-repair-123.0.bak"])
            self.assertTrue(sqlite_home.is_dir())
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "not-a-directory")

    def test_repair_backs_up_owned_database_files(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs repair_backs_up_owned_database_files.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_home = Path(tmp)
            state_path = state_db_path(sqlite_home)
            logs_path = logs_db_path(sqlite_home)
            goals_path = goals_db_path(sqlite_home)
            state_wal_path = state_db_sqlite_paths(state_path)[1]
            state_path.write_text("state", encoding="utf-8")
            state_wal_path.write_text("state-wal", encoding="utf-8")
            logs_path.write_text("logs", encoding="utf-8")
            goals_path.write_text("goals", encoding="utf-8")
            startup_error = LocalStateDbStartupError.new(state_path, "corrupt")

            backups = state_db_repair_files(startup_error, repair_suffix="codex-repair-123")

            self.assertEqual(len(backups), 4)
            self.assertFalse(state_path.exists())
            self.assertFalse(state_wal_path.exists())
            self.assertFalse(logs_path.exists())
            self.assertFalse(goals_path.exists())
            self.assertEqual(
                {backup.name for backup in backups},
                {
                    "state_5.sqlite.codex-repair-123.0.bak",
                    "state_5.sqlite-wal.codex-repair-123.0.bak",
                    "logs_2.sqlite.codex-repair-123.0.bak",
                    "goals_1.sqlite.codex-repair-123.0.bak",
                },
            )

    def test_repair_errors_when_no_repairable_files_exist(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs repair_files empty-backup guard.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_home = Path(tmp)
            startup_error = LocalStateDbStartupError.new(state_db_path(sqlite_home), "corrupt")

            with self.assertRaisesRegex(OSError, "no repairable Codex local data files were found"):
                state_db_repair_files(startup_error, repair_suffix="codex-repair-123")

    def test_print_locked_guidance_matches_rust_message_shape(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs print_locked_guidance.
        import contextlib
        import io

        db_path = Path("/tmp/codex/state_5.sqlite")
        startup_error = LocalStateDbStartupError.new(db_path, "database is busy")
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            state_db_print_locked_guidance(startup_error)

        self.assertEqual(
            stderr.getvalue().splitlines(),
            [
                "Codex couldn't start because another Codex process is using its local data.",
                "Quit any other copies of Codex that may still be running, then try again.",
                "Technical details:",
                f"  Location: {db_path}",
                "  Cause: database is busy",
            ],
        )

    def test_print_diagnostic_guidance_matches_rust_message_shape(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs print_diagnostic_guidance.
        import contextlib
        import io

        db_path = Path("/tmp/codex/state_5.sqlite")
        startup_error = LocalStateDbStartupError.new(db_path, "database disk image is malformed")
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            state_db_print_diagnostic_guidance(startup_error)

        self.assertEqual(
            stderr.getvalue().splitlines(),
            [
                "Codex couldn't start because its local database appears to be damaged.",
                "Run `codex doctor` to check your setup and get next-step guidance.",
                "If this keeps happening, share the technical details below when asking for help.",
                "Technical details:",
                f"  Location: {db_path}",
                "  Cause: database disk image is malformed",
            ],
        )

    def test_print_repair_backups_matches_rust_message_shape(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs print_repair_backups.
        import contextlib
        import io

        backups = [
            Path("/tmp/codex/state_5.sqlite.codex-repair-123.0.bak"),
            Path("/tmp/codex/logs_2.sqlite.codex-repair-123.0.bak"),
        ]
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            state_db_print_repair_backups(backups)

        self.assertEqual(
            stderr.getvalue().splitlines(),
            [
                "Backed up Codex local data before repair:",
                f"  {backups[0]}",
                f"  {backups[1]}",
                "Retrying startup with rebuilt local data...",
            ],
        )

    def test_confirm_repair_prints_guidance_and_delegates_prompt(self) -> None:
        # Rust parity: codex-cli/src/state_db_recovery.rs confirm_repair.
        import contextlib
        import io

        db_path = Path("/tmp/codex/state_5.sqlite")
        startup_error = LocalStateDbStartupError.new(db_path, "corrupt")
        prompts: list[str] = []
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            accepted = state_db_confirm_repair(startup_error, confirm=lambda prompt: prompts.append(prompt) or True)

        self.assertTrue(accepted)
        self.assertEqual(prompts, ["Repair Codex local data now? [y/N]: "])
        self.assertEqual(
            stderr.getvalue().splitlines(),
            [
                "Codex couldn't start because its local database appears to be damaged.",
                "Codex can try a safe repair by backing up those files and rebuilding them.",
                "Technical details:",
                f"  Location: {db_path}",
                "  Cause: corrupt",
            ],
        )


if __name__ == "__main__":
    unittest.main()
