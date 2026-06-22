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

        with self.assertRaisesRegex(TypeError, "thread id uuid must be a UUID"):
            ThreadId("11111111-1111-1111-1111-111111111111")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "thread id must be a string"):
            ThreadId.from_string(123)  # type: ignore[arg-type]

    def test_session_id_default_is_not_zeroes_and_converts_to_thread_id(self):
        thread_id = ThreadId.new()
        session_id = SessionId.from_thread_id(thread_id)

        self.assertNotEqual(SessionId.default().uuid, uuid.UUID(int=0))
        self.assertEqual(session_id.to_thread_id(), thread_id)
        self.assertEqual(SessionId.from_string(str(session_id)), session_id)

        with self.assertRaisesRegex(TypeError, "session id uuid must be a UUID"):
            SessionId("11111111-1111-1111-1111-111111111111")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "session id must be a string"):
            SessionId.from_string(123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "value must be a ThreadId"):
            SessionId.from_thread_id("11111111-1111-1111-1111-111111111111")  # type: ignore[arg-type]

    def test_tool_name_display_preserves_upstream_namespace_join(self):
        self.assertEqual(str(ToolName.plain("shell")), "shell")
        self.assertEqual(str(ToolName.namespaced("mcp__", "fetch")), "mcp__fetch")
        self.assertEqual(ToolName.new(None, "plain"), ToolName.plain("plain"))
        self.assertEqual(ToolName.from_value("shell"), ToolName.plain("shell"))
        namespaced = ToolName.namespaced("mcp__", "fetch")
        self.assertIs(ToolName.from_value(namespaced), namespaced)

    def test_tool_name_mapping_matches_serde_shape(self):
        plain = ToolName.from_mapping({"name": "shell"})
        namespaced = ToolName.from_mapping({"name": "fetch", "namespace": "mcp__"})

        self.assertEqual(plain, ToolName.plain("shell"))
        self.assertEqual(plain.to_mapping(), {"name": "shell", "namespace": None})
        self.assertEqual(namespaced, ToolName.namespaced("mcp__", "fetch"))
        self.assertEqual(namespaced.to_mapping(), {"name": "fetch", "namespace": "mcp__"})

    def test_tool_name_rejects_non_serde_shapes(self):
        with self.assertRaisesRegex(TypeError, "name must be a string"):
            ToolName.plain(123)

        with self.assertRaisesRegex(TypeError, "namespace must be a string or None"):
            ToolName.namespaced(123, "fetch")

        with self.assertRaisesRegex(TypeError, "ToolName value must be ToolName or string"):
            ToolName.from_value(123)

        with self.assertRaisesRegex(TypeError, "ToolName must be decoded from an object"):
            ToolName.from_mapping("shell")

        with self.assertRaisesRegex(TypeError, "name must be a string"):
            ToolName.from_mapping({"namespace": "mcp__"})

        with self.assertRaisesRegex(TypeError, "namespace must be a string or None"):
            ToolName.from_mapping({"name": "fetch", "namespace": 123})

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
        self.assertEqual(ByteRange.from_range(1, 3).to_mapping(), {"start": 1, "end": 3})
        self.assertEqual(
            TextElement.new(ByteRange(1, 3), None).to_mapping(),
            {"byte_range": {"start": 1, "end": 3}, "placeholder": None},
        )
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
            UserInput.from_mapping({"type": "text", "text": "hello", "text_elements": []}).to_mapping(),
            {"type": "text", "text": "hello", "text_elements": []},
        )
        self.assertEqual(
            UserInput.image("data:image/png;base64,abc", detail=ImageDetail.HIGH).to_mapping(),
            {"type": "image", "image_url": "data:image/png;base64,abc", "detail": "high"},
        )
        self.assertEqual(
            UserInput.from_mapping({"type": "image", "image_url": "data:image/png;base64,abc"}).to_mapping(),
            {"type": "image", "image_url": "data:image/png;base64,abc"},
        )
        self.assertEqual(
            UserInput.local_image(Path("image.png"), detail=ImageDetail.ORIGINAL).to_mapping(),
            {"type": "local_image", "path": "image.png", "detail": "original"},
        )
        self.assertEqual(
            UserInput.from_mapping({"type": "local_image", "path": "image.png"}).to_mapping(),
            {"type": "local_image", "path": "image.png"},
        )
        self.assertEqual(
            UserInput.skill("python", Path("SKILL.md")).to_mapping(),
            {"type": "skill", "name": "python", "path": "SKILL.md"},
        )
        self.assertEqual(
            UserInput.from_mapping({"type": "skill", "name": "python", "path": "SKILL.md"}),
            UserInput.skill("python", Path("SKILL.md")),
        )
        self.assertEqual(
            UserInput.mention("GitHub", "app://github").to_mapping(),
            {"type": "mention", "name": "GitHub", "path": "app://github"},
        )
        self.assertEqual(
            UserInput.from_mapping({"type": "mention", "name": "GitHub", "path": "app://github"}),
            UserInput.mention("GitHub", "app://github"),
        )

    def test_byte_range_and_text_element_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "start must be an integer"):
            ByteRange(True, 1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "start must be non-negative"):
            ByteRange(-1, 1)
        with self.assertRaisesRegex(ValueError, "end must be non-negative"):
            ByteRange(0, -1)
        with self.assertRaisesRegex(TypeError, "byte_range must be a ByteRange"):
            TextElement("0..1")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "placeholder must be a string or None"):
            TextElement.new(ByteRange(0, 1), 123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "map_range callback must return a ByteRange"):
            TextElement.new(ByteRange(0, 1), None).map_range(lambda _range: "0..1")  # type: ignore[return-value]
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            TextElement.new(ByteRange(0, 1), None).placeholder(123)  # type: ignore[arg-type]

    def test_user_input_rejects_non_rust_variant_shapes(self):
        with self.assertRaisesRegex(TypeError, "text input requires text"):
            UserInput(type="text")
        with self.assertRaisesRegex(TypeError, "text_elements must be a list or tuple"):
            UserInput.text_input("hello", "not-elements")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "text_elements entries must be TextElement"):
            UserInput.text_input("hello", ({"byte_range": {"start": 0, "end": 1}},))  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "image input requires image_url"):
            UserInput(type="image")
        with self.assertRaisesRegex(TypeError, "detail must be an ImageDetail or None"):
            UserInput.image("data:image/png;base64,abc", detail=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "detail must be a string"):
            UserInput.from_mapping({"type": "image", "image_url": "data:image/png;base64,abc", "detail": 123})
        with self.assertRaisesRegex(TypeError, "local_image input requires path"):
            UserInput(type="local_image", path=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "skill input requires name"):
            UserInput(type="skill", path=Path("SKILL.md"))
        with self.assertRaisesRegex(TypeError, "mention input requires path"):
            UserInput.mention("GitHub", Path("app://github"))  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "unknown user input type"):
            UserInput(type="unknown")
        with self.assertRaisesRegex(TypeError, "text_elements must be a list"):
            UserInput.from_mapping({"type": "text", "text": "hello", "text_elements": "bad"})


if __name__ == "__main__":
    unittest.main()
