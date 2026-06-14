from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.client_common import REVIEW_PROMPT
from pycodex.core.review_prompts import resolve_review_request
from pycodex.core.tasks.review import (
    parse_review_output_event,
    process_review_events,
    review_exit_messages,
)
from pycodex.exec.local_runtime import (
    LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES,
    LocalHttpModelInfo,
    LocalHttpProvider,
    LocalHttpReviewModelInfo,
    final_text_from_local_http_exec_result,
    local_http_model_disabled_tool_names,
    local_http_review_rollout_input_items,
    local_http_review_user_turn_plan,
    run_exec_review_http_sampling,
)
from pycodex.exec.run import ExecRunPlan, InitialOperation
from pycodex.exec.session import ExecSessionConfig
from pycodex.protocol import (
    ContentItem,
    Event,
    EventMsg,
    ResponseItem,
    ReviewCodeLocation,
    ReviewFinding,
    ReviewLineRange,
    ReviewOutputEvent,
    ReviewRequest,
    ReviewTarget,
    TurnItem,
)


class FakePayloadResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakePayloadResponse":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None


class ReviewSuiteParityTests(unittest.IsolatedAsyncioTestCase):
    def _config(self, cwd: Path | None = None, model: str | None = None) -> ExecSessionConfig:
        return ExecSessionConfig(model=model, model_provider_id=None, cwd=cwd or Path("C:/work/project"))

    def _plan(self, target: ReviewTarget | None = None) -> ExecRunPlan:
        request = ReviewRequest(target or ReviewTarget.custom("Please review my changes"))
        return ExecRunPlan(InitialOperation.review(request), "review")

    async def _run_review(self, assistant_text: str, *, model: str = "gpt-review") -> tuple[object, dict[str, object]]:
        captured: dict[str, object] = {}

        def opener(request: object) -> FakePayloadResponse:
            data = getattr(request, "data", b"{}") or b"{}"
            captured["body"] = json.loads(data.decode("utf-8"))
            return FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": assistant_text}],
                        }
                    ]
                }
            )

        result = await run_exec_review_http_sampling(
            self._config(),
            self._plan(),
            ModelClient(session_id="session", thread_id="review-thread", installation_id="install"),
            LocalHttpProvider(base_url="https://api.example.test/v1", auth="sk-test"),
            LocalHttpModelInfo(model),
            auth="sk-test",
            opener=opener,
        )
        return result, captured

    def test_review_op_emits_lifecycle_and_review_output(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_op_emits_lifecycle_and_review_output
        review_output = ReviewOutputEvent(
            findings=(
                ReviewFinding(
                    title="Prefer Stylize helpers",
                    body="Use .dim()/.bold() chaining instead of manual Style where possible.",
                    confidence_score=0.9,
                    priority=1,
                    code_location=ReviewCodeLocation(Path("/tmp/file.rs"), ReviewLineRange(10, 20)),
                ),
            ),
            overall_correctness="good",
            overall_explanation="All good with some improvements suggested.",
            overall_confidence_score=0.8,
        )

        messages = review_exit_messages(review_output)
        self.assertIn("full review output from reviewer model", messages.user_message)
        self.assertIn("Prefer Stylize helpers", messages.user_message)
        self.assertIn("file.rs:10-20", messages.user_message)
        self.assertIn("All good with some improvements suggested.", messages.assistant_message)
        self.assertNotIn("<user_action>", messages.assistant_message)

    async def test_review_op_with_plain_text_emits_review_fallback(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_op_with_plain_text_emits_review_fallback
        result, _captured = await self._run_review("just plain text")

        session_events = tuple(getattr(result, "session_events", ()))
        self.assertEqual(
            [event.type for event in session_events],
            ["entered_review_mode", "task_started", "exited_review_mode", "task_complete"],
        )
        self.assertEqual(session_events[2].payload.review_output, ReviewOutputEvent(overall_explanation="just plain text"))
        self.assertEqual(final_text_from_local_http_exec_result(result), "just plain text")

    async def test_review_filters_agent_message_related_events(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_filters_agent_message_related_events
        class Receiver:
            def __init__(self) -> None:
                self.events = [
                    Event("1", EventMsg.with_payload("agent_message_content_delta", "Hi")),
                    Event("2", EventMsg.with_payload("item_completed", SimpleNamespace(item=SimpleNamespace(type="AgentMessage")))),
                    Event("3", EventMsg.with_payload("agent_message", "Hi there")),
                    Event("4", EventMsg.with_payload("task_complete", SimpleNamespace(last_agent_message="Hi there"))),
                ]

            async def next_event(self) -> Event | None:
                return self.events.pop(0) if self.events else None

        sent: list[EventMsg] = []

        class Session:
            async def send_event(self, _ctx: object, msg: EventMsg) -> None:
                sent.append(msg)

        output = await process_review_events(Session(), object(), Receiver())

        self.assertEqual(output, ReviewOutputEvent(overall_explanation="Hi there"))
        self.assertEqual(sent, [])

    async def test_review_does_not_emit_agent_message_on_structured_output(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_does_not_emit_agent_message_on_structured_output
        result, _captured = await self._run_review(
            json.dumps(
                {
                    "findings": [
                        {
                            "title": "Example",
                            "body": "Structured review output.",
                            "confidence_score": 0.5,
                            "priority": 1,
                            "code_location": {
                                "absolute_file_path": "/tmp/file.rs",
                                "line_range": {"start": 1, "end": 2},
                            },
                        }
                    ],
                    "overall_correctness": "ok",
                    "overall_explanation": "ok",
                    "overall_confidence_score": 0.5,
                }
            )
        )

        agent_messages = [item for item in result.response_items if getattr(item, "type", None) == "message"]
        self.assertEqual(len(agent_messages), 1)
        self.assertTrue(final_text_from_local_http_exec_result(result).startswith("ok"))
        self.assertIn("Example", final_text_from_local_http_exec_result(result))

    async def test_review_uses_custom_review_model_from_config(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_uses_custom_review_model_from_config
        _result, captured = await self._run_review("", model="gpt-5.4")

        self.assertEqual(captured["body"]["model"], "gpt-5.4")

    async def test_review_uses_session_model_when_review_model_unset(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_uses_session_model_when_review_model_unset
        _result, captured = await self._run_review("", model="gpt-4.1")

        self.assertEqual(captured["body"]["model"], "gpt-4.1")

    def test_review_input_isolated_from_parent_history(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_input_isolated_from_parent_history
        plan = local_http_review_user_turn_plan(self._config(), self._plan(ReviewTarget.custom("Please review only this")))

        self.assertEqual(plan.initial_operation.kind, "user_turn")
        self.assertEqual(plan.initial_operation.items[0].text, "Please review only this")
        self.assertEqual(plan.prompt_summary, "Please review only this")

    async def test_review_history_surfaces_in_parent_session(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_history_surfaces_in_parent_session
        result, _captured = await self._run_review("review assistant output")

        rollout_items = local_http_review_rollout_input_items(result)
        rollout_text = "\n".join(item.text for item in rollout_items)
        self.assertIn("User initiated a review task.", rollout_text)
        self.assertIn("review assistant output", rollout_text)

    def test_review_uses_overridden_cwd_for_base_branch_merge_base(self) -> None:
        # Rust source: core/tests/suite/review.rs::review_uses_overridden_cwd_for_base_branch_merge_base
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            def merge_base(cwd: Path, branch: str) -> str:
                self.assertEqual(cwd, repo)
                self.assertEqual(branch, "main")
                return "abc123mergebase"

            resolved = resolve_review_request(
                ReviewRequest(ReviewTarget.base_branch("main")),
                repo,
                merge_base_with_head=merge_base,
            )

        self.assertIn("abc123mergebase", resolved.prompt)
        self.assertIn("main", resolved.user_facing_hint)

    async def test_review_request_uses_review_prompt_and_disables_review_tools(self) -> None:
        # Rust source: core/tests/suite/review.rs shared assertions for review instructions/tool filtering.
        _result, captured = await self._run_review("ok")
        review_model = LocalHttpReviewModelInfo(LocalHttpModelInfo("gpt-review"))

        self.assertEqual(captured["body"]["instructions"], REVIEW_PROMPT)
        self.assertEqual(local_http_model_disabled_tool_names(review_model), LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES)
        self.assertIn("view_image", LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES)
        self.assertIn("web_search", LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES)

    def test_parse_review_output_event_accepts_embedded_json(self) -> None:
        # Rust source: core/tests/suite/review.rs structured review JSON parsing path.
        parsed = parse_review_output_event(
            'prefix {"findings":[],"overall_correctness":"ok","overall_explanation":"embedded ok","overall_confidence_score":0.7} suffix'
        )

        self.assertEqual(
            parsed,
            ReviewOutputEvent(overall_correctness="ok", overall_explanation="embedded ok", overall_confidence_score=0.7),
        )


if __name__ == "__main__":
    unittest.main()
