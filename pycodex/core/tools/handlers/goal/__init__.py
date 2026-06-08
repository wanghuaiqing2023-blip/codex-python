"""Goal tool handlers ported from Codex core."""

from __future__ import annotations

import json
import inspect
import time
from dataclasses import dataclass, replace
from typing import Any, Protocol

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ThreadGoal, ThreadGoalStatus, ThreadId, ToolName

JsonValue = Any

GET_GOAL_TOOL_NAME = "get_goal"
CREATE_GOAL_TOOL_NAME = "create_goal"
UPDATE_GOAL_TOOL_NAME = "update_goal"

I64_MIN = -(2**63)
I64_MAX = 2**63 - 1

COMPLETION_BUDGET_REPORT_MESSAGE = (
    "Goal achieved. Report final usage from this tool result's structured goal fields. "
    "If `goal.tokenBudget` is present, include token usage from `goal.tokensUsed` and "
    "`goal.tokenBudget`. If `goal.timeUsedSeconds` is greater than 0, summarize elapsed "
    "time in a concise, human-friendly form appropriate to the response language."
)

UPDATE_GOAL_STATUS_ERROR = (
    "update_goal can only mark the existing goal complete or blocked; pause, resume, "
    "budget-limited, and usage-limited status changes are controlled by the user or system"
)


@dataclass(frozen=True)
class CreateGoalArgs:
    objective: str
    token_budget: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.objective, str):
            raise TypeError("objective must be a string")
        if self.token_budget is not None:
            _i64(self.token_budget, "token_budget")
            if self.token_budget <= 0:
                raise ValueError("token_budget must be positive")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CreateGoalArgs":
        if not isinstance(value, dict):
            raise TypeError("create_goal args must be a mapping")
        return cls(
            objective=_required_str(value, "objective"),
            token_budget=_optional_i64(value, "token_budget"),
        )


@dataclass(frozen=True)
class UpdateGoalArgs:
    status: ThreadGoalStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, ThreadGoalStatus):
            object.__setattr__(self, "status", ThreadGoalStatus(self.status))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "UpdateGoalArgs":
        if not isinstance(value, dict):
            raise TypeError("update_goal args must be a mapping")
        return cls(status=ThreadGoalStatus(_required_str(value, "status")))


@dataclass(frozen=True)
class GoalToolResponse:
    goal: ThreadGoal | None
    remaining_tokens: int | None = None
    completion_budget_report: str | None = None

    @classmethod
    def new(
        cls,
        goal: ThreadGoal | None,
        *,
        include_completion_budget_report: bool = False,
    ) -> "GoalToolResponse":
        if goal is not None and not isinstance(goal, ThreadGoal):
            raise TypeError("goal must be ThreadGoal or None")
        remaining_tokens = None
        if goal is not None and goal.token_budget is not None:
            remaining_tokens = max(goal.token_budget - goal.tokens_used, 0)
        report = None
        if (
            include_completion_budget_report
            and goal is not None
            and goal.status is ThreadGoalStatus.COMPLETE
        ):
            report = completion_budget_report(goal)
        return cls(goal, remaining_tokens, report)

    def __post_init__(self) -> None:
        if self.goal is not None and not isinstance(self.goal, ThreadGoal):
            raise TypeError("goal must be ThreadGoal or None")
        if self.remaining_tokens is not None:
            _i64(self.remaining_tokens, "remaining_tokens")
        if self.completion_budget_report is not None and not isinstance(self.completion_budget_report, str):
            raise TypeError("completion_budget_report must be a string or None")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "goal": None if self.goal is None else self.goal.to_mapping(),
            "remainingTokens": self.remaining_tokens,
            "completionBudgetReport": self.completion_budget_report,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_mapping(), indent=2)

    def to_output(self) -> FunctionToolOutput:
        return FunctionToolOutput.from_text(self.to_json(), True)


@dataclass(frozen=True)
class CreateGoalRequest:
    objective: str
    token_budget: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.objective, str):
            raise TypeError("objective must be a string")
        if self.token_budget is not None:
            _i64(self.token_budget, "token_budget")


@dataclass(frozen=True)
class SetGoalRequest:
    objective: str | None = None
    status: ThreadGoalStatus | None = None
    token_budget: int | None = None

    def __post_init__(self) -> None:
        if self.objective is not None and not isinstance(self.objective, str):
            raise TypeError("objective must be a string or None")
        if self.status is not None and not isinstance(self.status, ThreadGoalStatus):
            object.__setattr__(self, "status", ThreadGoalStatus(self.status))
        if self.token_budget is not None:
            _i64(self.token_budget, "token_budget")


