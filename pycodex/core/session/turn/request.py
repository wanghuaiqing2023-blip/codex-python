"""Turn-to-model request construction helpers.

This is the next transport-independent slice after ``turn_prompt``: assemble a
Rust-shaped ``Prompt`` for a turn, then hand it to ``ModelClient`` to build the
Responses API request payload.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.core.client import ModelClient
from pycodex.core.session.turn.prompt import build_turn_prompt
from pycodex.protocol import BaseInstructions, ResponseItem


@dataclass(frozen=True)
class TurnResponsesRequestPlan:
    """Request construction result for one model turn."""

    prompt: Any
    request: dict[str, Any]


def build_turn_responses_request(
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    prompt_input: Sequence[ResponseItem],
    router: Any,
    turn_context: Any,
    base_instructions: BaseInstructions,
    *,
    has_current_user_input: bool = False,
    effort: Any = None,
    summary: Any = None,
    service_tier: str | None = None,
    output_schema: Any = None,
    output_schema_strict: bool | None = None,
) -> TurnResponsesRequestPlan:
    """Build a Responses API request for a single turn.

    The helper keeps the same high-level sequence as Rust's session turn path:
    model-visible prompt assembly first, provider request payload construction
    second.
    """

    prompt = build_turn_prompt(
        prompt_input,
        router,
        turn_context,
        base_instructions,
        has_current_user_input=has_current_user_input,
        output_schema=output_schema,
        output_schema_strict=output_schema_strict,
    )
    request = model_client.build_responses_request(
        provider,
        prompt,
        model_info,
        effort=effort,
        summary=summary,
        service_tier=service_tier,
    )
    return TurnResponsesRequestPlan(prompt=prompt, request=request)


__all__ = [
    "TurnResponsesRequestPlan",
    "build_turn_responses_request",
]

