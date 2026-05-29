"""Execution-time rewrite for Apps SDK ``openai/fileParams`` arguments.

Ported from ``codex/codex-rs/core/src/mcp_openai_file.rs``.

This module owns only the MCP argument rewrite.  Uploading local files to
OpenAI file storage remains a host/client boundary represented by an injected
uploader callback.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

JsonValue = Any


@dataclass(frozen=True)
class UploadedOpenAIFile:
    download_url: str
    file_id: str
    mime_type: str
    file_name: str
    uri: str
    file_size_bytes: int

    def __post_init__(self) -> None:
        for field_name in ("download_url", "file_id", "mime_type", "file_name", "uri"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        if isinstance(self.file_size_bytes, bool) or not isinstance(self.file_size_bytes, int):
            raise TypeError("file_size_bytes must be an integer")
        if self.file_size_bytes < 0:
            raise ValueError("file_size_bytes must be non-negative")

    def to_argument_value(self) -> dict[str, JsonValue]:
        return {
            "download_url": self.download_url,
            "file_id": self.file_id,
            "mime_type": self.mime_type,
            "file_name": self.file_name,
            "uri": self.uri,
            "file_size_bytes": self.file_size_bytes,
        }


OpenAIFileUploader: TypeAlias = Callable[
    [Path, str, int | None],
    UploadedOpenAIFile | Mapping[str, JsonValue] | Awaitable[UploadedOpenAIFile | Mapping[str, JsonValue]],
]


async def rewrite_mcp_tool_arguments_for_openai_files(
    arguments_value: JsonValue | None,
    openai_file_input_params: Sequence[str] | None,
    *,
    uploader: OpenAIFileUploader | None = None,
    resolve_path: Callable[[str], Path] | None = None,
) -> JsonValue | None:
    if openai_file_input_params is None:
        return arguments_value
    params = _file_input_params(openai_file_input_params)
    if arguments_value is None:
        return None
    if not isinstance(arguments_value, Mapping):
        return arguments_value

    rewritten_arguments = dict(arguments_value)
    changed = False
    for field_name in params:
        if field_name not in arguments_value:
            continue
        uploaded_value = await rewrite_argument_value_for_openai_files(
            field_name,
            arguments_value[field_name],
            uploader=uploader,
            resolve_path=resolve_path,
        )
        if uploaded_value is None:
            continue
        rewritten_arguments[field_name] = uploaded_value
        changed = True

    if not changed:
        return arguments_value
    return rewritten_arguments


async def rewrite_argument_value_for_openai_files(
    field_name: str,
    value: JsonValue,
    *,
    uploader: OpenAIFileUploader | None = None,
    resolve_path: Callable[[str], Path] | None = None,
) -> JsonValue | None:
    if not isinstance(field_name, str):
        raise TypeError("field_name must be a string")
    if isinstance(value, str):
        return await build_uploaded_local_argument_value(
            field_name,
            None,
            value,
            uploader=uploader,
            resolve_path=resolve_path,
        )
    if isinstance(value, list):
        rewritten_values: list[JsonValue] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                return None
            rewritten_values.append(
                await build_uploaded_local_argument_value(
                    field_name,
                    index,
                    item,
                    uploader=uploader,
                    resolve_path=resolve_path,
                )
            )
        return rewritten_values
    return None


async def build_uploaded_local_argument_value(
    field_name: str,
    index: int | None,
    file_path: str,
    *,
    uploader: OpenAIFileUploader | None = None,
    resolve_path: Callable[[str], Path] | None = None,
) -> dict[str, JsonValue]:
    if not isinstance(field_name, str):
        raise TypeError("field_name must be a string")
    if index is not None and (isinstance(index, bool) or not isinstance(index, int)):
        raise TypeError("index must be an integer")
    if index is not None and index < 0:
        raise ValueError("index must be non-negative")
    if not isinstance(file_path, str):
        raise TypeError("file_path must be a string")
    if uploader is None:
        raise ValueError("ChatGPT auth is required to upload local files for Codex Apps tools")

    resolver = resolve_path or Path
    resolved_path = resolver(file_path)
    if not isinstance(resolved_path, Path):
        resolved_path = Path(resolved_path)

    try:
        uploaded = uploader(resolved_path, field_name, index)
        if inspect.isawaitable(uploaded):
            uploaded = await uploaded
        return uploaded_openai_file_from_value(uploaded).to_argument_value()
    except Exception as error:
        label = f"{field_name}[{index}]" if index is not None else field_name
        raise RuntimeError(f"failed to upload `{file_path}` for `{label}`: {error}") from error


def uploaded_openai_file_from_value(value: UploadedOpenAIFile | Mapping[str, JsonValue]) -> UploadedOpenAIFile:
    if isinstance(value, UploadedOpenAIFile):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("uploaded file must be UploadedOpenAIFile or mapping")
    return UploadedOpenAIFile(
        download_url=_required_str(value, "download_url"),
        file_id=_required_str(value, "file_id"),
        mime_type=_required_str(value, "mime_type"),
        file_name=_required_str(value, "file_name"),
        uri=_required_str(value, "uri"),
        file_size_bytes=_required_int(value, "file_size_bytes"),
    )


def _file_input_params(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError("openai_file_input_params must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError("openai_file_input_params must be a sequence of strings")
    return tuple(value)


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _required_int(value: Mapping[str, JsonValue], key: str) -> int:
    raw = value.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    return raw


__all__ = [
    "OpenAIFileUploader",
    "UploadedOpenAIFile",
    "build_uploaded_local_argument_value",
    "rewrite_argument_value_for_openai_files",
    "rewrite_mcp_tool_arguments_for_openai_files",
    "uploaded_openai_file_from_value",
]
