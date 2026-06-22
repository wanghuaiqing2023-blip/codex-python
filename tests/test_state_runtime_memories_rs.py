import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pycodex.protocol import ThreadId
from pycodex.state.model import (
    Phase2JobClaimOutcome,
    Phase2JobClaimed,
    Stage1JobClaimOutcome,
    Stage1JobClaimed,
    Stage1StartupClaimParams,
)
from pycodex.state.runtime.memories import (
    JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL,
    JOB_KIND_MEMORY_STAGE1,
    MEMORY_CONSOLIDATION_JOB_KEY,
    MemoryStore,
)


def _run(coro):
    return asyncio.run(coro)


def _thread_id(value: int) -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{value:012d}")


def _dt(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _connect_pair() -> tuple[sqlite3.Connection, sqlite3.Connection]:
    memory = sqlite3.connect(":memory:")
    state = sqlite3.connect(":memory:")
    _create_memory_schema(memory)
    _create_state_schema(state)
    return memory, state


def _create_memory_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE stage1_outputs (
            thread_id TEXT PRIMARY KEY,
            source_updated_at INTEGER NOT NULL,
            raw_memory TEXT NOT NULL,
            rollout_summary TEXT NOT NULL,
            rollout_slug TEXT,
            generated_at INTEGER NOT NULL,
            usage_count INTEGER NOT NULL DEFAULT 0,
            last_usage INTEGER,
            selected_for_phase2 INTEGER NOT NULL DEFAULT 0,
            selected_for_phase2_source_updated_at INTEGER
        );

        CREATE TABLE jobs (
            kind TEXT NOT NULL,
            job_key TEXT NOT NULL,
            status TEXT NOT NULL,
            worker_id TEXT,
            ownership_token TEXT,
            started_at INTEGER,
            finished_at INTEGER,
            lease_until INTEGER,
            retry_at INTEGER,
            retry_remaining INTEGER NOT NULL DEFAULT 3,
            last_error TEXT,
            input_watermark INTEGER,
            last_success_watermark INTEGER,
            PRIMARY KEY (kind, job_key)
        );
        """
    )


def _create_state_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT NOT NULL,
            created_at_ms INTEGER NOT NULL,
            updated_at_ms INTEGER NOT NULL,
            source TEXT NOT NULL,
            thread_source TEXT,
            agent_nickname TEXT,
            agent_role TEXT,
            agent_path TEXT,
            model_provider TEXT NOT NULL,
            model TEXT,
            reasoning_effort TEXT,
            cwd TEXT NOT NULL,
            cli_version TEXT NOT NULL,
            title TEXT NOT NULL,
            preview TEXT NOT NULL,
            sandbox_policy TEXT NOT NULL,
            approval_mode TEXT NOT NULL,
            tokens_used INTEGER NOT NULL,
            first_user_message TEXT NOT NULL,
            archived_at INTEGER,
            git_sha TEXT,
            git_branch TEXT,
            git_origin_url TEXT,
            memory_mode TEXT NOT NULL DEFAULT 'enabled',
            archived INTEGER NOT NULL DEFAULT 0
        );
        """
    )


def _insert_thread(
    connection: sqlite3.Connection,
    thread_id: ThreadId,
    *,
    updated_ms: int = 100_000,
    created_ms: int = 90_000,
    source: str = "cli",
    memory_mode: str = "enabled",
    archived: int = 0,
    preview: str = "preview",
    git_branch: str | None = "main",
) -> None:
    connection.execute(
        """
        INSERT INTO threads (
            id, rollout_path, created_at_ms, updated_at_ms, source, thread_source,
            agent_nickname, agent_role, agent_path, model_provider, model,
            reasoning_effort, cwd, cli_version, title, preview, sandbox_policy,
            approval_mode, tokens_used, first_user_message, archived_at, git_sha,
            git_branch, git_origin_url, memory_mode, archived
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?, ?)
        """,
        (
            str(thread_id),
            str(Path("rollouts") / f"{thread_id}.jsonl"),
            created_ms,
            updated_ms,
            source,
            "test-provider",
            "gpt-test",
            "medium",
            str(Path.cwd()),
            "pycodex-test",
            f"title-{thread_id}",
            preview,
            "workspace-write",
            "on-request",
            12,
            "first user message",
            git_branch,
            memory_mode,
            archived,
        ),
    )
    connection.commit()


def _insert_output(
    connection: sqlite3.Connection,
    thread_id: ThreadId,
    *,
    source_updated_at: int,
    raw_memory: str = "memory",
    rollout_summary: str = "summary",
    rollout_slug: str | None = None,
    generated_at: int = 70,
    usage_count: int = 0,
    last_usage: int | None = None,
    selected_for_phase2: int = 0,
    selected_source_updated_at: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO stage1_outputs (
            thread_id, source_updated_at, raw_memory, rollout_summary, rollout_slug,
            generated_at, usage_count, last_usage, selected_for_phase2,
            selected_for_phase2_source_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(thread_id),
            source_updated_at,
            raw_memory,
            rollout_summary,
            rollout_slug,
            generated_at,
            usage_count,
            last_usage,
            selected_for_phase2,
            selected_source_updated_at,
        ),
    )
    connection.commit()


