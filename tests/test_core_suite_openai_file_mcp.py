"""Suite parity tests for ``codex-rs/core/tests/suite/openai_file_mcp.rs``."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.core.mcp_openai_file import (
    OPENAI_FILE_PARAM_DESCRIPTION,
    UploadedOpenAIFile,
    annotate_openai_file_params_schema,
    rewrite_mcp_tool_arguments_for_openai_files,
)


def test_codex_apps_file_params_upload_local_paths_before_mcp_tool_call(tmp_path: Path) -> None:
    """Rust test: ``codex_apps_file_params_upload_local_paths_before_mcp_tool_call``."""

    report = tmp_path / "report.txt"
    report.write_text("hello world", encoding="utf-8")
    schema = {
        "type": "object",
        "properties": {
            "file": {"type": "string"},
            "note": {"type": "string"},
        },
    }

    annotated = annotate_openai_file_params_schema(schema, ("file",))

    assert annotated is not None
    assert annotated["properties"]["file"] == {
        "type": "string",
        "description": OPENAI_FILE_PARAM_DESCRIPTION,
    }
    assert annotated["properties"]["note"] == {"type": "string"}

    uploads = []

    def uploader(path: Path, field_name: str, index: int | None) -> UploadedOpenAIFile:
        uploads.append((path, field_name, index, path.read_bytes()))
        return UploadedOpenAIFile(
            download_url="https://example.test/download/file_123",
            file_id="file_123",
            mime_type="text/plain",
            file_name="report.txt",
            uri="sediment://file_123",
            file_size_bytes=11,
        )

    rewritten = asyncio.run(
        rewrite_mcp_tool_arguments_for_openai_files(
            {"file": str(report)},
            ("file",),
            uploader=uploader,
            resolve_path=Path,
        )
    )

    expected_payload = {
        "download_url": "https://example.test/download/file_123",
        "file_id": "file_123",
        "mime_type": "text/plain",
        "file_name": "report.txt",
        "uri": "sediment://file_123",
        "file_size_bytes": 11,
    }
    assert rewritten == {"file": expected_payload}
    assert uploads == [(report, "file", None, b"hello world")]

    post_tool_use_hook_input = {"tool_input": rewritten}

    assert post_tool_use_hook_input["tool_input"]["file"] == expected_payload
