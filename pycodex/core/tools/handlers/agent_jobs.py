"""Agent job helpers ported from Codex core."""

from __future__ import annotations

import csv
import asyncio
import inspect
import json
from datetime import datetime, timezone
import time
import threading
import uuid
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Protocol

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.core.agent import exceeds_thread_spawn_depth_limit, next_thread_spawn_depth
from pycodex.core.agent.status import is_final
from pycodex.protocol import (
    SessionSource,
    SubAgentSource,
    ThreadId,
    ToolName,
    UserInput,
)
from pycodex.protocol.error import CodexErr

JsonValue = Any

SPAWN_AGENTS_ON_CSV_TOOL_NAME = "spawn_agents_on_csv"
REPORT_AGENT_JOB_RESULT_TOOL_NAME = "report_agent_job_result"
DEFAULT_AGENT_JOB_CONCURRENCY = 16
MAX_AGENT_JOB_CONCURRENCY = 64
DEFAULT_AGENT_JOB_ITEM_TIMEOUT_SECONDS = 60 * 30
STATUS_POLL_INTERVAL_SECONDS = 0.25


@dataclass(frozen=True)
class SpawnAgentsOnCsvArgs:
    csv_path: str
    instruction: str
    id_column: str | None = None
    output_csv_path: str | None = None
    output_schema: JsonValue | None = None
    max_concurrency: int | None = None
    max_workers: int | None = None
    max_runtime_seconds: int | None = None

    def __post_init__(self) -> None:
        _require_str(self.csv_path, "csv_path")
        _require_str(self.instruction, "instruction")
        _optional_str_value(self.id_column, "id_column")
        _optional_str_value(self.output_csv_path, "output_csv_path")
        _optional_usize(self.max_concurrency, "max_concurrency")
        _optional_usize(self.max_workers, "max_workers")
        _optional_u64(self.max_runtime_seconds, "max_runtime_seconds")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SpawnAgentsOnCsvArgs":
        if not isinstance(value, dict):
            raise TypeError("spawn_agents_on_csv args must be a mapping")
        return cls(
            csv_path=_required_str(value, "csv_path"),
            instruction=_required_str(value, "instruction"),
            id_column=_optional_str(value, "id_column"),
            output_csv_path=_optional_str(value, "output_csv_path"),
            output_schema=value.get("output_schema"),
            max_concurrency=_optional_int(value, "max_concurrency"),
            max_workers=_optional_int(value, "max_workers"),
            max_runtime_seconds=_optional_int(value, "max_runtime_seconds"),
        )


@dataclass(frozen=True)
class ReportAgentJobResultArgs:
    job_id: str
    item_id: str
    result: Mapping[str, JsonValue]
    stop: bool | None = None

    def __post_init__(self) -> None:
        _require_str(self.job_id, "job_id")
        _require_str(self.item_id, "item_id")
        if not isinstance(self.result, Mapping):
            raise TypeError("result must be a JSON object")
        if self.stop is not None and not isinstance(self.stop, bool):
            raise TypeError("stop must be a bool or None")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReportAgentJobResultArgs":
        if not isinstance(value, dict):
            raise TypeError("report_agent_job_result args must be a mapping")
        result = value["result"]
        if not isinstance(result, Mapping):
            raise ValueError("result must be a JSON object")
        return cls(
            job_id=_required_str(value, "job_id"),
            item_id=_required_str(value, "item_id"),
            result=result,
            stop=_optional_bool(value, "stop"),
        )


@dataclass(frozen=True)
class AgentJobItemCreateParams:
    item_id: str
    row_index: int
    source_id: str | None
    row_json: dict[str, JsonValue]

    def __post_init__(self) -> None:
        _require_str(self.item_id, "item_id")
        _usize(self.row_index, "row_index")
        _optional_str_value(self.source_id, "source_id")
        if not isinstance(self.row_json, dict):
            raise TypeError("row_json must be a JSON object")


@dataclass(frozen=True)
class AgentJobItem:
    job_id: str
    item_id: str
    row_index: int
    row_json: dict[str, JsonValue]
    status: str
    source_id: str | None = None
    attempt_count: int = 0
    last_error: str | None = None
    result_json: JsonValue | None = None
    reported_at: str | None = None
    completed_at: str | None = None
    assigned_thread_id: str | None = None
    status_updated_at: str | None = None


@dataclass(frozen=True)
class AgentJobFailureSummary:
    item_id: str
    source_id: str | None
    last_error: str

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "item_id": self.item_id,
            "source_id": self.source_id,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class SpawnAgentsOnCsvResult:
    job_id: str
    status: str
    output_csv_path: str
    total_items: int
    completed_items: int
    failed_items: int
    job_error: str | None = None
    failed_item_errors: tuple[AgentJobFailureSummary, ...] | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "output_csv_path": self.output_csv_path,
            "total_items": self.total_items,
            "completed_items": self.completed_items,
            "failed_items": self.failed_items,
            "job_error": self.job_error,
            "failed_item_errors": None
            if self.failed_item_errors is None
            else [item.to_mapping() for item in self.failed_item_errors],
        }


@dataclass(frozen=True)
class ReportAgentJobResultToolResult:
    accepted: bool

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"accepted": self.accepted}


