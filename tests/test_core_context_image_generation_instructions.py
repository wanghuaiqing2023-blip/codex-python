import unittest

from pycodex.core.context import ImageGenerationInstructions, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class ImageGenerationInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/image_generation_instructions.rs

    def test_image_generation_instructions_empty_markers_do_not_match_arbitrary_text(self) -> None:
        text = (
            "Generated images are saved to C:/tmp/images as image.png by default.\n"
            "If you need to use a generated image at another path, copy it and leave the "
            "original in place unless the user explicitly asks you to delete it."
        )

        self.assertFalse(ImageGenerationInstructions.matches_text(text))
        self.assertFalse(is_standard_contextual_user_text(text))

    def test_image_generation_instructions_match_rust_contextual_fragment_contract(self) -> None:
        fragment = ImageGenerationInstructions.new(
            "C:/Users/demo/.codex/generated_images/session-1",
            "C:/Users/demo/.codex/generated_images/session-1/<image_id>.png",
        )

        expected_body = (
            "Generated images are saved to C:/Users/demo/.codex/generated_images/session-1 "
            "as C:/Users/demo/.codex/generated_images/session-1/<image_id>.png by default.\n"
            "If you need to use a generated image at another path, copy it and leave the "
            "original in place unless the user explicitly asks you to delete it."
        )

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_body)

        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(expected_body),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(expected_body),)),
        )


if __name__ == "__main__":
    unittest.main()
