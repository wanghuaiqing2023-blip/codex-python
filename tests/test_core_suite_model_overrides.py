"""Rust integration parity for ``core/tests/suite/model_overrides.rs``.

Thread settings updates are runtime/session overrides.  They must not persist
back into ``CODEX_HOME/config.toml`` and must not create the file when it is
absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.core.session.handlers import update_thread_settings
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.protocol import ReasoningEffort, ThreadSettingsOverrides


async def _apply_model_override(home: Path, *, config_contents: str | None) -> tuple[Path, InMemoryCodexSession]:
    config_path = home / "config.toml"
    if config_contents is not None:
        config_path.write_text(config_contents, encoding="utf-8")

    session = InMemoryCodexSession(cwd=home, reasoning_effort=ReasoningEffort.MEDIUM)
    await update_thread_settings(
        session,
        "settings-1",
        ThreadSettingsOverrides(
            model="o3",
            effort=ReasoningEffort.HIGH,
        ),
    )
    return config_path, session


@pytest.mark.asyncio
async def test_thread_settings_update_does_not_persist_when_config_exists(tmp_path: Path) -> None:
    """Rust: ``thread_settings_update_does_not_persist_when_config_exists``."""

    initial_contents = 'model = "gpt-4o"\n'
    config_path, session = await _apply_model_override(tmp_path, config_contents=initial_contents)

    assert config_path.read_text(encoding="utf-8") == initial_contents
    assert session.collaboration_mode.settings.model == "o3"
    assert session.reasoning_effort == ReasoningEffort.HIGH
    assert session.emitted_events[-1].type == "thread_settings_applied"


@pytest.mark.asyncio
async def test_thread_settings_update_does_not_create_config_file(tmp_path: Path) -> None:
    """Rust: ``thread_settings_update_does_not_create_config_file``."""

    config_path, session = await _apply_model_override(tmp_path, config_contents=None)

    assert not config_path.exists()
    assert session.collaboration_mode.settings.model == "o3"
    assert session.reasoning_effort == ReasoningEffort.HIGH
    assert session.emitted_events[-1].type == "thread_settings_applied"
