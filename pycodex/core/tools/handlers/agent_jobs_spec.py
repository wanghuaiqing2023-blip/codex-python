"""Tool specifications for the Rust ``agent_jobs_spec`` module."""

from __future__ import annotations

from typing import Any

JsonValue = Any

SPAWN_AGENTS_ON_CSV_TOOL_NAME = "spawn_agents_on_csv"
REPORT_AGENT_JOB_RESULT_TOOL_NAME = "report_agent_job_result"


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


__all__ = [
    "REPORT_AGENT_JOB_RESULT_TOOL_NAME",
    "SPAWN_AGENTS_ON_CSV_TOOL_NAME",
    "create_report_agent_job_result_tool",
    "create_spawn_agents_on_csv_tool",
]
