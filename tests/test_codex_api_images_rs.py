"""Rust-derived tests for ``codex-api/src/images.rs``."""

from __future__ import annotations

import unittest

from pycodex.codex_api import ImageBackground
from pycodex.codex_api import ImageData
from pycodex.codex_api import ImageEditRequest
from pycodex.codex_api import ImageGenerationRequest
from pycodex.codex_api import ImageQuality
from pycodex.codex_api import ImageResponse
from pycodex.codex_api import ImageUrl


class CodexApiImagesRsTests(unittest.TestCase):
    def test_generation_request_serializes_lowercase_enums_and_skips_none(self) -> None:
        # Rust module/test: codex-api/src/images.rs plus
        # endpoint/images.rs::generate_posts_typed_request_and_parses_image_response.
        # Contract: serde serializes lowercase enums and skips optional None
        # fields such as n.
        request = ImageGenerationRequest(
            prompt="a red fox in a field",
            background=ImageBackground.OPAQUE,
            model="gpt-image-1.5",
            n=None,
            quality=ImageQuality.MEDIUM,
            size="1024x1536",
        )

        self.assertEqual(
            request.to_json_dict(),
            {
                "prompt": "a red fox in a field",
                "background": "opaque",
                "model": "gpt-image-1.5",
                "quality": "medium",
                "size": "1024x1536",
            },
        )

    def test_edit_request_serializes_images_and_skips_absent_options(self) -> None:
        # Rust module/test: codex-api/src/images.rs plus
        # endpoint/images.rs::edit_posts_typed_request_and_parses_image_response.
        # Contract: image edit requests include images, prompt, model, and omit
        # optional None fields.
        request = ImageEditRequest(
            images=[ImageUrl("data:image/png;base64,Zm9v")],
            prompt="add a red hat",
            background=None,
            model="gpt-image-1.5",
            n=None,
            quality=None,
            size=None,
        )

        self.assertEqual(
            request.to_json_dict(),
            {
                "images": [{"image_url": "data:image/png;base64,Zm9v"}],
                "prompt": "add a red hat",
                "model": "gpt-image-1.5",
            },
        )

    def test_image_response_deserializes_optional_fields_with_defaults(self) -> None:
        # Rust module: codex-api/src/images.rs
        # Contract: ImageResponse requires created/data, while background,
        # quality, and size use serde(default) and deserialize as None when
        # absent.
        response = ImageResponse.from_json_dict(
            {
                "created": 1778832973,
                "data": [{"b64_json": "REDACT"}],
                "background": "opaque",
                "quality": "medium",
                "size": "1024x1536",
            }
        )

        self.assertEqual(
            response,
            ImageResponse(
                created=1778832973,
                data=[ImageData("REDACT")],
                background=ImageBackground.OPAQUE,
                quality=ImageQuality.MEDIUM,
                size="1024x1536",
            ),
        )
        self.assertEqual(
            ImageResponse.from_json_dict({"created": 1, "data": []}),
            ImageResponse(created=1, data=[]),
        )

    def test_image_response_requires_data_field(self) -> None:
        # Rust test: endpoint/images.rs::image_response_requires_image_data.
        # Contract: serde requires the data field.
        with self.assertRaises(KeyError):
            ImageResponse.from_json_dict({"created": 1778832973})

    def test_image_response_rejects_negative_created_as_u64(self) -> None:
        # Rust module: codex-api/src/images.rs
        # Contract: ImageResponse.created is u64, so serde rejects negative
        # integer values during deserialization.
        with self.assertRaises(KeyError):
            ImageResponse.from_json_dict({"created": -1, "data": []})

    def test_image_data_requires_b64_json_field(self) -> None:
        # Rust module: codex-api/src/images.rs
        # Contract: ImageData requires the b64_json wire field.
        with self.assertRaises(KeyError):
            ImageData.from_json_dict({})

    def test_image_enums_cover_all_lowercase_wire_values(self) -> None:
        # Rust module: codex-api/src/images.rs
        # Contract: serde(rename_all = "lowercase") covers every enum variant.
        self.assertEqual(
            {item.value for item in ImageBackground},
            {"transparent", "opaque", "auto"},
        )
        self.assertEqual(
            {item.value for item in ImageQuality},
            {"low", "medium", "high", "auto"},
        )

    def test_image_url_round_trips_wire_shape(self) -> None:
        # Rust module: codex-api/src/images.rs
        # Contract: ImageUrl's wire field is image_url.
        value = {"image_url": "data:image/png;base64,Zm9v"}
        self.assertEqual(ImageUrl.from_json_dict(value).to_json_dict(), value)


if __name__ == "__main__":
    unittest.main()
