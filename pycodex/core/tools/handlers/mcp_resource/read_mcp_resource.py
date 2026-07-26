"""Handler for the Rust ``read_mcp_resource`` module."""

from __future__ import annotations

import inspect
import time
from typing import Any

from pycodex.core.tools.context import FunctionToolOutput
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers import mcp_resource_spec
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ToolName

from . import JsonValue
from . import McpResourceProvider
from . import ReadResourceArgs
from . import ReadResourcePayload
from . import ReadResourceResult
from . import _await_events_then_output
from . import _await_events_then_raise
from . import _call_tool_result_from_content
from . import _duration_ms
from . import _emit_tool_call_begin
from . import _emit_tool_call_end
from . import _function_payload
from . import _matches_function
from . import _mcp_invocation
from . import _provider_call
from . import _required_normalized
from . import parse_mcp_resource_arguments
from . import serialize_function_output


class ReadMcpResourceHandler:
    def __init__(self, provider: McpResourceProvider) -> None:
        self.provider = provider

    def tool_name(self) -> ToolName:
        return ToolName.plain(mcp_resource_spec.READ_MCP_RESOURCE_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return mcp_resource_spec.create_read_mcp_resource_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        return _matches_function(payload)

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = _function_payload(
            invocation_or_payload,
            mcp_resource_spec.READ_MCP_RESOURCE_TOOL_NAME,
        )
        arguments = parse_mcp_resource_arguments(payload.arguments)
        args = ReadResourceArgs.from_mapping(arguments)
        server = _required_normalized("server", args.server)
        uri = _required_normalized("uri", args.uri)
        invocation = _mcp_invocation(
            server,
            mcp_resource_spec.READ_MCP_RESOURCE_TOOL_NAME,
            arguments,
        )
        started = _emit_tool_call_begin(invocation_or_payload, invocation)
        started_at = time.perf_counter()
        try:
            result = _provider_call(
                lambda: self.provider.read_resource(server, uri),
                "resources/read",
            )
            if not isinstance(result, ReadResourceResult):
                raise TypeError("read_resource must return ReadResourceResult")
            output = serialize_function_output(
                ReadResourcePayload(server, uri, result).to_mapping()
            )
        except FunctionCallError as err:
            ended = _emit_tool_call_end(
                invocation_or_payload,
                invocation,
                _duration_ms(started_at),
                error=str(err),
            )
            if inspect.isawaitable(started) or inspect.isawaitable(ended):
                return _await_events_then_raise(started, ended, err)
            raise
        ended = _emit_tool_call_end(
            invocation_or_payload,
            invocation,
            _duration_ms(started_at),
            result=_call_tool_result_from_content(output.into_text(), output.success),
        )
        if inspect.isawaitable(started) or inspect.isawaitable(ended):
            return _await_events_then_output(started, ended, output)
        return output


__all__ = ["ReadMcpResourceHandler"]
