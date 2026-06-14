import asyncio
import json
from types import SimpleNamespace

from pycodex.core import FunctionCallError, ToolPayload
from pycodex.core.context_manager.history import ContextManager
from pycodex.core.tools.handlers.view_image import (
    VIEW_IMAGE_UNSUPPORTED_MESSAGE,
    ViewImageHandler,
    ViewImageToolOptions,
    parse_view_image_arguments,
)
from pycodex.protocol import (
    ContentItem,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ImageDetail,
    ResponseItem,
)

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_png(root, name="image.png"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_1X1)
    return path


def _handle(root, args, *, options=ViewImageToolOptions(), turn=None, session=None, call_id="call-image"):
    invocation = SimpleNamespace(
        session=session,
        turn=turn,
        call_id=call_id,
        payload=ToolPayload.function(json.dumps(args)),
    )
    return ViewImageHandler(options, cwd=root).handle(invocation)


def test_user_turn_with_local_image_attaches_image(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::user_turn_with_local_image_attaches_image.
    _write_png(tmp_path)

    output = _handle(tmp_path, {"path": "image.png"})

    assert output.image_url.startswith("data:image/png;base64,")
    assert output.image_detail is ImageDetail.HIGH


def test_user_turn_with_vertical_local_image_resizes_to_square_bounds(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::user_turn_with_vertical_local_image_resizes_to_square_bounds.
    _write_png(tmp_path, "vertical.png")

    output = _handle(tmp_path, {"path": "vertical.png"})

    assert output.image_url.startswith("data:image/png;base64,")
    assert output.image_detail is ImageDetail.HIGH


def test_view_image_tool_attaches_local_image(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_attaches_local_image.
    _write_png(tmp_path, "assets/example.png")
    output = _handle(tmp_path, {"path": "assets/example.png"})
    response_item = output.to_response_item("view-image-call", ToolPayload.function("{}"))

    assert response_item.call_id == "view-image-call"
    assert response_item.output.success is True
    content_items = response_item.output.body.content_items
    assert len(content_items) == 1
    assert content_items[0].type == "input_image"
    assert content_items[0].image_url.startswith("data:image/png;base64,")


def test_view_image_routes_to_selected_local_environment(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_routes_to_selected_local_environment.
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _write_png(local, "local.png")
    turn = SimpleNamespace(environments=(SimpleNamespace(environment_id="local", cwd=local), SimpleNamespace(environment_id="remote", cwd=remote)))

    output = _handle(tmp_path, {"path": "local.png", "environment_id": "local"}, turn=turn)

    assert output.image_url.startswith("data:image/png;base64,")


def test_view_image_tool_applies_local_sandbox_read_denies(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_applies_local_sandbox_read_denies.
    with pytest_raises_function_error("unable to locate image"):
        _handle(tmp_path, {"path": "denied.png"})


def test_view_image_routes_to_selected_remote_environment(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_routes_to_selected_remote_environment.
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _write_png(remote, "remote.png")
    turn = SimpleNamespace(environments=(SimpleNamespace(environment_id="local", cwd=local), SimpleNamespace(environment_id="remote", cwd=remote)))

    output = _handle(tmp_path, {"path": "remote.png", "environment_id": "remote"}, turn=turn)

    assert output.image_url.startswith("data:image/png;base64,")


def test_view_image_tool_can_preserve_original_resolution_when_requested_on_gpt5_3_codex(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_can_preserve_original_resolution_when_requested_on_gpt5_3_codex.
    _write_png(tmp_path, "original.png")

    output = _handle(
        tmp_path,
        {"path": "original.png", "detail": "original"},
        options=ViewImageToolOptions(can_request_original_image_detail=True),
    )

    assert output.image_detail is ImageDetail.ORIGINAL


def test_view_image_tool_errors_clearly_for_unsupported_detail_values() -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_errors_clearly_for_unsupported_detail_values.
    with pytest_raises_function_error("only supports `high` or `original`"):
        parse_view_image_arguments(json.dumps({"path": "image.png", "detail": "low"}))


def test_view_image_tool_treats_null_detail_as_omitted(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_treats_null_detail_as_omitted.
    _write_png(tmp_path, "null-detail.png")

    output = _handle(tmp_path, {"path": "null-detail.png", "detail": None})

    assert output.image_detail is ImageDetail.HIGH


def test_view_image_tool_resizes_when_model_lacks_original_detail_support(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_resizes_when_model_lacks_original_detail_support.
    _write_png(tmp_path, "no-original.png")

    output = _handle(tmp_path, {"path": "no-original.png", "detail": "original"})

    assert output.image_detail is ImageDetail.HIGH


def test_view_image_tool_does_not_force_original_resolution_with_capability_only(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_does_not_force_original_resolution_with_capability_only.
    _write_png(tmp_path, "capability-only.png")

    output = _handle(tmp_path, {"path": "capability-only.png"}, options=ViewImageToolOptions(can_request_original_image_detail=True))

    assert output.image_detail is ImageDetail.HIGH


def test_view_image_tool_errors_when_path_is_directory(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_errors_when_path_is_directory.
    (tmp_path / "assets").mkdir()

    with pytest_raises_function_error("is not a file"):
        _handle(tmp_path, {"path": "assets"})


def test_view_image_tool_errors_for_non_image_files(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_errors_for_non_image_files.
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/example.json").write_text('{"message":"hello"}', encoding="utf-8")

    with pytest_raises_function_error("unsupported image MIME type"):
        _handle(tmp_path, {"path": "assets/example.json"})


def test_view_image_tool_errors_when_file_missing(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_errors_when_file_missing.
    with pytest_raises_function_error("unable to locate image"):
        _handle(tmp_path, {"path": "missing/example.png"})


def test_view_image_tool_returns_unsupported_message_for_text_only_model(tmp_path) -> None:
    # Rust: core/tests/suite/view_image.rs::view_image_tool_returns_unsupported_message_for_text_only_model.
    _write_png(tmp_path)
    turn = SimpleNamespace(model_info=SimpleNamespace(input_modalities=("text",)))

    with pytest_raises_function_error(VIEW_IMAGE_UNSUPPORTED_MESSAGE):
        _handle(tmp_path, {"path": "image.png"}, turn=turn)


def test_replaces_invalid_local_image_after_bad_request() -> None:
    # Rust: core/tests/suite/view_image.rs::replaces_invalid_local_image_after_bad_request.
    image_output = ResponseItem(
        type="function_call_output",
        call_id="call-image",
        output=FunctionCallOutputPayload.from_content_items(
            (FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA"),),
            success=True,
        ),
    )
    history = ContextManager.from_items((ResponseItem.function_call("view_image", "{}", "call-image"), image_output))

    assert history.replace_last_turn_images("Invalid image") is True
    replaced = history.items[-1].output.body.content_items[0]
    assert replaced == FunctionCallOutputContentItem.input_text("Invalid image")


class pytest_raises_function_error:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert exc_type is FunctionCallError
        assert self.expected in str(exc)
        return True
