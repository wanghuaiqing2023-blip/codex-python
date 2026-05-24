import unittest
import uuid
from pathlib import Path

from pycodex.core import (
    GOALS_DB_FILENAME,
    LOGS_DB_FILENAME,
    STATE_DB_FILENAME,
    find_codex_home,
    goals_db_path,
    logs_db_path,
    runtime_db_paths,
    state_db_path,
)


def workspace_tempdir():
    root = Path.cwd() / "tmp_tests_workspace"
    root.mkdir(exist_ok=True)
    path = root / f"case-{uuid.uuid4()}"
    path.mkdir()
    return path


class CorePathTests(unittest.TestCase):
    def test_find_codex_home_env_valid_directory_canonicalizes(self):
        raw = workspace_tempdir()
        resolved = find_codex_home(env={"CODEX_HOME": str(raw)})

        self.assertEqual(resolved, raw.resolve())

    def test_find_codex_home_env_missing_path_is_fatal(self):
        raw = workspace_tempdir()
        missing = str(raw / "missing-codex-home")

        with self.assertRaises(FileNotFoundError):
            find_codex_home(env={"CODEX_HOME": missing})

    def test_find_codex_home_env_file_path_is_fatal(self):
        raw = workspace_tempdir()
        file_path = raw / "codex-home.txt"
        file_path.write_text("not a directory", encoding="utf-8")

        with self.assertRaises(NotADirectoryError):
            find_codex_home(env={"CODEX_HOME": str(file_path)})

    def test_find_codex_home_without_env_uses_default_home_dir(self):
        home = Path("C:/Users/example")

        self.assertEqual(find_codex_home(env={}, home=home), home / ".codex")

    def test_runtime_db_paths_match_upstream_filenames(self):
        root = Path("/codex-home")

        self.assertEqual(STATE_DB_FILENAME, "state_5.sqlite")
        self.assertEqual(LOGS_DB_FILENAME, "logs_2.sqlite")
        self.assertEqual(GOALS_DB_FILENAME, "goals_1.sqlite")
        self.assertEqual(state_db_path(root), root / "state_5.sqlite")
        self.assertEqual(logs_db_path(root), root / "logs_2.sqlite")
        self.assertEqual(goals_db_path(root), root / "goals_1.sqlite")
        self.assertEqual(
            runtime_db_paths(root),
            [
                runtime_db_paths(root)[0].__class__("state DB", root / "state_5.sqlite"),
                runtime_db_paths(root)[1].__class__("log DB", root / "logs_2.sqlite"),
                runtime_db_paths(root)[2].__class__("goals DB", root / "goals_1.sqlite"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
