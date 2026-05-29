from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.core.codex_thread import (
    CodexThread,
    CodexThreadSettingsOverrides,
    InvalidThreadRequest,
    ThreadConfigSnapshot,
)
from pycodex.protocol import Op, SessionSource


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
async def test_inject_response_items_rejects_empty_and_flushes_non_empty():
    codex = DummyCodex()
    thread = CodexThread(codex, session_configured=None)

    with pytest.raises(InvalidThreadRequest):
        await thread.inject_response_items([])

    await thread.inject_response_items([{"item": 1}])

    assert codex.session.injected == [([{"item": 1}], "turn")]
    assert codex.session.flushed is True


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
