from pycodex.core.session.runtime import resume_model_mismatch_warning_event


def test_emits_warning_when_resumed_model_differs():
    # Rust: codex/codex-rs/core/tests/suite/resume_warning.rs
    # Test: emits_warning_when_resumed_model_differs.
    warning = resume_model_mismatch_warning_event("previous-model", "current-model")

    assert warning is not None
    assert warning.type == "warning"
    assert "previous-model" in warning.payload.message
    assert "current-model" in warning.payload.message
    assert resume_model_mismatch_warning_event("same-model", "same-model") is None
