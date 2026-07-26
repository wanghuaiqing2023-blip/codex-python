"""Tool specification helpers for the Rust ``request_user_input_spec`` module."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from pycodex.protocol import ModeKind, RequestUserInputArgs, RequestUserInputQuestion

JsonValue = Any
REQUEST_USER_INPUT_TOOL_NAME = "request_user_input"


def create_request_user_input_tool(description: str) -> dict[str, JsonValue]:
    if not isinstance(description, str):
        raise TypeError("description must be a string")
    return {
        "type": "function",
        "name": REQUEST_USER_INPUT_TOOL_NAME,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "Questions to show the user. Prefer 1 and do not exceed 3",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Stable identifier for mapping answers (snake_case)."},
                            "header": {"type": "string", "description": "Short header label shown in the UI (12 or fewer chars)."},
                            "question": {"type": "string", "description": "Single-sentence prompt shown to the user."},
                            "options": {
                                "type": "array",
                                "description": "Provide 2-3 mutually exclusive choices. Put the recommended option first and suffix its label with \"(Recommended)\". Do not include an \"Other\" option in this list; the client will add a free-form \"Other\" option automatically.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string", "description": "User-facing label (1-5 words)."},
                                        "description": {"type": "string", "description": "One short sentence explaining impact/tradeoff if selected."},
                                    },
                                    "required": ["label", "description"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["id", "header", "question", "options"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["questions"],
            "additionalProperties": False,
        },
    }


def request_user_input_unavailable_message(
    mode: ModeKind,
    available_modes: Iterable[ModeKind],
) -> str | None:
    mode = _mode_kind(mode, "mode")
    modes = _mode_tuple(available_modes, "available_modes")
    if mode in modes:
        return None
    return f"request_user_input is unavailable in {mode.display_name()} mode"


def normalize_request_user_input_args(args: RequestUserInputArgs) -> RequestUserInputArgs:
    if not isinstance(args, RequestUserInputArgs):
        raise TypeError("args must be RequestUserInputArgs")
    if any(question.options is None or not question.options for question in args.questions):
        raise ValueError("request_user_input requires non-empty options for every question")
    return RequestUserInputArgs(tuple(_with_other_option(question) for question in args.questions))


def request_user_input_tool_description(available_modes: Iterable[ModeKind]) -> str:
    modes = _mode_tuple(available_modes, "available_modes")
    return (
        "Request user input for one to three short questions and wait for the response. "
        f"This tool is only available in {_format_allowed_modes(modes)}."
    )


def _with_other_option(question: RequestUserInputQuestion) -> RequestUserInputQuestion:
    return replace(question, is_other=True)


def _mode_tuple(values: Iterable[ModeKind], field_name: str) -> tuple[ModeKind, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError(f"{field_name} must be an iterable of ModeKind")
    modes = tuple(values)
    if not all(isinstance(value, ModeKind) for value in modes):
        raise TypeError(f"{field_name} entries must be ModeKind")
    return modes


def _mode_kind(value: ModeKind | str | Any, field_name: str) -> ModeKind:
    raw_mode = getattr(value, "mode", value)
    if not isinstance(value, ModeKind):
        if isinstance(raw_mode, ModeKind):
            return raw_mode
        if isinstance(raw_mode, str):
            return ModeKind.parse(raw_mode)
        raise TypeError(f"{field_name} entries must be ModeKind")
    return raw_mode


def _format_allowed_modes(available_modes: tuple[ModeKind, ...]) -> str:
    names = tuple(mode.display_name() for mode in available_modes)
    if not names:
        return "no modes"
    if len(names) == 1:
        return f"{names[0]} mode"
    if len(names) == 2:
        return f"{names[0]} or {names[1]} mode"
    return f"modes: {','.join(names)}"


__all__ = [
    "REQUEST_USER_INPUT_TOOL_NAME",
    "create_request_user_input_tool",
    "normalize_request_user_input_args",
    "request_user_input_tool_description",
    "request_user_input_unavailable_message",
]
