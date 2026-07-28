"""Rust-derived tests for ``codex-rs/ext/web-search``."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pycodex.codex_api import (
    SearchCommands,
    SearchResponse,
    SearchResponseLength,
    SearchSettings,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.router import ConversationHistory, ToolCall
from pycodex.ext.web_search.extension import (
    WebSearchExtensionConfig,
    install,
)
from pycodex.ext.web_search.history import recent_input
from pycodex.ext.web_search.output import EncryptedSearchOutput
from pycodex.ext.web_search.schema import commands_schema
from pycodex.ext.web_search.tool import WebSearchTool, parse_commands
from pycodex.extension_api import ExtensionData, ExtensionRegistryBuilder, ToolName
from pycodex.model_provider_info import ModelProviderInfo
from pycodex.protocol import (
    ContentItem,
    FunctionCallOutputPayload,
    ResponseInputItem,
    ResponseItem,
    TruncationPolicyConfig,
)


def _message(role: str, text: str) -> ResponseItem:
    content = (
        ContentItem.output_text(text)
        if role == "assistant"
        else ContentItem.input_text(text)
    )
    return ResponseItem.message(role, (content,))


def test_history_keeps_current_user_and_previous_visible_turn() -> None:
    items = (
        _message("system", "system"),
        _message("user", "old user"),
        _message("assistant", "old assistant"),
        _message("user", "previous user"),
        ResponseItem.function_call("tool", "call-1", "{}"),
        _message("assistant", "previous assistant"),
        _message("developer", "developer"),
        _message("user", "current user"),
        _message("assistant", "current commentary"),
    )

    result = recent_input(items)

    assert result is not None
    assert result.value == [
        _message("user", "previous user"),
        _message("assistant", "previous assistant"),
        _message("user", "current user"),
    ]


def test_history_keeps_only_text_from_recent_user_messages() -> None:
    previous_user = ResponseItem.message(
        "user",
        (
            ContentItem.input_text("previous user"),
            ContentItem.input_image("data:image/png;base64,image"),
        ),
    )

    result = recent_input(
        (
            previous_user,
            _message("assistant", "previous assistant"),
            _message("user", "current user"),
        )
    )

    assert result is not None
    assert result.value == [
        _message("user", "previous user"),
        _message("assistant", "previous assistant"),
        _message("user", "current user"),
    ]


def test_history_ignores_contextual_user_messages() -> None:
    result = recent_input(
        (
            _message("user", "previous user"),
            _message("assistant", "previous assistant"),
            _message(
                "user",
                "<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>",
            ),
            _message("user", "current user"),
        )
    )

    assert result is not None
    assert result.value == [
        _message("user", "previous user"),
        _message("assistant", "previous assistant"),
        _message("user", "current user"),
    ]


def test_encrypted_output_emits_function_call_output() -> None:
    output = EncryptedSearchOutput.new("encrypted-search-output")

    assert output.to_response_item(
        "call-1",
        ToolPayload.function("{}"),
    ) == ResponseInputItem.function_call_output(
        "call-1",
        FunctionCallOutputPayload.from_content_items(
            (
                {
                    "type": "encrypted_content",
                    "encrypted_content": "encrypted-search-output",
                },
            )
        ),
    )


def test_installed_extension_contributes_web_run_when_enabled(monkeypatch) -> None:
    provider = object()
    monkeypatch.setattr(
        "pycodex.ext.web_search.extension.create_model_provider",
        lambda _provider, _auth_manager: provider,
    )
    builder = ExtensionRegistryBuilder.new()
    install(builder, object())
    registry = builder.build()
    session_store = ExtensionData("session")
    thread_store = ExtensionData("11111111-1111-4111-8111-111111111111")
    thread_store.insert(
        WebSearchExtensionConfig(
            enabled=True,
            provider=ModelProviderInfo.create_openai_provider(None),
            settings=SearchSettings(),
        )
    )

    tools = [
        tool
        for contributor in registry.tool_contributors()
        for tool in contributor.tools(session_store, thread_store)
    ]

    assert [tool.tool_name() for tool in tools] == [
        ToolName.namespaced("web", "run")
    ]
    assert tools[0].provider is provider
    assert tools[0].session_id == "session"


def test_parse_commands_matches_search_commands_wire_shape() -> None:
    call = ToolCall(
        tool_name=ToolName.namespaced("web", "run"),
        call_id="call-1",
        payload=ToolPayload.function(
            json.dumps(
                {
                    "search_query": [{"q": "Codex", "domains": ["openai.com"]}],
                    "response_length": "short",
                }
            )
        ),
    )

    commands = parse_commands(call)

    assert isinstance(commands, SearchCommands)
    assert commands.search_query is not None
    assert commands.search_query[0].q == "Codex"
    assert commands.search_query[0].domains == ["openai.com"]
    assert commands.response_length is SearchResponseLength.SHORT


def test_commands_schema_preserves_operation_fields_and_required_items() -> None:
    schema = commands_schema()
    properties = schema["properties"]

    assert properties["search_query"]["items"]["required"] == ["q"]
    assert set(properties["search_query"]["items"]["properties"]) == {
        "q",
        "recency",
        "domains",
    }
    assert properties["click"]["items"]["required"] == ["ref_id", "id"]
    assert properties["finance"]["items"]["properties"]["type"]["enum"] == [
        "equity",
        "fund",
        "crypto",
        "index",
    ]
    assert properties["sports"]["items"]["required"] == ["fn", "league"]
    assert properties["sports"]["items"]["properties"]["league"]["enum"] == [
        "nba",
        "wnba",
        "nfl",
        "nhl",
        "mlb",
        "epl",
        "ncaamb",
        "ncaawb",
        "ipl",
    ]
    assert properties["response_length"]["enum"] == ["short", "medium", "long"]


@pytest.mark.asyncio
async def test_tool_handle_calls_search_endpoint_with_history(monkeypatch) -> None:
    captured = {}

    class FakeProvider:
        async def api_provider(self):
            return "provider"

        async def api_auth(self):
            return "auth"

    class FakeSearchClient:
        def __init__(self, transport, provider, auth):
            captured["transport"] = transport
            captured["provider"] = provider
            captured["auth"] = auth

        async def search(self, request, headers):
            captured["request"] = request
            captured["headers"] = headers
            return SearchResponse(encrypted_output="encrypted")

    monkeypatch.setattr(
        "pycodex.ext.web_search.tool.SearchClient",
        FakeSearchClient,
    )
    tool = WebSearchTool(
        session_id="session-1",
        provider=FakeProvider(),
        settings=SearchSettings(),
    )
    call = ToolCall(
        tool_name=ToolName.namespaced("web", "run"),
        call_id="call-1",
        payload=ToolPayload.function('{"search_query":[{"q":"Codex"}]}'),
        truncation_policy=TruncationPolicyConfig.tokens(321),
        conversation_history=ConversationHistory(
            (
                _message("user", "previous"),
                _message("assistant", "answer"),
                _message("user", "current"),
            )
        ),
    )

    output = await tool.handle(call)

    assert output == EncryptedSearchOutput.new("encrypted")
    assert captured["provider"] == "provider"
    assert captured["auth"] == "auth"
    assert captured["headers"] == {}
    request = captured["request"]
    assert request.id == "session-1"
    assert request.max_output_tokens == 321
    assert request.commands.search_query[0].q == "Codex"
    assert request.input.value == list(call.conversation_history.items)


def test_tool_spec_is_direct_model_only_web_namespace() -> None:
    tool = WebSearchTool("session", SimpleNamespace(), SearchSettings())

    spec = tool.spec()

    assert tool.tool_name() == ToolName.namespaced("web", "run")
    assert tool.exposure().value == "direct_model_only"
    assert spec.type == "namespace"
    assert spec.payload["name"] == "web"
    assert [entry["name"] for entry in spec.payload["tools"]] == ["run"]
