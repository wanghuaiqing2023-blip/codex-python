"""Wait handler ported from ``core/src/tools/code_mode/wait_handler.rs``."""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.code_mode import DEFAULT_WAIT_YIELD_TIME_MS
from pycodex.code_mode import WAIT_TOOL_NAME
from pycodex.code_mode import RuntimeResponse
from pycodex.code_mode import WaitOutcome
from pycodex.code_mode import WaitRequest
from pycodex.protocol import ToolName

from .response_adapter import handle_runtime_response
from .wait_spec import create_wait_tool


@dataclass(frozen=True)
class ExecWaitArgs:
    cell_id: str
    yield_time_ms: int = DEFAULT_WAIT_YIELD_TIME_MS
    max_tokens: int | None = None
    terminate: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.cell_id, str):
            raise TypeError("cell_id must be a string")
        object.__setattr__(self, "yield_time_ms", _non_negative_int(self.yield_time_ms))
        object.__setattr__(
            self,
            "max_tokens",
            None if self.max_tokens is None else _non_negative_int(self.max_tokens),
        )
        if not isinstance(self.terminate, bool):
            raise TypeError("terminate must be a bool")


def parse_wait_arguments(arguments: str) -> ExecWaitArgs:
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to parse function arguments: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("failed to parse function arguments: expected JSON object")
    if "cell_id" not in value:
        raise ValueError("failed to parse function arguments: missing field `cell_id`")
    cell_id = value["cell_id"]
    if not isinstance(cell_id, str):
        raise ValueError("failed to parse function arguments: field `cell_id` must be a string")
    terminate = value.get("terminate", False)
    if not isinstance(terminate, bool):
        raise ValueError("failed to parse function arguments: field `terminate` must be a boolean")
    return ExecWaitArgs(
        cell_id=cell_id,
        yield_time_ms=_argument_int(value, "yield_time_ms", DEFAULT_WAIT_YIELD_TIME_MS),
        max_tokens=(
            None
            if value.get("max_tokens") is None
            else _argument_int(value, "max_tokens", DEFAULT_WAIT_YIELD_TIME_MS)
        ),
        terminate=terminate,
    )


@dataclass(frozen=True)
class CodeModeWaitHandler:
    wait_callback: Any = None
    can_request_original_detail: bool = True

    def tool_name(self) -> ToolName:
        return ToolName.plain(WAIT_TOOL_NAME)

    def spec(self) -> dict[str, Any]:
        return copy.deepcopy(create_wait_tool())

    def matches_kind(self, payload: Any) -> bool:
        return getattr(payload, "type", None) == "function"

    def pre_tool_use_payload(self, _invocation: Any) -> None:
        return None

    def post_tool_use_payload(self, _invocation: Any, _result: Any) -> None:
        return None

    def handle(self, invocation_or_payload: Any) -> Any:
        from pycodex.core.tools.context import ToolPayload

        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        tool_name = getattr(invocation_or_payload, "tool_name", self.tool_name())
        if (
            not isinstance(payload, ToolPayload)
            or payload.type != "function"
            or tool_name.namespace is not None
            or tool_name.name != WAIT_TOOL_NAME
            or payload.arguments is None
        ):
            raise ValueError(f"{WAIT_TOOL_NAME} expects JSON arguments")
        if self.wait_callback is None:
            raise ValueError("code-mode wait callback is not configured")

        args = parse_wait_arguments(payload.arguments)
        request = WaitRequest(
            cell_id=args.cell_id,
            yield_time_ms=args.yield_time_ms,
            terminate=args.terminate,
        )
        started_at = time.perf_counter()
        outcome = self.wait_callback(request)
        response = outcome.response if isinstance(outcome, WaitOutcome) else outcome
        if not isinstance(response, RuntimeResponse):
            response = RuntimeResponse.from_mapping(response)
        return handle_runtime_response(
            response,
            max_output_tokens=args.max_tokens,
            wall_time_seconds=time.perf_counter() - started_at,
            can_request_original_detail=self.can_request_original_detail,
        )


def _argument_int(value: Mapping[str, Any], field: str, default: int) -> int:
    candidate = value.get(field, default)
    if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
        raise ValueError(f"failed to parse function arguments: field `{field}` must be a number")
    if isinstance(candidate, float) and not candidate.is_integer():
        raise ValueError(f"failed to parse function arguments: field `{field}` must be an integer")
    try:
        return _non_negative_int(int(candidate))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"failed to parse function arguments: field `{field}` must be a non-negative integer"
        ) from exc


def _non_negative_int(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("value must be a non-negative integer")
    return value


__all__ = ["CodeModeWaitHandler", "ExecWaitArgs", "parse_wait_arguments"]
