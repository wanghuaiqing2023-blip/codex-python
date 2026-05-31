import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

from pycodex.core import (
    CompletedResponseItemRecordingPlan,
    FinalizedTurnItemFacts,
    GENERATED_IMAGE_ARTIFACTS_DIR,
    HandleOutputCtx,
    OutputItemResult,
    SamplingMailboxPreemptionPlan,
    SamplingOutputItemAddedPlan,
    SamplingOutputItemAddedApplyPlan,
    SamplingOutputTextDeltaPlan,
    SamplingOutputTextDeltaApplyPlan,
    SamplingAssistantTextFlushPlan,
    SamplingAssistantTextFlushAllPlan,
    SamplingStreamedAssistantTextDeltaPlan,
    SamplingOutputItemDoneTransitionPlan,
    SamplingOutputItemDoneApplyPlan,
    SamplingMetadataEventPlan,
    SamplingMetadataEventApplyPlan,
    SamplingCompletedEventPlan,
    SamplingCompletedEventApplyPlan,
    SamplingStreamEventDispatchPlan,
    SamplingStreamEventApplyPlan,
    SamplingPlanModeAssistantDonePlan,
    SamplingPlanSegmentAction,
    SamplingPlanSegmentsPlan,
    SamplingProposedPlanCompletionPlan,
    SamplingPendingAgentMessageStartPlan,
    SamplingPlanModeAgentMessageEmitPlan,
    SamplingPlanModeTurnItemEmitPlan,
    SamplingInFlightToolResultPlan,
    SamplingOutputState,
    SamplingReasoningDeltaPlan,
    SamplingReasoningDeltaApplyPlan,
    SamplingToolCallInputDeltaPlan,
    SamplingToolCallInputDeltaApplyPlan,
    ToolCallErrorHandlingPlan,
    ToolCallLifecyclePlan,
    UnexpectedToolOutputPlan,
    agent_message_text,
    apply_turn_item_contributors,
    completed_item_defers_mailbox_delivery_to_next_turn,
    completed_response_item_recording_plan,
    finalize_non_tool_response_item,
    finalized_turn_item_facts,
    function_call_error_output_result,
    function_call_error_to_response_input,
    get_last_assistant_message_from_turn,
    handle_non_tool_response_item,
    handle_non_tool_response_item_with_contributors,
    handle_output_item_done,
    image_generation_artifact_path,
    last_assistant_message_from_item,
    memory_citation_from_response_item,
    realtime_text_for_event,
    record_completed_response_item_with_finalized_facts,
    response_input_to_response_item,
    response_item_may_include_external_context,
    sampling_item_preempts_for_mailbox_mail,
    sampling_mailbox_preemption_plan,
    sampling_output_item_added_plan,
    sampling_output_item_added_apply_plan,
    sampling_output_item_done_transition_plan,
    sampling_output_item_done_apply_plan,
    sampling_output_text_delta_plan,
    sampling_output_text_delta_apply_plan,
    sampling_output_state_after_result,
    sampling_assistant_text_flush_plan,
    sampling_assistant_text_flush_all_plan,
    sampling_streamed_assistant_text_delta_plan,
    sampling_completed_event_plan,
    sampling_completed_event_apply_plan,
    sampling_stream_event_dispatch_plan,
    sampling_metadata_event_plan,
    sampling_metadata_event_apply_plan,
    sampling_stream_event_apply_plan,
    sampling_plan_mode_assistant_done_plan,
    sampling_plan_segments_plan,
    sampling_proposed_plan_completion_plan,
    sampling_pending_agent_message_start_plan,
    sampling_plan_mode_agent_message_emit_plan,
    sampling_plan_mode_turn_item_emit_plan,
    sampling_in_flight_tool_result_plan,
    sampling_reasoning_content_delta_plan,
    sampling_reasoning_delta_apply_plan,
    sampling_reasoning_summary_delta_plan,
    sampling_reasoning_summary_part_added_plan,
    sampling_tool_call_input_delta_plan,
    sampling_tool_call_input_delta_apply_plan,
    save_image_generation_result,
    strip_hidden_assistant_markup,
    tool_call_error_handling_plan,
    tool_call_lifecycle_plan,
    unexpected_tool_output_plan,
)
from pycodex.core.tool_router import ToolRouter
from pycodex.core.function_tool import FunctionCallError
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageItem,
    ContentItem,
    MessagePhase,
    ResponseInputItem,
    ResponseItem,
    TurnItem,
)
from pycodex.protocol import MemoryCitation


def assistant_output_text(text: str, phase: MessagePhase | None = None) -> ResponseItem:
    return ResponseItem.message(
        "assistant",
        (ContentItem.output_text(text),),
        id="msg-1",
        phase=phase,
    )


class ResponseSequence(Sequence):
    def __init__(self, items):
        self._items = tuple(items)

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return len(self._items)


