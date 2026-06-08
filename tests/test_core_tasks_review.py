from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.review_format import format_review_findings_block, render_review_output_text
from pycodex.core.state import TaskKind
from pycodex.core.tasks.review import (
    REVIEW_INTERRUPTED_ASSISTANT_MESSAGE,
    ReviewTask,
    collect_review_user_input,
    normalize_review_template_line_endings,
    parse_review_output_event,
    render_review_exit_interrupted,
    render_review_exit_success,
    review_exit_messages,
)
from pycodex.protocol import ReviewCodeLocation, ReviewFinding, ReviewLineRange, ReviewOutputEvent


def finding(title: str = "Finding A") -> ReviewFinding:
    return ReviewFinding(
        title=title,
        body="Body line.",
        confidence_score=0.9,
        priority=1,
        code_location=ReviewCodeLocation(Path("C:/repo/app.py"), ReviewLineRange(3, 4)),
    )


def test_review_task_identity_matches_rust_session_task_contract() -> None:
    # Rust source: codex-rs/core/src/tasks/review.rs
    # Contract: ReviewTask::new, kind, and span_name.
    task = ReviewTask.new()

    assert task.kind() == TaskKind.REVIEW
    assert task.span_name() == "session_task.review"


def test_parse_review_output_event_accepts_json_substring_and_fallback() -> None:
    # Rust source: tasks/review.rs::parse_review_output_event.
    output = ReviewOutputEvent(
        findings=(finding(),),
        overall_correctness="patch is incorrect",
        overall_explanation="Needs changes.",
        overall_confidence_score=0.8,
    )

    assert parse_review_output_event(json.dumps(output.to_mapping())) == output
    assert parse_review_output_event(f"prefix {json.dumps(output.to_mapping())} suffix") == output

    fallback = parse_review_output_event("plain explanation")
    assert fallback == ReviewOutputEvent(overall_explanation="plain explanation")


def test_render_review_exit_success_replaces_results_placeholder() -> None:
    # Rust inline test: render_review_exit_success_replaces_results_placeholder.
    assert render_review_exit_success("Finding A\nFinding B") == (
        "<user_action>\n"
        "  <context>User initiated a review task. Here's the full review output from reviewer model. User may select one or more comments to resolve.</context>\n"
        "  <action>review</action>\n"
        "  <results>\n"
        "  Finding A\n"
        "Finding B\n"
        "  </results>\n"
        "  </user_action>\n"
    )


def test_normalize_review_template_line_endings_rewrites_crlf() -> None:
    # Rust inline test: normalize_review_template_line_endings_rewrites_crlf.
    assert normalize_review_template_line_endings("<user_action>\r\n  <results>\r\n  None.\r\n") == (
        "<user_action>\n  <results>\n  None.\n"
    )


def test_review_exit_messages_match_success_and_interrupted_branches() -> None:
    # Rust source: tasks/review.rs::exit_review_mode.
    output = ReviewOutputEvent(
        findings=(finding("Bug"),),
        overall_explanation="Summary.",
        overall_correctness="patch is incorrect",
        overall_confidence_score=0.75,
    )

    messages = review_exit_messages(output)

    assert messages.user_message == render_review_exit_success(
        "Summary.\n" + format_review_findings_block(output.findings)
    )
    assert messages.assistant_message == render_review_output_text(output)

    interrupted = review_exit_messages(None)
    assert interrupted.user_message == render_review_exit_interrupted()
    assert interrupted.assistant_message == REVIEW_INTERRUPTED_ASSISTANT_MESSAGE


def test_collect_review_user_input_ignores_response_item_turn_inputs() -> None:
    # Rust source: ReviewTask::run collects TurnInput::UserInput and ignores
    # TurnInput::ResponseItem before starting the review conversation.
    assert collect_review_user_input(
        [
            SimpleNamespace(items=["first", "second"]),
            SimpleNamespace(item="response item"),
            SimpleNamespace(content=("third",)),
        ]
    ) == ["first", "second", "third"]
