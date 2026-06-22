from __future__ import annotations

from pathlib import Path

from pycodex.backend_client import CodeTaskDetailsResponse


FIXTURES = Path(__file__).resolve().parents[1] / "codex" / "codex-rs" / "backend-client" / "tests" / "fixtures"


def fixture(name: str) -> CodeTaskDetailsResponse:
    return CodeTaskDetailsResponse.from_json((FIXTURES / name).read_text(encoding="utf-8"))


def test_unified_diff_prefers_current_diff_task_turn() -> None:
    # Rust: codex-backend-client src/types.rs tests::unified_diff_prefers_current_diff_task_turn.
    details = fixture("task_details_with_diff.json")
    diff = details.unified_diff()
    assert diff is not None
    assert "diff --git" in diff


def test_unified_diff_falls_back_to_pr_output_diff() -> None:
    # Rust: codex-backend-client src/types.rs tests::unified_diff_falls_back_to_pr_output_diff.
    details = fixture("task_details_with_error.json")
    diff = details.unified_diff()
    assert diff is not None
    assert "lib.rs" in diff


def test_assistant_text_messages_extracts_text_content() -> None:
    # Rust: codex-backend-client src/types.rs tests::assistant_text_messages_extracts_text_content.
    details = fixture("task_details_with_diff.json")
    assert details.assistant_text_messages() == ["Assistant response"]


def test_user_text_prompt_joins_parts_with_spacing() -> None:
    # Rust: codex-backend-client src/types.rs tests::user_text_prompt_joins_parts_with_spacing.
    details = fixture("task_details_with_diff.json")
    assert details.user_text_prompt() == "First line\n\nSecond line"


def test_assistant_error_message_combines_code_and_message() -> None:
    # Rust: codex-backend-client src/types.rs tests::assistant_error_message_combines_code_and_message.
    details = fixture("task_details_with_error.json")
    assert details.assistant_error_message() == "APPLY_FAILED: Patch could not be applied"


def test_task_details_helpers_match_rust_edge_contracts() -> None:
    # Rust: codex-backend-client src/types.rs ContentFragment::text, WorklogMessage::is_assistant.
    details = CodeTaskDetailsResponse.from_mapping(
        {
            "current_user_turn": {
                "input_items": [
                    {"type": "message", "role": "system", "content": ["ignored"]},
                    {"type": "message", "role": "USER", "content": ["hello", "  "]},
                ]
            },
            "current_assistant_turn": {
                "output_items": [
                    {"type": "message", "content": [{"content_type": "image", "text": "ignored"}]},
                    {"type": "message", "content": [{"content_type": "TEXT", "text": "structured"}]},
                    {"type": "message", "content": ["raw"]},
                ],
                "worklog": {
                    "messages": [
                        {"author": {"role": "user"}, "content": {"parts": ["ignored"]}},
                        {"author": {"role": "assistant"}, "content": {"parts": [{"content_type": "text", "text": "worklog"}]}},
                    ]
                },
                "error": {"message": "message only"},
            },
        }
    )
    assert details.user_text_prompt() == "hello"
    assert details.assistant_text_messages() == ["structured", "raw", "worklog"]
    assert details.assistant_error_message() == "message only"
