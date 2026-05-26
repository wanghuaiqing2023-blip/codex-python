import tempfile
import unittest
from pathlib import Path

from pycodex.core import (
    GENERATED_IMAGE_ARTIFACTS_DIR,
    completed_item_defers_mailbox_delivery_to_next_turn,
    image_generation_artifact_path,
    last_assistant_message_from_item,
    response_input_to_response_item,
    response_item_may_include_external_context,
    save_image_generation_result,
    strip_hidden_assistant_markup,
)
from pycodex.protocol import (
    ContentItem,
    MessagePhase,
    ResponseInputItem,
    ResponseItem,
)


def assistant_output_text(text: str, phase: MessagePhase | None = None) -> ResponseItem:
    return ResponseItem.message(
        "assistant",
        (ContentItem.output_text(text),),
        id="msg-1",
        phase=phase,
    )


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


if __name__ == "__main__":
    unittest.main()
