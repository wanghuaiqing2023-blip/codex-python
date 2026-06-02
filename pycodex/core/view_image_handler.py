"""view_image tool handler ported from Codex core."""

from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.core.handler_utils import resolve_tool_environment
from pycodex.core.tool_context import FunctionToolOutput, ToolPayload
from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    ImageDetail,
    ResponseInputItem,
    ToolName,
)

JsonValue = Any

VIEW_IMAGE_TOOL_NAME = "view_image"
VIEW_IMAGE_UNSUPPORTED_MESSAGE = "view_image is not allowed because you do not support image inputs"


@dataclass(frozen=True)
class ViewImageToolOptions:
    can_request_original_image_detail: bool = False
    include_environment_id: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.can_request_original_image_detail, bool):
            raise TypeError("can_request_original_image_detail must be a bool")
        if not isinstance(self.include_environment_id, bool):
            raise TypeError("include_environment_id must be a bool")


@dataclass(frozen=True)
class ViewImageArgs:
    path: str
    environment_id: str | None = None
    detail: ImageDetail | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str):
            raise TypeError("path must be a string")
        if self.environment_id is not None and not isinstance(self.environment_id, str):
            raise TypeError("environment_id must be a string or None")
        if self.detail is not None and not isinstance(self.detail, ImageDetail):
            object.__setattr__(self, "detail", _parse_view_image_detail(self.detail))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ViewImageArgs":
        if not isinstance(value, dict):
            raise TypeError("view_image args must be a mapping")
        detail = value.get("detail")
        return cls(
            path=_required_str(value, "path"),
            environment_id=_optional_str(value, "environment_id"),
            detail=None if detail is None else _parse_view_image_detail(detail),
        )


@dataclass(frozen=True)
class ViewImageOutput:
    image_url: str
    image_detail: ImageDetail = DEFAULT_IMAGE_DETAIL

    def __post_init__(self) -> None:
        if not isinstance(self.image_url, str):
            raise TypeError("image_url must be a string")
        if not isinstance(self.image_detail, ImageDetail):
            object.__setattr__(self, "image_detail", ImageDetail(self.image_detail))

    def log_preview(self) -> str:
        return self.image_url

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        if not isinstance(call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return FunctionToolOutput.from_content(
            (
                FunctionCallOutputContentItem.input_image(
                    self.image_url,
                    self.image_detail,
                ),
            ),
            True,
        ).to_response_item(call_id, payload)

    def code_mode_result(self, payload: ToolPayload) -> dict[str, JsonValue]:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return {"image_url": self.image_url, "detail": self.image_detail.value}


def create_view_image_tool(
    options: ViewImageToolOptions = ViewImageToolOptions(),
) -> dict[str, JsonValue]:
    if not isinstance(options, ViewImageToolOptions):
        raise TypeError("options must be ViewImageToolOptions")
    properties: dict[str, JsonValue] = {
        "path": {
            "type": "string",
            "description": "Local filesystem path to an image file",
        }
    }
    if options.can_request_original_image_detail:
        properties["detail"] = {
            "type": "string",
            "enum": ["high", "original"],
            "description": (
                "Optional detail override. Supported values are `high` and `original`; omit this field "
                "for default high resized behavior. Use `original` to preserve the file's original "
                "resolution instead of resizing to fit. This is important when high-fidelity image "
                "perception or precise localization is needed, especially for CUA agents."
            ),
        }
    if options.include_environment_id:
        properties["environment_id"] = {
            "type": "string",
            "description": "Optional selected environment id to target. Omit this to use the primary environment.",
        }
    return {
        "type": "function",
        "name": VIEW_IMAGE_TOOL_NAME,
        "description": "View a local image file from the filesystem when visual inspection is needed. Use this for images already available on disk.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": ["path"],
            "additionalProperties": False,
        },
        "output_schema": {
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
    }


class ViewImageHandler:
    def __init__(
        self,
        options: ViewImageToolOptions = ViewImageToolOptions(),
        *,
        supports_image_inputs: bool = True,
        cwd: Path | None = None,
    ) -> None:
        if not isinstance(options, ViewImageToolOptions):
            raise TypeError("options must be ViewImageToolOptions")
        if not isinstance(supports_image_inputs, bool):
            raise TypeError("supports_image_inputs must be a bool")
        if cwd is not None and not isinstance(cwd, Path):
            raise TypeError("cwd must be Path or None")
        self.options = options
        self.supports_image_inputs = supports_image_inputs
        self.cwd = cwd or Path.cwd()

    def tool_name(self) -> ToolName:
        return ToolName.plain(VIEW_IMAGE_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_view_image_tool(self.options)

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type == "function"

    def handle(self, invocation_or_payload: Any) -> ViewImageOutput:
        if not self.supports_image_inputs:
            raise FunctionCallError.respond_to_model(VIEW_IMAGE_UNSUPPORTED_MESSAGE)
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model(
                "view_image handler received unsupported payload"
            )
        arguments = payload.arguments
        if arguments is None:
            raise FunctionCallError.respond_to_model(
                "view_image handler received unsupported payload"
            )
        args = parse_view_image_arguments(arguments)
        image_detail = _effective_detail(args.detail, self.options)
        cwd = self.cwd
        turn = getattr(invocation_or_payload, "turn", None)
        if turn is not None:
            turn_environment = resolve_tool_environment(turn, args.environment_id)
            if turn_environment is None:
                raise FunctionCallError.respond_to_model(
                    "view_image is unavailable in this session"
                )
            cwd = Path(getattr(turn_environment, "cwd", cwd))
        elif args.environment_id is not None:
            raise FunctionCallError.respond_to_model(
                "view_image is unavailable in this session"
            )
        path = _resolve_path(cwd, args.path)

        if not path.exists():
            raise FunctionCallError.respond_to_model(
                f"unable to locate image at `{path}`: file not found"
            )
        if not path.is_file():
            raise FunctionCallError.respond_to_model(f"image path `{path}` is not a file")
        try:
            file_bytes = path.read_bytes()
        except OSError as err:
            raise FunctionCallError.respond_to_model(
                f"unable to read image at `{path}`: {err}"
            ) from err
        try:
            image_url = data_url_for_image(path, file_bytes)
        except ValueError as err:
            raise FunctionCallError.respond_to_model(
                f"unable to process image at `{path}`: {err}"
            ) from err
        return ViewImageOutput(image_url=image_url, image_detail=image_detail)


def parse_view_image_arguments(arguments: str) -> ViewImageArgs:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        decoded = json.loads(arguments)
    except json.JSONDecodeError as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse function arguments: {err}"
        ) from err
    try:
        return ViewImageArgs.from_mapping(decoded)
    except ValueError as err:
        raise FunctionCallError.respond_to_model(str(err)) from err
    except (KeyError, TypeError) as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse function arguments: {err}"
        ) from err


