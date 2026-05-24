import unittest
import uuid
from pathlib import Path

from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    MAX_USER_INPUT_TEXT_CHARS,
    ByteRange,
    ImageDetail,
    SessionId,
    TextElement,
    ThreadId,
    ToolName,
    UserInput,
)


class ProtocolIdsToolUserInputTests(unittest.TestCase):
    def test_thread_id_default_is_not_zeroes_and_parses_strings(self):
        thread_id = ThreadId.default()

        self.assertNotEqual(thread_id.uuid, uuid.UUID(int=0))
        self.assertEqual(ThreadId.from_string(str(thread_id)), thread_id)
        self.assertEqual(thread_id.to_json(), str(thread_id))

    def test_session_id_default_is_not_zeroes_and_converts_to_thread_id(self):
        thread_id = ThreadId.new()
        session_id = SessionId.from_thread_id(thread_id)

        self.assertNotEqual(SessionId.default().uuid, uuid.UUID(int=0))
        self.assertEqual(session_id.to_thread_id(), thread_id)
        self.assertEqual(SessionId.from_string(str(session_id)), session_id)

    def test_tool_name_display_preserves_upstream_namespace_join(self):
        self.assertEqual(str(ToolName.plain("shell")), "shell")
        self.assertEqual(str(ToolName.namespaced("mcp__", "fetch")), "mcp__fetch")
        self.assertEqual(ToolName.new(None, "plain"), ToolName.plain("plain"))

    def test_tool_name_order_matches_upstream_tuple_order(self):
        names = [
            ToolName.namespaced("foo", "bar"),
            ToolName.plain("zeta"),
            ToolName.plain("foo"),
            ToolName.namespaced("alpha", "tool"),
        ]

        self.assertEqual(
            sorted(names),
            [
                ToolName.namespaced("alpha", "tool"),
                ToolName.plain("foo"),
                ToolName.namespaced("foo", "bar"),
                ToolName.plain("zeta"),
            ],
        )

    def test_image_detail_values_match_upstream(self):
        self.assertIs(DEFAULT_IMAGE_DETAIL, ImageDetail.HIGH)
        self.assertEqual(ImageDetail.HIGH.to_json(), "high")
        self.assertEqual(ImageDetail.ORIGINAL.to_json(), "original")

    def test_text_element_placeholder_uses_explicit_value_first(self):
        element = TextElement.new(ByteRange(0, 4), "shown")

        self.assertEqual(element.placeholder("text"), "shown")
        self.assertEqual(element.placeholder_for_conversion_only(), "shown")

    def test_text_element_placeholder_falls_back_to_utf8_byte_range(self):
        text = "a\u732bb"
        start = len("a".encode("utf-8"))
        end = len("a\u732b".encode("utf-8"))
        element = TextElement.new(ByteRange(start, end), None)

        self.assertEqual(element.placeholder(text), "\u732b")
        self.assertIsNone(TextElement.new(ByteRange(start, start + 1), None).placeholder(text))
        self.assertIsNone(TextElement.new(ByteRange(0, 99), None).placeholder(text))

    def test_text_element_map_range_and_set_placeholder(self):
        element = TextElement.new(ByteRange(1, 3), None)
        mapped = element.map_range(lambda byte_range: ByteRange(byte_range.start + 2, byte_range.end + 2))
        element.set_placeholder("manual")

        self.assertEqual(mapped.byte_range, ByteRange(3, 5))
        self.assertIsNone(mapped.placeholder_for_conversion_only())
        self.assertEqual(element.placeholder("abcdef"), "manual")

    def test_user_input_variants_emit_upstream_type_names(self):
        text_element = TextElement.new(ByteRange(0, 4), "test")

        self.assertEqual(MAX_USER_INPUT_TEXT_CHARS, 1 << 20)
        self.assertEqual(
            UserInput.text_input("test", (text_element,)).to_mapping(),
            {
                "type": "text",
                "text": "test",
                "text_elements": [{"byte_range": {"start": 0, "end": 4}, "placeholder": "test"}],
            },
        )
        self.assertEqual(
            UserInput.text_input("hello").to_mapping(),
            {"type": "text", "text": "hello", "text_elements": []},
        )
        self.assertEqual(UserInput.from_mapping({"type": "text", "text": "hello"}), UserInput.text_input("hello"))
        self.assertEqual(
            UserInput.image("data:image/png;base64,abc", detail=ImageDetail.HIGH).to_mapping(),
            {"type": "image", "image_url": "data:image/png;base64,abc", "detail": "high"},
        )
        self.assertEqual(
            UserInput.local_image(Path("image.png"), detail=ImageDetail.ORIGINAL).to_mapping(),
            {"type": "local_image", "path": "image.png", "detail": "original"},
        )
        self.assertEqual(
            UserInput.skill("python", Path("SKILL.md")).to_mapping(),
            {"type": "skill", "name": "python", "path": "SKILL.md"},
        )
        self.assertEqual(
            UserInput.mention("GitHub", "app://github").to_mapping(),
            {"type": "mention", "name": "GitHub", "path": "app://github"},
        )


if __name__ == "__main__":
    unittest.main()
