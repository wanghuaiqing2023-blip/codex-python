
"""Parity tests for Rust core/tests/suite/personality_migration.rs."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pycodex.core import PERSONALITY_MIGRATION_FILENAME, PersonalityMigrationStatus, maybe_migrate_personality, read_config_toml
from tests.test_core_personality_migration import (
    SESSIONS_SUBDIR,
    write_archived_session_with_user_event,
    write_rollout_with_meta_only,
    write_session_with_user_event,
)


def test_migration_marker_exists_no_sessions_no_change() -> None:
    """Rust test: migration_marker_exists_no_sessions_no_change."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        (home / PERSONALITY_MIGRATION_FILENAME).write_text("v1\n", encoding="utf-8")

        status = maybe_migrate_personality(home, {})

        assert status is PersonalityMigrationStatus.SKIPPED_MARKER
        assert not (home / "config.toml").exists()


def test_no_marker_no_sessions_no_change() -> None:
    """Rust test: no_marker_no_sessions_no_change."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)

        status = maybe_migrate_personality(home, {})

        assert status is PersonalityMigrationStatus.SKIPPED_NO_SESSIONS
        assert (home / PERSONALITY_MIGRATION_FILENAME).exists()
        assert not (home / "config.toml").exists()


def test_no_marker_sessions_sets_personality() -> None:
    """Rust test: no_marker_sessions_sets_personality."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        write_session_with_user_event(home)

        status = maybe_migrate_personality(home, {})

        assert status is PersonalityMigrationStatus.APPLIED
        assert (home / PERSONALITY_MIGRATION_FILENAME).exists()
        assert read_config_toml(home)["personality"] == "pragmatic"


def test_no_marker_sessions_preserves_existing_config_fields() -> None:
    """Rust test: no_marker_sessions_preserves_existing_config_fields."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        write_session_with_user_event(home)
        (home / "config.toml").write_text('model = "gpt-5.4"\n', encoding="utf-8")

        status = maybe_migrate_personality(home, read_config_toml(home))
        config = read_config_toml(home)

        assert status is PersonalityMigrationStatus.APPLIED
        assert config["model"] == "gpt-5.4"
        assert config["personality"] == "pragmatic"


def test_no_marker_meta_only_rollout_is_treated_as_no_sessions() -> None:
    """Rust test: no_marker_meta_only_rollout_is_treated_as_no_sessions."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        directory = home / SESSIONS_SUBDIR / "2025" / "01" / "01"
        write_rollout_with_meta_only(directory, "thread-meta-only")

        status = maybe_migrate_personality(home, {})

        assert status is PersonalityMigrationStatus.SKIPPED_NO_SESSIONS
        assert (home / PERSONALITY_MIGRATION_FILENAME).exists()
        assert not (home / "config.toml").exists()


def test_no_marker_explicit_global_personality_skips_migration() -> None:
    """Rust test: no_marker_explicit_global_personality_skips_migration."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        write_session_with_user_event(home)
        config = {"personality": "friendly"}

        status = maybe_migrate_personality(home, config)

        assert status is PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY
        assert (home / PERSONALITY_MIGRATION_FILENAME).exists()
        assert not (home / "config.toml").exists()


def test_no_marker_profile_personality_does_not_skip_migration() -> None:
    """Rust test: no_marker_profile_personality_does_not_skip_migration."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        write_session_with_user_event(home)
        config = {"profile": "work", "profiles": {"work": {"personality": "friendly"}}}

        status = maybe_migrate_personality(home, config)

        assert status is PersonalityMigrationStatus.APPLIED
        assert read_config_toml(home)["personality"] == "pragmatic"
        assert (home / PERSONALITY_MIGRATION_FILENAME).exists()


def test_marker_short_circuits_migration_with_legacy_profile() -> None:
    """Rust test: marker_short_circuits_migration_with_legacy_profile."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        (home / PERSONALITY_MIGRATION_FILENAME).write_text("v1\n", encoding="utf-8")

        status = maybe_migrate_personality(home, {"profile": "missing"})

        assert status is PersonalityMigrationStatus.SKIPPED_MARKER


def test_missing_legacy_profile_does_not_block_migration() -> None:
    """Rust test: missing_legacy_profile_does_not_block_migration."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)

        status = maybe_migrate_personality(home, {"profile": "missing"})

        assert status is PersonalityMigrationStatus.SKIPPED_NO_SESSIONS
        assert (home / PERSONALITY_MIGRATION_FILENAME).exists()


def test_applied_migration_is_idempotent_on_second_run() -> None:
    """Rust test: applied_migration_is_idempotent_on_second_run."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        write_session_with_user_event(home)

        first = maybe_migrate_personality(home, {})
        second = maybe_migrate_personality(home, {})

        assert first is PersonalityMigrationStatus.APPLIED
        assert second is PersonalityMigrationStatus.SKIPPED_MARKER
        assert read_config_toml(home)["personality"] == "pragmatic"


def test_no_marker_archived_sessions_sets_personality() -> None:
    """Rust test: no_marker_archived_sessions_sets_personality."""

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        write_archived_session_with_user_event(home)

        status = maybe_migrate_personality(home, {})

        assert status is PersonalityMigrationStatus.APPLIED
        assert (home / PERSONALITY_MIGRATION_FILENAME).exists()
        assert read_config_toml(home)["personality"] == "pragmatic"
