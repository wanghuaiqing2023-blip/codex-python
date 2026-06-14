"""Parity tests for Rust ``codex-tui::resume_picker::transcript``.

Rust source: ``codex/codex-rs/tui/src/resume_picker/transcript.rs``.
"""

import asyncio

from pycodex.tui.resume_picker.transcript import (
    RawReasoningVisibility,
    fallback_transcript_cell,
    load_session_transcript,
    thread_to_transcript_cells,
)


def _thread(items):
    return {"cwd": "/repo", "turns": [{"items": items}]}


def test_thread_to_transcript_cells_maps_core_item_types() -> None:
    cells = thread_to_transcript_cells(
        _thread([
            {"kind": "UserMessage", "id": "u1", "content": ["hello", {"text": "world"}]},
            {"kind": "AgentMessage", "text": "visible\n::git-stage{cwd=\"/repo\"}"},
            {"kind": "Plan", "text": "  ship it  "},
            {"kind": "Reasoning", "summary": ["short"], "content": ["raw one", "raw two"]},
        ]),
        RawReasoningVisibility.Hidden,
    )

    assert [cell.kind for cell in cells] == ["user", "agent_markdown", "proposed_plan", "reasoning"]
    assert cells[0].text == "hello\nworld"
    assert cells[0].metadata["id"] == "u1"
    assert cells[1].text == "visible"
    assert len(cells[1].metadata["git_actions"]) == 1
    assert cells[2].text == "  ship it  "
    assert cells[3].text == "short"
    assert cells[3].metadata["source"] == "summary"


def test_raw_reasoning_visibility_uses_content_when_available() -> None:
    cells = thread_to_transcript_cells(
        _thread([{"kind": "Reasoning", "summary": ["summary"], "content": ["raw one", "raw two"]}]),
        RawReasoningVisibility.Visible,
    )

    assert cells[0].kind == "reasoning"
    assert cells[0].text == "raw one\n\nraw two"
    assert cells[0].metadata["source"] == "content"


def test_empty_or_whitespace_items_fall_back_to_no_content_cell() -> None:
    cells = thread_to_transcript_cells(
        _thread([
            {"kind": "AgentMessage", "text": "   "},
            {"kind": "Plan", "text": "\n"},
            {"kind": "Reasoning", "summary": [], "content": []},
        ]),
        RawReasoningVisibility.Visible,
    )

    assert len(cells) == 1
    assert cells[0].kind == "plain"
    assert cells[0].text == "No transcript content available"


def test_fallback_transcript_cell_formats_tool_and_command_items() -> None:
    command = fallback_transcript_cell({
        "kind": "CommandExecution",
        "command": "cargo test",
        "status": "Failed",
        "exit_code": 101,
        "aggregated_output": "line 1\nline 2\n",
    })
    assert command is not None
    assert command.lines == ("$ cargo test", "status: Failed ， exit 101", "  line 1", "  line 2")

    assert fallback_transcript_cell({"kind": "FileChange", "status": "Done", "changes": [1, 2]}).text == "file changes: Done ， 2 changes"
    assert fallback_transcript_cell({"kind": "McpToolCall", "server": "srv", "tool": "lookup", "status": "Ok"}).text == "mcp tool: srv/lookup ， Ok"
    assert fallback_transcript_cell({"kind": "DynamicToolCall", "namespace": "ns", "tool": "run", "status": "Ok"}).text == "tool: ns/run ， Ok"
    assert fallback_transcript_cell({"kind": "DynamicToolCall", "tool": "run", "status": "Ok"}).text == "tool: run ， Ok"


def test_fallback_transcript_cell_formats_misc_items_and_skips_owned_core_types() -> None:
    assert fallback_transcript_cell({"kind": "HookPrompt", "fragments": [{"text": "  review me  "}]}).text == "hook prompt: review me"
    assert fallback_transcript_cell({"kind": "WebSearch", "query": "codex"}).text == "web search: codex"
    assert fallback_transcript_cell({"kind": "ImageView", "path": "/tmp/a.png"}).text == "image: /tmp/a.png"
    assert fallback_transcript_cell({"kind": "ImageGeneration", "status": "done", "saved_path": "/tmp/out.png"}).text == "image generation: done ， /tmp/out.png"
    assert fallback_transcript_cell({"kind": "EnteredReviewMode", "review": "abc"}).text == "review started: abc"
    assert fallback_transcript_cell({"kind": "ExitedReviewMode", "review": "abc"}).text == "review finished: abc"
    assert fallback_transcript_cell({"kind": "ContextCompaction"}).text == "context compacted"
    assert fallback_transcript_cell({"kind": "AgentMessage", "text": "owned elsewhere"}) is None


def test_load_session_transcript_reads_include_turns_true() -> None:
    class AppServer:
        def __init__(self) -> None:
            self.calls = []

        async def thread_read(self, thread_id, include_turns):
            self.calls.append((thread_id, include_turns))
            return _thread([{"kind": "Plan", "text": "plan"}])

    app = AppServer()
    cells = asyncio.run(load_session_transcript(app, "thread-1", RawReasoningVisibility.Hidden))

    assert app.calls == [("thread-1", True)]
    assert cells[0].kind == "proposed_plan"
