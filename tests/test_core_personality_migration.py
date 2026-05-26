from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from pycodex.core import (
    ARCHIVED_SESSIONS_SUBDIR,
    PERSONALITY_MIGRATION_FILENAME,
    SESSIONS_SUBDIR,
    PersonalityMigrationStatus,
    config_profile,
    has_recorded_sessions,
    maybe_migrate_personality,
    read_config_toml,
    set_top_level_toml_string,
)


TEST_TIMESTAMP = "2025-01-01T00-00-00"


def session_meta_payload(thread_id: str, model_provider: str | None = None) -> dict:
    return {
        "id": thread_id,
        "timestamp": TEST_TIMESTAMP,
        "cwd": ".",
        "originator": "test_originator",
        "cli_version": "test_version",
        "source": "cli",
        "thread_source": None,
        "agent_path": None,
        "agent_nickname": None,
        "agent_role": None,
        "model_provider": model_provider,
        "base_instructions": None,
        "dynamic_tools": None,
        "memory_mode": None,
    }


def write_rollout_with_user_event(directory: Path, thread_id: str, model_provider: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"rollout-{TEST_TIMESTAMP}-{thread_id}.jsonl"
    lines = [
        {
            "timestamp": TEST_TIMESTAMP,
            "type": "session_meta",
            "payload": session_meta_payload(thread_id, model_provider),
        },
        {
            "timestamp": TEST_TIMESTAMP,
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "hello"},
        },
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def write_session_with_user_event(codex_home: Path, model_provider: str | None = None) -> Path:
    thread_id = str(uuid.uuid4())
    directory = codex_home / SESSIONS_SUBDIR / "2025" / "01" / "01"
    return write_rollout_with_user_event(directory, thread_id, model_provider)


def write_archived_session_with_user_event(codex_home: Path, model_provider: str | None = None) -> Path:
    thread_id = str(uuid.uuid4())
    directory = codex_home / ARCHIVED_SESSIONS_SUBDIR
    return write_rollout_with_user_event(directory, thread_id, model_provider)


class PersonalityMigrationTests(unittest.TestCase):
    def test_applies_when_sessions_exist_and_no_personality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)

            status = maybe_migrate_personality(codex_home, {})

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertEqual((codex_home / PERSONALITY_MIGRATION_FILENAME).read_text(encoding="utf-8"), "v1\n")

    def test_applies_when_only_archived_sessions_exist_and_no_personality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_archived_session_with_user_event(codex_home)

            status = maybe_migrate_personality(codex_home, {})

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")

    def test_skips_when_marker_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / PERSONALITY_MIGRATION_FILENAME).write_text("v1\n", encoding="utf-8")

            status = maybe_migrate_personality(codex_home, {})

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_MARKER)
            self.assertFalse((codex_home / "config.toml").exists())

    def test_skips_when_personality_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / "config.toml").write_text('personality = "friendly"\n', encoding="utf-8")

            status = maybe_migrate_personality(codex_home, read_config_toml(codex_home))

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            self.assertEqual(read_config_toml(codex_home)["personality"], "friendly")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_skips_when_selected_profile_has_personality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            config = {
                "profile": "work",
                "profiles": {"work": {"personality": "friendly"}},
            }

            status = maybe_migrate_personality(codex_home, config)

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            self.assertFalse((codex_home / "config.toml").exists())
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_skips_when_no_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)

            status = maybe_migrate_personality(codex_home, {})

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_NO_SESSIONS)
            self.assertFalse((codex_home / "config.toml").exists())
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_has_recorded_sessions_uses_default_provider_without_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home, model_provider="anthropic")

            self.assertTrue(has_recorded_sessions(codex_home, "openai"))
            self.assertTrue(has_recorded_sessions(codex_home, "anthropic"))

    def test_config_profile_uses_override_before_top_level_profile(self) -> None:
        config = {
            "profile": "default",
            "profiles": {
                "default": {"personality": "friendly"},
                "override": {"model_provider": "anthropic"},
            },
        }

        self.assertEqual(config_profile(config), {"personality": "friendly"})
        self.assertEqual(config_profile(config, "override"), {"model_provider": "anthropic"})
        self.assertEqual(config_profile(config, "missing"), {})

    def test_set_top_level_toml_string_inserts_before_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text('[profiles.work]\nmodel = "gpt-5"\n', encoding="utf-8")

            set_top_level_toml_string(path, "personality", "pragmatic")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                'personality = "pragmatic"\n\n[profiles.work]\nmodel = "gpt-5"\n',
            )


if __name__ == "__main__":
    unittest.main()
