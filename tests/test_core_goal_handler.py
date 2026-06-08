import json
import asyncio
import unittest
from dataclasses import replace
from types import SimpleNamespace

from pycodex.core.tools.handlers.goal import (
    COMPLETION_BUDGET_REPORT_MESSAGE,
    UPDATE_GOAL_STATUS_ERROR,
    CreateGoalHandler,
    GetGoalHandler,
    GoalToolResponse,
    InMemoryGoalStore,
    UpdateGoalHandler,
    completion_budget_report,
    create_create_goal_tool,
    create_get_goal_tool,
    create_update_goal_tool,
    parse_create_goal_arguments,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import SearchToolCallParams, ThreadGoal, ThreadGoalStatus, ThreadId


def goal(
    *,
    status: ThreadGoalStatus = ThreadGoalStatus.ACTIVE,
    token_budget: int | None = None,
    tokens_used: int = 0,
    time_used_seconds: int = 0,
) -> ThreadGoal:
    return ThreadGoal(
        thread_id=ThreadId.new(),
        objective="keep porting",
        status=status,
        tokens_used=tokens_used,
        time_used_seconds=time_used_seconds,
        created_at=1,
        updated_at=2,
        token_budget=token_budget,
    )


class CoreGoalHandlerTests(unittest.TestCase):
    def test_goal_tool_specs_match_rust_schema_contracts(self) -> None:
        # Rust parity: codex-core::tools::handlers::goal_spec::{create_get_goal_tool,
        # create_create_goal_tool, create_update_goal_tool}.
        self.assertEqual(
            create_get_goal_tool(),
            {
                "type": "function",
                "name": "get_goal",
                "description": "Get the current goal for this thread, including status, budgets, token and elapsed-time usage, and remaining token budget.",
                "strict": False,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        )
        self.assertEqual(
            create_create_goal_tool(),
            {
                "type": "function",
                "name": "create_goal",
                "description": (
                    "Create a goal only when explicitly requested by the user or system/developer instructions; do not infer goals from ordinary tasks.\n"
                    "Set token_budget only when an explicit token budget is requested. Fails if a goal exists; use update_goal only for status."
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
            },
        )
        self.assertEqual(
            create_update_goal_tool(),
            {
                "type": "function",
                "name": "update_goal",
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
            },
        )

    def test_update_goal_tool_exposes_complete_and_blocked_statuses(self) -> None:
        # Rust unit test: goal_spec.rs::tests::update_goal_tool_exposes_complete_and_blocked_statuses.
        status_schema = create_update_goal_tool()["parameters"]["properties"]["status"]
        self.assertEqual(status_schema["enum"], ["complete", "blocked"])

    def test_goal_response_reports_remaining_tokens_and_completion_budget(self) -> None:
        current = goal(
            status=ThreadGoalStatus.COMPLETE,
            token_budget=10_000,
            tokens_used=3_250,
            time_used_seconds=75,
        )
        response = GoalToolResponse.new(current, include_completion_budget_report=True)
        self.assertEqual(response.remaining_tokens, 6_750)
        self.assertEqual(response.completion_budget_report, COMPLETION_BUDGET_REPORT_MESSAGE)
        payload = response.to_mapping()
        self.assertEqual(payload["goal"]["tokenBudget"], 10_000)
        self.assertEqual(payload["remainingTokens"], 6_750)

    def test_goal_response_omits_completion_budget_report_until_goal_is_complete(self) -> None:
        current = goal(
            status=ThreadGoalStatus.ACTIVE,
            token_budget=10_000,
            tokens_used=3_250,
            time_used_seconds=75,
        )

        response = GoalToolResponse.new(current, include_completion_budget_report=True)

        self.assertEqual(response.remaining_tokens, 6_750)
        self.assertIsNone(response.completion_budget_report)

    def test_unbudgeted_goal_omits_completion_budget_report_without_elapsed_time(self) -> None:
        self.assertIsNone(
            completion_budget_report(goal(status=ThreadGoalStatus.COMPLETE, tokens_used=120))
        )

    def test_create_get_and_update_goal_handlers_share_store(self) -> None:
        store = InMemoryGoalStore(ThreadId.new())
        self.assertFalse(CreateGoalHandler(store).supports_parallel_tool_calls())
        self.assertFalse(GetGoalHandler(store).supports_parallel_tool_calls())
        self.assertFalse(UpdateGoalHandler(store).supports_parallel_tool_calls())
        self.assertTrue(CreateGoalHandler(store).matches_kind(ToolPayload.tool_search(SearchToolCallParams("goal"))))
        self.assertTrue(GetGoalHandler(store).matches_kind(ToolPayload.tool_search(SearchToolCallParams("goal"))))
        self.assertTrue(UpdateGoalHandler(store).matches_kind(ToolPayload.tool_search(SearchToolCallParams("goal"))))

        created = CreateGoalHandler(store).handle(
            ToolPayload.function(json.dumps({"objective": "port Codex", "token_budget": 5000}))
        )
        created_payload = json.loads(created.into_text())
        self.assertEqual(created_payload["goal"]["objective"], "port Codex")
        self.assertEqual(created_payload["remainingTokens"], 5000)

        fetched = GetGoalHandler(store).handle(ToolPayload.function("{}"))
        self.assertEqual(json.loads(fetched.into_text())["goal"]["objective"], "port Codex")

        store.goal = replace(store.goal, tokens_used=1250, time_used_seconds=5)
        updated = UpdateGoalHandler(store).handle(ToolPayload.function(json.dumps({"status": "complete"})))
        updated_payload = json.loads(updated.into_text())
        self.assertEqual(updated_payload["goal"]["status"], "complete")
        self.assertEqual(updated_payload["remainingTokens"], 3750)
        self.assertEqual(updated_payload["completionBudgetReport"], COMPLETION_BUDGET_REPORT_MESSAGE)
        self.assertEqual(store.tool_completed_goal_count, 1)

    def test_handlers_use_rust_style_async_session_entrypoints(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/goal/{create_goal,get_goal,update_goal}.rs
        # Rust contract: handlers call session goal APIs with the turn context and apply ToolCompletedGoal before update.
        calls = []
        thread_id = ThreadId.new()

        class Session:
            def __init__(self) -> None:
                self.goal = None

            async def create_thread_goal(self, turn, request):
                calls.append(("create", turn, request.objective, request.token_budget))
                self.goal = ThreadGoal(
                    thread_id=thread_id,
                    objective=request.objective,
                    status=ThreadGoalStatus.ACTIVE,
                    tokens_used=0,
                    time_used_seconds=0,
                    created_at=1,
                    updated_at=1,
                    token_budget=request.token_budget,
                )
                return self.goal

            async def get_thread_goal(self):
                calls.append(("get",))
                return self.goal

            async def goal_runtime_apply(self, event):
                calls.append(("runtime", event))
                self.goal = replace(self.goal, tokens_used=750, time_used_seconds=12)

            async def set_thread_goal(self, turn, request):
                calls.append(("set", turn, request.status))
                self.goal = replace(self.goal, status=request.status, updated_at=2)
                return self.goal

        session = Session()
        turn = SimpleNamespace(name="turn")
        create_invocation = SimpleNamespace(
            session=session,
            turn=turn,
            payload=ToolPayload.function(json.dumps({"objective": "port Codex", "token_budget": 1000})),
        )
        created = asyncio.run(CreateGoalHandler().handle(create_invocation))
        self.assertEqual(json.loads(created.into_text())["goal"]["objective"], "port Codex")

        fetched = asyncio.run(
            GetGoalHandler().handle(SimpleNamespace(session=session, payload=ToolPayload.function("{}")))
        )
        self.assertEqual(json.loads(fetched.into_text())["remainingTokens"], 1000)

        updated = asyncio.run(
            UpdateGoalHandler().handle(
                SimpleNamespace(
                    session=session,
                    turn=turn,
                    payload=ToolPayload.function(json.dumps({"status": "complete"})),
                )
            )
        )
        updated_payload = json.loads(updated.into_text())
        self.assertEqual(updated_payload["goal"]["status"], "complete")
        self.assertEqual(updated_payload["remainingTokens"], 250)
        self.assertEqual(updated_payload["completionBudgetReport"], COMPLETION_BUDGET_REPORT_MESSAGE)
        self.assertEqual(calls[0], ("create", turn, "port Codex", 1000))
        self.assertEqual(calls[1], ("get",))
        self.assertEqual(calls[2][0], "runtime")
        self.assertEqual(calls[2][1], {"type": "tool_completed_goal", "turn_context": turn})
        self.assertEqual(calls[3], ("set", turn, ThreadGoalStatus.COMPLETE))

    def test_create_goal_rejects_existing_goal_with_rust_message(self) -> None:
        store = InMemoryGoalStore(ThreadId.new())
        handler = CreateGoalHandler(store)
        handler.handle(ToolPayload.function(json.dumps({"objective": "first"})))
        with self.assertRaisesRegex(FunctionCallError, "already has a goal"):
            handler.handle(ToolPayload.function(json.dumps({"objective": "second"})))

    def test_update_goal_rejects_non_terminal_statuses(self) -> None:
        store = InMemoryGoalStore(ThreadId.new())
        CreateGoalHandler(store).handle(ToolPayload.function(json.dumps({"objective": "x"})))
        with self.assertRaisesRegex(FunctionCallError, UPDATE_GOAL_STATUS_ERROR):
            UpdateGoalHandler(store).handle(ToolPayload.function(json.dumps({"status": "paused"})))

    def test_parse_create_goal_arguments_keeps_i64_boundaries(self) -> None:
        args = parse_create_goal_arguments(json.dumps({"objective": "x", "token_budget": 1}))
        self.assertEqual(args.token_budget, 1)
        with self.assertRaisesRegex(FunctionCallError, "token_budget must be positive"):
            parse_create_goal_arguments(json.dumps({"objective": "x", "token_budget": 0}))
        with self.assertRaisesRegex(FunctionCallError, "token_budget must be an integer"):
            parse_create_goal_arguments(json.dumps({"objective": "x", "token_budget": True}))

    def test_handlers_reject_unsupported_payloads(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            GetGoalHandler().handle(ToolPayload.custom("raw"))
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            CreateGoalHandler().handle(ToolPayload.custom("raw"))
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            UpdateGoalHandler().handle(ToolPayload.custom("raw"))


if __name__ == "__main__":
    unittest.main()
