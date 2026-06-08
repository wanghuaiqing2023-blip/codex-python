"""Internal test synchronization handler ported from Codex core."""

from __future__ import annotations

import json
import asyncio
import time
from dataclasses import dataclass
from typing import Any

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ToolName

JsonValue = Any

TEST_SYNC_TOOL_NAME = "test_sync_tool"
DEFAULT_TEST_SYNC_TIMEOUT_MS = 1_000

_BARRIERS: dict[str, "_BarrierState"] = {}
_BARRIERS_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class BarrierArgs:
    id: str
    participants: int
    timeout_ms: int = DEFAULT_TEST_SYNC_TIMEOUT_MS

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("barrier id must be a string")
        _ensure_usize(self.participants, "participants")
        _ensure_usize(self.timeout_ms, "timeout_ms")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "BarrierArgs":
        if not isinstance(value, dict):
            raise TypeError("barrier must be a mapping")
        return cls(
            id=_required_str(value, "id"),
            participants=_required_usize(value, "participants"),
            timeout_ms=_optional_usize(value, "timeout_ms", DEFAULT_TEST_SYNC_TIMEOUT_MS),
        )


@dataclass(frozen=True)
class TestSyncArgs:
    __test__ = False

    sleep_before_ms: int | None = None
    sleep_after_ms: int | None = None
    barrier: BarrierArgs | None = None

    def __post_init__(self) -> None:
        if self.sleep_before_ms is not None:
            _ensure_usize(self.sleep_before_ms, "sleep_before_ms")
        if self.sleep_after_ms is not None:
            _ensure_usize(self.sleep_after_ms, "sleep_after_ms")
        if self.barrier is not None and not isinstance(self.barrier, BarrierArgs):
            raise TypeError("barrier must be BarrierArgs or None")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TestSyncArgs":
        if not isinstance(value, dict):
            raise TypeError("test sync args must be a mapping")
        barrier = value.get("barrier")
        return cls(
            sleep_before_ms=_optional_usize(value, "sleep_before_ms", None),
            sleep_after_ms=_optional_usize(value, "sleep_after_ms", None),
            barrier=BarrierArgs.from_mapping(barrier) if barrier is not None else None,
        )


@dataclass
class _BarrierState:
    barrier: "_ReusableBarrier"
    participants: int


class _ReusableBarrier:
    def __init__(self, participants: int) -> None:
        if participants <= 0:
            raise ValueError("participants must be greater than zero")
        self.participants = participants
        self._condition = asyncio.Condition()
        self._waiting = 0
        self._generation = 0

    async def wait(self, timeout_seconds: float) -> int:
        deadline = time.monotonic() + timeout_seconds
        async with self._condition:
            generation = self._generation
            self._waiting += 1

            if self._waiting == self.participants:
                self._generation += 1
                self._waiting = 0
                self._condition.notify_all()
                return 0

            while generation == self._generation:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._waiting -= 1
                    self._condition.notify_all()
                    raise TimeoutError
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    if generation == self._generation:
                        self._waiting -= 1
                        self._condition.notify_all()
                        raise

            return 1


def create_test_sync_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": TEST_SYNC_TOOL_NAME,
        "description": "Internal synchronization helper used by Codex integration tests.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "sleep_before_ms": {
                    "type": "number",
                    "description": "Optional delay in milliseconds before any other action",
                },
                "sleep_after_ms": {
                    "type": "number",
                    "description": "Optional delay in milliseconds after completing the barrier",
                },
                "barrier": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Identifier shared by concurrent calls that should rendezvous",
                        },
                        "participants": {
                            "type": "number",
                            "description": "Number of tool calls that must arrive before the barrier opens",
                        },
                        "timeout_ms": {
                            "type": "number",
                            "description": "Maximum time in milliseconds to wait at the barrier",
                        },
                    },
                    "required": ["id", "participants"],
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    }


class TestSyncHandler:
    def tool_name(self) -> ToolName:
        return ToolName.plain(TEST_SYNC_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_test_sync_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    async def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model(
                "test_sync_tool handler received unsupported payload"
            )
        arguments = payload.arguments
        if arguments is None:
            raise FunctionCallError.respond_to_model(
                "test_sync_tool handler received unsupported payload"
            )
        args = parse_test_sync_arguments(arguments)

        if args.sleep_before_ms is not None and args.sleep_before_ms > 0:
            await asyncio.sleep(args.sleep_before_ms / 1000)
        if args.barrier is not None:
            await wait_on_barrier(args.barrier)
        if args.sleep_after_ms is not None and args.sleep_after_ms > 0:
            await asyncio.sleep(args.sleep_after_ms / 1000)

        return FunctionToolOutput.from_text("ok", True)


def parse_test_sync_arguments(arguments: str) -> TestSyncArgs:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        decoded = json.loads(arguments) if arguments.strip() else {}
        return TestSyncArgs.from_mapping(decoded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse function arguments: {err}"
        ) from err


async def wait_on_barrier(args: BarrierArgs) -> None:
    if not isinstance(args, BarrierArgs):
        raise TypeError("args must be BarrierArgs")
    if args.participants == 0:
        raise FunctionCallError.respond_to_model(
            "barrier participants must be greater than zero"
        )
    if args.timeout_ms == 0:
        raise FunctionCallError.respond_to_model(
            "barrier timeout must be greater than zero"
        )

    async with _BARRIERS_LOCK:
        state = _BARRIERS.get(args.id)
        if state is None:
            state = _BarrierState(
                barrier=_ReusableBarrier(args.participants),
                participants=args.participants,
            )
            _BARRIERS[args.id] = state
        elif state.participants != args.participants:
            raise FunctionCallError.respond_to_model(
                f"barrier {args.id} already registered with {state.participants} participants"
            )
        barrier = state.barrier

    try:
        index = await barrier.wait(args.timeout_ms / 1000)
    except TimeoutError as err:
        raise FunctionCallError.respond_to_model(
            "test_sync_tool barrier wait timed out"
        ) from err

    if index == 0:
        await _remove_barrier_if_current(args.id, barrier)


async def _remove_barrier_if_current(barrier_id: str, barrier: _ReusableBarrier) -> None:
    async with _BARRIERS_LOCK:
        state = _BARRIERS.get(barrier_id)
        if state is not None and state.barrier is barrier:
            _BARRIERS.pop(barrier_id, None)


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _required_usize(value: dict[str, JsonValue], key: str) -> int:
    return _ensure_usize(value[key], key)


def _optional_usize(value: dict[str, JsonValue], key: str, default: int | None) -> int | None:
    if key not in value or value[key] is None:
        return default
    return _ensure_usize(value[key], key)


def _ensure_usize(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


__all__ = [
    "DEFAULT_TEST_SYNC_TIMEOUT_MS",
    "TEST_SYNC_TOOL_NAME",
    "BarrierArgs",
    "TestSyncArgs",
    "TestSyncHandler",
    "create_test_sync_tool",
    "parse_test_sync_arguments",
    "wait_on_barrier",
]
