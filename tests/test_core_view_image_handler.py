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
        spec = create_view_image_tool(
            ViewImageToolOptions(
                can_request_original_image_detail=True,
                include_environment_id=True,
            )
        )

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], VIEW_IMAGE_TOOL_NAME)
        self.assertFalse(spec["strict"])
        self.assertEqual(spec["parameters"]["required"], ["path"])
        self.assertIn("detail", spec["parameters"]["properties"])
        self.assertIn("environment_id", spec["parameters"]["properties"])
        self.assertEqual(spec["output_schema"]["required"], ["image_url", "detail"])

    def test_parse_view_image_arguments_and_detail_validation(self) -> None:
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

    def test_handler_rejects_unsupported_and_bad_paths(self) -> None:
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