class CoreStreamEventsUtilsTests(unittest.TestCase):
    def test_external_context_pollution_items_include_web_search_and_tool_search(self) -> None:
        polluting_items = (
            ResponseItem.web_search_call(status="completed"),
            ResponseItem.tool_search_call({"query": "calendar"}, call_id="search-1", execution="client"),
            ResponseItem.from_response_input_item(
                ResponseInputItem.tool_search_output("search-1", "completed", "client", ())
            ),
        )

        self.assertTrue(all(response_item_may_include_external_context(item) for item in polluting_items))

    def test_external_context_pollution_items_exclude_local_tool_calls(self) -> None:
        non_polluting_items = (
            ResponseItem.function_call("shell", "{}", "call-1"),
            ResponseItem.from_response_input_item(ResponseInputItem.function_call_output("call-1", "ok")),
            ResponseItem.custom_tool_call("apply_patch", "*** Begin Patch\n*** End Patch\n", "custom-1"),
            ResponseItem.from_response_input_item(
                ResponseInputItem.custom_tool_call_output("custom-1", "ok", name="apply_patch")
            ),
            assistant_output_text("plain assistant text"),
        )

        self.assertFalse(any(response_item_may_include_external_context(item) for item in non_polluting_items))

    def test_last_assistant_message_from_item_strips_citations_and_plan_blocks(self) -> None:
        item = assistant_output_text(
            "before<oai-mem-citation>doc1</oai-mem-citation>\n"
            "<proposed_plan>\n- x\n</proposed_plan>\n"
            "after"
        )

        self.assertEqual(last_assistant_message_from_item(item, plan_mode=True), "before\nafter")

    def test_memory_citation_from_response_item_parses_rust_citation_markup(self) -> None:
        item = assistant_output_text(
            "hello<oai-mem-citation><citation_entries>\n"
            "MEMORY.md:1-2|note=[x]\n"
            "</citation_entries>\n"
            "<rollout_ids>\n"
            "019cc2ea-1dff-7902-8d40-c8f6e5d83cc4\n"
            "</rollout_ids></oai-mem-citation> world"
        )

        citation = memory_citation_from_response_item(item)

        self.assertIsInstance(citation, MemoryCitation)
        assert citation is not None
        self.assertEqual(citation.entries[0].path, "MEMORY.md")
        self.assertEqual(citation.entries[0].line_start, 1)
        self.assertEqual(citation.entries[0].line_end, 2)
        self.assertEqual(citation.rollout_ids, ("019cc2ea-1dff-7902-8d40-c8f6e5d83cc4",))

    def test_hidden_markup_strips_unterminated_citation_but_keeps_non_line_plan_tag(self) -> None:
        self.assertEqual(strip_hidden_assistant_markup("x<oai-mem-citation>source", False), "x")
        self.assertEqual(
            strip_hidden_assistant_markup("  <proposed_plan> extra\n", True),
            "  <proposed_plan> extra\n",
        )

    def test_last_assistant_message_from_item_returns_none_for_hidden_only_text(self) -> None:
        self.assertIsNone(
            last_assistant_message_from_item(
                assistant_output_text("<oai-mem-citation>doc1</oai-mem-citation>"),
                plan_mode=False,
            )
        )
        self.assertIsNone(
            last_assistant_message_from_item(
                assistant_output_text("<proposed_plan>\n- x\n</proposed_plan>"),
                plan_mode=True,
            )
        )

    def test_get_last_assistant_message_from_turn_scans_from_end_without_plan_mode(self) -> None:
        earlier = assistant_output_text("earlier")
        hidden_plan_later = assistant_output_text("<proposed_plan>\nsecret\n</proposed_plan>")
        latest_visible = assistant_output_text("latest<oai-mem-citation>source</oai-mem-citation>")

        self.assertEqual(
            get_last_assistant_message_from_turn(
                (
                    earlier,
                    ResponseItem.function_call("shell", "{}", "call-1"),
                    hidden_plan_later,
                    latest_visible,
                )
            ),
            "latest",
        )
        self.assertEqual(
            get_last_assistant_message_from_turn((earlier, hidden_plan_later)),
            "<proposed_plan>\nsecret\n</proposed_plan>",
        )

    def test_get_last_assistant_message_from_turn_returns_none_without_visible_assistant_text(self) -> None:
        self.assertIsNone(
            get_last_assistant_message_from_turn(
                (
                    ResponseItem.function_call("shell", "{}", "call-1"),
                    assistant_output_text("<oai-mem-citation>hidden</oai-mem-citation>"),
                )
            )
        )

    def test_get_last_assistant_message_from_turn_accepts_sequence_like_rust_slice(self) -> None:
        responses = ResponseSequence(
            (
                assistant_output_text("earlier"),
                ResponseItem.function_call("shell", "{}", "call-1"),
                assistant_output_text("latest"),
            )
        )

        self.assertEqual(get_last_assistant_message_from_turn(responses), "latest")

    def test_completed_item_defers_mailbox_delivery_for_unknown_phase_messages(self) -> None:
        self.assertTrue(
            completed_item_defers_mailbox_delivery_to_next_turn(
                assistant_output_text("final answer"),
                plan_mode=False,
            )
        )

    def test_completed_item_keeps_mailbox_delivery_open_for_commentary_messages(self) -> None:
        self.assertFalse(
            completed_item_defers_mailbox_delivery_to_next_turn(
                assistant_output_text("still working", MessagePhase.COMMENTARY),
                plan_mode=False,
            )
        )

    def test_completed_item_defers_mailbox_delivery_for_image_generation_calls(self) -> None:
        self.assertTrue(
            completed_item_defers_mailbox_delivery_to_next_turn(
                ResponseItem.image_generation_call("ig-1", "completed", "Zm9v"),
                plan_mode=False,
            )
        )

    def test_image_generation_artifact_path_sanitizes_components(self) -> None:
        path = image_generation_artifact_path(Path("home"), "", "../ig/..")

        self.assertEqual(
            path,
            Path("home") / GENERATED_IMAGE_ARTIFACTS_DIR / "generated_image" / "___ig___.png",
        )

        with self.assertRaisesRegex(TypeError, "session_id must be a string"):
            image_generation_artifact_path(Path("home"), 123, "ig")  # type: ignore[arg-type]

    def test_save_image_generation_result_saves_base64_to_png_in_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir)
            expected_path = image_generation_artifact_path(codex_home, "session-1", "ig_save_base64")

            saved_path = save_image_generation_result(codex_home, "session-1", "ig_save_base64", "Zm9v")

            self.assertEqual(saved_path, expected_path)
            self.assertEqual(saved_path.read_bytes(), b"foo")

    def test_save_image_generation_result_overwrites_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir)
            existing_path = image_generation_artifact_path(codex_home, "session-1", "ig_overwrite")
            existing_path.parent.mkdir(parents=True)
            existing_path.write_bytes(b"existing")

            saved_path = save_image_generation_result(codex_home, "session-1", "ig_overwrite", "Zm9v")

            self.assertEqual(saved_path, existing_path)
            self.assertEqual(saved_path.read_bytes(), b"foo")

    def test_save_image_generation_result_rejects_data_url_and_urlsafe_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir)

            with self.assertRaises(ValueError):
                save_image_generation_result(codex_home, "session-1", "ig_456", "data:image/jpeg;base64,Zm9v")
            with self.assertRaises(ValueError):
                save_image_generation_result(codex_home, "session-1", "ig_urlsafe", "_-8")
            with self.assertRaises(ValueError):
                save_image_generation_result(codex_home, "session-1", "ig_svg", "data:image/svg+xml,<svg/>")

            with self.assertRaisesRegex(TypeError, "result must be a string"):
                save_image_generation_result(codex_home, "session-1", "ig_bad_type", b"Zm9v")  # type: ignore[arg-type]

    def test_response_input_to_response_item_maps_tool_outputs_only(self) -> None:
        function_output = response_input_to_response_item(ResponseInputItem.function_call_output("call-1", "ok"))
        custom_output = response_input_to_response_item(
            ResponseInputItem.custom_tool_call_output("call-2", "ok", name="tool")
        )
        tool_search = response_input_to_response_item(
            ResponseInputItem.tool_search_output("call-3", "completed", "done", ({"name": "lookup"},))
        )

        self.assertIsNotNone(function_output)
        self.assertEqual(function_output.type, "function_call_output")
        self.assertIsNotNone(custom_output)
        self.assertEqual(custom_output.name, "tool")
        self.assertIsNotNone(tool_search)
        self.assertEqual(tool_search.to_mapping()["tools"], [{"name": "lookup"}])
        self.assertIsNone(response_input_to_response_item(ResponseInputItem.message("user", (ContentItem.input_text("hi"),))))

    def test_function_call_error_to_response_input_maps_model_visible_error(self) -> None:
        response = function_call_error_to_response_input(FunctionCallError.respond_to_model("patch rejected"))

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "")
        self.assertEqual(response.output.body.text, "patch rejected")

    def test_function_call_error_output_result_requests_follow_up(self) -> None:
        output, response_item = function_call_error_output_result(FunctionCallError.respond_to_model("unknown agent"))

        self.assertTrue(output.needs_follow_up)
        self.assertEqual(response_item.type, "function_call_output")
        self.assertEqual(response_item.output.body.text, "unknown agent")

    def test_function_call_error_to_response_input_raises_fatal(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "payload mismatch"):
            function_call_error_to_response_input(FunctionCallError.fatal("payload mismatch"))

    def test_finalize_non_tool_response_item_strips_hidden_markup_and_records_facts(self) -> None:
        item = assistant_output_text(
            "visible<oai-mem-citation>hidden</oai-mem-citation>\n"
            "<proposed_plan>\nsecret\n</proposed_plan>\n"
            "done"
        )

        finalized = finalize_non_tool_response_item(item, plan_mode=True)

        self.assertIsNotNone(finalized)
        self.assertEqual(finalized.turn_item.type, "AgentMessage")
        self.assertEqual(finalized.facts.last_agent_message, "visible\ndone")
        self.assertTrue(finalized.facts.defers_mailbox_delivery_to_next_turn)

    def test_finalize_non_tool_response_item_keeps_commentary_from_deferring_mailbox(self) -> None:
        finalized = finalize_non_tool_response_item(assistant_output_text("working", MessagePhase.COMMENTARY), False)

        self.assertIsNotNone(finalized)
        self.assertEqual(finalized.facts.last_agent_message, "working")
        self.assertFalse(finalized.facts.defers_mailbox_delivery_to_next_turn)

    def test_finalize_non_tool_response_item_defers_image_generation(self) -> None:
        finalized = finalize_non_tool_response_item(ResponseItem.image_generation_call("ig-1", "completed", "Zm9v"), False)

        self.assertIsNotNone(finalized)
        self.assertEqual(finalized.turn_item.type, "ImageGeneration")
        self.assertTrue(finalized.facts.defers_mailbox_delivery_to_next_turn)

    def test_handle_non_tool_response_item_ignores_tool_calls(self) -> None:
        self.assertIsNone(handle_non_tool_response_item(ResponseItem.function_call("shell", "{}", "call-1"), False))

    def test_handle_non_tool_response_item_with_contributors_runs_before_markup_normalization(self) -> None:
        class Contributor:
            async def contribute(self, thread_extension_data, turn_store, item):
                self.seen = (thread_extension_data, turn_store, item.type)
                agent_message = item.item
                combined = "".join(content.text for content in agent_message.content)
                return TurnItem.agent_message(
                    AgentMessageItem(
                        id=agent_message.id,
                        content=(AgentMessageContent.text_content(combined + " contributed"),),
                        phase=agent_message.phase,
                        memory_citation=agent_message.memory_citation,
                    )
                )

        contributor = Contributor()
        sess = SimpleNamespace(services=SimpleNamespace(thread_extension_data="thread-data"), turn_item_contributors=lambda: (contributor,))
        item = assistant_output_text("hello<oai-mem-citation>hidden</oai-mem-citation>")

        turn_item = _run_async(
            handle_non_tool_response_item_with_contributors(
                sess,
                SimpleNamespace(),
                "turn-store",
                item,
                False,
            )
        )

        self.assertEqual(contributor.seen, ("thread-data", "turn-store", "AgentMessage"))
        self.assertEqual(turn_item.item.content[0].text, "hello contributed")

    def test_handle_non_tool_response_item_with_contributors_saves_image_and_records_instructions(self) -> None:
        class Session:
            def __init__(self):
                self.conversation_id = "session-1"
                self.recorded = []

            async def record_conversation_items(self, turn_context, items):
                self.recorded.extend(items)

        with tempfile.TemporaryDirectory() as temp_dir:
            session = Session()
            turn_context = SimpleNamespace(config=SimpleNamespace(codex_home=Path(temp_dir)))

            turn_item = _run_async(
                handle_non_tool_response_item_with_contributors(
                    session,
                    turn_context,
                    None,
                    ResponseItem.image_generation_call("ig-1", "completed", "Zm9v"),
                    False,
                )
            )

            expected_path = image_generation_artifact_path(Path(temp_dir), "session-1", "ig-1")
            self.assertEqual(turn_item.item.saved_path, expected_path)
            self.assertEqual(expected_path.read_bytes(), b"foo")
            self.assertEqual(session.recorded[0].role, "developer")
            self.assertIn("Generated images are saved to", session.recorded[0].content[0].text)
            self.assertIn(str(image_generation_artifact_path(Path(temp_dir), "session-1", "<image_id>")), session.recorded[0].content[0].text)

    def test_apply_turn_item_contributors_ignores_failed_contributor(self) -> None:
        original = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content("ok"),))
        )

        class FailingContributor:
            def contribute(self, thread_extension_data, turn_store, item):
                raise RuntimeError("boom")

        result = _run_async(
            apply_turn_item_contributors(
                SimpleNamespace(turn_item_contributors=lambda: (FailingContributor(),)),
                None,
                original,
            )
        )

        self.assertEqual(result, original)

    def test_finalized_turn_item_facts_rejects_non_turn_item(self) -> None:
        with self.assertRaisesRegex(TypeError, "turn_item must be a TurnItem"):
            finalized_turn_item_facts(object())  # type: ignore[arg-type]

    def test_handle_output_item_done_records_non_tool_item_and_emits_turn_items(self) -> None:
        class Session:
            def __init__(self):
                self.recorded = []
                self.started = []
                self.completed = []

            async def record_conversation_items(self, turn_context, items):
                self.recorded.extend(items)

            async def emit_turn_item_started(self, turn_context, item):
                self.started.append(item)

            async def emit_turn_item_completed(self, turn_context, item):
                self.completed.append(item)

        session = Session()
        ctx = HandleOutputCtx(session, SimpleNamespace(collaboration_mode=SimpleNamespace(mode="plan"), sub_id="sub"))

        result = _run_async(handle_output_item_done(ctx, assistant_output_text("hello"), None))

        self.assertEqual(result.last_agent_message, "hello")
        self.assertEqual(session.recorded[0].type, "message")
        self.assertEqual(session.started[0].type, "AgentMessage")
        self.assertEqual(session.completed[0].type, "AgentMessage")

    def test_handle_output_item_done_tool_call_sets_follow_up_and_future(self) -> None:
        class Cancellation:
            def __init__(self):
                self.child = object()

            def child_token(self):
                return self.child

        class Runtime:
            def __init__(self):
                self.cancellation = None

            def handle_tool_call(self, call, cancellation):
                self.cancellation = cancellation
                return ("future", call.tool_name)

        class Session:
            def __init__(self):
                self.recorded = []
                self.lifecycle = []
                self.conversation_id = "thread-1"

            async def record_conversation_items(self, turn_context, items):
                self.recorded.extend(items)

            async def record_tool_call_lifecycle(self, turn_context, plan):
                self.lifecycle.append(plan)

        runtime = Runtime()
        cancellation = Cancellation()
        session = Session()
        ctx = HandleOutputCtx(
            session,
            SimpleNamespace(collaboration_mode=SimpleNamespace(mode="default")),
            tool_runtime=runtime,
            cancellation_token=cancellation,
        )

        result = _run_async(handle_output_item_done(ctx, ResponseItem.function_call("shell", "{}", "call-1"), None))

        self.assertTrue(result.needs_follow_up)
        self.assertIsNotNone(result.tool_future)
        self.assertIs(runtime.cancellation, cancellation.child)
        self.assertEqual(session.lifecycle[0].tool_name, "shell")
        self.assertEqual(session.lifecycle[0].payload_preview, "{}")
        self.assertEqual(session.lifecycle[0].thread_id, "thread-1")

    def test_tool_call_lifecycle_plan_rejects_non_tool_call(self) -> None:
        with self.assertRaisesRegex(TypeError, "call must be a ToolCall"):
            tool_call_lifecycle_plan(object())  # type: ignore[arg-type]

    def test_tool_call_lifecycle_plan_uses_payload_log_preview(self) -> None:
        call = ToolRouter.build_tool_call(ResponseItem.custom_tool_call("apply_patch", "*** Begin Patch", "call-1"))

        plan = tool_call_lifecycle_plan(call, "thread-1")

        self.assertEqual(
            plan,
            ToolCallLifecyclePlan(
                tool_name="apply_patch",
                payload_preview="*** Begin Patch",
                thread_id="thread-1",
            ),
        )

    def test_tool_call_error_handling_plan_maps_respond_to_model(self) -> None:
        plan = tool_call_error_handling_plan(FunctionCallError.respond_to_model("unsupported"))

        self.assertEqual(
            plan,
            ToolCallErrorHandlingPlan(
                response_item=plan.response_item,
                needs_follow_up=True,
                records_model_visible_response=True,
            ),
        )
        self.assertEqual(plan.response_item.output.body.text, "unsupported")

    def test_tool_call_error_handling_plan_maps_fatal(self) -> None:
        self.assertEqual(
            tool_call_error_handling_plan(FunctionCallError.fatal("boom")),
            ToolCallErrorHandlingPlan(fatal_message="boom"),
        )

    def test_handle_output_item_done_router_error_records_model_visible_response(self) -> None:
        from pycodex.core import tool_router

        class Session:
            def __init__(self):
                self.recorded = []

            async def record_conversation_items(self, turn_context, items):
                self.recorded.extend(items)

        original = tool_router.ToolRouter.build_tool_call
        session = Session()
        try:
            tool_router.ToolRouter.build_tool_call = staticmethod(
                lambda item: (_ for _ in ()).throw(tool_router.FunctionCallError.respond_to_model("unsupported"))
            )
            ctx = HandleOutputCtx(session, SimpleNamespace(collaboration_mode=SimpleNamespace(mode="default")))

            result = _run_async(handle_output_item_done(ctx, assistant_output_text("tool?"), None))
        finally:
            tool_router.ToolRouter.build_tool_call = original

        self.assertTrue(result.needs_follow_up)
        self.assertEqual(session.recorded[-1].output.body.text, "unsupported")

    def test_handle_output_item_done_router_fatal_error_raises_without_model_response(self) -> None:
        from pycodex.core import tool_router

        class Session:
            def __init__(self):
                self.recorded = []

            async def record_conversation_items(self, turn_context, items):
                self.recorded.extend(items)

        original = tool_router.ToolRouter.build_tool_call
        session = Session()
        try:
            tool_router.ToolRouter.build_tool_call = staticmethod(
                lambda item: (_ for _ in ()).throw(tool_router.FunctionCallError.fatal("fatal mismatch"))
            )
            ctx = HandleOutputCtx(session, SimpleNamespace(collaboration_mode=SimpleNamespace(mode="default")))

            with self.assertRaisesRegex(RuntimeError, "fatal mismatch"):
                _run_async(handle_output_item_done(ctx, assistant_output_text("tool?"), None))
        finally:
            tool_router.ToolRouter.build_tool_call = original

        self.assertEqual(session.recorded, [])

    def test_unexpected_tool_output_plan_maps_tool_outputs_only(self) -> None:
        output = ResponseItem.from_response_input_item(ResponseInputItem.function_call_output("call-1", "ok"))

        self.assertEqual(
            unexpected_tool_output_plan(output),
            UnexpectedToolOutputPlan(item_type="function_call_output"),
        )
        self.assertIsNone(unexpected_tool_output_plan(assistant_output_text("hello")))

    def test_handle_output_item_done_unexpected_tool_output_records_without_follow_up_or_emit(self) -> None:
        class Session:
            def __init__(self):
                self.recorded = []
                self.unexpected = []

            async def record_conversation_items(self, turn_context, items):
                self.recorded.extend(items)

            async def record_unexpected_tool_output(self, turn_context, plan):
                self.unexpected.append(plan)

        session = Session()
        ctx = HandleOutputCtx(session, SimpleNamespace(collaboration_mode=SimpleNamespace(mode="default")))
        item = ResponseItem.from_response_input_item(ResponseInputItem.function_call_output("call-1", "ok"))

        result = _run_async(handle_output_item_done(ctx, item, None))

        self.assertFalse(result.needs_follow_up)
        self.assertIsNone(result.tool_future)
        self.assertEqual(session.recorded, [item])
        self.assertEqual(session.unexpected, [UnexpectedToolOutputPlan(item_type="function_call_output")])

    def test_sampling_output_state_after_result_matches_rust_turn_loop_aggregation(self) -> None:
        state = SamplingOutputState()

        state = sampling_output_state_after_result(
            state,
            OutputItemResult(tool_future="future-1", needs_follow_up=True),
        )
        state = sampling_output_state_after_result(
            state,
            OutputItemResult(last_agent_message="first"),
        )
        state = sampling_output_state_after_result(
            state,
            OutputItemResult(tool_future="future-2", last_agent_message="second"),
        )

        self.assertEqual(
            state,
            SamplingOutputState(
                needs_follow_up=True,
                last_agent_message="second",
                in_flight=("future-1", "future-2"),
            ),
        )

    def test_sampling_output_state_after_result_rejects_wrong_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "state must be a SamplingOutputState"):
            sampling_output_state_after_result(object(), OutputItemResult())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "output_result must be an OutputItemResult"):
            sampling_output_state_after_result(SamplingOutputState(), object())  # type: ignore[arg-type]

    def test_sampling_mailbox_preemption_plan_matches_rust_item_filter(self) -> None:
        commentary = assistant_output_text("still thinking", MessagePhase.COMMENTARY)
        reasoning = ResponseItem.reasoning(id="rs-1", content=())
        final_message = assistant_output_text("done")
        state = SamplingOutputState(last_agent_message="prior")

        self.assertTrue(sampling_item_preempts_for_mailbox_mail(commentary))
        self.assertTrue(sampling_item_preempts_for_mailbox_mail(reasoning))
        self.assertFalse(sampling_item_preempts_for_mailbox_mail(final_message))
        self.assertEqual(
            sampling_mailbox_preemption_plan(commentary, has_pending_mailbox_items=True, state=state),
            SamplingMailboxPreemptionPlan(needs_follow_up=True, last_agent_message="prior"),
        )
        self.assertIsNone(
            sampling_mailbox_preemption_plan(final_message, has_pending_mailbox_items=True, state=state)
        )
        self.assertIsNone(
            sampling_mailbox_preemption_plan(commentary, has_pending_mailbox_items=False, state=state)
        )

    def test_sampling_mailbox_preemption_plan_rejects_wrong_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "has_pending_mailbox_items must be a bool"):
            sampling_mailbox_preemption_plan(
                assistant_output_text("still thinking", MessagePhase.COMMENTARY),
                has_pending_mailbox_items="yes",  # type: ignore[arg-type]
                state=SamplingOutputState(),
            )
        with self.assertRaisesRegex(TypeError, "state must be a SamplingOutputState"):
            sampling_mailbox_preemption_plan(
                assistant_output_text("still thinking", MessagePhase.COMMENTARY),
                has_pending_mailbox_items=True,
                state=object(),  # type: ignore[arg-type]
            )

    def test_sampling_output_item_added_plan_creates_custom_tool_diff_consumer(self) -> None:
        class Runtime:
            def __init__(self):
                self.tool_name = None

            def create_diff_consumer(self, tool_name):
                self.tool_name = tool_name
                return "consumer"

        runtime = Runtime()
        item = ResponseItem.custom_tool_call("apply_patch", "*** Begin Patch", "custom-1")

        plan = sampling_output_item_added_plan(
            item,
            plan_mode=False,
            tool_runtime=runtime,
        )

        self.assertEqual(plan.active_tool_argument_diff_consumer, ("custom-1", "consumer"))
        self.assertEqual(str(runtime.tool_name), "apply_patch")
        self.assertFalse(plan.reset_tool_argument_diff_consumer)
        self.assertIsNone(plan.active_item)

    def test_sampling_output_item_added_plan_resets_function_diff_consumer(self) -> None:
        plan = sampling_output_item_added_plan(
            ResponseItem.function_call("shell", "{}", "call-1"),
            plan_mode=False,
        )

        self.assertTrue(plan.reset_tool_argument_diff_consumer)
        self.assertIsNone(plan.active_tool_argument_diff_consumer)
        self.assertIsNone(plan.active_item)

    def test_sampling_output_item_added_plan_emits_non_tool_started_when_not_deferred(self) -> None:
        plan = sampling_output_item_added_plan(
            assistant_output_text("hello<oai-mem-citation>hidden</oai-mem-citation>"),
            plan_mode=False,
            defer_streamed_turn_items_for_contributors=False,
        )

        self.assertEqual(plan.active_item.type, "AgentMessage")
        self.assertEqual(plan.turn_item_to_emit, plan.active_item)
        self.assertTrue(plan.active_item_is_streaming_to_client)
        self.assertEqual(plan.seeded_item_id, "msg-1")
        self.assertEqual(plan.seeded_visible_text, "hello")
        self.assertEqual(plan.active_item.item.content[0].text, "hello")

    def test_sampling_output_item_added_plan_seeds_plan_mode_with_empty_visible_text(self) -> None:
        plan = sampling_output_item_added_plan(
            assistant_output_text("Intro\n<proposed_plan>\nsecret\n</proposed_plan>\nVisible"),
            plan_mode=True,
            defer_streamed_turn_items_for_contributors=False,
        )

        self.assertEqual(plan.active_item.type, "AgentMessage")
        self.assertEqual(plan.seeded_item_id, "msg-1")
        self.assertEqual(plan.seeded_visible_text, "Intro\nVisible")
        self.assertEqual(plan.seeded_parsed, {"visible_text": "Intro\nVisible"})
        self.assertEqual(plan.active_item.item.content[0].text, "")

    def test_sampling_output_item_added_plan_defers_streaming_for_contributors(self) -> None:
        plan = sampling_output_item_added_plan(
            assistant_output_text("hello"),
            plan_mode=False,
            defer_streamed_turn_items_for_contributors=True,
        )

        self.assertEqual(plan.active_item.type, "AgentMessage")
        self.assertIsNone(plan.turn_item_to_emit)
        self.assertFalse(plan.active_item_is_streaming_to_client)
        self.assertIsNone(plan.seeded_item_id)

    def test_sampling_output_item_added_apply_plan_emits_started_for_non_plan_items(self) -> None:
        added = sampling_output_item_added_plan(
            assistant_output_text("hello"),
            plan_mode=False,
            defer_streamed_turn_items_for_contributors=False,
        )

        plan = sampling_output_item_added_apply_plan(added, plan_mode=False)

        self.assertEqual(
            plan,
            SamplingOutputItemAddedApplyPlan(
                active_tool_argument_diff_consumer_after=None,
                should_reset_tool_argument_diff_consumer=False,
                pending_agent_message_item=None,
                turn_item_started_to_emit=added.turn_item_to_emit,
                seeded_streamed_assistant_text_plan=None,
                active_item_after=added.active_item,
                active_item_is_streaming_to_client_after=True,
            ),
        )

    def test_sampling_output_item_added_apply_plan_pending_and_seeded_delta_in_plan_mode(self) -> None:
        added = sampling_output_item_added_plan(
            assistant_output_text("hello"),
            plan_mode=True,
            defer_streamed_turn_items_for_contributors=False,
        )

        plan = sampling_output_item_added_apply_plan(
            added,
            plan_mode=True,
            plan_item_id="turn-1-plan",
        )

        self.assertEqual(plan.pending_agent_message_item, added.turn_item_to_emit)
        self.assertIsNone(plan.turn_item_started_to_emit)
        self.assertEqual(plan.active_item_after, added.active_item)
        self.assertTrue(plan.active_item_is_streaming_to_client_after)
        self.assertEqual(
            plan.seeded_streamed_assistant_text_plan,
            SamplingStreamedAssistantTextDeltaPlan(item_id="msg-1"),
        )

    def test_sampling_output_text_delta_plan_parses_agent_message_delta(self) -> None:
        active = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        plan = sampling_output_text_delta_plan(
            active,
            "visible<oai-mem-citation>hidden</oai-mem-citation>",
            active_item_is_streaming_to_client=True,
            plan_mode=False,
        )

        self.assertEqual(
            plan,
            SamplingOutputTextDeltaPlan(
                item_id="msg-1",
                delta="visible<oai-mem-citation>hidden</oai-mem-citation>",
                parsed={"visible_text": "visible"},
            ),
        )

    def test_sampling_output_text_delta_plan_uses_raw_delta_for_non_agent_items(self) -> None:
        active = handle_non_tool_response_item(ResponseItem.reasoning(id="rs-1", content=()), False)

        plan = sampling_output_text_delta_plan(
            active,
            "thinking",
            active_item_is_streaming_to_client=True,
            plan_mode=False,
        )

        self.assertEqual(
            plan,
            SamplingOutputTextDeltaPlan(item_id="rs-1", delta="thinking", raw_content_delta="thinking"),
        )

    def test_sampling_output_text_delta_plan_skips_non_streaming_or_missing_active_item(self) -> None:
        active = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        self.assertIsNone(
            sampling_output_text_delta_plan(
                active,
                "hidden",
                active_item_is_streaming_to_client=False,
                plan_mode=False,
            )
        )
        self.assertIsNone(
            sampling_output_text_delta_plan(
                None,
                "hidden",
                active_item_is_streaming_to_client=True,
                plan_mode=False,
            )
        )

    def test_sampling_output_text_delta_apply_plan_streams_agent_message_delta(self) -> None:
        text_delta_plan = SamplingOutputTextDeltaPlan(
            item_id="msg-1",
            delta="hello",
            parsed={"visible_text": "hello", "citations": (), "plan_segments": ()},
        )

        plan = sampling_output_text_delta_apply_plan(text_delta_plan, plan_mode=False)

        self.assertEqual(
            plan,
            SamplingOutputTextDeltaApplyPlan(
                item_id="msg-1",
                streamed_assistant_text_plan=SamplingStreamedAssistantTextDeltaPlan(
                    item_id="msg-1",
                    visible_text_delta="hello",
                ),
            ),
        )

    def test_sampling_output_text_delta_apply_plan_emits_raw_non_agent_delta(self) -> None:
        text_delta_plan = SamplingOutputTextDeltaPlan(
            item_id="rs-1",
            delta="thinking",
            raw_content_delta="thinking",
        )

        self.assertEqual(
            sampling_output_text_delta_apply_plan(text_delta_plan, plan_mode=False),
            SamplingOutputTextDeltaApplyPlan(
                item_id="rs-1",
                raw_content_delta="thinking",
            ),
        )
        self.assertIsNone(sampling_output_text_delta_apply_plan(None, plan_mode=False))

    def test_sampling_tool_call_input_delta_plan_consumes_matching_delta(self) -> None:
        class Consumer:
            def __init__(self):
                self.calls = []

            def consume_diff(self, turn_context, call_id, delta):
                self.calls.append((turn_context, call_id, delta))
                return {"type": "tool_call_input_delta", "call_id": call_id, "delta": delta}

        consumer = Consumer()
        turn_context = object()

        plan = sampling_tool_call_input_delta_plan(
            ("call-1", consumer),
            call_id=None,
            delta="abc",
            turn_context=turn_context,
        )

        self.assertEqual(consumer.calls, [(turn_context, "call-1", "abc")])
        self.assertEqual(
            plan,
            SamplingToolCallInputDeltaPlan(
                call_id="call-1",
                delta="abc",
                event={"type": "tool_call_input_delta", "call_id": "call-1", "delta": "abc"},
            ),
        )

    def test_sampling_tool_call_input_delta_plan_skips_missing_or_mismatched_consumer(self) -> None:
        class Consumer:
            def consume_diff(self, turn_context, call_id, delta):
                return {"unexpected": True}

        self.assertIsNone(
            sampling_tool_call_input_delta_plan(None, call_id="call-1", delta="abc")
        )
        self.assertIsNone(
            sampling_tool_call_input_delta_plan(("active", Consumer()), call_id="other", delta="abc")
        )

    def test_sampling_tool_call_input_delta_apply_plan_sends_consumer_event_when_present(self) -> None:
        tool_delta_plan = SamplingToolCallInputDeltaPlan(
            call_id="call-1",
            delta="abc",
            event={"type": "tool_call_input_delta", "call_id": "call-1"},
        )

        self.assertEqual(
            sampling_tool_call_input_delta_apply_plan(tool_delta_plan),
            SamplingToolCallInputDeltaApplyPlan(
                call_id="call-1",
                delta="abc",
                event_to_emit={"type": "tool_call_input_delta", "call_id": "call-1"},
                should_send_event=True,
            ),
        )

    def test_sampling_tool_call_input_delta_apply_plan_skips_without_event(self) -> None:
        self.assertEqual(
            sampling_tool_call_input_delta_apply_plan(
                SamplingToolCallInputDeltaPlan(call_id="call-1", delta="abc", event=None)
            ),
            SamplingToolCallInputDeltaApplyPlan(
                call_id="call-1",
                delta="abc",
                event_to_emit=None,
                should_send_event=False,
            ),
        )
        self.assertIsNone(sampling_tool_call_input_delta_apply_plan(None))

    def test_sampling_tool_call_input_delta_plan_rejects_wrong_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "active_tool_argument_diff_consumer"):
            sampling_tool_call_input_delta_plan(("call-1",), call_id=None, delta="abc")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "call_id must be a string or None"):
            sampling_tool_call_input_delta_plan(("call-1", object()), call_id=1, delta="abc")  # type: ignore[arg-type]

    def test_sampling_reasoning_delta_plans_match_rust_events(self) -> None:
        active = handle_non_tool_response_item(ResponseItem.reasoning(id="rs-1", content=()), False)

        self.assertEqual(
            sampling_reasoning_summary_delta_plan(
                active,
                delta="summary",
                summary_index=2,
                active_item_is_streaming_to_client=True,
            ),
            SamplingReasoningDeltaPlan(
                event_type="reasoning_content_delta",
                item_id="rs-1",
                delta="summary",
                summary_index=2,
            ),
        )
        self.assertEqual(
            sampling_reasoning_summary_part_added_plan(
                active,
                summary_index=3,
                active_item_is_streaming_to_client=True,
            ),
            SamplingReasoningDeltaPlan(
                event_type="agent_reasoning_section_break",
                item_id="rs-1",
                summary_index=3,
            ),
        )
        self.assertEqual(
            sampling_reasoning_content_delta_plan(
                active,
                delta="raw",
                content_index=1,
                active_item_is_streaming_to_client=True,
            ),
            SamplingReasoningDeltaPlan(
                event_type="reasoning_raw_content_delta",
                item_id="rs-1",
                delta="raw",
                content_index=1,
            ),
        )

    def test_sampling_reasoning_delta_plans_skip_when_not_streaming(self) -> None:
        active = handle_non_tool_response_item(ResponseItem.reasoning(id="rs-1", content=()), False)

        self.assertIsNone(
            sampling_reasoning_summary_delta_plan(
                active,
                delta="summary",
                summary_index=0,
                active_item_is_streaming_to_client=False,
            )
        )
        self.assertIsNone(
            sampling_reasoning_content_delta_plan(
                None,
                delta="raw",
                content_index=0,
                active_item_is_streaming_to_client=True,
            )
        )

        with self.assertRaisesRegex(TypeError, "active_item must be a TurnItem"):
            sampling_reasoning_summary_part_added_plan(
                object(),  # type: ignore[arg-type]
                summary_index=0,
                active_item_is_streaming_to_client=True,
            )
        with self.assertRaisesRegex(ValueError, "summary_index must be non-negative"):
            sampling_reasoning_summary_delta_plan(
                active,
                delta="summary",
                summary_index=-1,
                active_item_is_streaming_to_client=True,
            )

    def test_sampling_reasoning_delta_apply_plan_emits_reasoning_events(self) -> None:
        self.assertEqual(
            sampling_reasoning_delta_apply_plan(
                SamplingReasoningDeltaPlan(
                    event_type="reasoning_content_delta",
                    item_id="rs-1",
                    delta="summary",
                    summary_index=2,
                )
            ),
            SamplingReasoningDeltaApplyPlan(
                event_type="reasoning_content_delta",
                item_id="rs-1",
                event_to_emit={
                    "type": "reasoning_content_delta",
                    "item_id": "rs-1",
                    "delta": "summary",
                    "summary_index": 2,
                },
            ),
        )
        self.assertEqual(
            sampling_reasoning_delta_apply_plan(
                SamplingReasoningDeltaPlan(
                    event_type="agent_reasoning_section_break",
                    item_id="rs-1",
                    summary_index=3,
                )
            ),
            SamplingReasoningDeltaApplyPlan(
                event_type="agent_reasoning_section_break",
                item_id="rs-1",
                event_to_emit={
                    "type": "agent_reasoning_section_break",
                    "item_id": "rs-1",
                    "summary_index": 3,
                },
            ),
        )
        self.assertEqual(
            sampling_reasoning_delta_apply_plan(
                SamplingReasoningDeltaPlan(
                    event_type="reasoning_raw_content_delta",
                    item_id="rs-1",
                    delta="raw",
                    content_index=1,
                )
            ),
            SamplingReasoningDeltaApplyPlan(
                event_type="reasoning_raw_content_delta",
                item_id="rs-1",
                event_to_emit={
                    "type": "reasoning_raw_content_delta",
                    "item_id": "rs-1",
                    "delta": "raw",
                    "content_index": 1,
                },
            ),
        )
        self.assertIsNone(sampling_reasoning_delta_apply_plan(None))

    def test_sampling_reasoning_delta_apply_plan_rejects_incomplete_or_unknown_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "reasoning_content_delta requires delta"):
            sampling_reasoning_delta_apply_plan(
                SamplingReasoningDeltaPlan(
                    event_type="reasoning_content_delta",
                    item_id="rs-1",
                    summary_index=0,
                )
            )
        with self.assertRaisesRegex(ValueError, "unsupported reasoning delta event type"):
            sampling_reasoning_delta_apply_plan(
                SamplingReasoningDeltaPlan(event_type="mystery", item_id="rs-1")
            )

    def test_sampling_assistant_text_flush_plan_finishes_stream_parser_for_active_agent_message(self) -> None:
        active = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        class Parser:
            def __init__(self):
                self.finished = []

            def finish_item(self, item_id):
                self.finished.append(item_id)
                return {"visible_text": "tail", "citations": []}

        parser = Parser()

        plan = sampling_assistant_text_flush_plan(
            active,
            assistant_message_stream_parsers=parser,
            active_item_is_streaming_to_client=True,
        )

        self.assertEqual(parser.finished, ["msg-1"])
        self.assertEqual(
            plan,
            SamplingAssistantTextFlushPlan(
                item_id="msg-1",
                parsed={"visible_text": "tail", "citations": []},
            ),
        )

    def test_sampling_assistant_text_flush_plan_skips_non_agent_or_non_streaming_items(self) -> None:
        active_reasoning = handle_non_tool_response_item(ResponseItem.reasoning(id="rs-1", content=()), False)

        class Parser:
            def finish_item(self, item_id):
                return {"unexpected": item_id}

        parser = Parser()
        active_agent = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        self.assertIsNone(
            sampling_assistant_text_flush_plan(
                active_reasoning,
                assistant_message_stream_parsers=parser,
                active_item_is_streaming_to_client=True,
            )
        )
        self.assertIsNone(
            sampling_assistant_text_flush_plan(
                None,
                assistant_message_stream_parsers=parser,
                active_item_is_streaming_to_client=True,
            )
        )
        self.assertIsNone(
            sampling_assistant_text_flush_plan(
                active_agent,
                assistant_message_stream_parsers=parser,
                active_item_is_streaming_to_client=False,
            )
        )

        with self.assertRaisesRegex(TypeError, "assistant_message_stream_parsers must provide finish_item"):
            sampling_assistant_text_flush_plan(
                active_agent,
                assistant_message_stream_parsers=object(),
                active_item_is_streaming_to_client=True,
            )

    def test_sampling_assistant_text_flush_all_plan_drains_all_finished_parsers(self) -> None:
        class Parser:
            def __init__(self):
                self.drained = False

            def drain_finished(self):
                self.drained = True
                return (
                    ("msg-1", {"visible_text": "one"}),
                    ("msg-2", {"visible_text": "two"}),
                )

        parser = Parser()

        plan = sampling_assistant_text_flush_all_plan(
            assistant_message_stream_parsers=parser,
        )

        self.assertTrue(parser.drained)
        self.assertEqual(
            plan,
            SamplingAssistantTextFlushAllPlan(
                (
                    SamplingAssistantTextFlushPlan("msg-1", {"visible_text": "one"}),
                    SamplingAssistantTextFlushPlan("msg-2", {"visible_text": "two"}),
                )
            ),
        )

        with self.assertRaisesRegex(TypeError, "assistant_message_stream_parsers must provide drain_finished"):
            sampling_assistant_text_flush_all_plan(assistant_message_stream_parsers=object())

    def test_sampling_streamed_assistant_text_delta_plan_emits_visible_text_outside_plan_mode(self) -> None:
        plan = sampling_streamed_assistant_text_delta_plan(
            "msg-1",
            {"visible_text": "hello", "citations": ("doc",), "plan_segments": ()},
            plan_mode=False,
        )

        self.assertEqual(
            plan,
            SamplingStreamedAssistantTextDeltaPlan(
                item_id="msg-1",
                visible_text_delta="hello",
                citations=("doc",),
                ignored_citations=True,
            ),
        )
        self.assertIsNone(
            sampling_streamed_assistant_text_delta_plan(
                "msg-1",
                {"visible_text": "", "citations": (), "plan_segments": ()},
                plan_mode=False,
            )
        )
        self.assertIsNone(
            sampling_streamed_assistant_text_delta_plan(
                "msg-1",
                {"visible_text": "", "citations": ("doc",), "plan_segments": ()},
                plan_mode=False,
            )
        )

        class EmptyParsed:
            visible_text = "ignored"
            citations = ()
            plan_segments = ()

            def is_empty(self) -> bool:
                return True

        self.assertIsNone(
            sampling_streamed_assistant_text_delta_plan(
                "msg-1",
                EmptyParsed(),
                plan_mode=False,
            )
        )

    def test_sampling_streamed_assistant_text_delta_plan_routes_plan_segments_in_plan_mode(self) -> None:
        plan = sampling_streamed_assistant_text_delta_plan(
            "msg-1",
            {
                "visible_text": "ignored in plan mode",
                "citations": (),
                "plan_segments": (("proposed_plan_delta", "- step\n"),),
            },
            plan_mode=True,
            plan_item_id="turn-1-plan",
        )

        self.assertEqual(
            plan,
            SamplingStreamedAssistantTextDeltaPlan(
                item_id="msg-1",
                plan_segments_plan=SamplingPlanSegmentsPlan(
                    actions=(
                        SamplingPlanSegmentAction("start_plan_item", "turn-1-plan"),
                        SamplingPlanSegmentAction("plan_delta", "turn-1-plan", "- step\n"),
                    ),
                    leading_whitespace_by_item_after=(),
                    plan_item_started_after=True,
                    plan_item_completed_after=False,
                ),
            ),
        )
        self.assertEqual(
            sampling_streamed_assistant_text_delta_plan(
                "msg-1",
                {"visible_text": "", "citations": ("doc",), "plan_segments": ()},
                plan_mode=True,
            ),
            SamplingStreamedAssistantTextDeltaPlan(
                item_id="msg-1",
                citations=("doc",),
                ignored_citations=True,
            ),
        )

    def test_sampling_output_item_done_transition_plan_finishes_consumer_and_flushes_agent(self) -> None:
        active = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        class Consumer:
            def __init__(self):
                self.finished = False

            def finish(self):
                self.finished = True
                return {"type": "tool_call_input_delta_done", "call_id": "call-1"}

        class Parser:
            def finish_item(self, item_id):
                return {"visible_text": "tail", "item_id": item_id}

        consumer = Consumer()

        plan = sampling_output_item_done_transition_plan(
            active,
            active_item_is_streaming_to_client=True,
            active_tool_argument_diff_consumer=("call-1", consumer),
            assistant_message_stream_parsers=Parser(),
        )

        self.assertTrue(consumer.finished)
        self.assertEqual(
            plan,
            SamplingOutputItemDoneTransitionPlan(
                previously_active_item=active,
                previously_streamed_item=active,
                active_item_after=None,
                active_item_is_streaming_to_client_after=False,
                finished_tool_input_event={"type": "tool_call_input_delta_done", "call_id": "call-1"},
                assistant_text_flush_plan=SamplingAssistantTextFlushPlan(
                    item_id="msg-1",
                    parsed={"visible_text": "tail", "item_id": "msg-1"},
                ),
            ),
        )

    def test_sampling_output_item_done_transition_plan_only_streams_previous_when_flagged(self) -> None:
        active = handle_non_tool_response_item(ResponseItem.reasoning(id="rs-1", content=()), False)

        class BrokenConsumer:
            def finish(self):
                raise RuntimeError("ignored like Rust's Err branch")

        plan = sampling_output_item_done_transition_plan(
            active,
            active_item_is_streaming_to_client=False,
            active_tool_argument_diff_consumer=("call-1", BrokenConsumer()),
        )

        self.assertEqual(
            plan,
            SamplingOutputItemDoneTransitionPlan(
                previously_active_item=active,
                previously_streamed_item=None,
                active_item_after=None,
                active_item_is_streaming_to_client_after=False,
                finished_tool_input_event=None,
                assistant_text_flush_plan=None,
            ),
        )

    def test_sampling_output_item_done_apply_plan_handles_plan_mode_assistant_and_continues(self) -> None:
        item = assistant_output_text("final answer")
        active = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )
        transition = SamplingOutputItemDoneTransitionPlan(
            previously_active_item=active,
            previously_streamed_item=active,
            assistant_text_flush_plan=SamplingAssistantTextFlushPlan(
                item_id="msg-1",
                parsed={"visible_text": "tail", "citations": (), "plan_segments": ()},
            ),
        )

        plan = sampling_output_item_done_apply_plan(
            item,
            transition,
            plan_mode=True,
            state=SamplingOutputState(),
        )

        self.assertEqual(
            plan.streamed_assistant_text_plan,
            SamplingStreamedAssistantTextDeltaPlan(item_id="msg-1"),
        )
        self.assertIsNotNone(plan.plan_mode_assistant_done_plan)
        self.assertTrue(plan.plan_mode_assistant_done_plan.handled)
        self.assertTrue(plan.should_continue_loop)
        self.assertIsNone(plan.output_result)
        self.assertIsNone(plan.state_after_output_result)

    def test_sampling_output_item_done_apply_plan_aggregates_result_and_mailbox_preemption(self) -> None:
        item = ResponseItem.reasoning(id="rs-1", content=())
        transition = SamplingOutputItemDoneTransitionPlan()
        output_result = OutputItemResult(
            last_agent_message="assistant tail",
            needs_follow_up=False,
            tool_future="future-1",
        )

        plan = sampling_output_item_done_apply_plan(
            item,
            transition,
            plan_mode=False,
            state=SamplingOutputState(needs_follow_up=False),
            output_result=output_result,
            has_pending_mailbox_items=True,
        )

        self.assertEqual(plan.output_result, output_result)
        self.assertEqual(
            plan.state_after_output_result,
            SamplingOutputState(
                needs_follow_up=False,
                last_agent_message="assistant tail",
                in_flight=("future-1",),
            ),
        )
        self.assertTrue(plan.preempt_for_mailbox_mail)
        self.assertEqual(
            plan.mailbox_preemption_plan,
            SamplingMailboxPreemptionPlan(
                needs_follow_up=True,
                last_agent_message="assistant tail",
            ),
        )

    def test_sampling_stream_event_dispatch_plan_routes_core_stream_events(self) -> None:
        active = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        class Parser:
            def finish_item(self, item_id):
                return {"visible_text": "tail", "item_id": item_id}

        self.assertEqual(
            sampling_stream_event_dispatch_plan("created"),
            SamplingStreamEventDispatchPlan(event_type="created", no_op=True),
        )

        added_item = assistant_output_text("hello")
        self.assertEqual(
            sampling_stream_event_dispatch_plan("output_item_added", added_item, plan_mode=False),
            SamplingStreamEventDispatchPlan(
                event_type="output_item_added",
                output_item_added_plan=sampling_output_item_added_plan(added_item, plan_mode=False),
            ),
        )

        done = sampling_stream_event_dispatch_plan(
            "output_item_done",
            assistant_output_text("done"),
            active_item=active,
            active_item_is_streaming_to_client=True,
            assistant_message_stream_parsers=Parser(),
        )
        self.assertEqual(done.event_type, "output_item_done")
        self.assertIsNotNone(done.output_item_done_transition_plan)
        self.assertEqual(done.output_item_done_transition_plan.previously_streamed_item, active)
        self.assertEqual(
            done.output_item_done_transition_plan.assistant_text_flush_plan,
            SamplingAssistantTextFlushPlan(
                item_id="msg-1",
                parsed={"visible_text": "tail", "item_id": "msg-1"},
            ),
        )

        completed = sampling_stream_event_dispatch_plan(
            "completed",
            {"response_id": "resp-1", "token_usage": {"total": 3}, "end_turn": False},
            state=SamplingOutputState(last_agent_message="hello"),
        )
        self.assertEqual(
            completed,
            SamplingStreamEventDispatchPlan(
                event_type="completed",
                completed_event_plan=SamplingCompletedEventPlan(
                    response_id="resp-1",
                    token_usage={"total": 3},
                    needs_follow_up=True,
                    last_agent_message="hello",
                    completed_response_id="resp-1",
                ),
            ),
        )

    def test_sampling_stream_event_dispatch_plan_routes_deltas_and_metadata(self) -> None:
        active = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        self.assertEqual(
            sampling_stream_event_dispatch_plan(
                "output_text_delta",
                {"delta": "hello"},
                active_item=active,
                active_item_is_streaming_to_client=True,
                plan_mode=False,
            ),
            SamplingStreamEventDispatchPlan(
                event_type="output_text_delta",
                output_text_delta_plan=SamplingOutputTextDeltaPlan(
                    item_id="msg-1",
                    delta="hello",
                    parsed={"visible_text": "hello"},
                ),
            ),
        )

        reasoning = TurnItem.reasoning("rs-1", ())
        reasoning_delta = sampling_stream_event_dispatch_plan(
            "reasoning_summary_delta",
            {"delta": "summary"},
            active_item=reasoning,
            active_item_is_streaming_to_client=True,
            summary_index=0,
        )
        self.assertEqual(
            reasoning_delta.reasoning_delta_plan,
            SamplingReasoningDeltaPlan(
                event_type="reasoning_content_delta",
                item_id="rs-1",
                delta="summary",
                summary_index=0,
            ),
        )

        self.assertEqual(
            sampling_stream_event_dispatch_plan("server_model", "gpt-test"),
            SamplingStreamEventDispatchPlan(
                event_type="server_model",
                metadata_event_plan=SamplingMetadataEventPlan(
                    event_type="server_model",
                    payload="gpt-test",
                    should_maybe_warn_server_model_mismatch=True,
                    should_mark_server_model_warning_if_emitted=True,
                ),
            ),
        )

    def test_sampling_stream_event_apply_plan_routes_created_added_and_text_delta(self) -> None:
        self.assertEqual(
            sampling_stream_event_apply_plan(
                SamplingStreamEventDispatchPlan(event_type="created", no_op=True),
                plan_mode=False,
            ),
            SamplingStreamEventApplyPlan(event_type="created", no_op=True),
        )

        added_dispatch = SamplingStreamEventDispatchPlan(
            event_type="output_item_added",
            output_item_added_plan=sampling_output_item_added_plan(
                assistant_output_text("hello"),
                plan_mode=False,
            ),
        )
        added = sampling_stream_event_apply_plan(added_dispatch, plan_mode=False)
        self.assertEqual(added.event_type, "output_item_added")
        self.assertIsNotNone(added.output_item_added_apply_plan)
        self.assertIsNotNone(added.output_item_added_apply_plan.turn_item_started_to_emit)

        text_dispatch = SamplingStreamEventDispatchPlan(
            event_type="output_text_delta",
            output_text_delta_plan=SamplingOutputTextDeltaPlan(
                item_id="msg-1",
                delta="hello",
                parsed={"visible_text": "hello", "citations": (), "plan_segments": ()},
            ),
        )
        self.assertEqual(
            sampling_stream_event_apply_plan(text_dispatch, plan_mode=False),
            SamplingStreamEventApplyPlan(
                event_type="output_text_delta",
                output_text_delta_apply_plan=SamplingOutputTextDeltaApplyPlan(
                    item_id="msg-1",
                    streamed_assistant_text_plan=SamplingStreamedAssistantTextDeltaPlan(
                        item_id="msg-1",
                        visible_text_delta="hello",
                    ),
                ),
            ),
        )

    def test_sampling_stream_event_apply_plan_routes_done_and_completed(self) -> None:
        done_item = ResponseItem.reasoning(id="rs-1", content=())
        done_dispatch = SamplingStreamEventDispatchPlan(
            event_type="output_item_done",
            output_item_done_transition_plan=SamplingOutputItemDoneTransitionPlan(),
        )
        done = sampling_stream_event_apply_plan(
            done_dispatch,
            plan_mode=False,
            state=SamplingOutputState(),
            output_item_done_item=done_item,
            output_item_done_result=OutputItemResult(last_agent_message="tail"),
        )
        self.assertEqual(done.event_type, "output_item_done")
        self.assertIsNotNone(done.output_item_done_apply_plan)
        self.assertEqual(
            done.output_item_done_apply_plan.state_after_output_result,
            SamplingOutputState(last_agent_message="tail"),
        )

        class Parser:
            def drain_finished(self):
                return (("msg-1", {"visible_text": "tail"}),)

        completed_dispatch = SamplingStreamEventDispatchPlan(
            event_type="completed",
            completed_event_plan=SamplingCompletedEventPlan(
                response_id="resp-1",
                token_usage=None,
                needs_follow_up=False,
                completed_response_id="resp-1",
            ),
        )
        completed = sampling_stream_event_apply_plan(
            completed_dispatch,
            plan_mode=False,
            assistant_message_stream_parsers=Parser(),
        )
        self.assertEqual(completed.event_type, "completed")
        self.assertIsNotNone(completed.completed_event_apply_plan)
        self.assertEqual(completed.completed_event_apply_plan.completed_response_id_after, "resp-1")

    def test_sampling_metadata_event_plan_matches_rust_side_effect_flags(self) -> None:
        self.assertEqual(
            sampling_metadata_event_plan("server_model", "gpt-5", server_model_warning_emitted=False),
            SamplingMetadataEventPlan(
                event_type="server_model",
                payload="gpt-5",
                should_maybe_warn_server_model_mismatch=True,
                should_mark_server_model_warning_if_emitted=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_plan("model_verifications", {"verified": True}, model_verification_emitted=False),
            SamplingMetadataEventPlan(
                event_type="model_verifications",
                payload={"verified": True},
                should_emit_model_verification=True,
                should_mark_model_verification_emitted=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_plan("server_reasoning_included", True),
            SamplingMetadataEventPlan(
                event_type="server_reasoning_included",
                payload=True,
                should_set_server_reasoning_included=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_plan("rate_limits", {"remaining": 10}),
            SamplingMetadataEventPlan(
                event_type="rate_limits",
                payload={"remaining": 10},
                should_record_rate_limits=True,
                should_emit_token_count=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_plan("models_etag", "etag-1"),
            SamplingMetadataEventPlan(
                event_type="models_etag",
                payload="etag-1",
                should_refresh_models_etag=True,
            ),
        )

    def test_sampling_metadata_event_plan_respects_one_shot_latches_and_shapes(self) -> None:
        self.assertIsNone(
            sampling_metadata_event_plan("server_model", "gpt-5", server_model_warning_emitted=True)
        )
        self.assertIsNone(
            sampling_metadata_event_plan("model_verifications", {"verified": True}, model_verification_emitted=True)
        )
        with self.assertRaisesRegex(TypeError, "server_model must be a string"):
            sampling_metadata_event_plan("server_model", 5)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "server_reasoning_included must be a bool"):
            sampling_metadata_event_plan("server_reasoning_included", "yes")
        with self.assertRaisesRegex(ValueError, "unsupported sampling metadata event type"):
            sampling_metadata_event_plan("unknown", None)

    def test_sampling_metadata_event_apply_plan_maps_server_side_actions(self) -> None:
        self.assertEqual(
            sampling_metadata_event_apply_plan(sampling_metadata_event_plan("server_model", "gpt-5")),
            SamplingMetadataEventApplyPlan(
                event_type="server_model",
                server_model_to_check="gpt-5",
                should_mark_server_model_warning_if_emitted=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_apply_plan(
                sampling_metadata_event_plan("model_verifications", {"verified": True})
            ),
            SamplingMetadataEventApplyPlan(
                event_type="model_verifications",
                model_verification_to_emit={"verified": True},
                should_mark_model_verification_emitted=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_apply_plan(sampling_metadata_event_plan("server_reasoning_included", True)),
            SamplingMetadataEventApplyPlan(
                event_type="server_reasoning_included",
                server_reasoning_included=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_apply_plan(sampling_metadata_event_plan("rate_limits", {"remaining": 10})),
            SamplingMetadataEventApplyPlan(
                event_type="rate_limits",
                rate_limits_to_record={"remaining": 10},
                should_emit_token_count=True,
            ),
        )
        self.assertEqual(
            sampling_metadata_event_apply_plan(sampling_metadata_event_plan("models_etag", "etag-1")),
            SamplingMetadataEventApplyPlan(
                event_type="models_etag",
                models_etag_to_refresh="etag-1",
            ),
        )
        self.assertIsNone(sampling_metadata_event_apply_plan(None))

    def test_sampling_completed_event_plan_matches_rust_completion_branch(self) -> None:
        state = SamplingOutputState(
            needs_follow_up=False,
            last_agent_message="assistant tail",
        )

        plan = sampling_completed_event_plan(
            response_id="resp-1",
            token_usage={"input_tokens": 1},
            end_turn=True,
            state=state,
        )

        self.assertEqual(
            plan,
            SamplingCompletedEventPlan(
                response_id="resp-1",
                token_usage={"input_tokens": 1},
                needs_follow_up=False,
                last_agent_message="assistant tail",
                completed_response_id="resp-1",
                should_flush_assistant_text_segments_all=True,
                should_record_token_usage=True,
                should_emit_token_count=True,
                should_emit_turn_diff=True,
            ),
        )

    def test_sampling_completed_event_plan_forces_follow_up_when_end_turn_false(self) -> None:
        plan = sampling_completed_event_plan(
            response_id="resp-2",
            token_usage=None,
            end_turn=False,
            state=SamplingOutputState(needs_follow_up=False),
        )

        self.assertTrue(plan.needs_follow_up)
        self.assertEqual(plan.completed_response_id, "resp-2")

        preserved = sampling_completed_event_plan(
            response_id="resp-3",
            token_usage=None,
            end_turn=None,
            state=SamplingOutputState(needs_follow_up=True),
        )

        self.assertTrue(preserved.needs_follow_up)

        with self.assertRaisesRegex(TypeError, "response_id must be a string"):
            sampling_completed_event_plan(
                response_id=5,  # type: ignore[arg-type]
                token_usage=None,
                end_turn=True,
                state=SamplingOutputState(),
            )
        with self.assertRaisesRegex(TypeError, "end_turn must be a bool"):
            sampling_completed_event_plan(
                response_id="resp-4",
                token_usage=None,
                end_turn="false",  # type: ignore[arg-type]
                state=SamplingOutputState(),
            )
        with self.assertRaisesRegex(TypeError, "state must be a SamplingOutputState"):
            sampling_completed_event_plan(
                response_id="resp-5",
                token_usage=None,
                end_turn=True,
                state=object(),  # type: ignore[arg-type]
            )

    def test_sampling_completed_event_apply_plan_flushes_and_returns_result(self) -> None:
        class Parser:
            def drain_finished(self):
                return (
                    ("msg-1", {"visible_text": "tail"}),
                    ("msg-2", {"visible_text": ""}),
                )

        completed = SamplingCompletedEventPlan(
            response_id="resp-1",
            token_usage={"input_tokens": 1},
            needs_follow_up=True,
            last_agent_message="assistant tail",
            completed_response_id="resp-1",
        )

        self.assertEqual(
            sampling_completed_event_apply_plan(
                completed,
                assistant_message_stream_parsers=Parser(),
            ),
            SamplingCompletedEventApplyPlan(
                response_id="resp-1",
                flush_all_plan=SamplingAssistantTextFlushAllPlan(
                    (
                        SamplingAssistantTextFlushPlan("msg-1", {"visible_text": "tail"}),
                        SamplingAssistantTextFlushPlan("msg-2", {"visible_text": ""}),
                    )
                ),
                token_usage_to_record={"input_tokens": 1},
                should_record_token_usage=True,
                should_emit_token_count=True,
                should_emit_turn_diff=True,
                completed_response_id_after="resp-1",
                result_needs_follow_up=True,
                result_last_agent_message="assistant tail",
            ),
        )

    def test_sampling_completed_event_apply_plan_requires_parser_when_flushing(self) -> None:
        with self.assertRaisesRegex(TypeError, "assistant_message_stream_parsers is required"):
            sampling_completed_event_apply_plan(
                SamplingCompletedEventPlan(
                    response_id="resp-1",
                    token_usage=None,
                    needs_follow_up=False,
                    completed_response_id="resp-1",
                )
            )

    def test_sampling_plan_mode_assistant_done_plan_handles_assistant_message(self) -> None:
        item = assistant_output_text("final answer")
        previous = handle_non_tool_response_item(item, True)

        plan = sampling_plan_mode_assistant_done_plan(
            item,
            previously_active_item=previous,
        )

        self.assertTrue(plan.handled)
        self.assertTrue(plan.should_continue_loop)
        self.assertTrue(plan.should_complete_plan_item_from_message)
        self.assertIsNotNone(plan.finalized_turn_item)
        self.assertEqual(plan.last_agent_message, "final answer")
        self.assertTrue(plan.should_update_last_agent_message)
        self.assertTrue(plan.should_emit_agent_message_started_if_needed)
        self.assertTrue(plan.should_emit_agent_message_completed)
        self.assertFalse(plan.should_drop_empty_agent_message)
        self.assertEqual(plan.previously_active_item, previous)
        self.assertIsNone(plan.proposed_plan_completion_plan)
        self.assertIsNotNone(plan.turn_item_emit_plan)
        self.assertIsNotNone(plan.turn_item_emit_plan.agent_message_plan)
        self.assertEqual(
            plan.recording_plan,
            CompletedResponseItemRecordingPlan(defer_mailbox_delivery_to_next_turn=True),
        )

    def test_sampling_plan_mode_assistant_done_plan_drops_empty_agent_message_and_skips_non_assistant(self) -> None:
        empty = assistant_output_text("   ")

        plan = sampling_plan_mode_assistant_done_plan(empty)

        self.assertTrue(plan.handled)
        self.assertTrue(plan.should_continue_loop)
        self.assertTrue(plan.should_complete_plan_item_from_message)
        self.assertIsNone(plan.proposed_plan_completion_plan)
        self.assertEqual(plan.finalized_turn_item, finalize_non_tool_response_item(empty, True))
        self.assertEqual(
            plan.recording_plan,
            CompletedResponseItemRecordingPlan(defer_mailbox_delivery_to_next_turn=False),
        )
        self.assertIsNone(plan.last_agent_message)
        self.assertFalse(plan.should_update_last_agent_message)
        self.assertFalse(plan.should_emit_agent_message_started_if_needed)
        self.assertFalse(plan.should_emit_agent_message_completed)
        self.assertTrue(plan.should_drop_empty_agent_message)
        self.assertIsNotNone(plan.turn_item_emit_plan)
        self.assertIsNotNone(plan.turn_item_emit_plan.agent_message_plan)
        self.assertTrue(plan.turn_item_emit_plan.agent_message_plan.should_drop_empty_agent_message)
        self.assertEqual(
            sampling_plan_mode_assistant_done_plan(ResponseItem.function_call("shell", "{}", "call-1")),
            SamplingPlanModeAssistantDonePlan(handled=False),
        )

        with self.assertRaisesRegex(TypeError, "previously_active_item must be a TurnItem"):
            sampling_plan_mode_assistant_done_plan(
                empty,
                previously_active_item=object(),  # type: ignore[arg-type]
            )

    def test_sampling_plan_mode_assistant_done_plan_completes_embedded_plan_text(self) -> None:
        item = assistant_output_text("<proposed_plan>- step</proposed_plan>")

        plan = sampling_plan_mode_assistant_done_plan(
            item,
            plan_item_id="turn-1-plan",
            plan_item_started=False,
            plan_item_completed=False,
        )

        self.assertEqual(
            plan.proposed_plan_completion_plan,
            SamplingProposedPlanCompletionPlan(
                plan_item_id="turn-1-plan",
                plan_text="- step",
                should_start_plan_item=True,
                should_complete_plan_item=True,
                plan_item_started_after=True,
                plan_item_completed_after=True,
            ),
        )

    def test_sampling_plan_segments_plan_buffers_leading_whitespace_and_emits_normal_text(self) -> None:
        buffered = sampling_plan_segments_plan(
            "msg-1",
            (("normal", "  \n"),),
            started_agent_message_item_ids=(),
            leading_whitespace_by_item={},
            plan_item_id="turn-1-plan",
        )

        self.assertEqual(
            buffered,
            SamplingPlanSegmentsPlan(
                actions=(),
                leading_whitespace_by_item_after=(("msg-1", "  \n"),),
                plan_item_started_after=False,
                plan_item_completed_after=False,
            ),
        )

        emitted = sampling_plan_segments_plan(
            "msg-1",
            (("normal", "Visible"),),
            started_agent_message_item_ids=(),
            leading_whitespace_by_item={"msg-1": "  \n"},
            plan_item_id="turn-1-plan",
        )

        self.assertEqual(
            emitted,
            SamplingPlanSegmentsPlan(
                actions=(
                    SamplingPlanSegmentAction("emit_pending_agent_message_start", "msg-1"),
                    SamplingPlanSegmentAction("agent_message_delta", "msg-1", "  \nVisible"),
                ),
                leading_whitespace_by_item_after=(),
                plan_item_started_after=False,
                plan_item_completed_after=False,
            ),
        )

    def test_sampling_plan_segments_plan_starts_plan_and_emits_plan_delta(self) -> None:
        plan = sampling_plan_segments_plan(
            "msg-1",
            (
                ("proposed_plan_start",),
                ("proposed_plan_delta", "- step\n"),
                ("proposed_plan_end",),
            ),
            plan_item_started=False,
            plan_item_completed=False,
            plan_item_id="turn-1-plan",
        )

        self.assertEqual(
            plan,
            SamplingPlanSegmentsPlan(
                actions=(
                    SamplingPlanSegmentAction("start_plan_item", "turn-1-plan"),
                    SamplingPlanSegmentAction("plan_delta", "turn-1-plan", "- step\n"),
                ),
                leading_whitespace_by_item_after=(),
                plan_item_started_after=True,
                plan_item_completed_after=False,
            ),
        )

        completed = sampling_plan_segments_plan(
            "msg-1",
            (("proposed_plan_delta", "- ignored\n"),),
            plan_item_started=True,
            plan_item_completed=True,
            plan_item_id="turn-1-plan",
        )

        self.assertEqual(
            completed,
            SamplingPlanSegmentsPlan(
                actions=(),
                leading_whitespace_by_item_after=(),
                plan_item_started_after=True,
                plan_item_completed_after=True,
            ),
        )

        with self.assertRaisesRegex(ValueError, "unsupported plan segment type"):
            sampling_plan_segments_plan("msg-1", (("mystery", ""),))

    def test_sampling_proposed_plan_completion_plan_extracts_and_strips_citations(self) -> None:
        item = assistant_output_text(
            "Intro\n<proposed_plan>\n- Step 1\n"
            "<oai-mem-citation>plan-doc</oai-mem-citation>\n"
            "- Step 2\n</proposed_plan>\nOutro"
        )

        plan = sampling_proposed_plan_completion_plan(
            item,
            plan_item_id="turn-1-plan",
            plan_item_started=False,
            plan_item_completed=False,
        )

        self.assertEqual(
            plan,
            SamplingProposedPlanCompletionPlan(
                plan_item_id="turn-1-plan",
                plan_text="\n- Step 1\n\n- Step 2\n",
                should_start_plan_item=True,
                should_complete_plan_item=True,
                plan_item_started_after=True,
                plan_item_completed_after=True,
            ),
        )

    def test_sampling_proposed_plan_completion_plan_skips_missing_or_completed_plan(self) -> None:
        self.assertIsNone(
            sampling_proposed_plan_completion_plan(
                assistant_output_text("No plan here"),
                plan_item_id="turn-1-plan",
                plan_item_started=False,
                plan_item_completed=False,
            )
        )
        self.assertIsNone(
            sampling_proposed_plan_completion_plan(
                ResponseItem.function_call("shell", "{}", "call-1"),
                plan_item_id="turn-1-plan",
                plan_item_started=False,
                plan_item_completed=False,
            )
        )

        completed = sampling_proposed_plan_completion_plan(
            assistant_output_text("<proposed_plan>\n- Step\n</proposed_plan>"),
            plan_item_id="turn-1-plan",
            plan_item_started=True,
            plan_item_completed=True,
        )

        self.assertEqual(
            completed,
            SamplingProposedPlanCompletionPlan(
                plan_item_id="turn-1-plan",
                plan_text="\n- Step\n",
                should_start_plan_item=False,
                should_complete_plan_item=False,
                plan_item_started_after=True,
                plan_item_completed_after=True,
            ),
        )

        with self.assertRaisesRegex(TypeError, "plan_item_started must be a bool"):
            sampling_proposed_plan_completion_plan(
                assistant_output_text("<proposed_plan>x</proposed_plan>"),
                plan_item_id="turn-1-plan",
                plan_item_started="yes",  # type: ignore[arg-type]
                plan_item_completed=False,
            )

    def test_sampling_pending_agent_message_start_plan_starts_pending_once(self) -> None:
        pending_item = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        plan = sampling_pending_agent_message_start_plan(
            "msg-1",
            pending_agent_message_items={"msg-1": pending_item, "msg-2": pending_item},
            started_agent_message_item_ids=(),
        )

        self.assertEqual(
            plan,
            SamplingPendingAgentMessageStartPlan(
                item_id="msg-1",
                turn_item_to_start=pending_item,
                started_agent_message_item_ids_after=("msg-1",),
                pending_agent_message_item_ids_after=("msg-2",),
            ),
        )
        self.assertIsNone(
            sampling_pending_agent_message_start_plan(
                "msg-1",
                pending_agent_message_items={"msg-1": pending_item},
                started_agent_message_item_ids=("msg-1",),
            )
        )
        self.assertIsNone(
            sampling_pending_agent_message_start_plan(
                "missing",
                pending_agent_message_items={"msg-1": pending_item},
                started_agent_message_item_ids=(),
            )
        )

    def test_sampling_plan_mode_agent_message_emit_plan_drops_empty_and_completes_visible_text(self) -> None:
        pending_item = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content(""),))
        )

        empty = sampling_plan_mode_agent_message_emit_plan(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content("   "),)),
            pending_agent_message_items={"msg-1": pending_item},
            started_agent_message_item_ids=("msg-1",),
        )

        self.assertEqual(
            empty,
            SamplingPlanModeAgentMessageEmitPlan(
                item_id="msg-1",
                text="   ",
                should_drop_empty_agent_message=True,
                started_agent_message_item_ids_after=(),
                pending_agent_message_item_ids_after=(),
            ),
        )

        visible = sampling_plan_mode_agent_message_emit_plan(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content("hello"),)),
            pending_agent_message_items={"msg-1": pending_item},
            started_agent_message_item_ids=(),
        )

        self.assertEqual(
            visible,
            SamplingPlanModeAgentMessageEmitPlan(
                item_id="msg-1",
                text="hello",
                pending_start_plan=SamplingPendingAgentMessageStartPlan(
                    item_id="msg-1",
                    turn_item_to_start=pending_item,
                    started_agent_message_item_ids_after=("msg-1",),
                    pending_agent_message_item_ids_after=(),
                ),
                fallback_start_item=None,
                should_emit_completed=True,
                started_agent_message_item_ids_after=(),
                pending_agent_message_item_ids_after=(),
            ),
        )

    def test_sampling_plan_mode_agent_message_emit_plan_uses_fallback_start_when_missing_pending_item(self) -> None:
        plan = sampling_plan_mode_agent_message_emit_plan(
            AgentMessageItem(id="msg-9", content=(AgentMessageContent.text_content("hello"),)),
            pending_agent_message_items={},
            started_agent_message_item_ids=(),
        )

        self.assertIsNone(plan.pending_start_plan)
        self.assertIsNotNone(plan.fallback_start_item)
        self.assertTrue(plan.should_emit_completed)
        self.assertEqual(plan.started_agent_message_item_ids_after, ())

        with self.assertRaisesRegex(TypeError, "agent_message must be an AgentMessageItem"):
            sampling_plan_mode_agent_message_emit_plan(object())  # type: ignore[arg-type]

    def test_sampling_plan_mode_turn_item_emit_plan_delegates_agent_messages(self) -> None:
        turn_item = TurnItem.agent_message(
            AgentMessageItem(id="msg-1", content=(AgentMessageContent.text_content("hello"),))
        )

        plan = sampling_plan_mode_turn_item_emit_plan(turn_item)

        self.assertEqual(
            plan,
            SamplingPlanModeTurnItemEmitPlan(
                turn_item=turn_item,
                agent_message_plan=SamplingPlanModeAgentMessageEmitPlan(
                    item_id="msg-1",
                    text="hello",
                    fallback_start_item=TurnItem.agent_message(
                        AgentMessageItem(
                            id="msg-1",
                            content=(),
                            phase=None,
                            memory_citation=None,
                        )
                    ),
                    should_emit_completed=True,
                    started_agent_message_item_ids_after=(),
                    pending_agent_message_item_ids_after=(),
                ),
            ),
        )

    def test_sampling_plan_mode_turn_item_emit_plan_emits_non_agent_turn_items(self) -> None:
        turn_item = TurnItem.reasoning("rs-1", ())

        self.assertEqual(
            sampling_plan_mode_turn_item_emit_plan(turn_item),
            SamplingPlanModeTurnItemEmitPlan(
                turn_item=turn_item,
                should_emit_started=True,
                should_emit_completed=True,
            ),
        )
        self.assertEqual(
            sampling_plan_mode_turn_item_emit_plan(turn_item, previously_active_item=turn_item),
            SamplingPlanModeTurnItemEmitPlan(
                turn_item=turn_item,
                should_emit_started=False,
                should_emit_completed=True,
            ),
        )

    def test_sampling_in_flight_tool_result_plan_records_converted_response_item(self) -> None:
        result = ResponseInputItem.function_call_output("call-1", "ok")
        response_item = response_input_to_response_item(result)
        self.assertIsNotNone(response_item)

        plan = sampling_in_flight_tool_result_plan(result)

        self.assertEqual(
            plan,
            SamplingInFlightToolResultPlan(
                response_item=response_item,
                should_record_conversation_item=True,
                should_mark_thread_memory_mode_polluted=False,
            ),
        )

    def test_sampling_in_flight_tool_result_plan_marks_external_context_when_configured(self) -> None:
        result = ResponseInputItem.tool_search_output("call-1", "completed", "client", ())

        plan = sampling_in_flight_tool_result_plan(
            result,
            memories_disable_on_external_context=True,
        )

        self.assertTrue(plan.should_record_conversation_item)
        self.assertTrue(plan.should_mark_thread_memory_mode_polluted)

    def test_sampling_in_flight_tool_result_plan_reports_future_errors(self) -> None:
        plan = sampling_in_flight_tool_result_plan(RuntimeError("boom"))

        self.assertEqual(
            plan,
            SamplingInFlightToolResultPlan(
                error_message="in-flight tool future failed during drain: boom",
                should_error_or_panic=True,
            ),
        )

        with self.assertRaisesRegex(TypeError, "result must be a ResponseInputItem"):
            sampling_in_flight_tool_result_plan(object())

    def test_agent_message_text_concatenates_text_entries_like_rust(self) -> None:
        item = AgentMessageItem(
            id="msg-1",
            content=(
                AgentMessageContent.text_content("hello "),
                AgentMessageContent.text_content("world"),
            ),
        )

        self.assertEqual(agent_message_text(item), "hello world")

        with self.assertRaisesRegex(TypeError, "item must be an AgentMessageItem"):
            agent_message_text(object())  # type: ignore[arg-type]

    def test_realtime_text_for_event_matches_rust_agent_message_paths(self) -> None:
        turn_item = TurnItem.agent_message(
            AgentMessageItem(
                id="msg-1",
                content=(AgentMessageContent.text_content("completed text"),),
            )
        )

        self.assertEqual(
            realtime_text_for_event({"type": "agent_message", "message": "legacy text"}),
            "legacy text",
        )
        self.assertEqual(
            realtime_text_for_event({"type": "item_completed", "item": turn_item}),
            "completed text",
        )
        self.assertIsNone(
            realtime_text_for_event({"type": "agent_message_content_delta", "delta": "ignored"})
        )
        self.assertIsNone(
            realtime_text_for_event({"type": "item_completed", "item": TurnItem.reasoning("rs-1", ())})
        )

    def test_completed_response_item_recording_plan_falls_back_to_item_deferral(self) -> None:
        final_message = assistant_output_text("final answer")

        plan = completed_response_item_recording_plan(final_message, plan_mode=False)

        self.assertEqual(
            plan,
            CompletedResponseItemRecordingPlan(defer_mailbox_delivery_to_next_turn=True),
        )

    def test_completed_response_item_recording_plan_uses_finalized_facts(self) -> None:
        facts = FinalizedTurnItemFacts(
            memory_citation={"turn": 1},
            defers_mailbox_delivery_to_next_turn=True,
        )

        plan = completed_response_item_recording_plan(
            assistant_output_text("analysis", MessagePhase.POST_COMPACT),
            plan_mode=False,
            finalized_facts=facts,
        )

        self.assertTrue(plan.defer_mailbox_delivery_to_next_turn)
        self.assertEqual(plan.memory_citation, {"turn": 1})

    def test_completed_response_item_recording_plan_marks_external_context_pollution(self) -> None:
        web_search = ResponseItem.web_search_call("call-1", "completed")

        plan = completed_response_item_recording_plan(
            web_search,
            plan_mode=False,
            memories_disable_on_external_context=True,
        )

        self.assertTrue(plan.mark_thread_memory_mode_polluted)
        self.assertFalse(
            completed_response_item_recording_plan(
                web_search,
                plan_mode=False,
                memories_disable_on_external_context=False,
            ).mark_thread_memory_mode_polluted
        )

    def test_record_completed_response_item_applies_memory_side_effects_from_plan(self) -> None:
        class InputQueue:
            def __init__(self):
                self.deferred = []

            async def defer_mailbox_delivery_to_next_turn(self, active_turn, sub_id):
                self.deferred.append((active_turn, sub_id))

        class Session:
            def __init__(self):
                self.active_turn = "turn-1"
                self.input_queue = InputQueue()
                self.recorded = []
                self.polluted = []
                self.citations = []

            async def record_conversation_items(self, turn_context, items):
                self.recorded.extend(items)

            async def mark_thread_memory_mode_polluted(self, sub_id):
                self.polluted.append(sub_id)

            async def record_memory_citation_for_turn(self, sub_id):
                self.citations.append(sub_id)

        session = Session()
        turn_context = SimpleNamespace(
            collaboration_mode=SimpleNamespace(mode="default"),
            config=SimpleNamespace(memories=SimpleNamespace(disable_on_external_context=True)),
            sub_id="sub-1",
        )
        item = ResponseItem.web_search_call("call-1", "completed")
        facts = FinalizedTurnItemFacts(
            memory_citation={"memory": "m1"},
            defers_mailbox_delivery_to_next_turn=True,
        )

        _run_async(record_completed_response_item_with_finalized_facts(session, turn_context, item, facts))

        self.assertEqual(session.recorded, [item])
        self.assertEqual(session.input_queue.deferred, [("turn-1", "sub-1")])
        self.assertEqual(session.polluted, ["sub-1"])
        self.assertEqual(session.citations, ["sub-1"])

    def test_record_completed_response_item_detects_memory_citation_without_finalized_facts(self) -> None:
        class Memories:
            def __init__(self):
                self.stage1 = []

            async def record_stage1_output_usage(self, thread_ids):
                self.stage1.append(tuple(thread_ids))

        class Session:
            def __init__(self):
                self.memories = Memories()
                self.services = SimpleNamespace(state_db=SimpleNamespace(memories=lambda: self.memories))
                self.citations = []

            async def record_conversation_items(self, turn_context, items):
                pass

            async def record_memory_citation_for_turn(self, sub_id):
                self.citations.append(sub_id)

        session = Session()
        turn_context = SimpleNamespace(
            collaboration_mode=SimpleNamespace(mode="default"),
            config=SimpleNamespace(memories=SimpleNamespace(disable_on_external_context=False)),
            sub_id="sub-1",
        )
        item = assistant_output_text(
            "hello<oai-mem-citation><citation_entries>\n"
            "MEMORY.md:1-2|note=[x]\n"
            "</citation_entries>\n"
            "<rollout_ids>\n"
            "rollout-1\n"
            "</rollout_ids></oai-mem-citation> world"
        )

        _run_async(record_completed_response_item_with_finalized_facts(session, turn_context, item, None))

        self.assertEqual(session.memories.stage1, [("rollout-1",)])
        self.assertEqual(session.citations, ["sub-1"])

    def test_stream_event_helpers_reject_non_rust_item_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "item must be a ResponseItem"):
            response_item_may_include_external_context(object())  # type: ignore[arg-type]

        with self.assertRaisesRegex(TypeError, "plan_mode must be a bool"):
            completed_item_defers_mailbox_delivery_to_next_turn(
                assistant_output_text("hi"),
                plan_mode="false",  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(TypeError, "input_item must be a ResponseInputItem"):
            response_input_to_response_item(object())  # type: ignore[arg-type]

        with self.assertRaisesRegex(TypeError, "finalized_facts must be FinalizedTurnItemFacts or None"):
            completed_response_item_recording_plan(
                assistant_output_text("hi"),
                plan_mode=False,
                finalized_facts=object(),  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()


def _run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
