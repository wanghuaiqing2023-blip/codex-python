import pytest

from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers.dynamic import DynamicToolHandler
from pycodex.core.tools.handlers.multi_agents import SpawnAgentHandler
from pycodex.core.tools.handlers.tool_search import (
    TOOL_SEARCH_DEFAULT_LIMIT,
    TOOL_SEARCH_TOOL_NAME,
    ToolSearchHandler,
    create_tool_search_tool,
)
from pycodex.core.tools.spec_plan import (
    PlannedTools,
    ToolPlanOptions,
    build_model_visible_specs_and_registry,
)
from pycodex.core.tools.registry import ToolExposure
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.protocol import DynamicToolSpec, SearchToolCallParams, ToolName
from pycodex.tools.tool_discovery import ToolSearchSourceInfo

CALENDAR_CREATE_TOOL = "calendar_create_event"
CALENDAR_LIST_TOOL = "calendar_list_events"
SEARCH_CALENDAR_NAMESPACE = "mcp__calendar"
SEARCH_CALENDAR_CREATE_TOOL = "calendar_create_event"
SEARCH_CALENDAR_LIST_TOOL = "calendar_list_events"


class _DeferredHandler:
    def __init__(self, tool_name: ToolName, spec: dict, search_text: str, source: ToolSearchSourceInfo):
        self._tool_name = tool_name
        self._spec = spec
        self._search_text = search_text
        self._source = source

    def tool_name(self):
        return self._tool_name

    def spec(self):
        return self._spec

    def exposure(self):
        return ToolExposure.DEFERRED

    def search_info(self):
        return ToolSearchInfo.from_spec(self._search_text, self._spec, self._source)


def _source(name="Calendar", description="Plan events and manage your calendar."):
    return ToolSearchSourceInfo(name, description)


def _function_tool(name: str, description: str, *, schema_terms=()):
    properties = {term: {"type": "string"} for term in schema_terms}
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        },
        "output_schema": {"type": "object"},
    }


def _namespace(name: str, description: str, tools: list[dict]):
    return {"type": "namespace", "name": name, "description": description, "tools": tools}


def _calendar_create_spec():
    return _namespace(
        SEARCH_CALENDAR_NAMESPACE,
        "Calendar app tools.",
        [_function_tool(SEARCH_CALENDAR_CREATE_TOOL, "Create a calendar event.", schema_terms=("starts_at",))],
    )


def _calendar_list_spec():
    return _namespace(
        SEARCH_CALENDAR_NAMESPACE,
        "Calendar app tools.",
        [_function_tool(SEARCH_CALENDAR_LIST_TOOL, "List calendar events.")],
    )


def _search_info(search_text: str, spec: dict, source=None):
    info = ToolSearchInfo.from_spec(search_text, spec, source or _source())
    assert info is not None
    return info


def _handler(*infos: ToolSearchInfo):
    return ToolSearchHandler(tuple(infos))


def _tool_names(body: dict):
    return [tool.get("name") or tool.get("type") for tool in body.get("tools", ())]


def _namespace_child(tools, namespace, tool_name):
    for tool in tools:
        if tool.get("type") != "namespace" or tool.get("name") != namespace:
            continue
        for child in tool.get("tools", ()):
            if child.get("name") == tool_name:
                return child
    return None


def _visible_specs_for_deferred(*handlers):
    planned = PlannedTools()
    planned.runtimes.extend(handlers)
    specs, _registry = build_model_visible_specs_and_registry(planned, ToolPlanOptions(search_tool_enabled=True))
    return tuple(specs)


def test_search_tool_enabled_by_default_adds_tool_search():
    # Rust: core/tests/suite/search_tool.rs
    # test `search_tool_enabled_by_default_adds_tool_search`.
    tool = create_tool_search_tool((_source(),))

    assert tool["type"] == TOOL_SEARCH_TOOL_NAME
    assert tool["execution"] == "client"
    assert tool["parameters"] == {
        "type": "object",
        "properties": {
            "limit": {
                "type": "number",
                "description": f"Maximum number of tools to return (defaults to {TOOL_SEARCH_DEFAULT_LIMIT}).",
            },
            "query": {"type": "string", "description": "Search query for deferred tools."},
        },
        "required": ["query"],
        "additionalProperties": False,
    }


