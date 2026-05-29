from pathlib import Path
import unittest

from pycodex.protocol import ByteRange, ImageDetail, TextElement, UserInput


class ProtocolUserInputTests(unittest.TestCase):
    def test_user_input_serializes_rust_shapes(self):
        text = UserInput.text_input("hello")
        image = UserInput.image("data:image/png;base64,AAA", detail=ImageDetail.HIGH)
        local_image = UserInput.local_image(Path("image.png"), detail=ImageDetail.LOW)
        skill = UserInput.skill("python", Path("skills/python/SKILL.md"))
        mention = UserInput.mention("github", "app://github")

        self.assertEqual(text.to_mapping(), {"type": "text", "text": "hello", "text_elements": []})
        self.assertEqual(image.to_mapping()["detail"], "high")
        self.assertEqual(local_image.to_mapping()["path"], "image.png")
        self.assertEqual(skill.to_mapping()["name"], "python")
        self.assertEqual(mention.to_mapping()["path"], "app://github")

    def test_user_input_text_elements_roundtrip(self):
        element = TextElement.new(ByteRange(0, 5), None)
        item = UserInput.text_input("hello", (element,))
        parsed = UserInput.from_mapping(item.to_mapping())

        self.assertEqual(parsed, item)
        self.assertEqual(element.placeholder("hello"), "hello")

    def test_user_input_direct_construction_rejects_mixed_variant_fields(self):
        cases = (
            lambda: UserInput("text", text="hello", image_url="data:image/png;base64,AAA"),
            lambda: UserInput("image", image_url="data:image/png;base64,AAA", text="hello"),
            lambda: UserInput("local_image", path=Path("image.png"), image_url="data:image/png;base64,AAA"),
            lambda: UserInput("skill", name="python", path=Path("SKILL.md"), detail=ImageDetail.LOW),
            lambda: UserInput("mention", name="github", path="app://github", detail=ImageDetail.LOW),
        )

        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    case()

    def test_user_input_rejects_non_rust_field_shapes(self):
        with self.assertRaisesRegex(TypeError, "text input requires text"):
            UserInput.text_input(123)

        with self.assertRaisesRegex(TypeError, "text_elements entries must be TextElement"):
            UserInput.text_input("hello", ({"byte_range": {"start": 0, "end": 5}},))

        with self.assertRaisesRegex(TypeError, "image input requires image_url"):
            UserInput.image(123)

        with self.assertRaisesRegex(TypeError, "detail must be an ImageDetail or None"):
            UserInput.image("data:image/png;base64,AAA", detail=123)

        with self.assertRaisesRegex(TypeError, "local_image input requires path"):
            UserInput.local_image(123)

        with self.assertRaisesRegex(TypeError, "skill input requires name"):
            UserInput.skill(123, Path("SKILL.md"))

        with self.assertRaisesRegex(TypeError, "mention input requires path"):
            UserInput.mention("github", Path("app"))

        with self.assertRaisesRegex(ValueError, "unknown user input type"):
            UserInput("unknown")


if __name__ == "__main__":
    unittest.main()
