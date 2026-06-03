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

    def test_marker_takes_precedence_even_with_override_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            (codex_home / PERSONALITY_MIGRATION_FILENAME).write_text("v1\n", encoding="utf-8")

            status = maybe_migrate_personality(
                codex_home,
                None,
                override_profile="default",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_MARKER)
            self.assertFalse((codex_home / "config.toml").exists())

    def test_marker_takes_precedence_even_without_config_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / PERSONALITY_MIGRATION_FILENAME).write_text("v1\n", encoding="utf-8")

            status = maybe_migrate_personality(codex_home, None)

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

    def test_profile_personality_no_longer_blocks_current_upstream_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            config = {
                "profile": "work",
                "profiles": {"work": {"personality": "friendly"}},
            }

            status = maybe_migrate_personality(codex_home, config)

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_override_profile_personality_blocks_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            config = {
                "profile": "default",
                "profiles": {"default": {"personality": "friendly"}},
            }

            status = maybe_migrate_personality(codex_home, config, override_profile="default")

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            self.assertEqual(read_config_toml(codex_home), {})
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_override_profile_missing_profile_falls_back_to_top_level_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            config = {"personality": "friendly"}

            status = maybe_migrate_personality(
                codex_home,
                config,
                override_profile="missing-profile",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            self.assertEqual(read_config_toml(codex_home), {})
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_override_profile_missing_profile_allows_migration_by_top_level_logic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            config = {}

            status = maybe_migrate_personality(
                codex_home,
                config,
                override_profile="missing-profile",
            )

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_empty_profile_does_not_block_personality_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            config = {
                "profile": "default",
                "profiles": {"default": {}},
            }

            status = maybe_migrate_personality(codex_home, config, override_profile="default")

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_blank_override_profile_uses_top_level_profile_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            config = {
                "profiles": {"default": {"personality": "friendly"}},
            }

            status = maybe_migrate_personality(
                codex_home,
                config,
                override_profile="",
            )

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_override_profile_from_disk_config_respects_disk_top_level_personality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            (codex_home / "config.toml").write_text(
                'personality = "friendly"\n[profiles.default]\nmodel_provider = "anthropic"\n',
                encoding="utf-8",
            )

            status = maybe_migrate_personality(
                codex_home,
                None,
                override_profile="default",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            migrated_config = read_config_toml(codex_home)
            self.assertEqual(migrated_config["personality"], "friendly")
            self.assertEqual(migrated_config["profiles"]["default"]["model_provider"], "anthropic")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_model_provider_setting_does_not_block_migration_when_sessions_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home, model_provider="openai")
            config = {
                "model_provider": "anthropic",
            }

            status = maybe_migrate_personality(codex_home, config)

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_model_provider_setting_respects_no_sessions_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            config = {
                "model_provider": "anthropic",
            }

            status = maybe_migrate_personality(codex_home, config)

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_NO_SESSIONS)
            self.assertFalse((codex_home / "config.toml").exists())
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_missing_override_profile_respects_model_provider_without_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            config = {"model_provider": "anthropic"}

            status = maybe_migrate_personality(
                codex_home,
                config,
                override_profile="missing-profile",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_NO_SESSIONS)
            self.assertFalse((codex_home / "config.toml").exists())
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_missing_override_profile_respects_model_provider_with_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            config = {"model_provider": "anthropic"}

            status = maybe_migrate_personality(
                codex_home,
                config,
                override_profile="missing-profile",
            )

            self.assertEqual(status, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_override_profile_from_disk_config_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            (codex_home / "config.toml").write_text(
                "[profiles.default]\npersonality = \"friendly\"\n",
                encoding="utf-8",
            )

            status = maybe_migrate_personality(
                codex_home,
                None,
                override_profile="default",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            migrated_config = read_config_toml(codex_home)
            self.assertNotIn("personality", migrated_config)
            self.assertEqual(migrated_config["profiles"]["default"]["personality"], "friendly")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_top_level_personality_blocks_even_with_override_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            (codex_home / "config.toml").write_text(
                'personality = "friendly"\n[profiles.default]\npersonality = "concise"\n',
                encoding="utf-8",
            )

            status = maybe_migrate_personality(
                codex_home,
                None,
                override_profile="default",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            migrated_config = read_config_toml(codex_home)
            self.assertEqual(migrated_config["personality"], "friendly")
            self.assertEqual(migrated_config["profiles"]["default"]["personality"], "concise")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_top_level_personality_blocks_blank_override_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)
            (codex_home / "config.toml").write_text('personality = "friendly"\n', encoding="utf-8")

            status = maybe_migrate_personality(
                codex_home,
                read_config_toml(codex_home),
                override_profile="",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY)
            self.assertEqual(read_config_toml(codex_home)["personality"], "friendly")
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_override_profile_missing_profile_still_skips_without_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            config = {}

            status = maybe_migrate_personality(
                codex_home,
                config,
                override_profile="missing-profile",
            )

            self.assertEqual(status, PersonalityMigrationStatus.SKIPPED_NO_SESSIONS)
            self.assertFalse((codex_home / "config.toml").exists())
            self.assertTrue((codex_home / PERSONALITY_MIGRATION_FILENAME).exists())

    def test_config_profile_with_non_mapping_profiles_returns_empty(self) -> None:
        config = {
            "profile": "work",
            "profiles": "not-a-dict",
        }

        self.assertEqual(config_profile(config), {})
        self.assertEqual(config_profile(config, "work"), {})

    def test_config_profile_with_non_mapping_profile_entry_returns_empty(self) -> None:
        config = {
            "profile": "work",
            "profiles": {"work": "not-a-dict"},
        }

        self.assertEqual(config_profile(config), {})
        self.assertEqual(config_profile(config, "work"), {})

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

    def test_non_string_override_profile_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            with self.assertRaises(TypeError):
                config_profile({"profile": "default", "profiles": {}}, 1)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                maybe_migrate_personality(codex_home, {"profile": "default", "profiles": {}}, override_profile=1)


    def test_personality_migration_rejects_implicit_coercions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            with self.assertRaises(TypeError):
                maybe_migrate_personality(codex_home, [])
            with self.assertRaises(TypeError):
                maybe_migrate_personality(codex_home, {"model_provider": 123})
            with self.assertRaises(TypeError):
                has_recorded_sessions(codex_home, 123)
            with self.assertRaises(TypeError):
                set_top_level_toml_string(codex_home / "config.toml", 123, "value")
            with self.assertRaises(TypeError):
                set_top_level_toml_string(codex_home / "config.toml", "key", 123)

    def test_set_top_level_toml_string_inserts_before_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text('[profiles.work]\nmodel = "gpt-5"\n', encoding="utf-8")

            set_top_level_toml_string(path, "personality", "pragmatic")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                'personality = "pragmatic"\n\n[profiles.work]\nmodel = "gpt-5"\n',
            )

    def test_migration_is_idempotent_and_marked_subsequent_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            write_session_with_user_event(codex_home)

            first = maybe_migrate_personality(codex_home, {})
            second = maybe_migrate_personality(codex_home, {})

            self.assertEqual(first, PersonalityMigrationStatus.APPLIED)
            self.assertEqual(second, PersonalityMigrationStatus.SKIPPED_MARKER)
            self.assertEqual(read_config_toml(codex_home)["personality"], "pragmatic")
            self.assertEqual((codex_home / PERSONALITY_MIGRATION_FILENAME).read_text(encoding="utf-8"), "v1\n")


if __name__ == "__main__":
    unittest.main()