def test_always_defer_feature_hides_small_app_tool_sets():
    # Rust: core/tests/suite/search_tool.rs
    # test `always_defer_feature_hides_small_app_tool_sets`.
    deferred = _DeferredHandler(
        ToolName.namespaced(SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL),
        _calendar_create_spec(),
        "create calendar event",
        _source(),
    )

    body = {"tools": _visible_specs_for_deferred(deferred)}
    tools = _tool_names(body)

    assert TOOL_SEARCH_TOOL_NAME in tools
    assert not any(str(name).startswith("mcp__") for name in tools if name)


def test_app_search_sources_are_hidden_for_api_key_auth():
    # Rust: core/tests/suite/search_tool.rs
    # test `app_search_sources_are_hidden_for_api_key_auth`.
    tool = create_tool_search_tool(())

    assert "Calendar" not in tool["description"]
    assert "None currently enabled." in tool["description"]


def test_search_tool_adds_discovery_instructions_to_tool_description():
    # Rust: core/tests/suite/search_tool.rs
    # test `search_tool_adds_discovery_instructions_to_tool_description`.
    description = create_tool_search_tool((_source(),))["description"]

    assert "You have access to tools from the following sources" in description
    assert "- Calendar: Plan events and manage your calendar." in description
    assert "remainder of the current session/thread" not in description


def test_search_tool_hides_apps_tools_without_search():
    # Rust: core/tests/suite/search_tool.rs
    # test `search_tool_hides_apps_tools_without_search`.
    deferred = _DeferredHandler(
        ToolName.namespaced(SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL),
        _calendar_create_spec(),
        "create calendar event",
        _source(),
    )

    tools = _tool_names({"tools": _visible_specs_for_deferred(deferred)})

    assert TOOL_SEARCH_TOOL_NAME in tools
    assert CALENDAR_CREATE_TOOL not in tools
    assert CALENDAR_LIST_TOOL not in tools
    assert SEARCH_CALENDAR_NAMESPACE not in tools


def test_explicit_app_mentions_respect_always_defer():
    # Rust: core/tests/suite/search_tool.rs
    # test `explicit_app_mentions_respect_always_defer`.
    deferred = _DeferredHandler(
        ToolName.namespaced(SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL),
        _calendar_create_spec(),
        "explicit calendar create event",
        _source(),
    )

    visible = _visible_specs_for_deferred(deferred)

    assert _tool_names({"tools": visible}) == [TOOL_SEARCH_TOOL_NAME]
    assert _namespace_child(visible, SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL) is None


def test_tool_search_returns_deferred_tools_without_follow_up_tool_injection():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_returns_deferred_tools_without_follow_up_tool_injection`.
    deferred = _DeferredHandler(
        ToolName.namespaced(SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL),
        _calendar_create_spec(),
        "create calendar event lunch starts_at",
        _source(),
    )
    visible = _visible_specs_for_deferred(deferred)
    handler = next(runtime for runtime in PlannedTools([deferred]).runtimes if runtime is deferred)
    search = ToolSearchHandler((handler.search_info(),))

    tools = search.handle(ToolPayload.tool_search(SearchToolCallParams("create calendar event", 1))).tools

    assert _namespace_child(tools, SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL) is not None
    assert _namespace_child(visible, SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL) is None


def test_tool_search_returns_deferred_v1_multi_agent_tools():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_returns_deferred_v1_multi_agent_tools`.
    info = SpawnAgentHandler().search_info()
    assert info is not None

    tools = _handler(info).search("spawn sub-agent delegate work", 8)

    assert _namespace_child(tools, "multi_agent_v1", "spawn_agent") is not None


