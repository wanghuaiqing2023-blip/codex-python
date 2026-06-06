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
from pycodex.core.guardian.review import is_guardian_reviewer_source
from pycodex.protocol import BaseInstructions, ResponseItem


def build_turn_prompt(
    prompt_input: Sequence[ResponseItem],
    router: Any,
    turn_context: Any,
    base_instructions: BaseInstructions,
    *,
    has_current_user_input: bool = False,
    output_schema: Any = None,
    output_schema_strict: bool | None = None,
) -> Prompt:
    """Build a model ``Prompt`` from turn context and visible history.

    The Rust runtime expects contextual user fragments, including AGENTS.md
    instructions, to already be present in ``prompt_input`` after session
    context recording. Prompt construction itself should preserve input order.
    """

    tools = router.model_visible_specs() if hasattr(router, "model_visible_specs") else []
    return Prompt(
        input=list(prompt_input),
        tools=list(tools),
        parallel_tool_calls=_supports_parallel_tool_calls(turn_context),
        base_instructions=base_instructions,
        personality=getattr(turn_context, "personality", None),
        output_schema=output_schema,
        output_schema_strict=_output_schema_strict_for_turn(turn_context, output_schema_strict),
    )


def input_with_user_instructions(
    prompt_input: Sequence[ResponseItem],
    turn_context: Any,
    has_current_user_input: bool,
) -> list[ResponseItem]:
    return list(prompt_input)


def render_turn_user_instructions(turn_context: Any) -> ResponseItem | None:
    user_instructions = getattr(turn_context, "user_instructions", None)
    if user_instructions is None:
        return None
    text = str(user_instructions)
    if text == "":
        return None
    directory = str(getattr(turn_context, "cwd", ""))
    return UserInstructions(directory=directory, text=text).into_response_item()


def _supports_parallel_tool_calls(turn_context: Any) -> bool:
    model_info = getattr(turn_context, "model_info", None)
    return bool(getattr(model_info, "supports_parallel_tool_calls", False))


def _output_schema_strict_for_turn(turn_context: Any, output_schema_strict: bool | None) -> bool:
    if output_schema_strict is not None:
        if not isinstance(output_schema_strict, bool):
            raise TypeError("output_schema_strict must be a bool or None")
        return output_schema_strict
    return not is_guardian_reviewer_source(getattr(turn_context, "session_source", None))


__all__ = [
    "build_turn_prompt",
    "input_with_user_instructions",
    "is_guardian_reviewer_source",
    "render_turn_user_instructions",
]
