"""Session service ported from ``code-mode/src/service.rs``."""
from __future__ import annotations
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from .response import FunctionCallOutputContentItem
from .runtime import ExecuteRequest, ExecuteToPendingOutcome, RuntimeResponse, WaitOutcome, WaitRequest, WaitToPendingOutcome, WaitToPendingRequest, _coerce_execute_request, _coerce_execute_to_pending_outcome, _coerce_runtime_response, _coerce_wait_outcome, _coerce_wait_request, _coerce_wait_to_pending_outcome, _coerce_wait_to_pending_request
from .runtime import _ensure_str
JsonValue = Any
CodeModeExecuteCallback = Callable[[ExecuteRequest], RuntimeResponse | Mapping[str, JsonValue]]
CodeModeWaitCallback = Callable[[WaitRequest], WaitOutcome | RuntimeResponse | Mapping[str, JsonValue]]
CodeModeExecuteToPendingCallback = Callable[[ExecuteRequest], ExecuteToPendingOutcome | RuntimeResponse | Mapping[str, JsonValue]]
CodeModeWaitToPendingCallback = Callable[[WaitToPendingRequest], WaitToPendingOutcome | ExecuteToPendingOutcome | RuntimeResponse | Mapping[str, JsonValue]]
class CodeModeTurnHost(Protocol):
    def invoke_tool(self, invocation: Any, cancellation_token: Any = None) -> JsonValue: ...
    def notify(self, call_id: str, cell_id: str, text: str) -> None: ...
@dataclass
class CodeModeTurnWorker:
    shutdown: Callable[[], None] | None = None
    def close(self) -> None:
        if self.shutdown is not None:
            callback, self.shutdown = self.shutdown, None
            callback()

@dataclass(frozen=True)
class PendingResult:
    content_items: tuple[FunctionCallOutputContentItem, ...] = ()
    error_text: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_items",
            tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
        )
        if self.error_text is not None:
            object.__setattr__(self, "error_text", _ensure_str(self.error_text, "error_text"))


def missing_cell_response(cell_id: str) -> RuntimeResponse:
    return RuntimeResponse.result(
        cell_id=str(cell_id),
        error_text=f"exec cell {cell_id} not found",
    )


def pending_result_response(cell_id: str, result: PendingResult | Mapping[str, JsonValue]) -> RuntimeResponse:
    pending_result = _coerce_pending_result(result)
    return RuntimeResponse.result(
        cell_id=str(cell_id),
        content_items=pending_result.content_items,
        error_text=pending_result.error_text,
    )


class CodeModeService:
    def __init__(
        self,
        *,
        execute_callback: CodeModeExecuteCallback | None = None,
        wait_callback: CodeModeWaitCallback | None = None,
        execute_to_pending_callback: CodeModeExecuteToPendingCallback | None = None,
        wait_to_pending_callback: CodeModeWaitToPendingCallback | None = None,
    ) -> None:
        self._next_cell_id = 1
        self.execute_callback = execute_callback
        self.wait_callback = wait_callback
        self.execute_to_pending_callback = execute_to_pending_callback
        self.wait_to_pending_callback = wait_to_pending_callback

    def allocate_cell_id(self) -> str:
        cell_id = str(self._next_cell_id)
        self._next_cell_id += 1
        return cell_id

    def execute(self, request: ExecuteRequest | Mapping[str, JsonValue]) -> RuntimeResponse:
        if self.execute_callback is None:
            raise ValueError("code-mode execute callback is not configured")
        return _coerce_runtime_response(self.execute_callback(_coerce_execute_request(request)))

    def execute_to_pending(
        self,
        request: ExecuteRequest | Mapping[str, JsonValue],
    ) -> ExecuteToPendingOutcome:
        if self.execute_to_pending_callback is not None:
            return _coerce_execute_to_pending_outcome(
                self.execute_to_pending_callback(_coerce_execute_request(request))
            )
        return ExecuteToPendingOutcome.completed(self.execute(_coerce_execute_request(request)))

    def wait(self, request: WaitRequest | Mapping[str, JsonValue]) -> WaitOutcome:
        wait_request = _coerce_wait_request(request)
        if self.wait_callback is None:
            return WaitOutcome.missing_cell(missing_cell_response(wait_request.cell_id))
        return _coerce_wait_outcome(self.wait_callback(wait_request))

    def wait_to_pending(
        self,
        request: WaitToPendingRequest | Mapping[str, JsonValue],
    ) -> WaitToPendingOutcome:
        wait_request = _coerce_wait_to_pending_request(request)
        if self.wait_to_pending_callback is None:
            return WaitToPendingOutcome.missing_cell(missing_cell_response(wait_request.cell_id))
        return _coerce_wait_to_pending_outcome(self.wait_to_pending_callback(wait_request))


def _coerce_pending_result(value: PendingResult | Mapping[str, JsonValue]) -> PendingResult:
    if isinstance(value, PendingResult):
        return value
    if isinstance(value, Mapping):
        return PendingResult(
            content_items=tuple(value.get("content_items", ())),
            error_text=None if value.get("error_text") is None else str(value.get("error_text")),
        )
    raise TypeError("pending result must be a PendingResult or mapping")