@dataclass
class InMemoryAgentJobStore:
    reported_results: dict[tuple[str, str], JsonValue] = field(default_factory=dict)
    cancelled_jobs: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, Any] = field(default_factory=dict)
    items: dict[tuple[str, str], AgentJobItem] = field(default_factory=dict)

    def report_agent_job_item_result(
        self,
        job_id: str,
        item_id: str,
        reporting_thread_id: str,
        result: Mapping[str, JsonValue],
    ) -> bool:
        _require_str(reporting_thread_id, "reporting_thread_id")
        _require_str(job_id, "job_id")
        _require_str(item_id, "item_id")
        key = (job_id, item_id)
        item = self.items.get(key)
        if item is None:
            return False
        if item.status != "running" or item.assigned_thread_id != reporting_thread_id:
            return False
        self.reported_results[key] = dict(result)
        now = _utc_now()
        item = AgentJobItem(
            job_id=item.job_id,
            item_id=item.item_id,
            row_index=item.row_index,
            row_json=item.row_json,
            status="completed",
            source_id=item.source_id,
            attempt_count=item.attempt_count,
            last_error=None,
            result_json=dict(result),
            reported_at=now,
            completed_at=now,
            assigned_thread_id=None,
            status_updated_at=now,
        )
        self.items[key] = item
        return True

    def mark_agent_job_cancelled(self, job_id: str, message: str) -> None:
        self.cancelled_jobs[job_id] = message
        job = self.jobs.get(job_id)
        if job is not None and job.get("status") in {"pending", "running"}:
            job["status"] = "cancelled"

    def create_agent_job(
        self,
        *,
        job_id: str,
        name: str,
        instruction: str,
        auto_export: bool,
        max_runtime_seconds: int | None,
        output_schema_json: JsonValue | None,
        input_headers: list[str],
        input_csv_path: str,
        output_csv_path: str,
    ) -> None:
        _ = auto_export
        self.jobs[job_id] = {
            "id": job_id,
            "name": name,
            "status": "pending",
            "instruction": instruction,
            "output_schema_json": output_schema_json,
            "input_headers": list(input_headers),
            "input_csv_path": input_csv_path,
            "output_csv_path": output_csv_path,
            "max_runtime_seconds": max_runtime_seconds,
            "last_error": None,
            "last_reported_thread_id": None,
        }

    def create_agent_job_items(self, job_id: str, items: tuple[AgentJobItemCreateParams, ...]) -> None:
        now = _utc_now()
        for item in items:
            self.items[(job_id, item.item_id)] = AgentJobItem(
                job_id=job_id,
                item_id=item.item_id,
                row_index=item.row_index,
                row_json=item.row_json,
                status="pending",
                source_id=item.source_id,
                status_updated_at=now,
            )

    def get_agent_job(self, job_id: str) -> Any:
        _require_str(job_id, "job_id")
        value = self.jobs.get(job_id)
        if value is None:
            return None
        return AgentJobRecord(
            id=value["id"],
            status=value["status"],
            input_headers=value["input_headers"],
            input_csv_path=value["input_csv_path"],
            output_csv_path=value["output_csv_path"],
            last_error=value.get("last_error"),
            max_runtime_seconds=value.get("max_runtime_seconds"),
            instruction=value["instruction"],
            output_schema_json=value["output_schema_json"],
        )

    def list_agent_job_items(
        self,
        job_id: str,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[AgentJobItem]:
        rows = [
            item
            for key, item in self.items.items()
            if key[0] == job_id and (status is None or item.status == status)
        ]
        rows.sort(key=lambda item: (item.row_index, item.item_id))
        if limit is not None:
            rows = rows[:limit]
        return rows

    def get_agent_job_item(self, job_id: str, item_id: str) -> AgentJobItem | None:
        return self.items.get((job_id, item_id))

    def mark_agent_job_running(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if job is not None:
            job["status"] = "running"
            job["last_error"] = None
            job["completed_at"] = None

    def get_agent_job_progress(self, job_id: str) -> "AgentJobProgress":
        statuses = [item.status for item in self.list_agent_job_items(job_id)]
        return AgentJobProgress(
            total_items=len(statuses),
            completed_items=sum(1 for status in statuses if status == "completed"),
            failed_items=sum(1 for status in statuses if status == "failed"),
            running_items=sum(1 for status in statuses if status == "running"),
            pending_items=sum(1 for status in statuses if status == "pending"),
        )

    def is_agent_job_cancelled(self, job_id: str) -> bool:
        return self.jobs.get(job_id, {}).get("status") == "cancelled"

    def mark_agent_job_item_running_with_thread(
        self,
        job_id: str,
        item_id: str,
        thread_id: str,
    ) -> bool:
        key = (job_id, item_id)
        item = self.items.get(key)
        if item is None:
            return False
        if item.status != "pending":
            return False
        self.items[key] = AgentJobItem(
            job_id=item.job_id,
            item_id=item.item_id,
            row_index=item.row_index,
            row_json=item.row_json,
            status="running",
            source_id=item.source_id,
            attempt_count=item.attempt_count + 1,
            last_error=item.last_error,
            result_json=item.result_json,
            reported_at=item.reported_at,
            completed_at=None,
            assigned_thread_id=thread_id,
            status_updated_at=_utc_now(),
        )
        self.jobs[job_id]["last_reported_thread_id"] = thread_id
        return True

    def mark_agent_job_item_pending(self, job_id: str, item_id: str, error_message: str | None = None) -> None:
        key = (job_id, item_id)
        item = self.items.get(key)
        if item is None:
            return
        if item.status != "running":
            return
        self.items[key] = AgentJobItem(
            job_id=item.job_id,
            item_id=item.item_id,
            row_index=item.row_index,
            row_json=item.row_json,
            status="pending",
            source_id=item.source_id,
            attempt_count=item.attempt_count,
            last_error=error_message,
            result_json=item.result_json,
            reported_at=item.reported_at,
            completed_at=None,
            assigned_thread_id=None,
            status_updated_at=_utc_now(),
        )

    def mark_agent_job_item_failed(self, job_id: str, item_id: str, last_error: str) -> None:
        key = (job_id, item_id)
        item = self.items.get(key)
        if item is None:
            return
        if item.status not in {"running", "pending"}:
            return
        now = _utc_now()
        self.items[key] = AgentJobItem(
            job_id=item.job_id,
            item_id=item.item_id,
            row_index=item.row_index,
            row_json=item.row_json,
            status="failed",
            source_id=item.source_id,
            attempt_count=item.attempt_count,
            last_error=last_error,
            result_json=item.result_json,
            reported_at=item.reported_at,
            completed_at=now,
            assigned_thread_id=None,
            status_updated_at=now,
        )

    def mark_agent_job_item_completed(self, job_id: str, item_id: str) -> bool:
        key = (job_id, item_id)
        item = self.items.get(key)
        if item is None:
            return False
        if item.status != "running":
            return False
        now = _utc_now()
        self.items[key] = AgentJobItem(
            job_id=item.job_id,
            item_id=item.item_id,
            row_index=item.row_index,
            row_json=item.row_json,
            status="completed",
            source_id=item.source_id,
            attempt_count=item.attempt_count,
            last_error=None,
            result_json=item.result_json,
            reported_at=item.reported_at,
            completed_at=now,
            assigned_thread_id=None,
            status_updated_at=now,
        )
        return True

    def mark_agent_job_completed(self, job_id: str) -> None:
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = "completed"
            self.jobs[job_id]["last_error"] = None
            self.jobs[job_id]["completed_at"] = _utc_now()

    def mark_agent_job_failed(self, job_id: str, last_error: str) -> None:
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = "failed"
            self.jobs[job_id]["last_error"] = last_error
            self.jobs[job_id]["completed_at"] = _utc_now()


@dataclass(frozen=True)
class AgentJobRecord:
    id: str
    status: str
    input_headers: list[str]
    input_csv_path: str
    output_csv_path: str
    last_error: str | None
    max_runtime_seconds: int | None
    instruction: str
    output_schema_json: JsonValue | None = None


@dataclass(frozen=True)
class AgentJobProgress:
    total_items: int
    completed_items: int
    failed_items: int
    running_items: int = 0
    pending_items: int = 0


@dataclass(frozen=True)
class ActiveJobItem:
    item_id: str
    started_at: float
    status_subscription: Any = None


class AgentJobResultStore(Protocol):
    def report_agent_job_item_result(
        self,
        job_id: str,
        item_id: str,
        reporting_thread_id: str,
        result: Mapping[str, JsonValue],
    ) -> bool:
        ...

    def mark_agent_job_cancelled(self, job_id: str, message: str) -> None:
        ...


class AgentJobRuntimeStore(Protocol):
    def create_agent_job(self, **kwargs: Any) -> Any:
        ...

    def create_agent_job_items(self, job_id: str, items: tuple[AgentJobItemCreateParams, ...]) -> Any:
        ...

    def get_agent_job(self, job_id: str) -> Any:
        ...

    def mark_agent_job_running(self, job_id: str) -> Any:
        ...

    def get_agent_job_progress(self, job_id: str) -> Any:
        ...

    def list_agent_job_items(self, job_id: str, status: str | None = None, limit: int | None = None) -> Any:
        ...

    def is_agent_job_cancelled(self, job_id: str) -> bool:
        ...

    def mark_agent_job_completed(self, job_id: str) -> Any:
        ...

    def mark_agent_job_failed(self, job_id: str, message: str) -> Any:
        ...

    def mark_agent_job_item_pending(self, job_id: str, item_id: str, error_message: str | None = None) -> Any:
        ...

    def mark_agent_job_item_running_with_thread(self, job_id: str, item_id: str, thread_id: str) -> bool:
        ...

    def mark_agent_job_item_failed(self, job_id: str, item_id: str, message: str) -> Any:
        ...

    def mark_agent_job_item_completed(self, job_id: str, item_id: str) -> Any:
        ...

    def get_agent_job_item(self, job_id: str, item_id: str) -> Any:
        ...


class AgentJobAgentControl(Protocol):
    """Runtime interface consumed by Rust's agent-job runner."""

    def spawn_agent_with_metadata(
        self,
        spawn_config: Any,
        items: tuple[UserInput, ...],
        session_source: SessionSource | None,
        options: Any,
    ) -> Any:
        ...

    def subscribe_status(self, thread_id: Any) -> Any:
        ...

    def get_status(self, thread_id: Any) -> Any:
        ...

    def shutdown_live_agent(self, thread_id: Any) -> Any:
        ...


def create_spawn_agents_on_csv_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": SPAWN_AGENTS_ON_CSV_TOOL_NAME,
        "description": "Process a CSV by spawning one worker sub-agent per row. The instruction string is a template where `{column}` placeholders are replaced with row values. Each worker must call `report_agent_job_result` with a JSON object (matching `output_schema` when provided); missing reports are treated as failures. This call blocks until all rows finish and automatically exports results to `output_csv_path` (or a default path).",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "csv_path": {"type": "string", "description": "Path to the CSV file containing input rows."},
                "instruction": {"type": "string", "description": "Instruction template to apply to each CSV row. Use {column_name} placeholders to inject values from the row."},
                "id_column": {"type": "string", "description": "Optional column name to use as stable item id."},
                "output_csv_path": {"type": "string", "description": "Optional output CSV path for exported results."},
                "max_concurrency": {"type": "number", "description": "Maximum concurrent workers for this job. Defaults to 16 and is capped by config."},
                "max_workers": {"type": "number", "description": "Alias for max_concurrency. Set to 1 to run sequentially."},
                "max_runtime_seconds": {"type": "number", "description": "Maximum runtime per worker before it is failed. Defaults to 1800 seconds."},
                "output_schema": {"type": "object", "properties": {}},
            },
            "required": ["csv_path", "instruction"],
            "additionalProperties": False,
        },
    }


