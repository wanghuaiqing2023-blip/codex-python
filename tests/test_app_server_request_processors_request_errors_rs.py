"""Rust parity tests for ``request_processors/request_errors.rs``."""

from pycodex.app_server.request_processors_request_errors import environment_selection_error_message
from pycodex.protocol import CodexErr


class DisplayOnlyError(Exception):
    def __str__(self) -> str:
        return "display branch"


def test_environment_selection_error_message_returns_invalid_request_message() -> None:
    # Rust: CodexErr::InvalidRequest(message) returns message directly.
    assert environment_selection_error_message(CodexErr.invalid_request("unknown environment")) == "unknown environment"


def test_environment_selection_error_message_uses_display_for_other_codex_errors() -> None:
    # Rust: all non-InvalidRequest CodexErr variants fall through to Display.
    assert environment_selection_error_message(CodexErr.thread_not_found("thread-1")) == "no thread with id: thread-1"


def test_environment_selection_error_message_accepts_rust_shaped_duck_values() -> None:
    # Keeps the helper usable at the app-server boundary without depending on
    # every upstream CodexErr construction path.
    assert environment_selection_error_message({"type": "InvalidRequest", "message": "bad env"}) == "bad env"
    assert environment_selection_error_message(DisplayOnlyError()) == "display branch"
