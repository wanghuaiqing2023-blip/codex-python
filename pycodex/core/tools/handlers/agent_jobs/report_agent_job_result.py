"""Agent-job result handler owned by its Rust child module."""

from __future__ import annotations

import json
from typing import Any

from pycodex.core.tools.context import FunctionToolOutput
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers import agent_jobs_spec
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ToolName

from . import AgentJobResultStore
from . import JsonValue
from . import ReportAgentJobResultToolResult
from . import _matches_function
from . import _sync_await
from . import parse_report_agent_job_result_arguments


class ReportAgentJobResultHandler:
    def __init__(self, store: AgentJobResultStore | None = None, *, reporting_thread_id: str = "") -> None:
        self.store = store
        self.reporting_thread_id = reporting_thread_id

    def tool_name(self) -> ToolName:
        return ToolName.plain(agent_jobs_spec.REPORT_AGENT_JOB_RESULT_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return agent_jobs_spec.create_report_agent_job_result_tool()

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
        return FunctionToolOutput.from_text(
            json.dumps(
                ReportAgentJobResultToolResult(accepted).to_mapping(),
                separators=(",", ":"),
            ),
            True,
        )


__all__ = ["ReportAgentJobResultHandler"]
