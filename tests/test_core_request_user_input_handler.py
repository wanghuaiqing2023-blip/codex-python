import json
import unittest

from pycodex.core import (
    FunctionCallError,
    ToolPayload,
)
from pycodex.core.tools.handlers.request_user_input import (
    REQUEST_USER_INPUT_TOOL_NAME,
    RequestUserInputHandler,
    create_request_user_input_tool,
    normalize_request_user_input_args,
    parse_request_user_input_arguments,
    request_user_input_available_modes,
    request_user_input_tool_description,
    request_user_input_unavailable_message,
)
from pycodex.protocol import (
    ModeKind,
    RequestUserInputAnswer,
    RequestUserInputArgs,
    RequestUserInputQuestion,
    RequestUserInputQuestionOption,
    RequestUserInputResponse,
    SearchToolCallParams,
    ToolName,
)


def request_args_json() -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "id": "pick_one",
                    "header": "Hdr",
                    "question": "Pick one",
                    "options": [
                        {"label": "A", "description": "A"},
                        {"label": "B", "description": "B"},
                    ],
                }
            ]
        }
    )


class RequestUserInputHandlerTests(unittest.TestCase):
    def test_request_user_input_tool_includes_questions_schema(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_user_input_spec.rs::create_request_user_input_tool
        # Rust test: request_user_input_tool_includes_questions_schema
        spec = create_request_user_input_tool("Ask the user to choose.")

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], REQUEST_USER_INPUT_TOOL_NAME)
        self.assertEqual(spec["description"], "Ask the user to choose.")
        self.assertFalse(spec["strict"])
        self.assertIsNone(spec.get("defer_loading"))
        self.assertIsNone(spec.get("output_schema"))
        self.assertEqual(spec["parameters"]["required"], ["questions"])
        self.assertFalse(spec["parameters"]["additionalProperties"])
        questions = spec["parameters"]["properties"]["questions"]
        self.assertEqual(questions["type"], "array")
        self.assertEqual(
            questions["description"],
            "Questions to show the user. Prefer 1 and do not exceed 3",
        )
        question_schema = questions["items"]
        self.assertEqual(question_schema["type"], "object")
        self.assertEqual(
            question_schema["required"],
            ["id", "header", "question", "options"],
        )
        self.assertFalse(question_schema["additionalProperties"])
        self.assertEqual(
            question_schema["properties"]["id"],
            {
                "type": "string",
                "description": "Stable identifier for mapping answers (snake_case).",
            },
        )
        self.assertEqual(
            question_schema["properties"]["header"],
            {
                "type": "string",
                "description": "Short header label shown in the UI (12 or fewer chars).",
            },
        )
        self.assertEqual(
            question_schema["properties"]["question"],
            {
                "type": "string",
                "description": "Single-sentence prompt shown to the user.",
            },
        )
        options = question_schema["properties"]["options"]
        self.assertEqual(options["type"], "array")
        self.assertEqual(
            options["description"],
            (
                "Provide 2-3 mutually exclusive choices. Put the recommended option first and "
                'suffix its label with "(Recommended)". Do not include an "Other" option in this '
                'list; the client will add a free-form "Other" option automatically.'
            ),
        )
        self.assertEqual(options["items"]["type"], "object")
        self.assertEqual(options["items"]["required"], ["label", "description"])
        self.assertFalse(options["items"]["additionalProperties"])
        self.assertEqual(
            options["items"]["properties"],
            {
                "label": {
                    "type": "string",
                    "description": "User-facing label (1-5 words).",
                },
                "description": {
                    "type": "string",
                    "description": "One short sentence explaining impact/tradeoff if selected.",
                },
            },
        )

    def test_available_mode_helpers_match_rust_messages(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_user_input_spec.rs
        # Rust tests: request_user_input_unavailable_messages_respect_default_mode_feature_flag
        # and request_user_input_tool_description_mentions_available_modes
        self.assertEqual(request_user_input_available_modes(), (ModeKind.PLAN,))
        self.assertEqual(
            request_user_input_available_modes(default_mode_enabled=True),
            (ModeKind.DEFAULT, ModeKind.PLAN),
        )
        self.assertIsNone(
            request_user_input_unavailable_message(ModeKind.PLAN, request_user_input_available_modes())
        )
        self.assertEqual(
            request_user_input_unavailable_message(ModeKind.DEFAULT, request_user_input_available_modes()),
            "request_user_input is unavailable in Default mode",
        )
        self.assertIsNone(
            request_user_input_unavailable_message(
                ModeKind.DEFAULT,
                request_user_input_available_modes(default_mode_enabled=True),
            )
        )
        self.assertEqual(
            request_user_input_unavailable_message(ModeKind.EXECUTE, request_user_input_available_modes()),
            "request_user_input is unavailable in Execute mode",
        )
        self.assertEqual(
            request_user_input_unavailable_message(ModeKind.PAIR_PROGRAMMING, request_user_input_available_modes()),
            "request_user_input is unavailable in Pair Programming mode",
        )
        self.assertEqual(
            request_user_input_tool_description((ModeKind.PLAN,)),
            "Request user input for one to three short questions and wait for the response. This tool is only available in Plan mode.",
        )
        self.assertEqual(
            request_user_input_tool_description(request_user_input_available_modes(default_mode_enabled=True)),
            "Request user input for one to three short questions and wait for the response. This tool is only available in Default or Plan mode.",
        )
        with self.assertRaises(TypeError):
            request_user_input_available_modes(default_mode_enabled=1)

    def test_normalize_request_user_input_args_sets_other_and_requires_options(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_user_input_spec.rs::normalize_request_user_input_args
        # Rust contract: every question must have options and the client-provided "Other" option is enabled.
        args = parse_request_user_input_arguments(request_args_json())
        normalized = normalize_request_user_input_args(args)

        self.assertTrue(normalized.questions[0].is_other)

        with self.assertRaises(ValueError):
            normalize_request_user_input_args(
                RequestUserInputArgs(
                    (
                        RequestUserInputQuestion(
                            id="pick",
                            header="Hdr",
                            question="Pick",
                            options=(),
                        ),
                    )
                )
            )

    def test_handler_requests_input_and_serializes_response(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_user_input.rs
        # Rust contract: normalized args are sent to the client and the response is serialized as successful output.
        captured = {}

        def callback(call_id, args):
            captured["call_id"] = call_id
            captured["args"] = args
            return RequestUserInputResponse(
                {"pick_one": RequestUserInputAnswer(("A",))}
            )

        handler = RequestUserInputHandler(request_callback=callback)
        output = handler.handle(
            ToolPayload.function(request_args_json()),
            call_id="call-1",
            mode=ModeKind.PLAN,
        )

        self.assertEqual(handler.tool_name(), ToolName.plain("request_user_input"))
        self.assertFalse(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
        self.assertTrue(handler.matches_kind(ToolPayload.tool_search(SearchToolCallParams("input"))))
        self.assertEqual(captured["call_id"], "call-1")
        self.assertTrue(captured["args"].questions[0].is_other)
        self.assertEqual(
            json.loads(output.into_text()),
            {"answers": {"pick_one": {"answers": ["A"]}}},
        )

    def test_handler_rejects_unavailable_modes_subagents_and_bad_payloads(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_user_input.rs
        # Rust contract: unavailable modes, non-root threads, bad payloads, bad JSON, empty options, and cancellation are model-visible errors.
        handler = RequestUserInputHandler()

        with self.assertRaises(FunctionCallError) as unavailable:
            handler.handle(ToolPayload.function(request_args_json()), mode=ModeKind.DEFAULT)
        self.assertEqual(unavailable.exception.kind, "respond_to_model")

        with self.assertRaises(FunctionCallError):
            handler.handle(
                ToolPayload.function(request_args_json()),
                mode=ModeKind.PLAN,
                is_root_thread=False,
            )
        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.custom("raw"), mode=ModeKind.PLAN)
        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.function("{not json"), mode=ModeKind.PLAN)
        with self.assertRaisesRegex(FunctionCallError, "requires non-empty options") as bad_options:
            handler.handle(
                ToolPayload.function(
                    json.dumps(
                        {
                            "questions": [
                                {
                                    "id": "pick",
                                    "header": "Hdr",
                                    "question": "Pick",
                                    "options": [],
                                }
                            ]
                        }
                    )
                ),
                mode=ModeKind.PLAN,
            )
        self.assertTrue(bad_options.exception.is_model_response)
        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.function(request_args_json()), mode=ModeKind.PLAN)
        with self.assertRaises(TypeError):
            RequestUserInputHandler(available_modes=("plan",))
        with self.assertRaises(TypeError):
            handler.matches_kind(object())
        with self.assertRaises(TypeError):
            create_request_user_input_tool(1)
        with self.assertRaises(TypeError):
            parse_request_user_input_arguments({})


if __name__ == "__main__":
    unittest.main()
