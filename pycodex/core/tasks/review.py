"""Review task helpers aligned with ``codex-core::tasks::review``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pycodex.core.client_common import REVIEW_EXIT_INTERRUPTED_TMPL, REVIEW_EXIT_SUCCESS_TMPL
from pycodex.core.review_format import format_review_findings_block, render_review_output_text
from pycodex.core.state import TaskKind
from pycodex.protocol import ReviewOutputEvent


REVIEW_ROLLOUT_USER_MESSAGE_ID = "review_rollout_user"
REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID = "review_rollout_assistant"
REVIEW_INTERRUPTED_ASSISTANT_MESSAGE = "Review was interrupted. Please re-run /review and wait for it to complete."


@dataclass(frozen=True)
class ReviewExitMessages:
    user_message: str
    assistant_message: str


@dataclass(frozen=True)
class ReviewTask:
    """Python coordinate for Rust ``ReviewTask`` helper behavior.

    Full sub-Codex review execution remains a runtime boundary; this module
    carries the task identity and review-output/exit-message contracts owned by
    ``tasks::review``.
    """

    @classmethod
    def new(cls) -> "ReviewTask":
        return cls()

    def kind(self) -> TaskKind:
        return TaskKind.REVIEW

    def span_name(self) -> str:
        return "session_task.review"


def parse_review_output_event(text: str) -> ReviewOutputEvent:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    try:
        return ReviewOutputEvent.from_mapping(json.loads(text))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        try:
            return ReviewOutputEvent.from_mapping(json.loads(text[start : end + 1]))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    return ReviewOutputEvent(overall_explanation=text)


def normalize_review_template_line_endings(template: str) -> str:
    if not isinstance(template, str):
        raise TypeError("template must be a string")
    if "\r" not in template:
        return template
    return template.replace("\r\n", "\n").replace("\r", "\n")


def render_review_exit_success(results: str) -> str:
    if not isinstance(results, str):
        raise TypeError("results must be a string")
    return normalize_review_template_line_endings(REVIEW_EXIT_SUCCESS_TMPL).replace("{{results}}", results)


def render_review_exit_interrupted() -> str:
    return normalize_review_template_line_endings(REVIEW_EXIT_INTERRUPTED_TMPL)


def review_exit_messages(review_output: ReviewOutputEvent | None) -> ReviewExitMessages:
    if review_output is None:
        return ReviewExitMessages(
            user_message=render_review_exit_interrupted(),
            assistant_message=REVIEW_INTERRUPTED_ASSISTANT_MESSAGE,
        )
    findings = _review_findings_text(review_output)
    return ReviewExitMessages(
        user_message=render_review_exit_success(findings),
        assistant_message=render_review_output_text(review_output),
    )


def _review_findings_text(review_output: ReviewOutputEvent) -> str:
    text = review_output.overall_explanation.strip()
    findings = text
    if review_output.findings:
        findings += f"\n{format_review_findings_block(review_output.findings)}"
    return findings


def collect_review_user_input(turn_input: list[Any] | tuple[Any, ...]) -> list[Any]:
    collected: list[Any] = []
    for item in turn_input:
        content = getattr(item, "items", None)
        if content is None:
            content = getattr(item, "content", None)
        if content is not None:
            collected.extend(content)
    return collected


__all__ = [
    "REVIEW_INTERRUPTED_ASSISTANT_MESSAGE",
    "REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID",
    "REVIEW_ROLLOUT_USER_MESSAGE_ID",
    "ReviewExitMessages",
    "ReviewTask",
    "collect_review_user_input",
    "normalize_review_template_line_endings",
    "parse_review_output_event",
    "render_review_exit_interrupted",
    "render_review_exit_success",
    "review_exit_messages",
]