def data_url_for_image(path: Path, file_bytes: bytes) -> str:
    if not isinstance(path, Path):
        raise TypeError("path must be Path")
    if not isinstance(file_bytes, bytes):
        raise TypeError("file_bytes must be bytes")
    mime_type = mimetypes.guess_type(str(path))[0]
    if mime_type is None or not mime_type.startswith("image/"):
        raise ValueError("unsupported image MIME type")
    if not _looks_like_supported_image(file_bytes, mime_type):
        raise ValueError("image bytes do not match a supported image format")
    return f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('ascii')}"


def _effective_detail(
    detail: ImageDetail | None,
    options: ViewImageToolOptions,
) -> ImageDetail:
    if detail is ImageDetail.ORIGINAL and options.can_request_original_image_detail:
        return ImageDetail.ORIGINAL
    return DEFAULT_IMAGE_DETAIL


def _parse_view_image_detail(value: JsonValue) -> ImageDetail:
    if not isinstance(value, str):
        raise TypeError("detail must be a string")
    if value == "high":
        return ImageDetail.HIGH
    if value == "original":
        return ImageDetail.ORIGINAL
    raise ValueError(
        "view_image.detail only supports `high` or `original`; omit `detail` for default high resized behavior, got "
        f"`{value}`"
    )


def _resolve_path(cwd: Path, path: str) -> Path:
    if not isinstance(cwd, Path):
        raise TypeError("cwd must be Path")
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return cwd / candidate


def _looks_like_supported_image(file_bytes: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type in {"image/jpeg", "image/jpg"}:
        return file_bytes.startswith(b"\xff\xd8\xff")
    if mime_type == "image/gif":
        return file_bytes.startswith((b"GIF87a", b"GIF89a"))
    if mime_type == "image/webp":
        return len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP"
    if mime_type == "image/bmp":
        return file_bytes.startswith(b"BM")
    return bool(file_bytes)


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


__all__ = [
    "VIEW_IMAGE_TOOL_NAME",
    "VIEW_IMAGE_UNSUPPORTED_MESSAGE",
    "ViewImageArgs",
    "ViewImageHandler",
    "ViewImageOutput",
    "ViewImageToolOptions",
    "create_view_image_tool",
    "data_url_for_image",
    "parse_view_image_arguments",
]