class GoalStore(Protocol):
    def get_thread_goal(self) -> ThreadGoal | None:
        ...

    def create_thread_goal(self, request: CreateGoalRequest) -> ThreadGoal:
        ...

    def set_thread_goal(self, request: SetGoalRequest) -> ThreadGoal:
        ...

    def goal_runtime_tool_completed_goal(self) -> None:
        ...


class InMemoryGoalStore:
    """Small stdlib store mirroring the session methods used by Rust handlers."""

    def __init__(self, thread_id: ThreadId | None = None) -> None:
        if thread_id is not None and not isinstance(thread_id, ThreadId):
            raise TypeError("thread_id must be ThreadId or None")
        self.thread_id = thread_id or ThreadId.new()
        self.goal: ThreadGoal | None = None
        self.tool_completed_goal_count = 0

    def get_thread_goal(self) -> ThreadGoal | None:
        return self.goal

    def create_thread_goal(self, request: CreateGoalRequest) -> ThreadGoal:
        if not isinstance(request, CreateGoalRequest):
            raise TypeError("request must be CreateGoalRequest")
        if self.goal is not None:
            raise ValueError("thread already has a goal")
        now = _now_ms()
        self.goal = ThreadGoal(
            thread_id=self.thread_id,
            objective=request.objective,
            status=ThreadGoalStatus.ACTIVE,
            tokens_used=0,
            time_used_seconds=0,
            created_at=now,
            updated_at=now,
            token_budget=request.token_budget,
        )
        return self.goal

    def set_thread_goal(self, request: SetGoalRequest) -> ThreadGoal:
        if not isinstance(request, SetGoalRequest):
            raise TypeError("request must be SetGoalRequest")
        if self.goal is None:
            raise ValueError("thread does not have a goal")
        updates: dict[str, JsonValue] = {"updated_at": _now_ms()}
        if request.objective is not None:
            updates["objective"] = request.objective
        if request.status is not None:
            updates["status"] = request.status
        if request.token_budget is not None:
            updates["token_budget"] = request.token_budget
        self.goal = replace(self.goal, **updates)
        return self.goal

    def goal_runtime_tool_completed_goal(self) -> None:
        self.tool_completed_goal_count += 1


def create_get_goal_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": GET_GOAL_TOOL_NAME,
        "description": "Get the current goal for this thread, including status, budgets, token and elapsed-time usage, and remaining token budget.",
        "strict": False,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    }


def create_create_goal_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": CREATE_GOAL_TOOL_NAME,
        "description": (
            "Create a goal only when explicitly requested by the user or system/developer instructions; do not infer goals from ordinary tasks.\n"
            f"Set token_budget only when an explicit token budget is requested. Fails if a goal exists; use {UPDATE_GOAL_TOOL_NAME} only for status."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Required. The concrete objective to start pursuing. This starts a new active goal only when no goal is currently defined; if a goal already exists, this tool fails.",
                },
                "token_budget": {
                    "type": "integer",
                    "description": "Optional positive token budget for the new active goal.",
                },
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
    }


def create_update_goal_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": UPDATE_GOAL_TOOL_NAME,
        "description": (
            "Update the existing goal.\nUse this tool only to mark the goal achieved or genuinely blocked.\n"
            "Set status to `complete` only when the objective has actually been achieved and no required work remains.\n"
            "Set status to `blocked` only when the same blocking condition has repeated for at least three consecutive goal turns, counting the original/user-triggered turn and any automatic continuations, and the agent cannot make meaningful progress without user input or an external-state change.\n"
            "If the user resumes a goal that was previously marked `blocked`, treat the resumed run as a fresh blocked audit. If the same blocking condition then repeats for at least three consecutive resumed goal turns, set status to `blocked` again.\n"
            "Once the blocked threshold is satisfied, do not keep reporting that you are still blocked while leaving the goal active; set status to `blocked`.\n"
            "Do not use `blocked` merely because the work is hard, slow, uncertain, incomplete, or would benefit from clarification.\n"
            "Do not mark a goal complete merely because its budget is nearly exhausted or because you are stopping work.\n"
            "You cannot use this tool to pause, resume, budget-limit, or usage-limit a goal; those status changes are controlled by the user or system.\n"
            "When marking a budgeted goal achieved with status `complete`, report the final token usage from the tool result to the user."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["complete", "blocked"],
                    "description": "Required. Set to `complete` only when the objective is achieved and no required work remains. Set to `blocked` only after the same blocking condition has recurred for at least three consecutive goal turns and the agent is at an impasse. After a previously blocked goal is resumed, the resumed run starts a fresh blocked audit.",
                }
            },
            "required": ["status"],
            "additionalProperties": False,
        },
    }


