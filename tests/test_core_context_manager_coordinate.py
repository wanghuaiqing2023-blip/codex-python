from __future__ import annotations

from pycodex.core import context_manager
from pycodex.core.context_manager import history
from pycodex.protocol import ContentItem, FunctionCallOutputPayload, ResponseItem


def test_context_manager_root_reexports_rust_mod_history_items() -> None:
    # Rust source: codex/codex-rs/core/src/context_manager/mod.rs
    # Rust crate/module: codex-core::context_manager
    # Contract: mod.rs re-exports the selected history.rs public crate items.
    assert context_manager.ContextManager is history.ContextManager
    assert context_manager.TotalTokenUsageBreakdown is history.TotalTokenUsageBreakdown
    assert (
        context_manager.estimate_response_item_model_visible_bytes
        is history.estimate_response_item_model_visible_bytes
    )
    assert context_manager.is_codex_generated_item is history.is_codex_generated_item
    assert context_manager.is_user_turn_boundary is history.is_user_turn_boundary
    assert context_manager.truncate_function_output_payload is history.truncate_function_output_payload


def test_is_codex_generated_item_matches_rust_output_and_developer_boundary() -> None:
    # Rust source: codex/codex-rs/core/src/context_manager/history.rs::is_codex_generated_item
    # Contract: Codex-generated items are tool outputs plus developer messages.
    assert context_manager.is_codex_generated_item(
        ResponseItem(
            type="function_call_output",
            call_id="call-1",
            output=FunctionCallOutputPayload.from_text("ok"),
        )
    )
    assert context_manager.is_codex_generated_item(
        ResponseItem(type="tool_search_output", call_id="search-1", execution="client", tools=())
    )
    assert context_manager.is_codex_generated_item(
        ResponseItem(
            type="custom_tool_call_output",
            call_id="custom-1",
            output=FunctionCallOutputPayload.from_text("ok"),
        )
    )
    assert context_manager.is_codex_generated_item(
        ResponseItem.message("developer", (ContentItem.input_text("dev"),))
    )
    assert not context_manager.is_codex_generated_item(
        ResponseItem.message("assistant", (ContentItem.output_text("assistant"),))
    )
    assert not context_manager.is_codex_generated_item(ResponseItem.function_call("tool", "{}", "call-2"))
