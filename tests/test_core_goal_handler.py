import json
import unittest
from dataclasses import replace

from pycodex.core.tools.handlers.goal import (
    COMPLETION_BUDGET_REPORT_MESSAGE,
    UPDATE_GOAL_STATUS_ERROR,
    CreateGoalHandler,
    GetGoalHandler,
    GoalToolResponse,
    InMemoryGoalStore,
    UpdateGoalHandler,
    completion_budget_report,
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
    def test_update_goal_tool_exposes_complete_and_blocked_statuses(self) -> None:
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
