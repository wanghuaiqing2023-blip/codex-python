import json
import unittest

from pycodex.core import (
    PLAN_UPDATED_MESSAGE,
    UPDATE_PLAN_TOOL_NAME,
    FunctionCallError,
    PlanHandler,
    PlanToolOutput,
    ToolPayload,
    create_update_plan_tool,
    parse_update_plan_arguments,
)
from pycodex.protocol import PlanItemArg, SearchToolCallParams, StepStatus, ToolName, UpdatePlanArgs


class PlanHandlerTests(unittest.TestCase):
    def test_create_update_plan_tool_matches_upstream_shape(self) -> None:
        spec = create_update_plan_tool()

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], UPDATE_PLAN_TOOL_NAME)
        self.assertFalse(spec["strict"])
        self.assertEqual(spec["parameters"]["required"], ["plan"])
        self.assertFalse(spec["parameters"]["additionalProperties"])
        self.assertEqual(
            spec["parameters"]["properties"]["plan"]["items"]["required"],
            ["step", "status"],
        )

    def test_plan_tool_output_matches_rust_visible_output(self) -> None:
        output = PlanToolOutput()
        payload = ToolPayload.function("{}")
        response = output.to_response_item("call-plan", payload)

        self.assertEqual(output.log_preview(), PLAN_UPDATED_MESSAGE)
        self.assertTrue(output.success_for_logging())
        self.assertEqual(output.code_mode_result(payload), {})
        self.assertEqual(response.call_id, "call-plan")
        self.assertEqual(response.output.to_json(), PLAN_UPDATED_MESSAGE)
        self.assertTrue(response.output.success)

    def test_parse_update_plan_arguments(self) -> None:
        args = parse_update_plan_arguments(
            json.dumps(
                {
                    "explanation": "Moving carefully",
                    "plan": [{"step": "Read", "status": "completed"}],
                }
            )
        )

        self.assertEqual(
            args,
            UpdatePlanArgs(
                explanation="Moving carefully",
                plan=(PlanItemArg("Read", StepStatus.COMPLETED),),
            ),
        )

    def test_plan_handler_emits_callback_and_output(self) -> None:
        captured = []
        handler = PlanHandler(captured.append)
        payload = ToolPayload.function(
            json.dumps({"plan": [{"step": "Patch", "status": "in_progress"}]})
        )

        output = handler.handle(payload)

        self.assertEqual(handler.tool_name(), ToolName.plain("update_plan"))
        self.assertFalse(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.matches_kind(payload))
        self.assertTrue(handler.matches_kind(ToolPayload.tool_search(SearchToolCallParams("plan"))))
        self.assertIsInstance(output, PlanToolOutput)
        self.assertEqual(captured[0].plan[0].status, StepStatus.IN_PROGRESS)

    def test_plan_handler_rejects_plan_mode_and_bad_payloads(self) -> None:
        handler = PlanHandler()

        with self.assertRaises(FunctionCallError) as plan_mode:
            handler.handle(ToolPayload.function('{"plan":[]}'), collaboration_mode="plan")
        self.assertEqual(plan_mode.exception.kind, "respond_to_model")

        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.custom("raw"))
        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.function("{not json"))
        with self.assertRaises(TypeError):
            handler.matches_kind(object())
        with self.assertRaises(TypeError):
            PlanHandler(on_plan_update=object())
        with self.assertRaises(TypeError):
            parse_update_plan_arguments({})


if __name__ == "__main__":
    unittest.main()
