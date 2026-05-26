import unittest

from pycodex.core import (
    GoalContext,
    has_non_contextual_dev_message_content,
    is_contextual_dev_message_content,
    parse_turn_item,
)
from pycodex.protocol import (
    AgentMessageContent,
    ContentItem,
    DEFAULT_IMAGE_DETAIL,
    HookPromptFragment,
    ImageGenerationItem,
    ReasoningItemContent,
    ReasoningItemReasoningSummary,
    ResponseItem,
    TurnItem,
    UserInput,
    WebSearchAction,
    WebSearchItem,
    build_hook_prompt_message,
    image_close_tag_text,
    image_open_tag_text,
    local_image_open_tag_text,
)


class CoreEventMappingTests(unittest.TestCase):
    def test_parses_user_message_with_text_and_two_images(self) -> None:
        img1 = "https://example.com/one.png"
        img2 = "https://example.com/two.jpg"
        item = ResponseItem.message(
            "user",
            (
                ContentItem.input_text("Hello world"),
                ContentItem.input_image(img1, detail=DEFAULT_IMAGE_DETAIL),
                ContentItem.input_image(img2, detail=DEFAULT_IMAGE_DETAIL),
            ),
        )

        turn_item = parse_turn_item(item)

        self.assertIsNotNone(turn_item)
        self.assertEqual(turn_item.type, "UserMessage")
        self.assertEqual(
            turn_item.item.content,
            (
                UserInput.text_input("Hello world"),
                UserInput.image(img1, detail=DEFAULT_IMAGE_DETAIL),
                UserInput.image(img2, detail=DEFAULT_IMAGE_DETAIL),
            ),
        )

    def test_skips_image_label_text(self) -> None:
        image_url = "data:image/png;base64,abc"
        item = ResponseItem.message(
            "user",
            (
                ContentItem.input_text(local_image_open_tag_text(1)),
                ContentItem.input_image(image_url, detail=DEFAULT_IMAGE_DETAIL),
                ContentItem.input_text(image_close_tag_text()),
                ContentItem.input_text("Please review this image."),
            ),
        )

        turn_item = parse_turn_item(item)

        self.assertIsNotNone(turn_item)
        self.assertEqual(
            turn_item.item.content,
            (
                UserInput.image(image_url, detail=DEFAULT_IMAGE_DETAIL),
                UserInput.text_input("Please review this image."),
            ),
        )

    def test_skips_unnamed_image_label_text(self) -> None:
        image_url = "data:image/png;base64,abc"
        item = ResponseItem.message(
            "user",
            (
                ContentItem.input_text(image_open_tag_text()),
                ContentItem.input_image(image_url, detail=DEFAULT_IMAGE_DETAIL),
                ContentItem.input_text(image_close_tag_text()),
            ),
        )

        turn_item = parse_turn_item(item)

        self.assertIsNotNone(turn_item)
        self.assertEqual(turn_item.item.content, (UserInput.image(image_url, detail=DEFAULT_IMAGE_DETAIL),))

    def test_skips_contextual_user_messages(self) -> None:
        items = (
            ResponseItem.message("user", (ContentItem.input_text("<environment_context>ctx</environment_context>"),)),
            ResponseItem.message("user", (ContentItem.input_text(GoalContext("Continue working.").render()),)),
            ResponseItem.message(
                "user",
                (
                    ContentItem.input_text("<environment_context>ctx</environment_context>"),
                    ContentItem.input_text("# AGENTS.md instructions for dir\n\n<INSTRUCTIONS>\nbody\n</INSTRUCTIONS>"),
                ),
            ),
        )

        for item in items:
            self.assertIsNone(parse_turn_item(item))

    def test_parses_hook_prompt_message_as_distinct_turn_item(self) -> None:
        item = build_hook_prompt_message(
            (HookPromptFragment.from_single_hook("Retry with exactly the requested phrase.", "hook-run-1"),)
        )
        self.assertIsNotNone(item)

        turn_item = parse_turn_item(item)

        self.assertIsNotNone(turn_item)
        self.assertEqual(turn_item.type, "HookPrompt")
        self.assertEqual(
            turn_item.item.fragments,
            (HookPromptFragment(text="Retry with exactly the requested phrase.", hook_run_id="hook-run-1"),),
        )

    def test_parses_hook_prompt_and_hides_other_contextual_fragments(self) -> None:
        item = ResponseItem.message(
            "user",
            (
                ContentItem.input_text("<environment_context>ctx</environment_context>"),
                ContentItem.input_text(
                    "<hook_prompt hook_run_id=\"hook-run-1\">Retry with care &amp; joy.</hook_prompt>"
                ),
            ),
            id="msg-1",
        )

        turn_item = parse_turn_item(item)

        self.assertIsNotNone(turn_item)
        self.assertEqual(turn_item.type, "HookPrompt")
        self.assertEqual(turn_item.item.id, "msg-1")
        self.assertEqual(
            turn_item.item.fragments,
            (HookPromptFragment(text="Retry with care & joy.", hook_run_id="hook-run-1"),),
        )

    def test_parses_assistant_message_input_text_for_backward_compatibility(self) -> None:
        text = "author: /root\nrecipient: /root/worker\nother_recipients: []\nContent: continue"
        item = ResponseItem.message("assistant", (ContentItem.input_text(text),))

        turn_item = parse_turn_item(item)

        self.assertIsNotNone(turn_item)
        self.assertEqual(turn_item.type, "AgentMessage")
        self.assertEqual(turn_item.item.content, (AgentMessageContent.text_content(text),))

    def test_parses_reasoning_summary_and_raw_content(self) -> None:
        item = ResponseItem(
            "reasoning",
            id="reasoning_1",
            summary=(
                ReasoningItemReasoningSummary.summary_text("Step 1"),
                ReasoningItemReasoningSummary.summary_text("Step 2"),
            ),
            reasoning_content=(
                ReasoningItemContent.reasoning_text("raw step"),
                ReasoningItemContent.text_content("final thought"),
            ),
        )

        turn_item = parse_turn_item(item)

        self.assertIsNotNone(turn_item)
        self.assertEqual(turn_item.type, "Reasoning")
        self.assertEqual(turn_item.item.summary_text, ("Step 1", "Step 2"))
        self.assertEqual(turn_item.item.raw_content, ("raw step", "final thought"))

    def test_parses_web_search_calls(self) -> None:
        cases = (
            (
                ResponseItem.web_search_call("ws_1", "completed", WebSearchAction.search(query="weather")),
                WebSearchItem("ws_1", "weather", WebSearchAction.search(query="weather")),
            ),
            (
                ResponseItem.web_search_call("ws_open", "completed", WebSearchAction.open_page("https://example.com")),
                WebSearchItem("ws_open", "https://example.com", WebSearchAction.open_page("https://example.com")),
            ),
            (
                ResponseItem.web_search_call(
                    "ws_find",
                    "completed",
                    WebSearchAction.find_in_page("https://example.com", "needle"),
                ),
                WebSearchItem(
                    "ws_find",
                    "'needle' in https://example.com",
                    WebSearchAction.find_in_page("https://example.com", "needle"),
                ),
            ),
            (
                ResponseItem.web_search_call("ws_partial", "in_progress", None),
                WebSearchItem("ws_partial", "", WebSearchAction.other()),
            ),
        )

        for item, expected in cases:
            self.assertEqual(parse_turn_item(item), TurnItem.web_search(expected))

    def test_parses_image_generation_call(self) -> None:
        item = ResponseItem.image_generation_call("ig-1", "completed", "Zm9v", revised_prompt="draw it")

        self.assertEqual(
            parse_turn_item(item),
            TurnItem.image_generation(ImageGenerationItem("ig-1", "completed", "Zm9v", "draw it")),
        )

    def test_contextual_dev_fragment_helpers(self) -> None:
        contextual = ContentItem.input_text("  <MODEL_SWITCH>\ngpt-5</model_switch>")
        plain = ContentItem.input_text("Persistent project guidance")

        self.assertTrue(is_contextual_dev_message_content((contextual, plain)))
        self.assertTrue(has_non_contextual_dev_message_content((contextual, plain)))
        self.assertFalse(has_non_contextual_dev_message_content((contextual,)))


if __name__ == "__main__":
    unittest.main()
