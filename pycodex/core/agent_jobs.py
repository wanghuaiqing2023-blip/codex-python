"""Agent job helpers ported from Codex core."""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Protocol

from pycodex.core.tool_context import FunctionToolOutput, ToolPayload
from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import ToolName

JsonValue = Any

SPAWN_AGENTS_ON_CSV_TOOL_NAME = "spawn_agents_on_csv"
REPORT_AGENT_JOB_RESULT_TOOL_NAME = "report_agent_job_result"
DEFAULT_AGENT_JOB_CONCURRENCY = 16
MAX_AGENT_JOB_CONCURRENCY = 64
DEFAULT_AGENT_JOB_ITEM_TIMEOUT_SECONDS = 60 * 30


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

    def report_agent_job_item_result(
        self,
        job_id: str,
        item_id: str,
        reporting_thread_id: str,
        result: Mapping[str, JsonValue],
    ) -> bool:
        _require_str(reporting_thread_id, "reporting_thread_id")
        self.reported_results[(job_id, item_id)] = dict(result)
        return True

    def mark_agent_job_cancelled(self, job_id: str, message: str) -> None:
        self.cancelled_jobs[job_id] = message


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
    def tool_name(self) -> ToolName:
        return ToolName.plain(SPAWN_AGENTS_ON_CSV_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_spawn_agents_on_csv_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return _matches_function(payload)

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


class ReportAgentJobResultHandler:
    def __init__(self, store: AgentJobResultStore | None = None, *, reporting_thread_id: str = "") -> None:
        self.store = store or InMemoryAgentJobStore()
        self.reporting_thread_id = reporting_thread_id

    def tool_name(self) -> ToolName:
        return ToolName.plain(REPORT_AGENT_JOB_RESULT_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_report_agent_job_result_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return _matches_function(payload)

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model("report_agent_job_result handler received unsupported payload")
        try:
            args = parse_report_agent_job_result_arguments(payload.arguments or "")
        except Exception as err:
            if isinstance(err, FunctionCallError):
                raise
            raise FunctionCallError.respond_to_model(str(err)) from err
        try:
            accepted = self.store.report_agent_job_item_result(
                args.job_id,
                args.item_id,
                self.reporting_thread_id,
                args.result,
            )
        except Exception as err:
            raise FunctionCallError.respond_to_model(
                f"failed to record agent job result for {args.job_id} / {args.item_id}: {err}"
            ) from err
        if accepted and args.stop is True:
            self.store.mark_agent_job_cancelled(args.job_id, "cancelled by worker request")
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
    except StopIteration:
        return [], []
    if headers:
        headers[0] = headers[0].lstrip("\ufeff")
    rows = [row for row in reader if not all(value == "" for value in row)]
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