def _job(connection: sqlite3.Connection, kind: str, job_key: str = MEMORY_CONSOLIDATION_JOB_KEY) -> sqlite3.Row | None:
    old_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute("SELECT * FROM jobs WHERE kind = ? AND job_key = ?", (kind, job_key)).fetchone()
    finally:
        connection.row_factory = old_factory


def test_stage1_claim_skips_when_source_is_up_to_date_and_claims_stale_thread():
    # Rust: codex-state/src/runtime/memories.rs stage1_claim_skips_when_up_to_date.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    thread = _thread_id(1)
    worker = _thread_id(99)
    _insert_thread(state, thread)
    _insert_output(memory, thread, source_updated_at=200)

    assert _run(store.stage1_source_needs_update(thread, 199)) is False
    assert _run(store.try_claim_stage1_job(thread, worker, 199, 30, 1)) is Stage1JobClaimOutcome.SKIPPED_UP_TO_DATE

    claim = _run(store.try_claim_stage1_job(thread, worker, 201, 30, 1))
    assert isinstance(claim, Stage1JobClaimed)
    row = _job(memory, JOB_KIND_MEMORY_STAGE1, str(thread))
    assert row is not None
    assert row["status"] == "running"
    assert row["input_watermark"] == 201


def test_stage1_success_persists_output_hydrates_global_list_and_enqueues_phase2():
    # Rust: mark_stage1_job_succeeded persists stage1 output and enqueues global consolidation.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    thread = _thread_id(2)
    worker = _thread_id(99)
    _insert_thread(state, thread, updated_ms=210_000)

    claim = _run(store.try_claim_stage1_job(thread, worker, 210, 30, 1))
    assert isinstance(claim, Stage1JobClaimed)
    assert _run(store.mark_stage1_job_succeeded(thread, claim.ownership_token, 210, "remember this", "rollout summary", "slug")) is True

    outputs = _run(store.list_stage1_outputs_for_global(10))
    assert [output.thread_id for output in outputs] == [thread]
    assert outputs[0].raw_memory == "remember this"
    assert outputs[0].rollout_summary == "rollout summary"
    assert outputs[0].rollout_slug == "slug"
    assert outputs[0].source_updated_at == _dt(210)

    phase2 = _job(memory, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL)
    assert phase2 is not None
    assert phase2["status"] == "pending"
    assert phase2["input_watermark"] == 210


def test_stage1_no_output_deletes_existing_output_and_enqueues_phase2():
    # Rust: mark_stage1_job_succeeded_no_output deletes any stale stage1 output and wakes phase2.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    thread = _thread_id(3)
    worker = _thread_id(99)
    _insert_thread(state, thread)
    _insert_output(memory, thread, source_updated_at=300, selected_for_phase2=1, selected_source_updated_at=300)

    claim = _run(store.try_claim_stage1_job(thread, worker, 301, 30, 1))
    assert isinstance(claim, Stage1JobClaimed)
    assert _run(store.mark_stage1_job_succeeded_no_output(thread, claim.ownership_token)) is True

    assert memory.execute("SELECT COUNT(*) FROM stage1_outputs WHERE thread_id = ?", (str(thread),)).fetchone()[0] == 0
    assert _job(memory, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL)["input_watermark"] == 301


def test_usage_phase2_selection_retention_and_disabled_thread_filtering():
    # Rust: get_phase2_input_selection ranks live enabled outputs; retention prunes only unselected stale rows.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    enabled = _thread_id(4)
    older = _thread_id(5)
    disabled = _thread_id(6)
    selected = _thread_id(7)
    _insert_thread(state, enabled, updated_ms=400_000)
    _insert_thread(state, older, updated_ms=350_000)
    _insert_thread(state, disabled, updated_ms=300_000, memory_mode="disabled")
    _insert_thread(state, selected, updated_ms=250_000)
    _insert_output(memory, enabled, source_updated_at=400, usage_count=1, last_usage=900)
    _insert_output(memory, older, source_updated_at=100, usage_count=0, last_usage=None)
    _insert_output(memory, disabled, source_updated_at=800, usage_count=10, last_usage=950)
    _insert_output(memory, selected, source_updated_at=50, selected_for_phase2=1, selected_source_updated_at=50)

    assert _run(store.record_stage1_output_usage([enabled, _thread_id(404)])) == 1
    selection = _run(store.get_phase2_input_selection(10, 36_500))
    assert [output.thread_id for output in selection] == [enabled, older, selected]

    assert _run(store.prune_stage1_outputs_for_retention(1, 10)) >= 1
    remaining = {row[0] for row in memory.execute("SELECT thread_id FROM stage1_outputs").fetchall()}
    assert str(selected) in remaining


