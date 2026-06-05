"""Prompt debug input construction boundaries.

Ported from ``codex/codex-rs/core/src/prompt_debug.rs``. The Rust module builds
a short-lived session/thread and then asks the session to construct the
model-visible prompt input for a debug turn. This Python port preserves that
two-layer shape while keeping thread/session creation, tool building, and prompt
construction injectable runtime boundaries.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.core.client_common import Prompt
from pycodex.core.session.turn.prompt import build_turn_prompt, render_turn_user_instructions
from pycodex.protocol import BaseInstructions, ResponseInputItem, ResponseItem, UserInput


SessionFactory = Callable[[Any, Any | None], Any | Awaitable[Any]]
BuiltToolsFn = Callable[[Any, Any], Any | Awaitable[Any]]
BuildPromptFn = Callable[[list[ResponseItem], Any, Any, BaseInstructions], Prompt]


@dataclass(frozen=True)
class PromptDebugThread:
    session: Any
    thread_id: str | None = None
    shutdown: Callable[[], Any | Awaitable[Any]] | None = None
    remove: Callable[[str | None], Any | Awaitable[Any]] | None = None

    async def shutdown_and_remove(self) -> None:
        if self.shutdown is not None:
            await _maybe_await(self.shutdown())
        if self.remove is not None:
            await _maybe_await(self.remove(self.thread_id))


async def build_prompt_input(
    config: Any,
    input: Sequence[UserInput],
    state_db: Any | None = None,
    *,
    session_factory: SessionFactory | None = None,
    built_tools: BuiltToolsFn | None = None,
    build_prompt: BuildPromptFn | None = None,
) -> list[ResponseItem]:
    mark_config_ephemeral(config)
    if session_factory is None:
        raise RuntimeError("build_prompt_input requires a session_factory boundary")
    thread_like = await _maybe_await(session_factory(config, state_db))
    debug_thread = _debug_thread(thread_like)
    try:
        return await build_prompt_input_from_session(
            debug_thread.session,
            input,
            built_tools=built_tools,
            build_prompt=build_prompt,
        )
    finally:
        await debug_thread.shutdown_and_remove()


async def build_prompt_input_from_session(
    sess: Any,
    input: Sequence[UserInput],
    *,
    built_tools: BuiltToolsFn | None = None,
    build_prompt: BuildPromptFn | None = None,
) -> list[ResponseItem]:
    user_input = _user_inputs(input)
    turn_context = await _maybe_await(sess.new_default_turn())
    await _maybe_await(sess.record_context_updates_and_set_reference_context_item(turn_context))

    if user_input:
        input_item = ResponseInputItem.from_user_inputs(user_input)
        response_item = ResponseItem.from_response_input_item(input_item)
        await _maybe_await(sess.record_conversation_items(turn_context, (response_item,)))

    history = await _maybe_await(sess.clone_history())
    input_modalities = getattr(getattr(turn_context, "model_info", None), "input_modalities", None)
    prompt_input = history.for_prompt(input_modalities) if hasattr(history, "for_prompt") else list(history)
    if user_input:
        instruction_item = render_turn_user_instructions(turn_context)
        if instruction_item is not None:
            prompt_input = list(prompt_input)
            if prompt_input:
                prompt_input.insert(-1, instruction_item)
            else:
                prompt_input.append(instruction_item)

    built_tools_fn = built_tools or _default_built_tools
    router = await _maybe_await(built_tools_fn(sess, turn_context))
    base_instructions = await _maybe_await(sess.get_base_instructions())
    if not isinstance(base_instructions, BaseInstructions):
        base_instructions = BaseInstructions(str(getattr(base_instructions, "text", base_instructions)))

    if build_prompt is None:
        prompt = build_turn_prompt(
            list(prompt_input),
            router,
            turn_context,
            base_instructions,
            has_current_user_input=bool(user_input),
        )
    else:
        prompt = build_prompt(
            list(prompt_input),
            router,
            turn_context,
            base_instructions,
        )
    if not isinstance(prompt, Prompt):
        raise TypeError("build_prompt must return Prompt")
    return prompt.get_formatted_input()


def mark_config_ephemeral(config: Any) -> None:
    if isinstance(config, Mapping):
        try:
            config["ephemeral"] = True
        except TypeError:
            raise TypeError("mapping config must be mutable to mark ephemeral") from None
        return
    setattr(config, "ephemeral", True)


def _debug_thread(value: Any) -> PromptDebugThread:
    if isinstance(value, PromptDebugThread):
        return value
    session = getattr(value, "session", None)
    if session is not None:
        return PromptDebugThread(
            session=session,
            thread_id=getattr(value, "thread_id", None),
            shutdown=getattr(value, "shutdown_and_wait", None),
            remove=getattr(value, "remove_thread", None),
        )
    return PromptDebugThread(session=value)


def _user_inputs(value: Sequence[UserInput]) -> tuple[UserInput, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("input must be a sequence of UserInput")
    return tuple(item if isinstance(item, UserInput) else UserInput.from_mapping(item) for item in value)


async def _default_built_tools(_sess: Any, _turn_context: Any) -> Any:
    return None


def _default_build_prompt(
    prompt_input: list[ResponseItem],
    router: Any,
    _turn_context: Any,
    base_instructions: BaseInstructions,
) -> Prompt:
    tools = router.model_visible_specs() if hasattr(router, "model_visible_specs") else []
    return Prompt(input=prompt_input, tools=list(tools), base_instructions=base_instructions)


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable) or inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "BuildPromptFn",
    "BuiltToolsFn",
    "PromptDebugThread",
    "SessionFactory",
    "build_prompt_input",
    "build_prompt_input_from_session",
    "mark_config_ephemeral",
]