class GetGoalHandler:
    def __init__(self, store: GoalStore | None = None) -> None:
        self.store = store or InMemoryGoalStore()
        self._store_provided = store is not None

    def tool_name(self) -> ToolName:
        return ToolName.plain(GET_GOAL_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_get_goal_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | Any:
        payload = _payload(invocation_or_payload)
        if payload.type != "function":
            raise FunctionCallError.respond_to_model("get_goal handler received unsupported payload")
        session = getattr(invocation_or_payload, "session", None)
        getter = getattr(session, "get_thread_goal", None)
        if callable(getter) and not self._store_provided:
            try:
                goal = getter()
            except Exception as err:
                raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
            if inspect.isawaitable(goal):
                return _await_goal_response(goal, include_completion_budget_report=False)
            goal = _checked_goal_result(goal)
        else:
            goal = _call_goal_store(self.store.get_thread_goal)
        return goal_response(goal, include_completion_budget_report=False)


class CreateGoalHandler:
    def __init__(self, store: GoalStore | None = None) -> None:
        self.store = store or InMemoryGoalStore()
        self._store_provided = store is not None

    def tool_name(self) -> ToolName:
        return ToolName.plain(CREATE_GOAL_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_create_goal_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | Any:
        payload = _payload(invocation_or_payload)
        if payload.type != "function" or payload.arguments is None:
            raise FunctionCallError.respond_to_model("goal handler received unsupported payload")
        args = parse_create_goal_arguments(payload.arguments)
        request = CreateGoalRequest(args.objective, args.token_budget)
        session = getattr(invocation_or_payload, "session", None)
        creator = getattr(session, "create_thread_goal", None)
        if callable(creator) and not self._store_provided:
            try:
                goal = creator(getattr(invocation_or_payload, "turn", None), request)
            except Exception as err:
                message = _format_goal_error(err)
                if "already has a goal" in message:
                    raise FunctionCallError.respond_to_model(
                        "cannot create a new goal because this thread already has a goal; use update_goal only when the existing goal is complete"
                    ) from err
                raise FunctionCallError.respond_to_model(message) from err
            if inspect.isawaitable(goal):
                return _await_create_goal_response(goal)
            return goal_response(_checked_goal_result(goal), include_completion_budget_report=False)
        try:
            goal = self.store.create_thread_goal(request)
        except Exception as err:
            message = _format_goal_error(err)
            if "already has a goal" in message:
                raise FunctionCallError.respond_to_model(
                    "cannot create a new goal because this thread already has a goal; use update_goal only when the existing goal is complete"
                ) from err
            raise FunctionCallError.respond_to_model(message) from err
        return goal_response(goal, include_completion_budget_report=False)


class UpdateGoalHandler:
    def __init__(self, store: GoalStore | None = None) -> None:
        self.store = store or InMemoryGoalStore()
        self._store_provided = store is not None

    def tool_name(self) -> ToolName:
        return ToolName.plain(UPDATE_GOAL_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_update_goal_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | Any:
        payload = _payload(invocation_or_payload)
        if payload.type != "function" or payload.arguments is None:
            raise FunctionCallError.respond_to_model("update_goal handler received unsupported payload")
        args = parse_update_goal_arguments(payload.arguments)
        if args.status not in (ThreadGoalStatus.COMPLETE, ThreadGoalStatus.BLOCKED):
            raise FunctionCallError.respond_to_model(UPDATE_GOAL_STATUS_ERROR)
        request = SetGoalRequest(status=args.status)
        session = getattr(invocation_or_payload, "session", None)
        if not self._store_provided and callable(getattr(session, "set_thread_goal", None)):
            return _handle_update_goal_with_session(invocation_or_payload, session, request, args.status)
        try:
            self.store.goal_runtime_tool_completed_goal()
            goal = self.store.set_thread_goal(request)
        except Exception as err:
            raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
        return goal_response(goal, include_completion_budget_report=args.status is ThreadGoalStatus.COMPLETE)


def parse_create_goal_arguments(arguments: str) -> CreateGoalArgs:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        return CreateGoalArgs.from_mapping(json.loads(arguments))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(f"failed to parse function arguments: {err}") from err


def parse_update_goal_arguments(arguments: str) -> UpdateGoalArgs:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        return UpdateGoalArgs.from_mapping(json.loads(arguments))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(f"failed to parse function arguments: {err}") from err


def goal_response(goal: ThreadGoal | None, *, include_completion_budget_report: bool) -> FunctionToolOutput:
    return GoalToolResponse.new(goal, include_completion_budget_report=include_completion_budget_report).to_output()


async def _await_goal_response(response: Any, *, include_completion_budget_report: bool) -> FunctionToolOutput:
    try:
        goal = await response
    except Exception as err:
        raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
    return goal_response(_checked_goal_result(goal), include_completion_budget_report=include_completion_budget_report)


async def _await_create_goal_response(response: Any) -> FunctionToolOutput:
    try:
        goal = await response
    except Exception as err:
        message = _format_goal_error(err)
        if "already has a goal" in message:
            raise FunctionCallError.respond_to_model(
                "cannot create a new goal because this thread already has a goal; use update_goal only when the existing goal is complete"
            ) from err
        raise FunctionCallError.respond_to_model(message) from err
    return goal_response(_checked_goal_result(goal), include_completion_budget_report=False)


def _handle_update_goal_with_session(
    invocation_or_payload: Any,
    session: Any,
    request: SetGoalRequest,
    status: ThreadGoalStatus,
) -> FunctionToolOutput | Any:
    apply = getattr(session, "goal_runtime_apply", None)
    if callable(apply):
        try:
            applied = apply({"type": "tool_completed_goal", "turn_context": getattr(invocation_or_payload, "turn", None)})
        except Exception as err:
            raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
        if inspect.isawaitable(applied):
            return _await_update_goal_with_session(applied, invocation_or_payload, session, request, status)
    setter = getattr(session, "set_thread_goal")
    try:
        goal = setter(getattr(invocation_or_payload, "turn", None), request)
    except Exception as err:
        raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
    if inspect.isawaitable(goal):
        return _await_goal_response(
            goal,
            include_completion_budget_report=status is ThreadGoalStatus.COMPLETE,
        )
    return goal_response(
        _checked_goal_result(goal),
        include_completion_budget_report=status is ThreadGoalStatus.COMPLETE,
    )


async def _await_update_goal_with_session(
    applied: Any,
    invocation_or_payload: Any,
    session: Any,
    request: SetGoalRequest,
    status: ThreadGoalStatus,
) -> FunctionToolOutput:
    try:
        await applied
        goal = session.set_thread_goal(getattr(invocation_or_payload, "turn", None), request)
        if inspect.isawaitable(goal):
            goal = await goal
    except Exception as err:
        raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
    return goal_response(
        _checked_goal_result(goal),
        include_completion_budget_report=status is ThreadGoalStatus.COMPLETE,
    )


def completion_budget_report(goal: ThreadGoal) -> str | None:
    if not isinstance(goal, ThreadGoal):
        raise TypeError("goal must be ThreadGoal")
    if goal.token_budget is None and goal.time_used_seconds <= 0:
        return None
    return COMPLETION_BUDGET_REPORT_MESSAGE


def _payload(invocation_or_payload: Any) -> ToolPayload:
    payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    return payload


def _call_goal_store(func: Any) -> ThreadGoal | None:
    try:
        result = func()
    except Exception as err:
        raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
    return _checked_goal_result(result)


def _checked_goal_result(result: Any) -> ThreadGoal | None:
    if result is not None and not isinstance(result, ThreadGoal):
        raise TypeError("goal store returned a non-ThreadGoal value")
    return result


def _format_goal_error(err: BaseException) -> str:
    messages: list[str] = []
    current: BaseException | None = err
    while current is not None:
        messages.append(str(current))
        current = current.__cause__ or current.__context__
    return ": ".join(message for message in messages if message)


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_i64(value: dict[str, JsonValue], key: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    return _i64(raw, key)


def _i64(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < I64_MIN or value > I64_MAX:
        raise ValueError(f"{field_name} is outside i64 range")
    return value


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "COMPLETION_BUDGET_REPORT_MESSAGE",
    "CREATE_GOAL_TOOL_NAME",
    "GET_GOAL_TOOL_NAME",
    "UPDATE_GOAL_STATUS_ERROR",
    "UPDATE_GOAL_TOOL_NAME",
    "CreateGoalArgs",
    "CreateGoalHandler",
    "CreateGoalRequest",
    "GetGoalHandler",
    "GoalStore",
    "GoalToolResponse",
    "InMemoryGoalStore",
    "SetGoalRequest",
    "UpdateGoalArgs",
    "UpdateGoalHandler",
    "completion_budget_report",
    "create_create_goal_tool",
    "create_get_goal_tool",
    "create_update_goal_tool",
    "goal_response",
    "parse_create_goal_arguments",
    "parse_update_goal_arguments",
]
