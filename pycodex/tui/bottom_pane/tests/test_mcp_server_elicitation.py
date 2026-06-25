from pycodex.tui.bottom_pane.mcp_server_elicitation import (
    APPROVAL_ACCEPT_ALWAYS_VALUE,
    APPROVAL_ACCEPT_SESSION_VALUE,
    APPROVAL_CANCEL_VALUE,
    APPROVAL_FIELD_ID,
    APPROVAL_KIND_MCP_TOOL_CALL,
    APPROVAL_KIND_TOOL_SUGGESTION,
    APPROVAL_META_KIND_KEY,
    APPROVAL_PERSIST_KEY,
    APPROVAL_TOOL_PARAMS_DISPLAY_KEY,
    APPROVAL_TOOL_PARAMS_KEY,
    TOOL_ID_KEY,
    TOOL_NAME_KEY,
    TOOL_SUGGEST_INSTALL_URL_KEY,
    TOOL_SUGGEST_REASON_KEY,
    TOOL_SUGGEST_SUGGEST_TYPE_KEY,
    TOOL_TYPE_KEY,
    McpServerElicitationFormRequest,
    McpServerElicitationOverlay,
    McpServerElicitationResponseMode,
    ToolSuggestionToolType,
    ToolSuggestionType,
    empty_object_schema,
    format_tool_approval_display_message,
    format_tool_approval_display_param_value,
    parse_tool_approval_display_params,
)


def _request(schema, meta=None, request_id="req-1"):
    return McpServerElicitationFormRequest.from_parts(
        thread_id="thread-1",
        server_name="server",
        request_id=request_id,
        message="Allow this?",
        schema=schema,
        meta=meta or {},
    )


def test_parses_boolean_form_request():
    req = _request({"type": "object", "required": ["confirmed"], "properties": {"confirmed": {"type": "boolean", "title": "Confirm", "description": "Proceed?", "default": True}}})
    assert req.response_mode is McpServerElicitationResponseMode.FORM_CONTENT
    assert req.fields[0].id == "confirmed"
    assert req.fields[0].input.options[0].value is True
    assert req.fields[0].input.default_idx == 0


def test_unsupported_numeric_form_falls_back_to_none():
    assert _request({"type": "object", "properties": {"count": {"type": "number"}}}) is None


def test_empty_object_schema_uses_approval_actions():
    req = _request(empty_object_schema())
    assert req.response_mode is McpServerElicitationResponseMode.APPROVAL_ACTION
    assert req.fields[0].id == APPROVAL_FIELD_ID
    assert [option.value for option in req.fields[0].input.options] == ["accept", "decline", "cancel"]


def test_empty_tool_approval_schema_uses_persist_actions_and_cancel():
    req = _request(empty_object_schema(), {APPROVAL_META_KIND_KEY: APPROVAL_KIND_MCP_TOOL_CALL, APPROVAL_PERSIST_KEY: ["session", "always"]})
    assert [option.value for option in req.fields[0].input.options] == ["accept", APPROVAL_ACCEPT_SESSION_VALUE, APPROVAL_ACCEPT_ALWAYS_VALUE, APPROVAL_CANCEL_VALUE]


def test_tool_suggestion_meta_is_parsed_into_request_payload():
    req = _request(empty_object_schema(), {APPROVAL_META_KIND_KEY: APPROVAL_KIND_TOOL_SUGGESTION, TOOL_TYPE_KEY: "connector", TOOL_SUGGEST_SUGGEST_TYPE_KEY: "install", TOOL_SUGGEST_REASON_KEY: "Need it", TOOL_ID_KEY: "conn-1", TOOL_NAME_KEY: "Connector", TOOL_SUGGEST_INSTALL_URL_KEY: "https://example.test/install"})
    assert req.tool_suggestion.tool_type is ToolSuggestionToolType.CONNECTOR
    assert req.tool_suggestion.suggest_type is ToolSuggestionType.INSTALL
    assert req.tool_suggestion.install_url == "https://example.test/install"


