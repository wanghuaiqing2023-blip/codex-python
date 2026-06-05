import unittest

from pycodex.tools.original_image_detail import (
    can_request_original_image_detail,
    normalize_output_image_detail,
    sanitize_original_image_detail,
)
from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    ImageDetail,
    ModelInfo,
)


def model_info(supports_original: bool = True) -> ModelInfo:
    return ModelInfo.from_mapping(
        {
            "slug": "test-model",
            "display_name": "Test Model",
            "description": None,
            "supported_reasoning_levels": [],
            "shell_type": "shell_command",
            "visibility": "list",
            "supported_in_api": True,
            "priority": 1,
            "availability_nux": None,
            "upgrade": None,
            "base_instructions": "base",
            "model_messages": None,
            "supports_reasoning_summaries": False,
            "default_reasoning_summary": "auto",
            "support_verbosity": False,
            "default_verbosity": None,
            "apply_patch_tool_type": None,
            "truncation_policy": {
                "mode": "bytes",
                "limit": 10000,
            },
            "supports_parallel_tool_calls": False,
            "supports_image_detail_original": supports_original,
            "context_window": None,
            "auto_compact_token_limit": None,
            "effective_context_window_percent": 95,
            "experimental_supported_tools": [],
            "input_modalities": ["text", "image"],
            "supports_search_tool": False,
        }
    )


class OriginalImageDetailTests(unittest.TestCase):
    def test_explicit_original_is_allowed_when_model_supports_it(self) -> None:
        info = model_info()

        self.assertTrue(can_request_original_image_detail(info))
        self.assertIs(
            normalize_output_image_detail(info, ImageDetail.ORIGINAL),
            ImageDetail.ORIGINAL,
        )
        self.assertIsNone(normalize_output_image_detail(info, None))

    def test_explicit_original_is_dropped_without_model_support(self) -> None:
        self.assertIsNone(
            normalize_output_image_detail(
                model_info(supports_original=False),
                ImageDetail.ORIGINAL,
            )
        )

    def test_explicit_non_original_detail_is_preserved(self) -> None:
        self.assertIs(
            normalize_output_image_detail(model_info(), ImageDetail.AUTO),
            ImageDetail.AUTO,
        )
        self.assertIs(
            normalize_output_image_detail(model_info(), ImageDetail.LOW),
            ImageDetail.LOW,
        )
        self.assertIs(
            normalize_output_image_detail(model_info(), ImageDetail.HIGH),
            ImageDetail.HIGH,
        )

    def test_sanitize_original_falls_back_to_high_without_support(self) -> None:
        items = (
            FunctionCallOutputContentItem.input_text("header"),
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,AAA",
                ImageDetail.ORIGINAL,
            ),
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,BBB",
                ImageDetail.HIGH,
            ),
        )

        self.assertEqual(
            sanitize_original_image_detail(False, items),
            (
                FunctionCallOutputContentItem.input_text("header"),
                FunctionCallOutputContentItem.input_image(
                    "data:image/png;base64,AAA",
                    DEFAULT_IMAGE_DETAIL,
                ),
                FunctionCallOutputContentItem.input_image(
                    "data:image/png;base64,BBB",
                    ImageDetail.HIGH,
                ),
            ),
        )

    def test_sanitize_original_preserves_items_when_supported(self) -> None:
        items = (
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,AAA",
                ImageDetail.ORIGINAL,
            ),
        )

        self.assertEqual(sanitize_original_image_detail(True, items), items)

    def test_rejects_non_rust_input_shapes(self) -> None:
        with self.assertRaises(TypeError):
            can_request_original_image_detail(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            normalize_output_image_detail(model_info(), "high")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            normalize_output_image_detail(object(), ImageDetail.HIGH)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            sanitize_original_image_detail(1, ())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
