from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from pycodex.core import (
    SessionIndexEntry,
    SessionMeta,
    append_session_index_entry,
    find_archived_thread_path_by_id_str,
    find_thread_meta_by_name_str,
    find_thread_path_by_id_str,
    materialize_session_rollout,
)


def write_minimal_rollout_with_id_at_path(path: Path, thread_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "timestamp": "2024-01-01T00:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": thread_id,
                    "timestamp": "2024-01-01T00:00:00Z",
                    "cwd": ".",
                    "originator": "test",
                    "cli_version": "test",
                    "model_provider": "test-provider",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_minimal_rollout_with_id_in_subdir(codex_home: Path, subdir: str, thread_id: str) -> Path:
    path = codex_home / subdir / "2024" / "01" / "01" / f"rollout-2024-01-01T00-00-00-{thread_id}.jsonl"
    write_minimal_rollout_with_id_at_path(path, thread_id)
    return path


def write_minimal_rollout_with_id(codex_home: Path, thread_id: str) -> Path:
    return write_minimal_rollout_with_id_in_subdir(codex_home, "sessions", thread_id)


class FakeStateDb:
    def __init__(self, paths_by_id: dict[str, Path]) -> None:
        self.paths_by_id = paths_by_id


class RolloutListFindSuiteParityTests(unittest.TestCase):
    def test_find_locates_rollout_file_by_id(self) -> None:
        # Rust source: core/tests/suite/rollout_list_find.rs::find_locates_rollout_file_by_id
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            thread_id = str(uuid.uuid4())
            expected = write_minimal_rollout_with_id(home, thread_id)

            found = find_thread_path_by_id_str(home, thread_id)

        self.assertEqual(found, expected)

    def test_find_handles_gitignore_covering_codex_home_directory(self) -> None:
        # Rust source: core/tests/suite/rollout_list_find.rs::find_handles_gitignore_covering_codex_home_directory
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            codex_home = repo / ".codex"
            codex_home.mkdir()
            (repo / ".gitignore").write_text(".codex/**\n", encoding="utf-8")
            thread_id = str(uuid.uuid4())
            expected = write_minimal_rollout_with_id(codex_home, thread_id)

            found = find_thread_path_by_id_str(codex_home, thread_id)

        self.assertEqual(found, expected)

    def test_find_prefers_sqlite_path_by_id(self) -> None:
        # Rust source: core/tests/suite/rollout_list_find.rs::find_prefers_sqlite_path_by_id
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            thread_id = str(uuid.uuid4())
            db_path = home / "sessions" / "2030" / "12" / "30" / f"rollout-2030-12-30T00-00-00-{thread_id}.jsonl"
            write_minimal_rollout_with_id_at_path(db_path, thread_id)
            write_minimal_rollout_with_id(home, thread_id)
            state_db = FakeStateDb({thread_id: db_path})

            found = find_thread_path_by_id_str(home, thread_id, state_db)

        self.assertEqual(found, db_path)

    def test_find_falls_back_to_filesystem_when_sqlite_has_no_match(self) -> None:
        # Rust source: core/tests/suite/rollout_list_find.rs::find_falls_back_to_filesystem_when_sqlite_has_no_match
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            thread_id = str(uuid.uuid4())
            unrelated_id = str(uuid.uuid4())
            expected = write_minimal_rollout_with_id(home, thread_id)
            state_db = FakeStateDb({unrelated_id: home / "sessions" / "2030" / "12" / "30" / "unrelated.jsonl"})

            found = find_thread_path_by_id_str(home, thread_id, state_db)

        self.assertEqual(found, expected)

    def test_find_ignores_granular_gitignore_rules(self) -> None:
        # Rust source: core/tests/suite/rollout_list_find.rs::find_ignores_granular_gitignore_rules
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            thread_id = str(uuid.uuid4())
            expected = write_minimal_rollout_with_id(home, thread_id)
            (home / "sessions" / ".gitignore").write_text("*.jsonl\n", encoding="utf-8")

            found = find_thread_path_by_id_str(home, thread_id)

        self.assertEqual(found, expected)

    def test_find_locates_rollout_file_written_by_recorder(self) -> None:
        # Rust source: core/tests/suite/rollout_list_find.rs::find_locates_rollout_file_written_by_recorder
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            thread_id = str(uuid.uuid4())
            thread_name = "named thread"
            meta = SessionMeta(
                id=thread_id,
                timestamp="2024-01-01T00:00:00Z",
                cwd=".",
                originator="test",
                cli_version="test",
                model_provider="test-provider",
            )
            path = materialize_session_rollout(home, meta)
            assert path is not None
            append_session_index_entry(home, SessionIndexEntry(thread_id, thread_name, "2024-01-01T00:00:00Z"))

            found = find_thread_meta_by_name_str(home, thread_name)

            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found[0], path)
            self.assertEqual(found[1].meta.id, thread_id)
            self.assertIn(thread_id, path.read_text(encoding="utf-8"))

    def test_find_archived_locates_rollout_file_by_id(self) -> None:
        # Rust source: core/tests/suite/rollout_list_find.rs::find_archived_locates_rollout_file_by_id
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            thread_id = str(uuid.uuid4())
            expected = write_minimal_rollout_with_id_in_subdir(home, "archived_sessions", thread_id)

            found = find_archived_thread_path_by_id_str(home, thread_id)

        self.assertEqual(found, expected)


if __name__ == "__main__":
    unittest.main()
