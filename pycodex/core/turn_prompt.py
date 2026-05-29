"""Turn prompt assembly helpers for the core Codex runtime.

This module contains the transport-independent prompt assembly slice from
``codex-rs/core/src/session`` and ``session/turn.rs`` that can already be
represented in the Python port: model-visible history, contextual user
instructions, model-visible tool specs, and base instructions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pycodex.core.client_common import Prompt
from pycodex.core.context import UserInstructions
from pycodex.protocol import BaseInstructions, ResponseItem


def build_turn_prompt(
    prompt_input: Sequence[ResponseItem],
    router: Any,
    turn_context: Any,
    base_instructions: BaseInstructions,
    *,
    has_current_user_input: bool = False,
    output_schema: Any = None,
    output_schema_strict: bool = True,
) -> Prompt:
    """Build a model ``Prompt`` from turn context and visible history.

    The Rust runtime renders ``turn_context.user_instructions`` as a contextual
    user fragment before other per-turn user content. Keeping that behavior in
    one helper lets prompt-debug and the future main agent loop share the same
    ordering and rendering rules.
    """

    input_items = input_with_user_instructions(prompt_input, turn_context, has_current_user_input)
    tools = router.model_visible_specs() if hasattr(router, "model_visible_specs") else []
    return Prompt(
        input=input_items,
        tools=list(tools),
        base_instructions=base_instructions,
        output_schema=output_schema,
        output_schema_strict=output_schema_strict,
    )


def input_with_user_instructions(
    prompt_input: Sequence[ResponseItem],
    turn_context: Any,
    has_current_user_input: bool,
) -> list[ResponseItem]:
    rendered = render_turn_user_instructions(turn_context)
    items = list(prompt_input)
    if rendered is None:
        return items
    insert_at = max(len(items) - 1, 0) if has_current_user_input else len(items)
    items.insert(insert_at, rendered)
    return items


def render_turn_user_instructions(turn_context: Any) -> ResponseItem | None:
    user_instructions = getattr(turn_context, "user_instructions", None)
    if user_instructions is None:
        return None
    text = str(user_instructions)
    if text == "":
        return None
    directory = str(getattr(turn_context, "cwd", ""))
    return UserInstructions(directory=directory, text=text).into_response_item()


__all__ = [
    "build_turn_prompt",
    "input_with_user_instructions",
    "render_turn_user_instructions",
]