def test_startup_claim_filters_disabled_current_archived_blank_and_sources():
    # Rust: claim_stage1_jobs_for_startup filters candidates before stage1 claiming.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    current = _thread_id(8)
    good = _thread_id(9)
    disabled = _thread_id(10)
    archived = _thread_id(11)
    blank = _thread_id(12)
    other_source = _thread_id(13)
    _insert_thread(state, current, updated_ms=900_000)
    _insert_thread(state, good, updated_ms=800_000, source="cli")
    _insert_thread(state, disabled, updated_ms=790_000, memory_mode="disabled", source="cli")
    _insert_thread(state, archived, updated_ms=780_000, archived=1, source="cli")
    _insert_thread(state, blank, updated_ms=770_000, preview="", source="cli")
    _insert_thread(state, other_source, updated_ms=760_000, source="ide")

    params = Stage1StartupClaimParams(
        scan_limit=10,
        max_claimed=4,
        max_age_days=36_500,
        min_rollout_idle_hours=0,
        allowed_sources=("cli",),
        lease_seconds=30,
    )
    claims = _run(store.claim_stage1_jobs_for_startup(current, params))
    assert [claim.thread.id for claim in claims] == [good]
    assert _job(memory, JOB_KIND_MEMORY_STAGE1, str(good))["status"] == "running"


def test_polluted_mode_enqueues_phase2_for_selected_outputs_even_without_transition():
    # Rust: mark_thread_memory_mode_polluted enqueues phase2 for selected threads, including already polluted rows.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    thread = _thread_id(14)
    _insert_thread(state, thread, memory_mode="enabled")
    _insert_output(memory, thread, source_updated_at=1400, selected_for_phase2=1, selected_source_updated_at=1400)

    assert _run(store.mark_thread_memory_mode_polluted(thread)) is True
    assert state.execute("SELECT memory_mode FROM threads WHERE id = ?", (str(thread),)).fetchone()[0] == "polluted"
    first_watermark = _job(memory, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL)["input_watermark"]

    assert _run(store.mark_thread_memory_mode_polluted(thread)) is False
    assert _job(memory, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL)["input_watermark"] > first_watermark


def test_phase2_claim_heartbeat_success_snapshot_and_cooldown():
    # Rust: phase2 claim is single-runner, success rewrites the exact selected snapshot and enforces cooldown.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    thread = _thread_id(15)
    worker = _thread_id(99)
    other_worker = _thread_id(100)
    _insert_thread(state, thread)
    _insert_output(memory, thread, source_updated_at=1500, generated_at=1501)
    output = _run(store.get_phase2_input_selection(1, 36_500))[0]

    _run(store.enqueue_global_consolidation(1500))
    claim = _run(store.try_claim_global_phase2_job(worker, 30))
    assert isinstance(claim, Phase2JobClaimed)
    assert _run(store.try_claim_global_phase2_job(other_worker, 30)) is Phase2JobClaimOutcome.SKIPPED_RUNNING
    assert _run(store.heartbeat_global_phase2_job(claim.ownership_token, 60)) is True
    assert _run(store.mark_global_phase2_job_succeeded(claim.ownership_token, 1500, [output])) is True

    row = memory.execute(
        "SELECT selected_for_phase2, selected_for_phase2_source_updated_at FROM stage1_outputs WHERE thread_id = ?",
        (str(thread),),
    ).fetchone()
    assert row == (1, 1500)
    assert _run(store.try_claim_global_phase2_job(worker, 30)) is Phase2JobClaimOutcome.SKIPPED_COOLDOWN


def test_phase2_failure_retry_and_unowned_fallback_and_clear_memory_data():
    # Rust: phase2 failures update retry state; clear_memory_data removes memory jobs/outputs but not thread rows.
    memory, state = _connect_pair()
    store = MemoryStore(memory, state)
    thread = _thread_id(16)
    worker = _thread_id(99)
    _insert_thread(state, thread, memory_mode="disabled")
    _insert_output(memory, thread, source_updated_at=1600)

    _run(store.enqueue_global_consolidation(1600))
    claim = _run(store.try_claim_global_phase2_job(worker, 30))
    assert isinstance(claim, Phase2JobClaimed)
    assert _run(store.mark_global_phase2_job_failed(claim.ownership_token, "model error", 60)) is True
    row = _job(memory, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL)
    assert row["status"] == "error"
    assert row["last_error"] == "model error"
    assert row["retry_remaining"] == 2

    memory.execute(
        """
        UPDATE jobs
        SET status = 'running', ownership_token = NULL, lease_until = ?, retry_at = NULL
        WHERE kind = ? AND job_key = ?
        """,
        (0, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY),
    )
    memory.commit()
    assert _run(store.mark_global_phase2_job_failed_if_unowned("fallback-token", "fallback error", 5)) is True
    assert _job(memory, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL)["last_error"] == "fallback error"

    _run(store.clear_memory_data())
    assert memory.execute("SELECT COUNT(*) FROM stage1_outputs").fetchone()[0] == 0
    assert memory.execute("SELECT COUNT(*) FROM jobs WHERE kind IN (?, ?)", (JOB_KIND_MEMORY_STAGE1, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL)).fetchone()[0] == 0
    assert state.execute("SELECT memory_mode FROM threads WHERE id = ?", (str(thread),)).fetchone()[0] == "disabled"
