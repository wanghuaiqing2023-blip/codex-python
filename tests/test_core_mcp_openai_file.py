import unittest
from pathlib import Path

from pycodex.core.mcp_openai_file import (
    UploadedOpenAIFile,
    build_uploaded_local_argument_value,
    rewrite_argument_value_for_openai_files,
    rewrite_mcp_tool_arguments_for_openai_files,
    uploaded_openai_file_from_value,
)


def uploaded(name: str, file_id: str = "file_123") -> UploadedOpenAIFile:
    return UploadedOpenAIFile(
        download_url=f"https://example.test/download/{file_id}",
        file_id=file_id,
        mime_type="text/csv",
        file_name=name,
        uri=f"sediment://{file_id}",
        file_size_bytes=5,
    )


class McpOpenAIFileTests(unittest.IsolatedAsyncioTestCase):
    async def test_rewrite_requires_declared_file_params(self) -> None:
        arguments = {"file": "/tmp/codex-smoke-file.txt"}

        rewritten = await rewrite_mcp_tool_arguments_for_openai_files(
            arguments,
            None,
            uploader=lambda path, field, index: uploaded(path.name),
        )

        self.assertIs(rewritten, arguments)

    async def test_rewrite_ignores_missing_or_non_object_arguments(self) -> None:
        self.assertIsNone(
            await rewrite_mcp_tool_arguments_for_openai_files(None, ("file",))
        )
        self.assertEqual(
            await rewrite_mcp_tool_arguments_for_openai_files("not-object", ("file",)),
            "not-object",
        )

    async def test_rewrite_argument_value_rewrites_scalar_path(self) -> None:
        calls = []

        def uploader(path: Path, field_name: str, index: int | None) -> UploadedOpenAIFile:
            calls.append((path, field_name, index))
            return uploaded(path.name)

        rewritten = await rewrite_argument_value_for_openai_files(
            "file",
            "file_report.csv",
            uploader=uploader,
            resolve_path=lambda path: Path("/repo") / path,
        )

        self.assertEqual(calls, [(Path("/repo/file_report.csv"), "file", None)])
        self.assertEqual(
            rewritten,
            {
                "download_url": "https://example.test/download/file_123",
                "file_id": "file_123",
                "mime_type": "text/csv",
                "file_name": "file_report.csv",
                "uri": "sediment://file_123",
                "file_size_bytes": 5,
            },
        )

    async def test_rewrite_argument_value_rewrites_array_paths(self) -> None:
        def uploader(path: Path, field_name: str, index: int | None) -> UploadedOpenAIFile:
            return uploaded(path.name, f"file_{index}")

        rewritten = await rewrite_argument_value_for_openai_files(
            "files",
            ["one.csv", "two.csv"],
            uploader=uploader,
            resolve_path=lambda path: Path("/repo") / path,
        )

        self.assertEqual(
            rewritten,
            [
                {
                    "download_url": "https://example.test/download/file_0",
                    "file_id": "file_0",
                    "mime_type": "text/csv",
                    "file_name": "one.csv",
                    "uri": "sediment://file_0",
                    "file_size_bytes": 5,
                },
                {
                    "download_url": "https://example.test/download/file_1",
                    "file_id": "file_1",
                    "mime_type": "text/csv",
                    "file_name": "two.csv",
                    "uri": "sediment://file_1",
                    "file_size_bytes": 5,
                },
            ],
        )

    async def test_rewrite_argument_value_ignores_non_string_array_items(self) -> None:
        rewritten = await rewrite_argument_value_for_openai_files(
            "files",
            ["one.csv", 2],
            uploader=lambda path, field, index: uploaded(path.name),
        )

        self.assertIsNone(rewritten)

    async def test_rewrite_mcp_tool_arguments_only_rewrites_declared_fields(self) -> None:
        rewritten = await rewrite_mcp_tool_arguments_for_openai_files(
            {"file": "one.csv", "note": "leave me alone"},
            ("file",),
            uploader=lambda path, field, index: uploaded(path.name),
            resolve_path=lambda path: Path("/repo") / path,
        )

        self.assertEqual(rewritten["note"], "leave me alone")
        self.assertEqual(rewritten["file"]["file_name"], "one.csv")

    async def test_build_uploaded_local_argument_value_requires_uploader(self) -> None:
        with self.assertRaisesRegex(ValueError, "ChatGPT auth is required"):
            await build_uploaded_local_argument_value("file", None, "one.csv")

    async def test_upload_failure_mentions_field_and_index(self) -> None:
        def failing_uploader(path: Path, field_name: str, index: int | None) -> UploadedOpenAIFile:
            raise OSError("missing")

        with self.assertRaisesRegex(RuntimeError, "failed to upload `two.csv` for `files\\[1\\]`"):
            await build_uploaded_local_argument_value(
                "files",
                1,
                "two.csv",
                uploader=failing_uploader,
            )

    def test_uploaded_openai_file_from_value_validates_payload(self) -> None:
        parsed = uploaded_openai_file_from_value(
            {
                "download_url": "https://example.test/download/file_123",
                "file_id": "file_123",
                "mime_type": "text/csv",
                "file_name": "file.csv",
                "uri": "sediment://file_123",
                "file_size_bytes": 5,
            }
        )

        self.assertEqual(parsed, uploaded("file.csv"))
        with self.assertRaisesRegex(TypeError, "file_size_bytes must be an integer"):
            uploaded_openai_file_from_value(
                {
                    "download_url": "https://example.test/download/file_123",
                    "file_id": "file_123",
                    "mime_type": "text/csv",
                    "file_name": "file.csv",
                    "uri": "sediment://file_123",
                    "file_size_bytes": "5",
                }
            )


if __name__ == "__main__":
    unittest.main()
