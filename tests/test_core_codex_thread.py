from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.core.codex_thread import (
    CodexThread,
    CodexThreadSettingsOverrides,
    InvalidThreadRequest,
    ThreadConfigSnapshot,
)
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.protocol import CollaborationMode, ModeKind, NetworkSandboxPolicy, Op, PermissionProfile, ReasoningEffort, SandboxPolicy, SessionSource, Settings


class DummySession:
    def __init__(self):
        self.pause_states = []
        self.injected = []
        self.flushed = False

    async def collaboration_mode(self):
        return SimpleNamespace(with_updates=lambda model, effort, developer_instructions: ("updated", model, effort))

    def set_out_of_band_elicitation_pause_state(self, paused):
        self.pause_states.append(paused)

    async def new_default_turn(self):
        return "turn"

    async def reference_context_item(self):
        return None

    async def record_context_updates_and_set_reference_context_item(self, turn_context):
        self.reference = turn_context

    async def inject_no_new_turn(self, items, turn_context):
        self.injected.append((items, turn_context))

    async def flush_rollout(self):
        self.flushed = True


class DummyCodex:
    def __init__(self):
        self.session = DummySession()
        self.submitted = []

    async def submit(self, op):
        self.submitted.append(op)
        return "sub-1"

    async def submit_with_trace(self, op, trace):
        self.submitted.append((op, trace))
        return "sub-trace"

    async def shutdown_and_wait(self):
        self.shutdown = True


def test_thread_config_snapshot_normalizes_paths():
    snapshot = ThreadConfigSnapshot(
        model="gpt-5",
        model_provider_id="openai",
        cwd=".",
        workspace_roots=["."],
        session_source=SessionSource.cli(),
    )

    assert isinstance(snapshot.cwd, Path)
    assert snapshot.workspace_roots == (Path("."),)


def test_thread_config_snapshot_sandbox_policy_uses_permission_profile():
    # Rust source: codex-rs/core/src/codex_thread.rs
    # Behavior anchor: ThreadConfigSnapshot::sandbox_policy derives the legacy
    # SandboxPolicy from the required PermissionProfile and cwd.
    profile = PermissionProfile.workspace_write(
        (Path("C:/work/project"),),
        network=NetworkSandboxPolicy.ENABLED,
    )
    snapshot = ThreadConfigSnapshot(
        model="gpt-5",
        model_provider_id="openai",
        cwd=Path("C:/work/project/subdir"),
        permission_profile=profile,
        session_source=SessionSource.cli(),
    )

    assert snapshot.sandbox_policy() == profile.to_legacy_sandbox_policy(snapshot.cwd)
    assert snapshot.sandbox_policy() == SandboxPolicy.workspace_write((Path("C:/work/project"),), network_access=True)


def test_thread_config_snapshot_sandbox_policy_requires_permission_profile():
    snapshot = ThreadConfigSnapshot(
        model="gpt-5",
        model_provider_id="openai",
        cwd=Path("C:/work/project"),
        session_source=SessionSource.cli(),
    )

    with pytest.raises(TypeError, match="permission_profile is required"):
        snapshot.sandbox_policy()


@pytest.mark.asyncio
async def test_codex_thread_delegates_submit_and_trace():
    codex = DummyCodex()
    thread = CodexThread(codex, session_configured={"ok": True}, session_source=SessionSource.cli())

    assert await thread.submit(Op("noop", {})) == "sub-1"
    assert await thread.submit_with_trace(Op("trace", {}), None) == "sub-trace"
    assert codex.submitted[0].type == "noop"


@pytest.mark.asyncio
async def test_thread_settings_update_derives_collaboration_mode():
    thread = CodexThread(DummyCodex(), session_configured=None)

    update = await thread.thread_settings_update(CodexThreadSettingsOverrides(model="gpt-5", effort="high"))

    assert update.collaboration_mode == ("updated", "gpt-5", "high")


@pytest.mark.asyncio
async def test_thread_settings_update_synthesizes_collaboration_mode_for_in_memory_session():
    session = InMemoryCodexSession(cwd="C:/work/project")
    thread = CodexThread(SimpleNamespace(session=session), session_configured={"model": "gpt-base"})

    update = await thread.thread_settings_update(
        CodexThreadSettingsOverrides(model="gpt-5.2-codex", effort=ReasoningEffort.HIGH)
    )

    assert update.collaboration_mode.mode == ModeKind.DEFAULT
    assert update.collaboration_mode.settings.model == "gpt-5.2-codex"
    assert update.collaboration_mode.settings.reasoning_effort == ReasoningEffort.HIGH


@pytest.mark.asyncio
async def test_thread_settings_update_uses_in_memory_session_collaboration_mode_field():
    session = InMemoryCodexSession(
        cwd="C:/work/project",
        collaboration_mode=CollaborationMode(
            mode=ModeKind.DEFAULT,
            settings=Settings(model="gpt-current", developer_instructions="keep this"),
        ),
    )
    thread = CodexThread(SimpleNamespace(session=session), session_configured={"model": "gpt-base"})

    update = await thread.thread_settings_update(CodexThreadSettingsOverrides(effort=ReasoningEffort.HIGH))

    assert update.collaboration_mode.mode == ModeKind.DEFAULT
    assert update.collaboration_mode.settings.model == "gpt-current"
    assert update.collaboration_mode.settings.reasoning_effort == ReasoningEffort.HIGH
    assert update.collaboration_mode.settings.developer_instructions == "keep this"


@pytest.mark.asyncio
async def test_inject_response_items_rejects_empty_and_flushes_non_empty():
    codex = DummyCodex()
    thread = CodexThread(codex, session_configured=None)

    with pytest.raises(InvalidThreadRequest):
        await thread.inject_response_items([])

    await thread.inject_response_items([{"item": 1}])

    assert codex.session.injected == [([{"item": 1}], "turn")]
    assert codex.session.flushed is True


@pytest.mark.asyncio
async def test_inject_response_items_works_with_in_memory_session():
    session = InMemoryCodexSession(cwd="C:/work/project")
    codex = SimpleNamespace(session=session)
    thread = CodexThread(codex, session_configured=None)
    item = {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": "injected"}],
    }

    await thread.inject_response_items([item])

    assert session.context_updates_recorded == 1
    assert await session.reference_context_item() is not None
    assert session.flush_rollout_count == 1
    assert session.history[-1].role == "user"
    assert session.history[-1].content[0].text == "injected"


@pytest.mark.asyncio
async def test_out_of_band_elicitation_count_toggles_pause_state():
    codex = DummyCodex()
    thread = CodexThread(codex, session_configured=None)

    assert await thread.increment_out_of_band_elicitation_count() == 1
    assert await thread.increment_out_of_band_elicitation_count() == 2
    assert await thread.decrement_out_of_band_elicitation_count() == 1
    assert await thread.decrement_out_of_band_elicitation_count() == 0

    assert codex.session.pause_states == [True, False]


@pytest.mark.asyncio
async def test_decrement_out_of_band_elicitation_count_rejects_zero():
    thread = CodexThread(DummyCodex(), session_configured=None)

    with pytest.raises(InvalidThreadRequest):
        await thread.decrement_out_of_band_elicitation_count()

