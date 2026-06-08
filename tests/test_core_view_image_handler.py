import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core import (
    FunctionCallError,
    ToolPayload,
)
from pycodex.core.tools.handlers.view_image import (
    VIEW_IMAGE_TOOL_NAME,
    VIEW_IMAGE_UNSUPPORTED_MESSAGE,
    ViewImageHandler,
    ViewImageOutput,
    ViewImageToolOptions,
    create_view_image_tool,
    data_url_for_image,
    parse_view_image_arguments,
)
from pycodex.protocol import DEFAULT_IMAGE_DETAIL, ImageDetail, SearchToolCallParams, ToolName


class ViewImageHandlerTests(unittest.TestCase):
    def test_create_view_image_tool_matches_expected_shape(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image_spec.rs::create_view_image_tool
        # Rust contract: view_image is a non-strict function tool requiring a local image path.
        spec = create_view_image_tool(
            ViewImageToolOptions(
                can_request_original_image_detail=True,
                include_environment_id=True,
            )
        )

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], VIEW_IMAGE_TOOL_NAME)
        self.assertEqual(
            spec["description"],
            "View a local image file from the filesystem when visual inspection is needed. Use this for images already available on disk.",
        )
        self.assertFalse(spec["strict"])
        self.assertIsNone(spec.get("defer_loading"))
        self.assertEqual(spec["parameters"]["required"], ["path"])
        self.assertFalse(spec["parameters"]["additionalProperties"])
        self.assertEqual(
            spec["parameters"]["properties"]["path"],
            {
                "type": "string",
                "description": "Local filesystem path to an image file",
            },
        )
        self.assertEqual(
            spec["parameters"]["properties"]["detail"],
            {
                "type": "string",
                "enum": ["high", "original"],
                "description": (
                    "Optional detail override. Supported values are `high` and `original`; omit this field "
                    "for default high resized behavior. Use `original` to preserve the file's original "
                    "resolution instead of resizing to fit. This is important when high-fidelity image "
                    "perception or precise localization is needed, especially for CUA agents."
                ),
            },
        )
        self.assertEqual(
            spec["parameters"]["properties"]["environment_id"],
            {
                "type": "string",
                "description": "Optional selected environment id to target. Omit this to use the primary environment.",
            },
        )
        self.assertEqual(
            spec["output_schema"],
            {
                "type": "object",
                "properties": {
                    "image_url": {
                        "type": "string",
                        "description": "Data URL for the loaded image.",
                    },
                    "detail": {
                        "type": "string",
                        "enum": ["high", "original"],
                        "description": "Image detail hint returned by view_image. Returns `high` for default resized behavior or `original` when original resolution is preserved.",
                    },
                },
                "required": ["image_url", "detail"],
                "additionalProperties": False,
            },
        )

    def test_create_view_image_tool_omits_optional_schema_fields_when_disabled(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image_spec.rs::create_view_image_tool
        # Rust contract: detail and environment_id are included only when their options are enabled.
        spec = create_view_image_tool(ViewImageToolOptions())

        self.assertNotIn("detail", spec["parameters"]["properties"])
        self.assertNotIn("environment_id", spec["parameters"]["properties"])

    def test_parse_view_image_arguments_and_detail_validation(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image.rs
        # Rust contract: view_image accepts `high` and `original`; invalid details are model-visible errors.
        args = parse_view_image_arguments(
            json.dumps({"path": "image.png", "detail": "original"})
        )

        self.assertEqual(args.path, "image.png")
        self.assertEqual(args.detail, ImageDetail.ORIGINAL)

        with self.assertRaises(FunctionCallError) as bad:
            parse_view_image_arguments(json.dumps({"path": "image.png", "detail": "low"}))
        self.assertIn("only supports `high` or `original`", str(bad.exception))

        with self.assertRaises(FunctionCallError) as bad_json:
            parse_view_image_arguments("{")
        self.assertIn("failed to parse function arguments:", str(bad_json.exception))

        with self.assertRaises(FunctionCallError) as missing_path:
            parse_view_image_arguments("{}")
        self.assertIn("failed to parse function arguments:", str(missing_path.exception))

    def test_view_image_output_shapes(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image.rs
        # Rust contract: output returns an image content item to the model and image_url/detail to code mode.
        output = ViewImageOutput("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL)
        payload = ToolPayload.function("{}")
        response = output.to_response_item("call-image", payload)

        self.assertEqual(output.log_preview(), "data:image/png;base64,AAA")
        self.assertTrue(output.success_for_logging())
        self.assertEqual(
            output.code_mode_result(payload),
            {"image_url": "data:image/png;base64,AAA", "detail": "high"},
        )
        self.assertEqual(response.call_id, "call-image")

    def test_handler_reads_local_file_as_data_url(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image.rs
        # Rust contract: local image files are returned as data URLs and original detail is honored when enabled.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            image.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            handler = ViewImageHandler(
                ViewImageToolOptions(can_request_original_image_detail=True),
                cwd=root,
            )

            output = handler.handle(
                ToolPayload.function(
                    json.dumps({"path": "image.png", "detail": "original"})
                )
            )

            self.assertEqual(handler.tool_name(), ToolName.plain("view_image"))
            self.assertTrue(handler.supports_parallel_tool_calls())
            self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
            self.assertFalse(handler.matches_kind(ToolPayload.tool_search(SearchToolCallParams("image"))))
            self.assertTrue(output.image_url.startswith("data:image/png;base64,"))
            self.assertEqual(output.image_detail, ImageDetail.ORIGINAL)

    def test_handler_resolves_environment_id_from_invocation_turn(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image.rs
        # Rust contract: environment_id selects the target turn environment cwd when available.
        with tempfile.TemporaryDirectory() as local_dir, tempfile.TemporaryDirectory() as remote_dir:
            local_root = Path(local_dir)
            remote_root = Path(remote_dir)
            (local_root / "image.png").write_bytes(b"not a png")
            (remote_root / "image.png").write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    environments=(
                        SimpleNamespace(environment_id="local", cwd=local_root),
                        SimpleNamespace(environment_id="remote", cwd=remote_root),
                    )
                ),
                payload=ToolPayload.function(
                    json.dumps({"path": "image.png", "environment_id": "remote"})
                ),
            )

            output = ViewImageHandler().handle(invocation)

            self.assertTrue(output.image_url.startswith("data:image/png;base64,"))

            with self.assertRaises(FunctionCallError) as unknown:
                ViewImageHandler().handle(
                    SimpleNamespace(
                        turn=invocation.turn,
                        payload=ToolPayload.function(
                            json.dumps({"path": "image.png", "environment_id": "missing"})
                        ),
                    )
                )
            self.assertIn("unknown turn environment id `missing`", str(unknown.exception))

    def test_handler_rejects_turn_without_image_input_modality_like_rust(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image.rs
        # Rust contract: view_image is rejected when the model does not support image input.
        invocation = SimpleNamespace(
            turn=SimpleNamespace(model_info=SimpleNamespace(input_modalities=("text",))),
            payload=ToolPayload.function(json.dumps({"path": "image.png"})),
        )

        with self.assertRaises(FunctionCallError) as unsupported:
            ViewImageHandler().handle(invocation)

        self.assertEqual(str(unsupported.exception), VIEW_IMAGE_UNSUPPORTED_MESSAGE)

    def test_handler_emits_image_view_turn_item_like_rust(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image.rs
        # Rust contract: successful view_image calls emit ImageView turn item started/completed events.
        class Session:
            def __init__(self) -> None:
                self.started = []
                self.completed = []

            async def emit_turn_item_started(self, turn, item):
                self.started.append((turn, item))

            async def emit_turn_item_completed(self, turn, item):
                self.completed.append((turn, item))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            image.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            turn = SimpleNamespace(
                model_info=SimpleNamespace(input_modalities=("text", "image")),
                environments=(SimpleNamespace(environment_id="local", cwd=root),),
            )
            session = Session()
            invocation = SimpleNamespace(
                session=session,
                turn=turn,
                call_id="call-view-image",
                payload=ToolPayload.function(json.dumps({"path": "image.png"})),
            )

            output = asyncio.run(ViewImageHandler().handle(invocation))

        self.assertTrue(output.image_url.startswith("data:image/png;base64,"))
        self.assertEqual(len(session.started), 1)
        self.assertEqual(len(session.completed), 1)
        self.assertIs(session.started[0][0], turn)
        self.assertIs(session.completed[0][0], turn)
        self.assertEqual(session.started[0][1], session.completed[0][1])
        self.assertEqual(session.started[0][1].type, "ImageView")
        self.assertEqual(session.started[0][1].item.id, "call-view-image")
        self.assertEqual(session.started[0][1].item.path, root / "image.png")

    def test_handler_rejects_unsupported_and_bad_paths(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/view_image.rs
        # Rust contract: unsupported image input, missing paths, directories, bad MIME, and invalid bytes are model-visible errors.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            directory_path = root / "folder"
            directory_path.mkdir()
            text_file = root / "note.txt"
            text_file.write_text("not image", encoding="utf-8")
            fake_png = root / "fake.png"
            fake_png.write_bytes(b"not a real png")
            handler = ViewImageHandler(cwd=root)

            with self.assertRaises(FunctionCallError) as unsupported:
                ViewImageHandler(supports_image_inputs=False).handle(
                    ToolPayload.function(json.dumps({"path": "image.png"}))
                )
            self.assertEqual(str(unsupported.exception), VIEW_IMAGE_UNSUPPORTED_MESSAGE)

            with self.assertRaises(FunctionCallError) as missing:
                handler.handle(ToolPayload.function(json.dumps({"path": "missing.png"})))
            self.assertIn("unable to locate image", str(missing.exception))

            with self.assertRaises(FunctionCallError) as not_file:
                handler.handle(ToolPayload.function(json.dumps({"path": "folder"})))
            self.assertIn("is not a file", str(not_file.exception))

            with self.assertRaises(FunctionCallError) as bad_mime:
                handler.handle(ToolPayload.function(json.dumps({"path": "note.txt"})))
            self.assertIn("unable to process image", str(bad_mime.exception))

            with self.assertRaises(FunctionCallError) as bad_bytes:
                handler.handle(ToolPayload.function(json.dumps({"path": "fake.png"})))
            self.assertIn("image bytes do not match", str(bad_bytes.exception))

    def test_rejects_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            ViewImageToolOptions(can_request_original_image_detail=1)
        with self.assertRaises(TypeError):
            create_view_image_tool(object())
        with self.assertRaises(TypeError):
            ViewImageHandler(cwd=".")
        with self.assertRaises(TypeError):
            ViewImageHandler().matches_kind(object())
        with self.assertRaises(TypeError):
            parse_view_image_arguments({})
        with self.assertRaises(TypeError):
            data_url_for_image("image.png", b"abc")
        with self.assertRaises(TypeError):
            data_url_for_image(Path("image.png"), "abc")


if __name__ == "__main__":
    unittest.main()
