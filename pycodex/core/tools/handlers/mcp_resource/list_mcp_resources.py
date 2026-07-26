"""Handler for the Rust ``list_mcp_resources`` module."""

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
from . import ListResourcesArgs
from . import ListResourcesPayload
from . import McpResourceProvider
from . import _await_events_then_output
from . import _await_events_then_raise
from . import _call_tool_result_from_content
from . import _duration_ms
from . import _emit_tool_call_begin
from . import _emit_tool_call_end
from . import _function_payload
from . import _matches_function
from . import _mcp_invocation
from . import _optional_normalized
from . import _provider_call
from . import parse_mcp_resource_arguments
from . import serialize_function_output


class ListMcpResourcesHandler:
    def __init__(self, provider: McpResourceProvider) -> None:
        self.provider = provider

    def tool_name(self) -> ToolName:
        return ToolName.plain(mcp_resource_spec.LIST_MCP_RESOURCES_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return mcp_resource_spec.create_list_mcp_resources_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        return _matches_function(payload)

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = _function_payload(
            invocation_or_payload,
            mcp_resource_spec.LIST_MCP_RESOURCES_TOOL_NAME,
        )
        arguments = parse_mcp_resource_arguments(payload.arguments)
        args = ListResourcesArgs.from_mapping(arguments)
        server = _optional_normalized(args.server)
        cursor = _optional_normalized(args.cursor)
        invocation = _mcp_invocation(
            server or "codex",
            mcp_resource_spec.LIST_MCP_RESOURCES_TOOL_NAME,
            arguments,
        )
        started = _emit_tool_call_begin(invocation_or_payload, invocation)
        started_at = time.perf_counter()
        try:
            if server is None:
                if cursor is not None:
                    raise FunctionCallError.respond_to_model(
                        "cursor can only be used when a server is specified"
                    )
                result = ListResourcesPayload.from_all_servers(
                    _provider_call(self.provider.list_all_resources, "resources/list")
                )
            else:
                result = ListResourcesPayload.from_single_server(
                    server,
                    _provider_call(
                        lambda: self.provider.list_resources(server, cursor),
                        "resources/list",
                    ),
                )
            output = serialize_function_output(result.to_mapping())
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


__all__ = ["ListMcpResourcesHandler"]
