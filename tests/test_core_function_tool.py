from pycodex.core.function_tool import FunctionCallError, FunctionCallErrorKind


def test_function_call_error_respond_to_model_renders_message():
    error = FunctionCallError.respond_to_model("try a different target")

    assert error.kind is FunctionCallErrorKind.RESPOND_TO_MODEL
    assert error.is_model_response is True
    assert error.is_fatal is False
    assert str(error) == "try a different target"


def test_function_call_error_fatal_renders_prefixed_message():
    error = FunctionCallError.fatal("tool payload mismatch")

    assert error.kind is FunctionCallErrorKind.FATAL
    assert error.is_model_response is False
    assert error.is_fatal is True
    assert str(error) == "Fatal error: tool payload mismatch"
