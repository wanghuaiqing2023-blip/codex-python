"""Code-mode execute handler owned by the Rust ``execute_handler`` module."""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import ToolName

from . import CellIdAllocator
from . import CodeModeExecuteCallback
from . import ExecuteRequest
from . import JsonValue
from . import PUBLIC_TOOL_NAME
from . import ToolNamespaceDescription
from . import _coerce_runtime_response
from . import collect_code_mode_tool_definitions
from . import create_code_mode_tool
from . import handle_runtime_response
from . import is_exec_tool_name
from . import parse_exec_source
from . import sort_code_mode_tool_definitions


@dataclass(frozen=True)
class CodeModeExecuteHandler:
    nested_tool_specs: tuple[Mapping[str, JsonValue] | Any, ...] = ()
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None = None
    code_mode_only: bool = False
    deferred_tools_available: bool = False
    execute_callback: CodeModeExecuteCallback | None = None
    cell_id_allocator: CellIdAllocator | None = None
    can_request_original_detail: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "nested_tool_specs", tuple(self.nested_tool_specs))

    def tool_name(self) -> ToolName:
        return ToolName.plain(PUBLIC_TOOL_NAME)

    def spec(self) -> Any:
        enabled_tools = sort_code_mode_tool_definitions(
            collect_code_mode_tool_definitions(self.nested_tool_specs),
            self.namespace_descriptions,
        )
        return create_code_mode_tool(
            enabled_tools,
            self.namespace_descriptions,
            code_mode_only=self.code_mode_only,
            deferred_tools_available=self.deferred_tools_available,
        )

    def matches_kind(self, payload: Any) -> bool:
        return getattr(payload, "type", None) == "custom"

    def handle(self, invocation_or_payload: Any) -> Any:
        from pycodex.core.tools.context import ToolPayload

        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        tool_name = getattr(invocation_or_payload, "tool_name", self.tool_name())
        call_id = str(getattr(invocation_or_payload, "call_id", ""))
        if (
            not isinstance(payload, ToolPayload)
            or payload.type != "custom"
            or not is_exec_tool_name(tool_name)
            or payload.input is None
        ):
            raise ValueError(f"{PUBLIC_TOOL_NAME} expects raw JavaScript source text")
        if self.execute_callback is None:
            raise ValueError("code-mode execute callback is not configured")

        parsed = parse_exec_source(payload.input)
        request = ExecuteRequest(
            cell_id=self._allocate_cell_id(),
            tool_call_id=call_id,
            enabled_tools=collect_code_mode_tool_definitions(self.nested_tool_specs),
            source=parsed.code,
            yield_time_ms=parsed.yield_time_ms,
            max_output_tokens=parsed.max_output_tokens,
        )
        started_at = time.perf_counter()
        response = _coerce_runtime_response(self.execute_callback(request))
        return handle_runtime_response(
            response,
            max_output_tokens=parsed.max_output_tokens,
            wall_time_seconds=time.perf_counter() - started_at,
            can_request_original_detail=self.can_request_original_detail,
        )

    def _allocate_cell_id(self) -> str:
        if self.cell_id_allocator is not None:
            return str(self.cell_id_allocator())
        return str(uuid.uuid4())


__all__ = ["CodeModeExecuteHandler"]
