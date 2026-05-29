"""request_user_input tool handler ported from Codex core."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Callable, Iterable

from pycodex.core.tool_context import FunctionToolOutput, ToolPayload
from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import (
    ModeKind,
    RequestUserInputArgs,
    RequestUserInputQuestion,
    RequestUserInputResponse,
    ToolName,
)

JsonValue = Any

REQUEST_USER_INPUT_TOOL_NAME = "request_user_input"

RequestUserInputCallback = Callable[[str, RequestUserInputArgs], RequestUserInputResponse | dict[str, JsonValue] | None]


def request_user_input_available_modes(
    *,
    default_mode_enabled: bool = False,
) -> tuple[ModeKind, ...]:
    if not isinstance(default_mode_enabled, bool):
        raise TypeError("default_mode_enabled must be a bool")
    if default_mode_enabled:
        return (ModeKind.DEFAULT, ModeKind.PLAN)
    return (ModeKind.PLAN,)


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
                            "id": {
                                "type": "string",
                                "description": "Stable identifier for mapping answers (snake_case).",
                            },
                            "header": {
                                "type": "string",
                                "description": "Short header label shown in the UI (12 or fewer chars).",
                            },
                            "question": {
                                "type": "string",
                                "description": "Single-sentence prompt shown to the user.",
                            },
                            "options": {
                                "type": "array",
                                "description": (
                                    "Provide 2-3 mutually exclusive choices. Put the recommended option first and "
                                    'suffix its label with "(Recommended)". Do not include an "Other" option in this '
                                    "list; the client will add a free-form \"Other\" option automatically."
                                ),
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {
                                            "type": "string",
                                            "description": "User-facing label (1-5 words).",
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": "One short sentence explaining impact/tradeoff if selected.",
                                        },
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


def normalize_request_user_input_args(
    args: RequestUserInputArgs,
) -> RequestUserInputArgs:
    if not isinstance(args, RequestUserInputArgs):
        raise TypeError("args must be RequestUserInputArgs")
    missing_options = any(
        question.options is None or len(question.options) == 0
        for question in args.questions
    )
    if missing_options:
        raise ValueError("request_user_input requires non-empty options for every question")
    return RequestUserInputArgs(
        tuple(_with_other_option(question) for question in args.questions)
    )


def request_user_input_tool_description(available_modes: Iterable[ModeKind]) -> str:
    modes = _mode_tuple(available_modes, "available_modes")
    return (
        "Request user input for one to three short questions and wait for the response. "
        f"This tool is only available in {_format_allowed_modes(modes)}."
    )


class RequestUserInputHandler:
    def __init__(
        self,
        available_modes: Iterable[ModeKind] = (ModeKind.PLAN,),
        request_callback: RequestUserInputCallback | None = None,
    ) -> None:
        self.available_modes = _mode_tuple(available_modes, "available_modes")
        if request_callback is not None and not callable(request_callback):
            raise TypeError("request_callback must be callable or None")
        self._request_callback = request_callback

    def tool_name(self) -> ToolName:
        return ToolName.plain(REQUEST_USER_INPUT_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_request_user_input_tool(
            request_user_input_tool_description(self.available_modes)
        )

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(
        self,
        invocation_or_payload: Any,
        *,
        call_id: str = "",
        mode: ModeKind = ModeKind.PLAN,
        is_root_thread: bool = True,
    ) -> FunctionToolOutput:
        if not isinstance(call_id, str):
            raise TypeError("call_id must be a string")
        mode = _mode_kind(mode, "mode")
        if not isinstance(is_root_thread, bool):
            raise TypeError("is_root_thread must be a bool")
        if not is_root_thread:
            raise FunctionCallError.respond_to_model(
                "request_user_input can only be used by the root thread"
            )
        unavailable = request_user_input_unavailable_message(mode, self.available_modes)
        if unavailable is not None:
            raise FunctionCallError.respond_to_model(unavailable)

        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model(
                f"{REQUEST_USER_INPUT_TOOL_NAME} handler received unsupported payload"
            )
        arguments = payload.arguments
        if arguments is None:
            raise FunctionCallError.respond_to_model(
                f"{REQUEST_USER_INPUT_TOOL_NAME} handler received unsupported payload"
            )

        args = parse_request_user_input_arguments(arguments)
        try:
            args = normalize_request_user_input_args(args)
        except ValueError as err:
            raise FunctionCallError.respond_to_model(str(err)) from err
        response = None if self._request_callback is None else self._request_callback(call_id, args)
        if response is None:
            raise FunctionCallError.respond_to_model(
                f"{REQUEST_USER_INPUT_TOOL_NAME} was cancelled before receiving a response"
            )
        if not isinstance(response, RequestUserInputResponse):
            response = RequestUserInputResponse.from_mapping(response)
        content = json.dumps(response.to_mapping(), separators=(",", ":"))
        return FunctionToolOutput.from_text(content, True)


def parse_request_user_input_arguments(arguments: str) -> RequestUserInputArgs:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        decoded = json.loads(arguments)
        return RequestUserInputArgs.from_mapping(decoded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse function arguments: {err}"
        ) from err


def _with_other_option(question: RequestUserInputQuestion) -> RequestUserInputQuestion:
    return replace(question, is_other=True)


def _mode_tuple(values: Iterable[ModeKind], field_name: str) -> tuple[ModeKind, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError(f"{field_name} must be an iterable of ModeKind")
    return tuple(_mode_kind(value, field_name) for value in values)


def _mode_kind(value: ModeKind, field_name: str) -> ModeKind:
    if not isinstance(value, ModeKind):
        raise TypeError(f"{field_name} entries must be ModeKind")
    return value


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
    "RequestUserInputCallback",
    "RequestUserInputHandler",
    "create_request_user_input_tool",
    "normalize_request_user_input_args",
    "parse_request_user_input_arguments",
    "request_user_input_available_modes",
    "request_user_input_tool_description",
    "request_user_input_unavailable_message",
]
