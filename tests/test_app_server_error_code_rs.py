from pycodex.app_server.error_code import (
    INPUT_TOO_LARGE_ERROR_CODE,
    INTERNAL_ERROR_CODE,
    INVALID_PARAMS_ERROR_CODE,
    INVALID_REQUEST_ERROR_CODE,
    METHOD_NOT_FOUND_ERROR_CODE,
    OVERLOADED_ERROR_CODE,
    internal_error,
    invalid_params,
    invalid_request,
    method_not_found,
)
from pycodex.app_server_protocol import JSONRPCErrorError


def test_error_code_constants_match_rust_module() -> None:
    # Rust: error_code.rs module constants.
    assert INVALID_REQUEST_ERROR_CODE == -32600
    assert METHOD_NOT_FOUND_ERROR_CODE == -32601
    assert INVALID_PARAMS_ERROR_CODE == -32602
    assert INTERNAL_ERROR_CODE == -32603
    assert OVERLOADED_ERROR_CODE == -32001
    assert INPUT_TOO_LARGE_ERROR_CODE == "input_too_large"


def test_error_helpers_construct_jsonrpc_error_without_data() -> None:
    # Rust: invalid_request/method_not_found/invalid_params/internal_error call error(...).
    assert invalid_request("bad") == JSONRPCErrorError(code=-32600, message="bad", data=None)
    assert method_not_found("missing") == JSONRPCErrorError(code=-32601, message="missing", data=None)
    assert invalid_params("wrong") == JSONRPCErrorError(code=-32602, message="wrong", data=None)
    assert internal_error("boom") == JSONRPCErrorError(code=-32603, message="boom", data=None)


def test_error_helpers_convert_message_like_rust_into_string() -> None:
    # Rust accepts impl Into<String>; Python mirrors that boundary with str(...).
    assert invalid_request(123).message == "123"