def test_plugin_tool_suggestion_meta_without_install_url_is_parsed():
    req = _request(empty_object_schema(), {APPROVAL_META_KIND_KEY: APPROVAL_KIND_TOOL_SUGGESTION, TOOL_TYPE_KEY: "plugin", TOOL_SUGGEST_SUGGEST_TYPE_KEY: "enable", TOOL_SUGGEST_REASON_KEY: "Need plugin", TOOL_ID_KEY: "plug-1", TOOL_NAME_KEY: "Plugin"})
    assert req.tool_suggestion.tool_type is ToolSuggestionToolType.PLUGIN
    assert req.tool_suggestion.suggest_type is ToolSuggestionType.ENABLE
    assert req.tool_suggestion.install_url is None


def test_tool_approval_display_params_prefer_explicit_display_order():
    params = parse_tool_approval_display_params({APPROVAL_TOOL_PARAMS_DISPLAY_KEY: [{"name": "b", "display_name": "Bee", "value": "two"}, {"name": "a", "value": "one"}], APPROVAL_TOOL_PARAMS_KEY: {"z": 1}})
    assert [(param.name, param.display_name, param.value) for param in params] == [("b", "Bee", "two"), ("a", "a", "one")]


def test_tool_approval_display_params_fallback_sort_and_format():
    params = parse_tool_approval_display_params({APPROVAL_TOOL_PARAMS_KEY: {"z": 1, "a": "hello\nworld"}})
    message = format_tool_approval_display_message(" Run tool ", params)
    assert [param.name for param in params] == ["a", "z"]
    assert "a: hello world" in message
    assert message.endswith("\n")
    assert format_tool_approval_display_param_value("x" * 70).endswith("...")


def test_submit_sends_accept_with_typed_content():
    req = _request({"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}})
    emitted = []
    overlay = McpServerElicitationOverlay.new(req, tx_event=emitted)
    overlay.set_text_answer("hello")
    event = overlay.submit_answers()
    assert event["decision"] == "Accept"
    assert event["content"] == {"answer": "hello"}
    assert emitted == [event]
    assert overlay.is_complete()


def test_session_and_always_choices_set_persist_meta():
    req = _request(empty_object_schema(), {APPROVAL_PERSIST_KEY: ["session", "always"]})
    overlay = McpServerElicitationOverlay.new(req)
    overlay.select_option(1)
    session_event = overlay.submit_answers()
    assert session_event["meta"] == {APPROVAL_PERSIST_KEY: "session"}
    overlay = McpServerElicitationOverlay.new(req)
    overlay.select_option(2)
    always_event = overlay.submit_answers()
    assert always_event["meta"] == {APPROVAL_PERSIST_KEY: "always"}


def test_ctrl_c_cancels_elicitation():
    req = _request(empty_object_schema())
    overlay = McpServerElicitationOverlay.new(req)
    assert overlay.on_ctrl_c() == "Handled"
    assert overlay.emitted_events[-1]["decision"] == "Cancel"
    assert overlay.is_complete()


def test_queues_requests_fifo():
    first = _request(empty_object_schema(), request_id="first")
    second = _request(empty_object_schema(), request_id="second")
    overlay = McpServerElicitationOverlay.new(first)
    overlay.try_consume_mcp_server_elicitation_request(second)
    overlay.submit_answers()
    assert not overlay.is_complete()
    assert overlay.request.request_id == "second"
    overlay.submit_answers()
    assert overlay.is_complete()


def test_resolved_request_dismisses_overlay_without_emitting_events():
    first = _request(empty_object_schema(), request_id="first")
    second = _request(empty_object_schema(), request_id="second")
    overlay = McpServerElicitationOverlay.new(first)
    overlay.try_consume_mcp_server_elicitation_request(second)
    assert overlay.dismiss_app_server_request("server", "first") is True
    assert overlay.request.request_id == "second"
    assert overlay.emitted_events == []