def test_tool_search_returns_deferred_dynamic_tool_and_routes_follow_up_call():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_returns_deferred_dynamic_tool_and_routes_follow_up_call`.
    dynamic = DynamicToolHandler.new(
        DynamicToolSpec(
            namespace="orbit_ops",
            name="quasar_ping_beacon",
            description="Trigger the saffron metronome workflow.",
            input_schema={"type": "object", "properties": {"chrono_spec": {"type": "string"}}},
            defer_loading=True,
        )
    )
    assert dynamic is not None

    tools = _handler(dynamic.search_info()).search("quasar ping beacon", 8)

    assert _namespace_child(tools, "orbit_ops", "quasar_ping_beacon") is not None


def test_tool_search_indexes_only_enabled_non_app_mcp_tools():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_indexes_only_enabled_non_app_mcp_tools`.
    echo_info = _search_info(
        "Echo back the provided message and include environment data.",
        _namespace("mcp__rmcp", "Use these tools to exercise the rmcp test server.", [_function_tool("echo", "Echo text.")]),
        _source("Dynamic tools", "Tools provided by the current Codex thread."),
    )

    tools = _handler(echo_info).search("Return a single image content block.", 8)

    assert _namespace_child(_handler(echo_info).search("Echo back the provided message", 8), "mcp__rmcp", "echo")
    assert _namespace_child(tools, "mcp__rmcp", "image") is None


def test_tool_search_surfaced_mcp_tool_errors_are_returned_to_model():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_surfaced_mcp_tool_errors_are_returned_to_model`.
    dynamic = DynamicToolHandler.new(
        DynamicToolSpec(
            namespace="mcp__rmcp",
            name="echo",
            description="Echo back the provided message and include environment data.",
            input_schema={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
            defer_loading=True,
        )
    )
    assert dynamic is not None
    assert _namespace_child(_handler(dynamic.search_info()).search("rmcp echo", 8), "mcp__rmcp", "echo") is not None

    with pytest.raises(FunctionCallError) as exc:
        dynamic.handle(ToolPayload(type="function", arguments="{}"))

    assert "cancelled before receiving a response" in str(exc.value)


def test_tool_search_uses_non_app_mcp_server_instructions_as_namespace_description():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_uses_non_app_mcp_server_instructions_as_namespace_description`.
    info = _search_info(
        "Echo back the provided message and include environment data.",
        _namespace("mcp__rmcp", "Use these tools to exercise the rmcp test server.", [_function_tool("echo", "Echo text.")]),
        _source("Dynamic tools", "Tools provided by the current Codex thread."),
    )

    namespace = _handler(info).search("echo provided message", 8)[0]

    assert namespace["name"] == "mcp__rmcp"
    assert namespace["description"] == "Use these tools to exercise the rmcp test server."


def test_tool_search_matches_mcp_tools_by_distinct_name_description_and_schema_terms():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_matches_mcp_tools_by_distinct_name_description_and_schema_terms`.
    handler = _handler(
        _search_info("calendar_timezone_option_99", _namespace(SEARCH_CALENDAR_NAMESPACE, "Calendar app tools.", [_function_tool("_timezone_option_99", "Time zone option.")])),
        _search_info("uploaded document", _namespace(SEARCH_CALENDAR_NAMESPACE, "Calendar app tools.", [_function_tool("_extract_text", "Extract uploaded document text.")])),
        _search_info("starts_at", _calendar_create_spec()),
    )

    assert _namespace_child(handler.search("calendar_timezone_option_99", 8), SEARCH_CALENDAR_NAMESPACE, "_timezone_option_99")
    assert _namespace_child(handler.search("uploaded document", 8), SEARCH_CALENDAR_NAMESPACE, "_extract_text")
    assert _namespace_child(handler.search("starts_at", 8), SEARCH_CALENDAR_NAMESPACE, SEARCH_CALENDAR_CREATE_TOOL)


def test_tool_search_matches_dynamic_tools_by_name_description_namespace_and_schema_terms():
    # Rust: core/tests/suite/search_tool.rs
    # test `tool_search_matches_dynamic_tools_by_name_description_namespace_and_schema_terms`.
    dynamic = DynamicToolHandler.new(
        DynamicToolSpec(
            namespace="orbit_ops",
            name="quasar_ping_beacon",
            description="Trigger the saffron metronome workflow for reminder follow-ups.",
            input_schema={
                "type": "object",
                "properties": {
                    "chrono_spec": {"type": "string"},
                    "targetThreadId": {"type": "string"},
                },
                "required": ["chrono_spec"],
                "additionalProperties": False,
            },
            defer_loading=True,
        )
    )
    assert dynamic is not None
    handler = _handler(dynamic.search_info())

    for query in [
        "quasar_ping_beacon",
        "quasar ping beacon",
        "saffron metronome",
        "orbit_ops",
        "chrono_spec",
    ]:
        assert _namespace_child(handler.search(query, 8), "orbit_ops", "quasar_ping_beacon")
