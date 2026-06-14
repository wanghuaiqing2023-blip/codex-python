"""Suite parity tests for ``codex-rs/core/tests/suite/override_updates.rs``."""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.core.session.handlers import update_thread_settings
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.protocol import (
    AskForApproval,
    CollaborationMode,
    ModeKind,
    PermissionProfile,
    Settings,
    ThreadSettingsOverrides,
)


def _collab_mode_with_instructions(instructions: str | None) -> CollaborationMode:
    return CollaborationMode(
        mode=ModeKind.DEFAULT,
        settings=Settings(model="gpt-5.4", reasoning_effort=None, developer_instructions=instructions),
    )


async def _apply_thread_settings_without_user_turn(session: InMemoryCodexSession, overrides: ThreadSettingsOverrides) -> None:
    await update_thread_settings(session, "settings-override", overrides)
    assert session.emitted_events[-1].type == "thread_settings_applied"


@pytest.mark.asyncio
async def test_thread_settings_update_without_user_turn_does_not_record_permissions_update(tmp_path: Path) -> None:
    """Rust test: ``thread_settings_update_without_user_turn_does_not_record_permissions_update``."""

    session = InMemoryCodexSession(
        cwd=tmp_path,
        approval_policy=AskForApproval.ON_REQUEST,
        permission_profile=PermissionProfile.disabled(),
    )

    await _apply_thread_settings_without_user_turn(
        session,
        ThreadSettingsOverrides(approval_policy=AskForApproval.NEVER),
    )

    assert session.approval_policy == AskForApproval.NEVER
    assert session.context_updates_recorded == 0
    assert session.recorded_batches == []
    assert session.history == []
    assert session.flush_rollout_count == 0


@pytest.mark.asyncio
async def test_thread_settings_update_without_user_turn_does_not_record_environment_update(tmp_path: Path) -> None:
    """Rust test: ``thread_settings_update_without_user_turn_does_not_record_environment_update``."""

    new_cwd = tmp_path / "new_cwd"
    new_cwd.mkdir()
    session = InMemoryCodexSession(cwd=tmp_path)

    await _apply_thread_settings_without_user_turn(
        session,
        ThreadSettingsOverrides(cwd=new_cwd),
    )

    assert session.cwd == new_cwd
    assert session.context_updates_recorded == 0
    assert session.recorded_batches == []
    assert session.history == []
    assert session.flush_rollout_count == 0


@pytest.mark.asyncio
async def test_thread_settings_update_without_user_turn_does_not_record_collaboration_update(tmp_path: Path) -> None:
    """Rust test: ``thread_settings_update_without_user_turn_does_not_record_collaboration_update``."""

    session = InMemoryCodexSession(cwd=tmp_path)
    collaboration_mode = _collab_mode_with_instructions("override collaboration instructions")

    await _apply_thread_settings_without_user_turn(
        session,
        ThreadSettingsOverrides(collaboration_mode=collaboration_mode),
    )

    assert session.collaboration_mode == collaboration_mode
    assert session.context_updates_recorded == 0
    assert session.recorded_batches == []
    assert session.history == []
    assert session.flush_rollout_count == 0
