from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.context import ToolPayload
from pycodex.ext.memories.local import LocalMemoriesBackend
from pycodex.ext.memories.tools import memory_tools
from pycodex.extension_api import ToolCall
from pycodex.protocol import ToolName


def _call(name: str, arguments: str) -> ToolCall:
    return ToolCall(
        tool_name=ToolName.namespaced("memories", name),
        call_id=f"call-{name}",
        payload=ToolPayload.function(arguments),
    )


def test_memory_tools_match_rust_registration_and_specs(tmp_path: Path) -> None:
    tools = memory_tools(LocalMemoriesBackend.from_codex_home(tmp_path))

    assert [tool.tool_name().name for tool in tools] == [
        "add_ad_hoc_note",
        "list",
        "read",
        "search",
    ]
    for tool in tools:
        spec = tool.spec()
        assert spec.type == "namespace"
        assert spec.payload["name"] == "memories"
        assert spec.payload["tools"][0]["name"] == tool.tool_name().name


def test_memory_tools_execute_real_local_backend_chain(tmp_path: Path) -> None:
    tools = {
        tool.tool_name().name: tool
        for tool in memory_tools(LocalMemoriesBackend.from_codex_home(tmp_path))
    }
    add_output = asyncio.run(
        tools["add_ad_hoc_note"].handle(
            _call(
                "add_ad_hoc_note",
                '{"filename":"2026-07-27T12-30-45-project.md","note":"remember this"}',
            )
        )
    )
    assert add_output.value == {}

    list_output = asyncio.run(tools["list"].handle(_call("list", "{}")))
    assert list_output.value["entries"][0]["path"] == "extensions"

    read_output = asyncio.run(
        tools["read"].handle(
            _call("read", '{"path":"extensions/ad_hoc/notes/2026-07-27T12-30-45-project.md"}')
        )
    )
    assert read_output.value["content"] == "remember this"

    search_output = asyncio.run(
        tools["search"].handle(_call("search", '{"queries":["remember"]}'))
    )
    assert search_output.value["matches"][0]["matched_queries"] == ["remember"]


def test_memory_tool_argument_errors_respond_to_model(tmp_path: Path) -> None:
    tool = memory_tools(LocalMemoriesBackend.from_codex_home(tmp_path))[1]

    with pytest.raises(FunctionCallError) as error:
        asyncio.run(tool.handle(_call("list", '{"unexpected":true}')))

    assert error.value.is_model_response
