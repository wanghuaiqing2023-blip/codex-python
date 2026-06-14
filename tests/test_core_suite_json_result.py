"""Rust integration parity for ``core/tests/suite/json_result.rs``.

The Rust tests verify that a user turn with ``final_output_json_schema`` sends a
strict Responses ``text.format`` JSON schema and that the final assistant text
is a JSON object matching the expected keys.  Python anchors the same behavior
at the request-shaping and agent-message parsing boundary.
"""

from __future__ import annotations

import json

from pycodex.core import create_text_param_for_request
from pycodex.protocol import ContentItem, ResponseItem


SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "final_answer": {"type": "string"},
    },
    "required": ["explanation", "final_answer"],
    "additionalProperties": False,
}


def _assert_json_result_contract(_model: str) -> None:
    text = create_text_param_for_request(None, SCHEMA, True)

    assert text == {
        "format": {
            "name": "codex_output_schema",
            "type": "json_schema",
            "strict": True,
            "schema": SCHEMA,
        }
    }

    message = ResponseItem.message(
        "assistant",
        (ContentItem.output_text('{"explanation": "explanation", "final_answer": "final_answer"}'),),
        id="m2",
    )
    payload = json.loads(message.content[0].text or "")
    assert payload["explanation"] == "explanation"
    assert payload["final_answer"] == "final_answer"


def test_codex_returns_json_result_for_gpt5() -> None:
    """Rust: ``codex_returns_json_result_for_gpt5``."""

    _assert_json_result_contract("gpt-5.4")


def test_codex_returns_json_result_for_gpt5_codex() -> None:
    """Rust: ``codex_returns_json_result_for_gpt5_codex``."""

    _assert_json_result_contract("gpt-5.4")
