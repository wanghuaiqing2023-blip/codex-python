# Parity source: codex-rs/tui/src/session_resume.rs

import uuid
from dataclasses import dataclass

import pytest

from pycodex.tui.session_resume import (
    ResolveCwdOutcome,
    ResolveCwdOutcomeKind,
    cwds_differ,
    read_rollout_resume_state,
    read_session_cwd,
    read_session_model,
    resolve_cwd_for_resume_or_fork,
    resolve_session_thread_id,
    rollout_line,
    write_rollout_lines,
)


@dataclass
class Metadata:
    cwd: str
    model: str | None = None


class StateDb:
    def __init__(self, metadata=None):
        self.metadata = metadata

    async def get_thread(self, thread_id):
        return self.metadata


class PromptTui:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def run_cwd_selection_prompt(self, action, current_cwd, history_cwd):
        self.calls.append((action, current_cwd, history_cwd))
        return self.outcome


@pytest.mark.asyncio
async def test_rollout_resume_state_prefers_latest_turn_context(tmp_path):
    thread_id = str(uuid.uuid4())
    original = tmp_path / "original"
    latest = tmp_path / "latest"
    rollout_path = tmp_path / "rollout.jsonl"
    write_rollout_lines(
        rollout_path,
        [
            rollout_line("t0", "session_meta", {"id": thread_id, "cwd": original}),
            rollout_line("t1", "turn_context", {"cwd": tmp_path / "middle", "model": "middle"}),
            rollout_line("t2", "turn_context", {"cwd": latest, "model": "latest"}),
        ],
    )

    state = await read_rollout_resume_state(rollout_path)

    assert state.thread_id == thread_id
    assert state.cwd == latest
    assert state.model == "latest"


@pytest.mark.asyncio
async def test_rollout_resume_state_falls_back_to_session_meta(tmp_path):
    thread_id = str(uuid.uuid4())
    cwd = tmp_path / "session"
    rollout_path = tmp_path / "rollout.jsonl"
    write_rollout_lines(rollout_path, [rollout_line("t0", "session_meta", {"id": thread_id, "cwd": cwd})])

    state = await read_rollout_resume_state(rollout_path)

    assert state.thread_id == thread_id
    assert state.cwd == cwd
    assert state.model is None


@pytest.mark.asyncio
async def test_rollout_resume_state_skips_malformed_lines(tmp_path):
    thread_id = str(uuid.uuid4())
    cwd = tmp_path / "session"
    rollout_path = tmp_path / "rollout.jsonl"
    write_rollout_lines(rollout_path, [rollout_line("t0", "session_meta", {"id": thread_id, "cwd": cwd})])
    with rollout_path.open("a", encoding="utf-8") as file:
        file.write("{\n")

    state = await read_rollout_resume_state(rollout_path)

    assert state.thread_id == thread_id
    assert state.cwd == cwd


@pytest.mark.asyncio
async def test_read_rollout_resume_state_errors_when_no_records(tmp_path):
    rollout_path = tmp_path / "empty.jsonl"
    rollout_path.write_text("\n   \n", encoding="utf-8")

    with pytest.raises(OSError, match="is empty"):
        await read_rollout_resume_state(rollout_path)


@pytest.mark.asyncio
async def test_resolve_session_thread_id_prefers_explicit_uuid(tmp_path):
    explicit = str(uuid.uuid4())
    rollout = tmp_path / "missing.jsonl"

    assert await resolve_session_thread_id(rollout, explicit) == explicit
    assert await resolve_session_thread_id(rollout, "not-a-uuid") is None


@pytest.mark.asyncio
async def test_read_session_model_prefers_state_db_then_rollout(tmp_path):
    thread_id = str(uuid.uuid4())
    rollout = tmp_path / "rollout.jsonl"
    write_rollout_lines(rollout, [rollout_line("t1", "turn_context", {"cwd": tmp_path, "model": "rollout"})])

    assert await read_session_model(StateDb(Metadata(str(tmp_path), "db-model")), thread_id, rollout) == "db-model"
    assert await read_session_model(None, thread_id, rollout) == "rollout"


@pytest.mark.asyncio
async def test_read_session_cwd_prefers_state_db_then_rollout(tmp_path):
    thread_id = str(uuid.uuid4())
    rollout_cwd = tmp_path / "rollout"
    db_cwd = tmp_path / "db"
    rollout = tmp_path / "rollout.jsonl"
    write_rollout_lines(rollout, [rollout_line("t0", "session_meta", {"id": thread_id, "cwd": rollout_cwd})])

    assert await read_session_cwd(StateDb(Metadata(str(db_cwd))), thread_id, rollout) == db_cwd
    assert await read_session_cwd(None, thread_id, rollout) == rollout_cwd


@pytest.mark.asyncio
async def test_resolve_cwd_for_resume_or_fork_prompts_when_allowed_and_cwds_differ(tmp_path):
    thread_id = str(uuid.uuid4())
    current = tmp_path / "current"
    session = tmp_path / "session"
    tui = PromptTui("session")

    outcome = await resolve_cwd_for_resume_or_fork(
        tui,
        StateDb(Metadata(str(session))),
        current,
        thread_id,
        None,
        "resume",
        True,
    )

    assert outcome == ResolveCwdOutcome.Continue(session)
    assert tui.calls


@pytest.mark.asyncio
async def test_resolve_cwd_for_resume_or_fork_without_history_continues_none(tmp_path):
    outcome = await resolve_cwd_for_resume_or_fork(
        PromptTui("session"),
        None,
        tmp_path / "current",
        str(uuid.uuid4()),
        None,
        "resume",
        True,
    )

    assert outcome == ResolveCwdOutcome.Continue(None)


@pytest.mark.asyncio
async def test_resolve_cwd_for_resume_or_fork_uses_history_without_prompt_when_disallowed(tmp_path):
    thread_id = str(uuid.uuid4())
    current = tmp_path / "current"
    session = tmp_path / "session"
    tui = PromptTui("current")

    outcome = await resolve_cwd_for_resume_or_fork(
        tui,
        StateDb(Metadata(str(session))),
        current,
        thread_id,
        None,
        "resume",
        False,
    )

    assert outcome == ResolveCwdOutcome.Continue(session)
    assert tui.calls == []


@pytest.mark.asyncio
async def test_resolve_cwd_for_resume_or_fork_exit_selection(tmp_path):
    thread_id = str(uuid.uuid4())
    tui = PromptTui("exit")

    outcome = await resolve_cwd_for_resume_or_fork(
        tui,
        StateDb(Metadata(str(tmp_path / "session"))),
        tmp_path / "current",
        thread_id,
        None,
        "resume",
        True,
    )

    assert outcome.kind == ResolveCwdOutcomeKind.EXIT


def test_cwds_differ_uses_normalized_paths(tmp_path):
    assert cwds_differ(tmp_path / "a" / ".." / "b", tmp_path / "b") is False
    assert cwds_differ(tmp_path / "a", tmp_path / "b") is True
