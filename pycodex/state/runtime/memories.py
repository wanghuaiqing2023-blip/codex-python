"""Memory runtime store ported from ``codex-state/src/runtime/memories.rs``."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

from pycodex.protocol import ThreadId

from ..model import (
    Phase2JobClaimOutcome,
    Phase2JobClaimed,
    Stage1JobClaim,
    Stage1JobClaimOutcome,
    Stage1JobClaimed,
    Stage1Output,
    Stage1StartupClaimParams,
    ThreadMetadata,
    ThreadRow,
    claimed_phase2,
    claimed_stage1,
    datetime_to_epoch_seconds,
    epoch_seconds_to_datetime,
)

JsonValue = Any

JOB_KIND_MEMORY_STAGE1 = "memory_stage1"
JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL = "memory_consolidate_global"
MEMORY_CONSOLIDATION_JOB_KEY = "global"
PHASE2_SUCCESS_COOLDOWN_SECONDS = 6 * 60 * 60
PHASE2_INPUT_SELECTION_PAGE_SIZE = 512
DEFAULT_RETRY_REMAINING = 3


class MemoryStore:
    def __init__(self, db: sqlite3.Connection | Path | str, state_db: sqlite3.Connection | Path | str):
        self._db = db
        self._state_db = state_db

    async def clear_memory_data(self) -> None:
        await _call(self._db, clear_memory_data_in_connection)

    async def record_stage1_output_usage(self, thread_ids: Sequence[ThreadId]) -> int:
        return await _call(self._db, _record_stage1_output_usage_sync, tuple(_thread_id(item) for item in thread_ids), now=_now())

    async def claim_stage1_jobs_for_startup(
        self,
        current_thread_id: ThreadId,
        params: Stage1StartupClaimParams,
    ) -> list[Stage1JobClaim]:
        if params.scan_limit == 0 or params.max_claimed == 0:
            return []
        now = _now()
        state_rows = await _call(
            self._state_db,
            _startup_candidate_threads_sync,
            _thread_id(current_thread_id),
            params,
            now=now,
        )
        claimed: list[Stage1JobClaim] = []
        for thread in state_rows:
            if len(claimed) >= params.max_claimed:
                break
            if not await self.stage1_source_needs_update(thread.id, datetime_to_epoch_seconds(thread.updated_at)):
                continue
            outcome = await self.try_claim_stage1_job(
                thread.id,
                current_thread_id,
                datetime_to_epoch_seconds(thread.updated_at),
                params.lease_seconds,
                params.max_claimed,
            )
            if isinstance(outcome, Stage1JobClaimed):
                claimed.append(Stage1JobClaim(thread=thread, ownership_token=outcome.ownership_token))
        return claimed

    async def stage1_source_needs_update(self, thread_id: ThreadId, source_updated_at: int) -> bool:
        return await _call(self._db, _stage1_source_needs_update_sync, _thread_id(thread_id), _i64(source_updated_at, "source_updated_at"))

    async def delete_thread_memory(self, thread_id: ThreadId) -> None:
        await _call(self._db, _delete_thread_memory_sync, _thread_id(thread_id), now=_now())

    async def list_stage1_outputs_for_global(self, n: int) -> list[Stage1Output]:
        if _usize(n, "n") == 0:
            return []
        rows = await _call(self._db, _list_stage1_output_rows_sync, n)
        return await _hydrate_outputs(self._state_db, rows, limit=n)

    async def prune_stage1_outputs_for_retention(self, max_unused_days: int, limit: int) -> int:
        return await _call(
            self._db,
            _prune_stage1_outputs_for_retention_sync,
            _i64(max_unused_days, "max_unused_days"),
            _usize(limit, "limit"),
            now=_now(),
        )

    async def get_phase2_input_selection(self, n: int, max_unused_days: int) -> list[Stage1Output]:
        n = _usize(n, "n")
        if n == 0:
            return []
        rows = await _call(
            self._db,
            _phase2_candidate_rows_sync,
            n,
            _i64(max_unused_days, "max_unused_days"),
            now=_now(),
        )
        selected: list[dict[str, JsonValue]] = []
        offset = 0
        while len(selected) < n and offset < len(rows):
            row = rows[offset]
            offset += 1
            thread = await _call(self._state_db, _enabled_thread_metadata_sync, str(row["thread_id"]))
            if thread is not None:
                selected.append(row)
        outputs = await _hydrate_outputs(self._state_db, selected, limit=n)
        return sorted(outputs, key=lambda item: str(item.thread_id))

    async def mark_thread_memory_mode_polluted(self, thread_id: ThreadId) -> bool:
        thread_id_str = _thread_id(thread_id)
        selected_for_phase2 = await _call(self._db, _selected_for_phase2_sync, thread_id_str)
        rows = await _call(self._state_db, _mark_thread_polluted_sync, thread_id_str)
        if selected_for_phase2:
            await self.enqueue_global_consolidation(_now())
        return rows > 0

    async def try_claim_stage1_job(
        self,
        thread_id: ThreadId,
        worker_id: ThreadId,
        source_updated_at: int,
        lease_seconds: int,
        max_running_jobs: int,
    ) -> Stage1JobClaimed | Stage1JobClaimOutcome:
        return await _call(
            self._db,
            _try_claim_stage1_job_sync,
            _thread_id(thread_id),
            _thread_id(worker_id),
            _i64(source_updated_at, "source_updated_at"),
            _i64(lease_seconds, "lease_seconds"),
            _usize(max_running_jobs, "max_running_jobs"),
            now=_now(),
        )

    async def mark_stage1_job_succeeded(
        self,
        thread_id: ThreadId,
        ownership_token: str,
        source_updated_at: int,
        raw_memory: str,
        rollout_summary: str,
        rollout_slug: str | None = None,
    ) -> bool:
        return await _call(
            self._db,
            _mark_stage1_job_succeeded_sync,
            _thread_id(thread_id),
            _required_str(ownership_token, "ownership_token"),
            _i64(source_updated_at, "source_updated_at"),
            _required_str(raw_memory, "raw_memory"),
            _required_str(rollout_summary, "rollout_summary"),
            _optional_str(rollout_slug, "rollout_slug"),
            now=_now(),
        )

    async def mark_stage1_job_succeeded_no_output(self, thread_id: ThreadId, ownership_token: str) -> bool:
        return await _call(self._db, _mark_stage1_job_succeeded_no_output_sync, _thread_id(thread_id), _required_str(ownership_token, "ownership_token"), now=_now())

    async def mark_stage1_job_failed(
        self,
        thread_id: ThreadId,
        ownership_token: str,
        failure_reason: str,
        retry_delay_seconds: int,
    ) -> bool:
        return await _call(
            self._db,
            _mark_stage1_job_failed_sync,
            _thread_id(thread_id),
            _required_str(ownership_token, "ownership_token"),
            _required_str(failure_reason, "failure_reason"),
            _i64(retry_delay_seconds, "retry_delay_seconds"),
            now=_now(),
        )

    async def enqueue_global_consolidation(self, input_watermark: int) -> None:
        await _call(self._db, enqueue_global_consolidation_in_connection, _i64(input_watermark, "input_watermark"))

    async def try_claim_global_phase2_job(self, worker_id: ThreadId, lease_seconds: int) -> Phase2JobClaimed | Phase2JobClaimOutcome:
        return await _call(
            self._db,
            _try_claim_global_phase2_job_sync,
            _thread_id(worker_id),
            _i64(lease_seconds, "lease_seconds"),
            now=_now(),
        )

    async def heartbeat_global_phase2_job(self, ownership_token: str, lease_seconds: int) -> bool:
        return await _call(
            self._db,
            _heartbeat_global_phase2_job_sync,
            _required_str(ownership_token, "ownership_token"),
            _i64(lease_seconds, "lease_seconds"),
            now=_now(),
        )

    async def mark_global_phase2_job_succeeded(
        self,
        ownership_token: str,
        completed_watermark: int,
        selected_outputs: Sequence[Stage1Output],
    ) -> bool:
        return await _call(
            self._db,
            _mark_global_phase2_job_succeeded_sync,
            _required_str(ownership_token, "ownership_token"),
            _i64(completed_watermark, "completed_watermark"),
            tuple(selected_outputs),
            now=_now(),
        )

    async def mark_global_phase2_job_failed(self, ownership_token: str, failure_reason: str, retry_delay_seconds: int) -> bool:
        return await _call(
            self._db,
            _mark_global_phase2_job_failed_sync,
            _required_str(ownership_token, "ownership_token"),
            _required_str(failure_reason, "failure_reason"),
            _i64(retry_delay_seconds, "retry_delay_seconds"),
            False,
            now=_now(),
        )

    async def mark_global_phase2_job_failed_if_unowned(self, ownership_token: str, failure_reason: str, retry_delay_seconds: int) -> bool:
        return await _call(
            self._db,
            _mark_global_phase2_job_failed_sync,
            _required_str(ownership_token, "ownership_token"),
            _required_str(failure_reason, "failure_reason"),
            _i64(retry_delay_seconds, "retry_delay_seconds"),
            True,
            now=_now(),
        )


def _record_stage1_output_usage_sync(connection: sqlite3.Connection, thread_ids: tuple[str, ...], *, now: int) -> int:
    if not thread_ids:
        return 0
    updated = 0
    with connection:
        for thread_id in thread_ids:
            result = connection.execute(
                """
                UPDATE stage1_outputs
                SET usage_count = COALESCE(usage_count, 0) + 1,
                    last_usage = ?
                WHERE thread_id = ?
                """,
                (now, thread_id),
            )
            updated += result.rowcount
    return updated


def _stage1_source_needs_update_sync(connection: sqlite3.Connection, thread_id: str, source_updated_at: int) -> bool:
    row = connection.execute("SELECT source_updated_at FROM stage1_outputs WHERE thread_id = ?", (thread_id,)).fetchone()
    if row is not None and int(row[0]) >= source_updated_at:
        return False
    row = connection.execute(
        "SELECT last_success_watermark FROM jobs WHERE kind = ? AND job_key = ?",
        (JOB_KIND_MEMORY_STAGE1, thread_id),
    ).fetchone()
    return not (row is not None and row[0] is not None and int(row[0]) >= source_updated_at)


def _startup_candidate_threads_sync(connection: sqlite3.Connection, current_thread_id: str, params: Stage1StartupClaimParams, *, now: int) -> list[ThreadMetadata]:
    max_age_cutoff = (now - max(params.max_age_days, 0) * 24 * 60 * 60) * 1000
    idle_cutoff = (now - max(params.min_rollout_idle_hours, 0) * 60 * 60) * 1000
    clauses = [
        "threads.archived = 0",
        "threads.preview <> ''",
        "threads.memory_mode = 'enabled'",
        "threads.id != ?",
        "threads.updated_at_ms >= ?",
        "threads.updated_at_ms <= ?",
    ]
    values: list[JsonValue] = [current_thread_id, max_age_cutoff, idle_cutoff]
    if params.allowed_sources:
        clauses.append("threads.source IN (" + ", ".join("?" for _ in params.allowed_sources) + ")")
        values.extend(params.allowed_sources)
    sql = _thread_select_sql("WHERE " + " AND ".join(clauses) + " ORDER BY threads.updated_at_ms DESC LIMIT ?")
    values.append(params.scan_limit)
    return [_thread_from_row(row) for row in _rows(connection, sql, values)]


def _delete_thread_memory_sync(connection: sqlite3.Connection, thread_id: str, *, now: int) -> None:
    with connection:
        row = connection.execute("SELECT selected_for_phase2 FROM stage1_outputs WHERE thread_id = ?", (thread_id,)).fetchone()
        was_selected = row is not None and int(row[0] or 0) != 0
        deleted = connection.execute("DELETE FROM stage1_outputs WHERE thread_id = ?", (thread_id,)).rowcount
        connection.execute("DELETE FROM jobs WHERE kind = ? AND job_key = ?", (JOB_KIND_MEMORY_STAGE1, thread_id))
        if deleted > 0 and was_selected:
            enqueue_global_consolidation_in_connection(connection, now)


def _list_stage1_output_rows_sync(connection: sqlite3.Connection, n: int) -> list[dict[str, JsonValue]]:
    rows = _rows(
        connection,
        """
        SELECT thread_id, source_updated_at, raw_memory, rollout_summary, rollout_slug, generated_at
        FROM stage1_outputs
        WHERE length(trim(raw_memory)) > 0 OR length(trim(rollout_summary)) > 0
        ORDER BY source_updated_at DESC, thread_id DESC
        """,
        [],
    )
    return [dict(row) for row in rows[:n]]


def _prune_stage1_outputs_for_retention_sync(connection: sqlite3.Connection, max_unused_days: int, limit: int, *, now: int) -> int:
    if limit == 0:
        return 0
    cutoff = now - max(max_unused_days, 0) * 24 * 60 * 60
    with connection:
        return connection.execute(
            """
            DELETE FROM stage1_outputs
            WHERE thread_id IN (
                SELECT thread_id
                FROM stage1_outputs
                WHERE selected_for_phase2 = 0
                  AND COALESCE(last_usage, source_updated_at) < ?
                ORDER BY COALESCE(last_usage, source_updated_at) ASC, source_updated_at ASC, thread_id ASC
                LIMIT ?
            )
            """,
            (cutoff, limit),
        ).rowcount


def _phase2_candidate_rows_sync(connection: sqlite3.Connection, n: int, max_unused_days: int, *, now: int) -> list[dict[str, JsonValue]]:
    cutoff = now - max(max_unused_days, 0) * 24 * 60 * 60
    rows = _rows(
        connection,
        """
        SELECT thread_id, source_updated_at, raw_memory, rollout_summary, rollout_slug, generated_at
        FROM stage1_outputs
        WHERE (length(trim(raw_memory)) > 0 OR length(trim(rollout_summary)) > 0)
          AND ((last_usage IS NOT NULL AND last_usage >= ?) OR (last_usage IS NULL AND source_updated_at >= ?))
        ORDER BY
          COALESCE(usage_count, 0) DESC,
          COALESCE(last_usage, source_updated_at) DESC,
          source_updated_at DESC,
          thread_id DESC
        """,
        (cutoff, cutoff),
    )
    return [dict(row) for row in rows]


def _selected_for_phase2_sync(connection: sqlite3.Connection, thread_id: str) -> bool:
    row = connection.execute("SELECT selected_for_phase2 FROM stage1_outputs WHERE thread_id = ?", (thread_id,)).fetchone()
    return row is not None and int(row[0] or 0) != 0


def _mark_thread_polluted_sync(connection: sqlite3.Connection, thread_id: str) -> int:
    with connection:
        return connection.execute("UPDATE threads SET memory_mode = 'polluted' WHERE id = ? AND memory_mode != 'polluted'", (thread_id,)).rowcount


def _try_claim_stage1_job_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    worker_id: str,
    source_updated_at: int,
    lease_seconds: int,
    max_running_jobs: int,
    *,
    now: int,
) -> Stage1JobClaimed | Stage1JobClaimOutcome:
    if not _stage1_source_needs_update_sync(connection, thread_id, source_updated_at):
        return Stage1JobClaimOutcome.SKIPPED_UP_TO_DATE
    lease_until = now + max(lease_seconds, 0)
    token = str(uuid.uuid4())
    with connection:
        running_count = _running_stage1_count(connection, now, exclude_job_key=None)
        row = _job_row(connection, JOB_KIND_MEMORY_STAGE1, thread_id)
        if row is None:
            if running_count >= max_running_jobs:
                return Stage1JobClaimOutcome.SKIPPED_RUNNING
            connection.execute(
                """
                INSERT INTO jobs(kind, job_key, status, worker_id, ownership_token, started_at, finished_at,
                                 lease_until, retry_at, retry_remaining, last_error, input_watermark, last_success_watermark)
                VALUES (?, ?, 'running', ?, ?, ?, NULL, ?, NULL, ?, NULL, ?, NULL)
                """,
                (JOB_KIND_MEMORY_STAGE1, thread_id, worker_id, token, now, lease_until, DEFAULT_RETRY_REMAINING, source_updated_at),
            )
            return claimed_stage1(token)
        if int(row["retry_remaining"]) <= 0 and source_updated_at <= int(row["input_watermark"] or -1):
            return Stage1JobClaimOutcome.SKIPPED_RETRY_EXHAUSTED
        if row["retry_at"] is not None and int(row["retry_at"]) > now and source_updated_at <= int(row["input_watermark"] or -1):
            return Stage1JobClaimOutcome.SKIPPED_RETRY_BACKOFF
        if row["status"] == "running" and row["lease_until"] is not None and int(row["lease_until"]) > now:
            return Stage1JobClaimOutcome.SKIPPED_RUNNING
        if _running_stage1_count(connection, now, exclude_job_key=thread_id) >= max_running_jobs:
            return Stage1JobClaimOutcome.SKIPPED_RUNNING
        retry_remaining = DEFAULT_RETRY_REMAINING if source_updated_at > int(row["input_watermark"] or -1) else int(row["retry_remaining"])
        connection.execute(
            """
            UPDATE jobs
            SET status = 'running', worker_id = ?, ownership_token = ?, started_at = ?, finished_at = NULL,
                lease_until = ?, retry_at = NULL, retry_remaining = ?, last_error = NULL, input_watermark = ?
            WHERE kind = ? AND job_key = ?
            """,
            (worker_id, token, now, lease_until, retry_remaining, source_updated_at, JOB_KIND_MEMORY_STAGE1, thread_id),
        )
        return claimed_stage1(token)


def _mark_stage1_job_succeeded_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    ownership_token: str,
    source_updated_at: int,
    raw_memory: str,
    rollout_summary: str,
    rollout_slug: str | None,
    *,
    now: int,
) -> bool:
    with connection:
        rows = connection.execute(
            """
            UPDATE jobs
            SET status = 'done', finished_at = ?, lease_until = NULL, last_error = NULL,
                last_success_watermark = input_watermark
            WHERE kind = ? AND job_key = ? AND status = 'running' AND ownership_token = ?
            """,
            (now, JOB_KIND_MEMORY_STAGE1, thread_id, ownership_token),
        ).rowcount
        if rows == 0:
            return False
        connection.execute(
            """
            INSERT INTO stage1_outputs(thread_id, source_updated_at, raw_memory, rollout_summary, rollout_slug, generated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                source_updated_at = excluded.source_updated_at,
                raw_memory = excluded.raw_memory,
                rollout_summary = excluded.rollout_summary,
                rollout_slug = excluded.rollout_slug,
                generated_at = excluded.generated_at
            WHERE excluded.source_updated_at >= stage1_outputs.source_updated_at
            """,
            (thread_id, source_updated_at, raw_memory, rollout_summary, rollout_slug, now),
        )
        enqueue_global_consolidation_in_connection(connection, source_updated_at)
        return True


def _mark_stage1_job_succeeded_no_output_sync(connection: sqlite3.Connection, thread_id: str, ownership_token: str, *, now: int) -> bool:
    with connection:
        rows = connection.execute(
            """
            UPDATE jobs
            SET status = 'done', finished_at = ?, lease_until = NULL, last_error = NULL,
                last_success_watermark = input_watermark
            WHERE kind = ? AND job_key = ? AND status = 'running' AND ownership_token = ?
            """,
            (now, JOB_KIND_MEMORY_STAGE1, thread_id, ownership_token),
        ).rowcount
        if rows == 0:
            return False
        watermark_row = connection.execute(
            "SELECT input_watermark FROM jobs WHERE kind = ? AND job_key = ? AND ownership_token = ?",
            (JOB_KIND_MEMORY_STAGE1, thread_id, ownership_token),
        ).fetchone()
        deleted = connection.execute("DELETE FROM stage1_outputs WHERE thread_id = ?", (thread_id,)).rowcount
        if deleted > 0 and watermark_row is not None:
            enqueue_global_consolidation_in_connection(connection, int(watermark_row[0] or 0))
        return True


def _mark_stage1_job_failed_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    ownership_token: str,
    failure_reason: str,
    retry_delay_seconds: int,
    *,
    now: int,
) -> bool:
    retry_at = now + max(retry_delay_seconds, 0)
    with connection:
        rows = connection.execute(
            """
            UPDATE jobs
            SET status = 'error', finished_at = ?, lease_until = NULL, retry_at = ?,
                retry_remaining = retry_remaining - 1, last_error = ?
            WHERE kind = ? AND job_key = ? AND status = 'running' AND ownership_token = ?
            """,
            (now, retry_at, failure_reason, JOB_KIND_MEMORY_STAGE1, thread_id, ownership_token),
        ).rowcount
    return rows > 0


def enqueue_global_consolidation_in_connection(connection: sqlite3.Connection, input_watermark: int) -> None:
    connection.execute(
        """
        INSERT INTO jobs(kind, job_key, status, worker_id, ownership_token, started_at, finished_at,
                         lease_until, retry_at, retry_remaining, last_error, input_watermark, last_success_watermark)
        VALUES (?, ?, 'pending', NULL, NULL, NULL, NULL, NULL, NULL, ?, NULL, ?, 0)
        ON CONFLICT(kind, job_key) DO UPDATE SET
            status = CASE WHEN jobs.status = 'running' THEN 'running' ELSE 'pending' END,
            retry_at = CASE WHEN jobs.status = 'running' THEN jobs.retry_at ELSE NULL END,
            retry_remaining = max(jobs.retry_remaining, excluded.retry_remaining),
            input_watermark = CASE
                WHEN excluded.input_watermark > COALESCE(jobs.input_watermark, 0) THEN excluded.input_watermark
                ELSE COALESCE(jobs.input_watermark, 0) + 1
            END
        """,
        (JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY, DEFAULT_RETRY_REMAINING, input_watermark),
    )


def _try_claim_global_phase2_job_sync(
    connection: sqlite3.Connection,
    worker_id: str,
    lease_seconds: int,
    *,
    now: int,
) -> Phase2JobClaimed | Phase2JobClaimOutcome:
    lease_until = now + max(lease_seconds, 0)
    cooldown_cutoff = now - PHASE2_SUCCESS_COOLDOWN_SECONDS
    token = str(uuid.uuid4())
    with connection:
        row = _job_row(connection, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY)
        if row is None:
            connection.execute(
                """
                INSERT INTO jobs(kind, job_key, status, worker_id, ownership_token, started_at, finished_at,
                                 lease_until, retry_at, retry_remaining, last_error, input_watermark, last_success_watermark)
                VALUES (?, ?, 'running', ?, ?, ?, NULL, ?, NULL, ?, NULL, 0, 0)
                """,
                (JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY, worker_id, token, now, lease_until, DEFAULT_RETRY_REMAINING),
            )
            return claimed_phase2(token, 0)
        if row["retry_at"] is not None and int(row["retry_at"]) > now:
            return Phase2JobClaimOutcome.SKIPPED_RETRY_UNAVAILABLE
        if row["status"] == "running" and row["lease_until"] is not None and int(row["lease_until"]) > now:
            return Phase2JobClaimOutcome.SKIPPED_RUNNING
        if row["last_error"] is None and row["finished_at"] is not None and int(row["finished_at"]) > cooldown_cutoff:
            return Phase2JobClaimOutcome.SKIPPED_COOLDOWN
        connection.execute(
            """
            UPDATE jobs
            SET status = 'running', worker_id = ?, ownership_token = ?, started_at = ?,
                finished_at = NULL, lease_until = ?, retry_at = NULL, last_error = NULL
            WHERE kind = ? AND job_key = ?
            """,
            (worker_id, token, now, lease_until, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY),
        )
        return claimed_phase2(token, int(row["input_watermark"] or 0))


def _heartbeat_global_phase2_job_sync(connection: sqlite3.Connection, ownership_token: str, lease_seconds: int, *, now: int) -> bool:
    with connection:
        return connection.execute(
            """
            UPDATE jobs SET lease_until = ?
            WHERE kind = ? AND job_key = ? AND status = 'running' AND ownership_token = ?
            """,
            (now + max(lease_seconds, 0), JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY, ownership_token),
        ).rowcount > 0


def _mark_global_phase2_job_succeeded_sync(
    connection: sqlite3.Connection,
    ownership_token: str,
    completed_watermark: int,
    selected_outputs: tuple[Stage1Output, ...],
    *,
    now: int,
) -> bool:
    with connection:
        rows = connection.execute(
            """
            UPDATE jobs
            SET status = 'done', finished_at = ?, lease_until = NULL, last_error = NULL,
                last_success_watermark = max(COALESCE(last_success_watermark, 0), ?)
            WHERE kind = ? AND job_key = ? AND status = 'running' AND ownership_token = ?
            """,
            (now, completed_watermark, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY, ownership_token),
        ).rowcount
        if rows == 0:
            return False
        connection.execute(
            """
            UPDATE stage1_outputs
            SET selected_for_phase2 = 0, selected_for_phase2_source_updated_at = NULL
            WHERE selected_for_phase2 != 0 OR selected_for_phase2_source_updated_at IS NOT NULL
            """
        )
        for output in selected_outputs:
            source_updated_at = datetime_to_epoch_seconds(output.source_updated_at)
            connection.execute(
                """
                UPDATE stage1_outputs
                SET selected_for_phase2 = 1, selected_for_phase2_source_updated_at = ?
                WHERE thread_id = ? AND source_updated_at = ?
                """,
                (source_updated_at, str(output.thread_id), source_updated_at),
            )
        return True


def _mark_global_phase2_job_failed_sync(
    connection: sqlite3.Connection,
    ownership_token: str,
    failure_reason: str,
    retry_delay_seconds: int,
    allow_unowned: bool,
    *,
    now: int,
) -> bool:
    retry_at = now + max(retry_delay_seconds, 0)
    ownership_predicate = "(ownership_token = ? OR ownership_token IS NULL)" if allow_unowned else "ownership_token = ?"
    with connection:
        return connection.execute(
            f"""
            UPDATE jobs
            SET status = 'error', finished_at = ?, lease_until = NULL, retry_at = ?,
                retry_remaining = max(retry_remaining - 1, 0), last_error = ?
            WHERE kind = ? AND job_key = ? AND status = 'running' AND {ownership_predicate}
            """,
            (now, retry_at, failure_reason, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL, MEMORY_CONSOLIDATION_JOB_KEY, ownership_token),
        ).rowcount > 0


def clear_memory_data_in_connection(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute("DELETE FROM stage1_outputs")
        connection.execute("DELETE FROM jobs WHERE kind = ? OR kind = ?", (JOB_KIND_MEMORY_STAGE1, JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL))


async def _hydrate_outputs(db: sqlite3.Connection | Path | str, rows: Sequence[dict[str, JsonValue]], *, limit: int) -> list[Stage1Output]:
    outputs: list[Stage1Output] = []
    for row in rows:
        thread = await _call(db, _enabled_thread_metadata_sync, str(row["thread_id"]))
        if thread is None:
            continue
        outputs.append(_stage1_output_from_row_and_thread(row, thread))
        if len(outputs) >= limit:
            break
    return outputs


def _stage1_output_from_row_and_thread(row: dict[str, JsonValue], thread: ThreadMetadata) -> Stage1Output:
    return Stage1Output(
        thread_id=thread.id,
        rollout_path=thread.rollout_path,
        source_updated_at=epoch_seconds_to_datetime(_i64(row["source_updated_at"], "source_updated_at")),
        raw_memory=_required_str(row["raw_memory"], "raw_memory"),
        rollout_summary=_required_str(row["rollout_summary"], "rollout_summary"),
        rollout_slug=_optional_str(row.get("rollout_slug"), "rollout_slug"),
        cwd=thread.cwd,
        git_branch=thread.git_branch,
        generated_at=epoch_seconds_to_datetime(_i64(row["generated_at"], "generated_at")),
    )


def _enabled_thread_metadata_sync(connection: sqlite3.Connection, thread_id: str) -> ThreadMetadata | None:
    rows = _rows(connection, _thread_select_sql("WHERE threads.id = ? AND threads.memory_mode = 'enabled'"), (thread_id,))
    return _thread_from_row(rows[0]) if rows else None


def _thread_select_sql(suffix: str) -> str:
    return (
        """
        SELECT
            threads.id,
            threads.rollout_path,
            threads.created_at_ms AS created_at,
            threads.updated_at_ms AS updated_at,
            threads.source,
            threads.thread_source,
            threads.agent_nickname,
            threads.agent_role,
            threads.agent_path,
            threads.model_provider,
            threads.model,
            threads.reasoning_effort,
            threads.cwd,
            threads.cli_version,
            threads.title,
            threads.preview,
            threads.sandbox_policy,
            threads.approval_mode,
            threads.tokens_used,
            threads.first_user_message,
            threads.archived_at,
            threads.git_sha,
            threads.git_branch,
            threads.git_origin_url
        FROM threads
        """
        + suffix
    )


def _thread_from_row(row: sqlite3.Row) -> ThreadMetadata:
    return ThreadRow.from_mapping(dict(row)).to_thread_metadata()


def _job_row(connection: sqlite3.Connection, kind: str, job_key: str) -> sqlite3.Row | None:
    rows = _rows(connection, "SELECT * FROM jobs WHERE kind = ? AND job_key = ?", (kind, job_key))
    return rows[0] if rows else None


def _running_stage1_count(connection: sqlite3.Connection, now: int, exclude_job_key: str | None) -> int:
    sql = """
        SELECT COUNT(*) FROM jobs
        WHERE kind = ? AND status = 'running' AND lease_until IS NOT NULL AND lease_until > ?
    """
    params: list[JsonValue] = [JOB_KIND_MEMORY_STAGE1, now]
    if exclude_job_key is not None:
        sql += " AND job_key != ?"
        params.append(exclude_job_key)
    return int(connection.execute(sql, params).fetchone()[0])


def _rows(connection: sqlite3.Connection, sql: str, params: Sequence[JsonValue]) -> list[sqlite3.Row]:
    old_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.row_factory = old_factory


async def _call(db: sqlite3.Connection | Path | str, fn, *args, **kwargs):
    if isinstance(db, sqlite3.Connection):
        return fn(db, *args, **kwargs)
    return await asyncio.to_thread(_with_connection, _path(db, "db"), fn, *args, **kwargs)


def _with_connection(path: Path, fn, *args, **kwargs):
    connection = sqlite3.connect(path)
    try:
        return fn(connection, *args, **kwargs)
    finally:
        connection.close()


def _now() -> int:
    return int(time.time())


def _thread_id(value: ThreadId) -> str:
    if not isinstance(value, ThreadId):
        raise TypeError("thread_id must be ThreadId")
    return str(value)


def _i64(value: JsonValue, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")
    return value


def _usize(value: JsonValue, name: str) -> int:
    value = _i64(value, name)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _required_str(value, name)


def _path(value: JsonValue, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a string or Path")
    return Path(value)


__all__ = [
    "DEFAULT_RETRY_REMAINING",
    "JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL",
    "JOB_KIND_MEMORY_STAGE1",
    "MEMORY_CONSOLIDATION_JOB_KEY",
    "MemoryStore",
    "PHASE2_INPUT_SELECTION_PAGE_SIZE",
    "PHASE2_SUCCESS_COOLDOWN_SECONDS",
    "clear_memory_data_in_connection",
    "enqueue_global_consolidation_in_connection",
]
