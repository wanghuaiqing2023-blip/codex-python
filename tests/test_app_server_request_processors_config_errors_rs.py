"""Rust parity tests for ``request_processors/config_errors.rs``."""

from __future__ import annotations

from pycodex.app_server.request_processors_config_errors import config_load_error
from pycodex.config import CloudRequirementsLoadError, CloudRequirementsLoadErrorCode


def _io_error(message: str, source: BaseException | None = None) -> OSError:
    err = OSError(message)
    if source is not None:
        err.__cause__ = source
    return err


def test_config_load_error_marks_cloud_requirements_failures_for_relogin() -> None:
    # Rust source: config_load_error_marks_cloud_requirements_failures_for_relogin.
    source = CloudRequirementsLoadError.new(
        CloudRequirementsLoadErrorCode.AUTH,
        401,
        "Your authentication session could not be refreshed automatically. Please log out and sign in again.",
    )

    error = config_load_error(_io_error(str(source), source))

    assert error.code == -32600
    assert "failed to load configuration" in error.message
    assert error.data == {
        "reason": "cloudRequirements",
        "errorCode": "Auth",
        "action": "relogin",
        "statusCode": 401,
        "detail": "Your authentication session could not be refreshed automatically. Please log out and sign in again.",
    }


def test_config_load_error_leaves_non_cloud_requirements_failures_unmarked() -> None:
    # Rust source: config_load_error_leaves_non_cloud_requirements_failures_unmarked.
    error = config_load_error(_io_error("required MCP servers failed to initialize"))

    assert error.code == -32600
    assert "failed to load configuration" in error.message
    assert error.data is None


def test_config_load_error_marks_non_auth_cloud_requirements_failures_without_relogin() -> None:
    # Rust source: config_load_error_marks_non_auth_cloud_requirements_failures_without_relogin.
    source = CloudRequirementsLoadError.new(
        CloudRequirementsLoadErrorCode.REQUEST_FAILED,
        None,
        "Failed to load cloud requirements (workspace-managed policies).",
    )

    error = config_load_error(_io_error(str(source), source))

    assert error.data == {
        "reason": "cloudRequirements",
        "errorCode": "RequestFailed",
        "detail": "Failed to load cloud requirements (workspace-managed policies).",
    }