def create_report_agent_job_result_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": REPORT_AGENT_JOB_RESULT_TOOL_NAME,
        "description": "Worker-only tool to report a result for an agent job item. Main agents should not call this.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Identifier of the job."},
                "item_id": {"type": "string", "description": "Identifier of the job item."},
                "result": {"type": "object", "properties": {}},
                "stop": {"type": "boolean", "description": "Optional. When true, cancels the remaining job items after this result is recorded."},
            },
            "required": ["job_id", "item_id", "result"],
            "additionalProperties": False,
        },
    }


class SpawnAgentsOnCsvHandler:
    def __init__(
        self,
        state_db: Any | None = None,
    ) -> None:
        self.state_db = state_db

    def tool_name(self) -> ToolName:
        return ToolName.plain(SPAWN_AGENTS_ON_CSV_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_spawn_agents_on_csv_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return _matches_function(payload)

    def _resolve_runtime_store(self, invocation_or_payload: Any) -> AgentJobRuntimeStore:
        if self.state_db is not None:
            return self.state_db
        session = getattr(invocation_or_payload, "session", None)
        if session is None:
            raise FunctionCallError.respond_to_model("sqlite state db is unavailable for this session")
        candidate = getattr(session, "state_db", None)
        if candidate is not None:
            return candidate
        candidate = getattr(session, "state_runtime", None)
        if candidate is not None:
            return candidate
        services = getattr(session, "services", None)
        candidate = getattr(services, "state_db", None)
        if candidate is not None:
            return candidate
        raise FunctionCallError.respond_to_model("sqlite state db is unavailable for this session")

    def _resolve_agent_control(self, invocation_or_payload: Any) -> AgentJobAgentControl:
        session = getattr(invocation_or_payload, "session", None)
        services = getattr(session, "services", None)
        candidate = getattr(services, "agent_control", None)
        if candidate is None:
            candidate = getattr(session, "agent_control", None)
        if candidate is None:
            raise FunctionCallError.respond_to_model("agent_control is unavailable for this session")
        missing = [
            name
            for name in (
                "spawn_agent_with_metadata",
                "subscribe_status",
                "get_status",
                "shutdown_live_agent",
            )
            if not callable(getattr(candidate, name, None))
        ]
        if missing:
            raise FunctionCallError.respond_to_model(
                f"agent_control is missing required methods: {', '.join(missing)}"
            )
        return candidate

    def _job_name(self, job_id: str) -> str:
        return f"agent-job-{job_id[:8]}"

    def _run_agent_job_runtime(
        self,
        store: AgentJobRuntimeStore,
        agent_control: AgentJobAgentControl,
        invocation_or_payload: Any,
        job_id: str,
        concurrency: int,
        max_runtime_seconds: int | None,
    ) -> None:
        if concurrency <= 0:
            concurrency = 1
        job = _sync_await(store.get_agent_job(job_id))
        if job is None:
            raise RuntimeError(f"agent job {job_id} was not found")
        active_items: dict[Any, ActiveJobItem] = {}
        self._recover_running_items(store, agent_control, job_id, active_items, max_runtime_seconds)
        cancel_requested = bool(_sync_await(store.is_agent_job_cancelled(job_id)))
        while True:
            progressed = False
            if not cancel_requested and _sync_await(store.is_agent_job_cancelled(job_id)):
                cancel_requested = True

            if not cancel_requested and len(active_items) < concurrency:
                if self._spawn_pending_items(
                    store,
                    agent_control,
                    invocation_or_payload,
                    job,
                    active_items,
                    concurrency - len(active_items),
                ):
                    progressed = True

            if self._reap_stale_active_items(
                store,
                agent_control,
                job_id,
                active_items,
                max_runtime_seconds,
            ):
                progressed = True

            finished = self._find_finished_threads(agent_control, active_items)
            if finished:
                for thread_id, item_id in finished:
                    self._finalize_finished_item(store, agent_control, job_id, item_id, thread_id)
                    active_items.pop(thread_id, None)
                continue

            progress = _sync_await(store.get_agent_job_progress(job_id))
            if cancel_requested and progress.running_items == 0 and not active_items:
                break
            if (
                not cancel_requested
                and progress.pending_items == 0
                and progress.running_items == 0
                and not active_items
            ):
                break
            if not progressed:
                time.sleep(STATUS_POLL_INTERVAL_SECONDS)

        return

    def _recover_running_items(
        self,
        store: AgentJobRuntimeStore,
        agent_control: AgentJobAgentControl,
        job_id: str,
        active_items: dict[Any, ActiveJobItem],
        max_runtime_seconds: int | None,
    ) -> None:
        running_items = _sync_await(store.list_agent_job_items(job_id, status="running", limit=None))
        for item in running_items:
            thread_id_text = getattr(item, "assigned_thread_id", None)
            if not thread_id_text:
                _sync_await(store.mark_agent_job_item_failed(job_id, item.item_id, "running item is missing assigned_thread_id"))
                continue
            try:
                thread_id = ThreadId.from_string(thread_id_text)
            except Exception:
                thread_id = thread_id_text
            if _is_item_stale(item, max_runtime_seconds):
                _sync_await(store.mark_agent_job_item_failed(
                    job_id,
                    item.item_id,
                    f"worker exceeded max runtime of {max_runtime_seconds}s",
                ))
                _shutdown_live_agent(agent_control, thread_id)
                continue
            if _status_is_final(_sync_await(agent_control.get_status(thread_id))):
                self._finalize_finished_item(store, agent_control, job_id, item.item_id, thread_id)
                continue
            active_items[thread_id] = ActiveJobItem(
                item_id=item.item_id,
                started_at=_started_at_from_item(item),
                status_subscription=_optional_subscribe_status(agent_control, thread_id),
            )

    def _spawn_pending_items(
        self,
        store: AgentJobRuntimeStore,
        agent_control: AgentJobAgentControl,
        invocation_or_payload: Any,
        job: AgentJobRecord,
        active_items: dict[Any, ActiveJobItem],
        slots: int,
    ) -> bool:
        progressed = False
        pending_items = _sync_await(store.list_agent_job_items(job.id, status="pending", limit=slots))
        for item in pending_items:
            prompt = build_worker_prompt(
                job_id=job.id,
                item_id=item.item_id,
                instruction=job.instruction,
                row_json=item.row_json,
                output_schema=job.output_schema_json,
            )
            try:
                spawned = _sync_await(agent_control.spawn_agent_with_metadata(
                    _spawn_config_for(invocation_or_payload),
                    (UserInput.text_input(prompt),),
                    SessionSource.subagent(SubAgentSource.other_source(f"agent_job:{job.id}")),
                    _spawn_options_for(invocation_or_payload),
                ))
            except Exception as err:
                if _is_agent_limit_reached(err):
                    _sync_await(store.mark_agent_job_item_pending(job.id, item.item_id, None))
                    break
                _sync_await(store.mark_agent_job_item_failed(job.id, item.item_id, f"failed to spawn worker: {err}"))
                progressed = True
                continue
            thread_id = _spawned_thread_id(spawned)
            assigned = _sync_await(store.mark_agent_job_item_running_with_thread(
                job.id,
                item.item_id,
                str(thread_id),
            ))
            if not assigned:
                _shutdown_live_agent(agent_control, thread_id)
                continue
            active_items[thread_id] = ActiveJobItem(
                item_id=item.item_id,
                started_at=time.time(),
                status_subscription=_optional_subscribe_status(agent_control, thread_id),
            )
            progressed = True
        return progressed

    def _find_finished_threads(
        self,
        agent_control: AgentJobAgentControl,
        active_items: dict[Any, ActiveJobItem],
    ) -> list[tuple[Any, str]]:
        finished: list[tuple[Any, str]] = []
        for thread_id, item in active_items.items():
            status = _active_item_status(agent_control, thread_id, item)
            if _status_is_final(status):
                finished.append((thread_id, item.item_id))
        return finished

    def _reap_stale_active_items(
        self,
        store: AgentJobRuntimeStore,
        agent_control: AgentJobAgentControl,
        job_id: str,
        active_items: dict[Any, ActiveJobItem],
        max_runtime_seconds: int | None,
    ) -> bool:
        if max_runtime_seconds is None:
            return False
        stale = [
            (thread_id, item.item_id)
            for thread_id, item in active_items.items()
            if time.time() - item.started_at >= max_runtime_seconds
        ]
        for thread_id, item_id in stale:
            _sync_await(store.mark_agent_job_item_failed(
                job_id,
                item_id,
                f"worker exceeded max runtime of {max_runtime_seconds}s",
            ))
            _shutdown_live_agent(agent_control, thread_id)
            active_items.pop(thread_id, None)
        return bool(stale)

    def _finalize_finished_item(
        self,
        store: AgentJobRuntimeStore,
        agent_control: AgentJobAgentControl,
        job_id: str,
        item_id: str,
        thread_id: Any,
    ) -> None:
        item = _sync_await(store.get_agent_job_item(job_id, item_id))
        if item is None:
            raise RuntimeError(f"job item not found for finalization: {job_id}/{item_id}")
        if _status_text(item.status) == "running":
            if item.result_json is not None:
                _sync_await(store.mark_agent_job_item_completed(job_id, item_id))
            else:
                _sync_await(store.mark_agent_job_item_failed(
                    job_id,
                    item_id,
                    "worker finished without calling report_agent_job_result",
                ))
        _shutdown_live_agent(agent_control, thread_id)

    def _export_job_csv_snapshot(self, store: AgentJobRuntimeStore, job_id: str) -> None:
        job = _sync_await(store.get_agent_job(job_id))
        if job is None:
            return
        items = _sync_await(store.list_agent_job_items(job_id, None, None))
        output_csv_path = Path(job.output_csv_path)
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        output_csv_path.write_text(
            render_job_csv(job.input_headers, items),
            encoding="utf-8",
        )

    def _collect_failed_item_summaries(
        self,
        store: AgentJobRuntimeStore,
        job_id: str,
    ) -> tuple[AgentJobFailureSummary, ...] | None:
        failed_items = _sync_await(store.list_agent_job_items(job_id, status="failed", limit=5))
        summaries = [
            AgentJobFailureSummary(
                item_id=item.item_id,
                source_id=item.source_id,
                last_error=item.last_error or "",
            )
            for item in failed_items
            if item.last_error and item.last_error.strip()
        ]
        if not summaries:
            return None
        return tuple(summaries)

    def _max_runtime_seconds_or_default(self, turn: Any, requested_seconds: int | None) -> int:
        requested = normalize_max_runtime_seconds(
            requested_seconds if requested_seconds is not None else _turn_max_runtime_seconds(turn)
        )
        return requested if requested is not None else DEFAULT_AGENT_JOB_ITEM_TIMEOUT_SECONDS

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model("agent jobs handler received unsupported payload")

        args = parse_spawn_agents_on_csv_arguments(payload.arguments or "")
        if args.instruction.strip() == "":
            raise FunctionCallError.respond_to_model("instruction must be non-empty")

        turn = getattr(invocation_or_payload, "turn", None)
        if turn is None:
            raise FunctionCallError.respond_to_model("spawn_agents_on_csv requires a turn context")
        cwd = single_local_environment_cwd(turn)
        store = self._resolve_runtime_store(invocation_or_payload)
        agent_control = self._resolve_agent_control(invocation_or_payload)
        max_depth = _turn_max_depth(turn)
        if max_depth is not None:
            session_source = getattr(turn, "session_source", None)
            if not isinstance(session_source, SessionSource):
                session_source = SessionSource.default()
            child_depth = next_thread_spawn_depth(session_source)
            if exceeds_thread_spawn_depth_limit(child_depth, max_depth):
                raise FunctionCallError.respond_to_model(
                    "agent depth limit reached; this session cannot spawn more subagents"
                )

        input_path = cwd / args.csv_path
        try:
            csv_content = input_path.read_text()
        except OSError as err:
            raise FunctionCallError.respond_to_model(
                f"failed to read csv input {input_path}: {err}"
            ) from err

        headers, rows = parse_csv(csv_content)
        if not headers:
            raise FunctionCallError.respond_to_model("csv input must include a header row")
        ensure_unique_headers(headers)

        items = build_agent_job_items(headers, rows, args.id_column)
        job_id = str(uuid.uuid4())
        output_csv_path = default_output_csv_path(input_path, job_id) if args.output_csv_path is None else cwd / args.output_csv_path

        max_threads = _turn_max_threads(turn)
        if max_threads == 0:
            raise FunctionCallError.respond_to_model(
                "agent thread limit reached; this session cannot spawn more subagents"
            )
        concurrency = normalize_concurrency(args.max_concurrency or args.max_workers, max_threads)
        max_runtime_seconds = self._max_runtime_seconds_or_default(
            turn,
            args.max_runtime_seconds,
        )

        try:
            _sync_await(store.create_agent_job(
                job_id=job_id,
                name=self._job_name(job_id),
                instruction=args.instruction,
                auto_export=True,
                max_runtime_seconds=max_runtime_seconds,
                output_schema_json=args.output_schema,
                input_headers=headers,
                input_csv_path=str(input_path),
                output_csv_path=str(output_csv_path),
            ))
            _sync_await(store.create_agent_job_items(job_id, items))
            _sync_await(store.mark_agent_job_running(job_id))
        except Exception as err:
            raise FunctionCallError.respond_to_model(f"failed to create or start agent job {job_id}: {err}") from err

        try:
            self._run_agent_job_runtime(
                store,
                agent_control,
                invocation_or_payload,
                job_id,
                concurrency,
                max_runtime_seconds,
            )
        except Exception as err:
            _sync_await(store.mark_agent_job_failed(job_id, f"agent job failed: {err}"))
            raise FunctionCallError.respond_to_model(f"agent job {job_id} failed: {err}") from err

        try:
            self._export_job_csv_snapshot(store, job_id)
        except Exception as err:
            _sync_await(store.mark_agent_job_failed(job_id, f"auto-export failed: {err}"))

        progress = _sync_await(store.get_agent_job_progress(job_id))
        job_record = _sync_await(store.get_agent_job(job_id))
        failed_item_errors = self._collect_failed_item_summaries(store, job_id)
        job_error = None if job_record is None else job_record.last_error
        if progress.failed_items > 0 and failed_item_errors is None and job_error is None:
            job_error = "agent job has failed items but no error details were recorded"

        if _sync_await(store.is_agent_job_cancelled(job_id)):
            status = "cancelled"
        elif job_record is not None and job_record.status == "failed":
            status = "failed"
        elif job_record is None or job_record.status != "completed":
            try:
                _sync_await(store.mark_agent_job_completed(job_id))
            except Exception:
                pass
            status = "completed"
        else:
            status = job_record.status

        result = SpawnAgentsOnCsvResult(
            job_id=job_id,
            status=status,
            output_csv_path=str(output_csv_path),
            total_items=progress.total_items,
            completed_items=progress.completed_items,
            failed_items=progress.failed_items,
            job_error=job_error,
            failed_item_errors=failed_item_errors,
        )
        return FunctionToolOutput.from_text(json.dumps(result.to_mapping(), separators=(",", ":")), True)

    def handle_prepare_only(self, arguments: str, cwd: Path) -> tuple[str, str, tuple[AgentJobItemCreateParams, ...]]:
        args = parse_spawn_agents_on_csv_arguments(arguments)
        if args.instruction.strip() == "":
            raise FunctionCallError.respond_to_model("instruction must be non-empty")
        input_path = cwd / args.csv_path
        try:
            csv_content = input_path.read_text()
        except OSError as err:
            raise FunctionCallError.respond_to_model(f"failed to read csv input {input_path}: {err}") from err
        headers, rows = parse_csv(csv_content)
        if not headers:
            raise FunctionCallError.respond_to_model("csv input must include a header row")
        ensure_unique_headers(headers)
        job_id = str(uuid.uuid4())
        return job_id, str(default_output_csv_path(input_path, job_id)), build_agent_job_items(headers, rows, args.id_column)


def single_local_environment_cwd(turn: Any) -> Path:
    environments = getattr(turn, "environments", None)
    if environments is None:
        raise FunctionCallError.respond_to_model(
            "spawn_agents_on_csv requires exactly one local environment"
        )

    turn_environments = tuple(getattr(environments, "turn_environments", ()) or ())
    if len(turn_environments) != 1:
        raise FunctionCallError.respond_to_model(
            "spawn_agents_on_csv requires exactly one local environment"
        )
    environment = turn_environments[0]
    env_value = getattr(environment, "environment", None)
    if env_value is not None:
        is_remote = getattr(env_value, "is_remote", None)
        if callable(is_remote) and is_remote():
            raise FunctionCallError.respond_to_model(
                "spawn_agents_on_csv is not supported for remote environments"
            )

    cwd = getattr(environment, "cwd", None)
    if not isinstance(cwd, Path):
        raise TypeError("environment cwd must be a path")
    return cwd


def _turn_max_threads(turn: Any) -> int | None:
    config = getattr(turn, "config", None)
    return getattr(config, "agent_max_threads", None)


def _turn_max_depth(turn: Any) -> int | None:
    config = getattr(turn, "config", None)
    return getattr(config, "agent_max_depth", None)


def _turn_max_runtime_seconds(turn: Any) -> int | None:
    config = getattr(turn, "config", None)
    return getattr(config, "agent_job_max_runtime_seconds", None)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sync_await(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)

    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["value"] = asyncio.run(value)
        except BaseException as err:
            result["error"] = err

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _spawn_config_for(invocation_or_payload: Any) -> Any:
    session = getattr(invocation_or_payload, "session", None)
    turn = getattr(invocation_or_payload, "turn", None)
    builder = getattr(session, "build_agent_spawn_config", None)
    if callable(builder):
        return _sync_await(builder(turn))
    candidate = getattr(turn, "spawn_config", None)
    if candidate is not None:
        return candidate
    return getattr(turn, "config", None)


def _spawn_options_for(invocation_or_payload: Any) -> dict[str, Any]:
    turn = getattr(invocation_or_payload, "turn", None)
    environments = getattr(turn, "environments", None)
    selections = None
    to_selections = getattr(environments, "to_selections", None)
    if callable(to_selections):
        selections = to_selections()
    return {"environments": selections}


def _spawned_thread_id(spawned: Any) -> Any:
    if isinstance(spawned, Mapping):
        thread_id = spawned.get("thread_id")
    else:
        thread_id = getattr(spawned, "thread_id", None)
    if thread_id is None:
        raise RuntimeError("spawn_agent_with_metadata returned no thread_id")
    if isinstance(thread_id, str):
        try:
            return ThreadId.from_string(thread_id)
        except Exception:
            return thread_id
    return thread_id


def _optional_subscribe_status(agent_control: AgentJobAgentControl, thread_id: Any) -> Any:
    try:
        return _sync_await(agent_control.subscribe_status(thread_id))
    except Exception:
        return None


def _active_item_status(
    agent_control: AgentJobAgentControl,
    thread_id: Any,
    item: ActiveJobItem,
) -> Any:
    subscription = item.status_subscription
    if subscription is not None:
        status = _subscription_status_if_changed(subscription)
        if status is not None:
            return status
    return _sync_await(agent_control.get_status(thread_id))


def _subscription_status_if_changed(subscription: Any) -> Any:
    has_changed = getattr(subscription, "has_changed", None)
    if callable(has_changed):
        try:
            changed = _sync_await(has_changed())
        except Exception:
            changed = False
        if changed:
            return _subscription_current_status(subscription)
    return None


def _subscription_current_status(subscription: Any) -> Any:
    for name in ("borrow", "get", "value"):
        candidate = getattr(subscription, name, None)
        if callable(candidate):
            return _sync_await(candidate())
        if candidate is not None:
            return candidate
    return None


def _shutdown_live_agent(agent_control: AgentJobAgentControl, thread_id: Any) -> None:
    try:
        _sync_await(agent_control.shutdown_live_agent(thread_id))
    except Exception:
        pass


def _status_is_final(status: Any) -> bool:
    if status is None:
        return False
    try:
        return bool(is_final(status))
    except Exception:
        status_type = getattr(status, "type", None)
        if status_type is None and isinstance(status, Mapping):
            status_type = status.get("type")
        return status_type not in {None, "pending_init", "running", "interrupted"}


def _is_agent_limit_reached(err: Exception) -> bool:
    if isinstance(CodexErr, type) and isinstance(err, CodexErr):
        return "AgentLimitReached" in type(err).__name__ or "agent limit" in str(err).lower()
    return "agentlimitreached" in type(err).__name__.lower() or "agent limit" in str(err).lower()


def _status_text(status: Any) -> str:
    if isinstance(status, str):
        return status
    value = getattr(status, "value", None)
    if isinstance(value, str):
        return value
    value = getattr(status, "type", None)
    if isinstance(value, str):
        return value
    return str(status)


def _started_at_from_item(item: AgentJobItem) -> float:
    timestamp = getattr(item, "status_updated_at", None) or getattr(item, "updated_at", None)
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return time.time()
    return time.time() - max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _is_item_stale(item: AgentJobItem, max_runtime_seconds: int | None) -> bool:
    if max_runtime_seconds is None:
        return False
    timestamp = getattr(item, "status_updated_at", None) or getattr(item, "updated_at", None)
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return False
    return (datetime.now(timezone.utc) - parsed).total_seconds() >= max_runtime_seconds


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class ReportAgentJobResultHandler:
    def __init__(self, store: AgentJobResultStore | None = None, *, reporting_thread_id: str = "") -> None:
        self.store = store
        self.reporting_thread_id = reporting_thread_id

    def tool_name(self) -> ToolName:
        return ToolName.plain(REPORT_AGENT_JOB_RESULT_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_report_agent_job_result_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return _matches_function(payload)

    def _resolve_store(self, invocation_or_payload: Any) -> AgentJobResultStore:
        if self.store is not None:
            return self.store
        session = getattr(invocation_or_payload, "session", None)
        if session is None:
            raise FunctionCallError.respond_to_model("sqlite state db is unavailable for this session")
        candidate = getattr(session, "state_db", None)
        if candidate is not None:
            return candidate
        candidate = getattr(session, "state_runtime", None)
        if candidate is not None:
            return candidate
        services = getattr(session, "services", None)
        candidate = getattr(services, "state_db", None)
        if candidate is not None:
            return candidate
        raise FunctionCallError.respond_to_model("sqlite state db is unavailable for this session")

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model("report_agent_job_result handler received unsupported payload")
        reporting_thread_id = self.reporting_thread_id
        if reporting_thread_id == "":
            session = getattr(invocation_or_payload, "session", None)
            reporting_thread_id = getattr(session, "conversation_id", "")
            if reporting_thread_id == "":
                raise FunctionCallError.respond_to_model(
                    "report_agent_job_result requires a reporting_thread_id"
                )
        try:
            args = parse_report_agent_job_result_arguments(payload.arguments or "")
        except Exception as err:
            if isinstance(err, FunctionCallError):
                raise
            raise FunctionCallError.respond_to_model(str(err)) from err
        try:
            store = self._resolve_store(invocation_or_payload)
            accepted = _sync_await(store.report_agent_job_item_result(
                args.job_id,
                args.item_id,
                reporting_thread_id,
                args.result,
            ))
        except FunctionCallError:
            raise
        except Exception as err:
            raise FunctionCallError.respond_to_model(
                f"failed to record agent job result for {args.job_id} / {args.item_id}: {err}"
            ) from err
        if accepted and args.stop is True:
            _sync_await(store.mark_agent_job_cancelled(args.job_id, "cancelled by worker request"))
        return FunctionToolOutput.from_text(json.dumps(ReportAgentJobResultToolResult(accepted).to_mapping(), separators=(",", ":")), True)


def parse_spawn_agents_on_csv_arguments(arguments: str) -> SpawnAgentsOnCsvArgs:
    return SpawnAgentsOnCsvArgs.from_mapping(_parse_json_object(arguments))


def parse_report_agent_job_result_arguments(arguments: str) -> ReportAgentJobResultArgs:
    return ReportAgentJobResultArgs.from_mapping(_parse_json_object(arguments))


def normalize_concurrency(requested: int | None, max_threads: int | None) -> int:
    requested = max(requested if requested is not None else DEFAULT_AGENT_JOB_CONCURRENCY, 1)
    requested = min(requested, MAX_AGENT_JOB_CONCURRENCY)
    if max_threads is None:
        return requested
    return min(requested, max(max_threads, 1))


def normalize_max_runtime_seconds(requested: int | None) -> int | None:
    if requested is None:
        return None
    _u64(requested, "max_runtime_seconds")
    if requested == 0:
        raise FunctionCallError.respond_to_model("max_runtime_seconds must be >= 1")
    return requested


def parse_csv(content: str) -> tuple[list[str], list[list[str]]]:
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    reader = csv.reader(StringIO(content))
    try:
        headers = next(reader)
    except csv.Error as err:
        raise FunctionCallError.respond_to_model(f"failed to parse csv input: {err}") from err
    except StopIteration:
        return [], []
    if headers:
        headers[0] = headers[0].lstrip("\ufeff")
    try:
        rows = [row for row in reader if not all(value == "" for value in row)]
    except csv.Error as err:
        raise FunctionCallError.respond_to_model(f"failed to parse csv input: {err}") from err
    return headers, rows


def build_agent_job_items(
    headers: list[str],
    rows: list[list[str]],
    id_column: str | None,
) -> tuple[AgentJobItemCreateParams, ...]:
    id_column_index = None
    if id_column is not None:
        try:
            id_column_index = headers.index(id_column)
        except ValueError as err:
            raise FunctionCallError.respond_to_model(f"id_column {id_column} was not found in csv headers") from err
    items: list[AgentJobItemCreateParams] = []
    seen_ids: set[str] = set()
    for idx, row in enumerate(rows):
        if len(row) != len(headers):
            raise FunctionCallError.respond_to_model(
                f"csv row {idx + 2} has {len(row)} fields but header has {len(headers)}"
            )
        source_id = None
        if id_column_index is not None:
            raw_source_id = row[id_column_index]
            if raw_source_id.strip() != "":
                source_id = raw_source_id
        row_index = idx + 1
        base_item_id = source_id or f"row-{row_index}"
        item_id = base_item_id
        suffix = 2
        while item_id in seen_ids:
            item_id = f"{base_item_id}-{suffix}"
            suffix += 1
        seen_ids.add(item_id)
        items.append(
            AgentJobItemCreateParams(
                item_id=item_id,
                row_index=idx,
                source_id=source_id,
                row_json=dict(zip(headers, row)),
            )
        )
    return tuple(items)


def render_instruction_template(instruction: str, row_json: Mapping[str, JsonValue]) -> str:
    if not isinstance(instruction, str):
        raise TypeError("instruction must be a string")
    if not isinstance(row_json, Mapping):
        raise TypeError("row_json must be a mapping")
    open_sentinel = "__CODEX_OPEN_BRACE__"
    close_sentinel = "__CODEX_CLOSE_BRACE__"
    rendered = instruction.replace("{{", open_sentinel).replace("}}", close_sentinel)
    for key, value in row_json.items():
        rendered = rendered.replace(
            f"{{{key}}}",
            value if isinstance(value, str) else json.dumps(value, separators=(",", ":")),
        )
    return rendered.replace(open_sentinel, "{").replace(close_sentinel, "}")


def build_worker_prompt(
    *,
    job_id: str,
    item_id: str,
    instruction: str,
    row_json: Mapping[str, JsonValue],
    output_schema: JsonValue | None = None,
) -> str:
    _require_str(job_id, "job_id")
    _require_str(item_id, "item_id")
    _require_str(instruction, "instruction")
    if not isinstance(row_json, Mapping):
        raise TypeError("row_json must be a mapping")
    rendered_instruction = render_instruction_template(instruction, row_json)
    output_schema_json = (
        "{}"
        if output_schema is None
        else json.dumps(output_schema, indent=2, ensure_ascii=False)
    )
    row_json_pretty = json.dumps(dict(row_json), indent=2, ensure_ascii=False)
    return (
        "You are processing one item for a generic agent job.\n"
        f"Job ID: {job_id}\n"
        f"Item ID: {item_id}\n\n"
        "Task instruction:\n"
        f"{rendered_instruction}\n\n"
        "Input row (JSON):\n"
        f"{row_json_pretty}\n\n"
        "Expected result schema (JSON Schema or {}):\n"
        f"{output_schema_json}\n\n"
        "You MUST call the `report_agent_job_result` tool exactly once with:\n"
        f"1. `job_id` = \"{job_id}\"\n"
        f"2. `item_id` = \"{item_id}\"\n"
        "3. `result` = a JSON object that contains your analysis result for this row.\n\n"
        "If you need to stop the job early, include `stop` = true in the tool call.\n\n"
        "After the tool call succeeds, stop."
    )


def ensure_unique_headers(headers: list[str]) -> None:
    seen: set[str] = set()
    for header in headers:
        if header in seen:
            raise FunctionCallError.respond_to_model(f"csv header {header} is duplicated")
        seen.add(header)


def default_output_csv_path(input_csv_path: Path, job_id: str) -> Path:
    if not isinstance(input_csv_path, Path):
        raise TypeError("input_csv_path must be Path")
    _require_str(job_id, "job_id")
    stem = input_csv_path.stem or "agent_job_output"
    output_dir = input_csv_path.parent
    return output_dir / f"{stem}.agent-job-{job_id[:8]}.csv"


def render_job_csv(headers: list[str], items: list[AgentJobItem]) -> str:
    output_headers = headers + [
        "job_id",
        "item_id",
        "row_index",
        "source_id",
        "status",
        "attempt_count",
        "last_error",
        "result_json",
        "reported_at",
        "completed_at",
    ]
    lines = [",".join(csv_escape(header) for header in output_headers)]
    for item in items:
        row_values = [csv_escape(value_to_csv_string(item.row_json.get(header))) for header in headers]
        row_values.extend(
            [
                csv_escape(item.job_id),
                csv_escape(item.item_id),
                csv_escape(str(item.row_index)),
                csv_escape(item.source_id or ""),
                csv_escape(item.status),
                csv_escape(str(item.attempt_count)),
                csv_escape(item.last_error or ""),
                csv_escape(value_to_csv_string(item.result_json)),
                csv_escape(item.reported_at or ""),
                csv_escape(item.completed_at or ""),
            ]
        )
        lines.append(",".join(row_values))
    return "\n".join(lines) + "\n"


def value_to_csv_string(value: JsonValue) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value, separators=(",", ":"))


def csv_escape(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    if any(char in value for char in (",", "\n", "\r", '"')):
        return '"' + value.replace('"', '""') + '"'
    return value


def _matches_function(payload: ToolPayload) -> bool:
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    return payload.type == "function"


def _parse_json_object(arguments: str) -> dict[str, JsonValue]:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError as err:
        raise FunctionCallError.respond_to_model(f"failed to parse function arguments: {err}") from err
    if not isinstance(value, dict):
        raise FunctionCallError.respond_to_model("failed to parse function arguments: expected object")
    return value


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    return _require_str(value[key], key)


def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    return _require_str(raw, key)


def _optional_bool(value: Mapping[str, JsonValue], key: str) -> bool | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


def _optional_int(value: Mapping[str, JsonValue], key: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    return raw


def _require_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str_value(value: str | None, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")


def _optional_usize(value: int | None, field_name: str) -> None:
    if value is not None:
        _usize(value, field_name)


def _optional_u64(value: int | None, field_name: str) -> None:
    if value is not None:
        _u64(value, field_name)


def _usize(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _u64(value: JsonValue, field_name: str) -> int:
    _usize(value, field_name)
    if value > 2**64 - 1:
        raise ValueError(f"{field_name} is outside u64 range")
    return value
