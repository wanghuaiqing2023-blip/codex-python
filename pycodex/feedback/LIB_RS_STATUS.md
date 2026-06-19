# feedback/src/lib.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/feedback/src/lib.rs`

Python target:

- `pycodex/feedback/__init__.py`

Implemented public API:

- `DOCTOR_REPORT_ATTACHMENT_FILENAME`
- `WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME`
- `FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME` re-export
- `FeedbackRequestTags`
- `emit_feedback_request_tags`
- `emit_feedback_request_tags_with_auth_env`
- `CodexFeedback`
- `FeedbackMakeWriter`
- `FeedbackWriter`
- `FeedbackSnapshot`
- `FeedbackAttachmentPath`
- `FeedbackAttachment`
- `FeedbackUploadOptions`

Implemented source-contract helpers:

- byte-capacity ring buffer with front eviction
- metadata tag capture with Rust bool string formatting and tag cap behavior
- no-active-thread snapshot id generation
- diagnostics-gated feedback attachment construction
- upload tag merging with reserved field preservation
- classification display strings and upload event shaping

Notes:

- Rust's Sentry transport is represented by an injectable `sender` on
  `FeedbackUploadOptions`. This keeps the Python port dependency-light while
  preserving the Rust module's event/tag/attachment construction contract at the
  public boundary used by app-server feedback processing.
- Existing Python compatibility attributes such as `snapshot.logs`,
  `FeedbackAttachment(data=...)`, and `FeedbackAttachmentPath(filename=...)`
  remain supported.

Validation:

- `python -m pytest tests/test_feedback_lib_rs.py tests/test_feedback_feedback_diagnostics_rs.py -q`
  (`9 passed`)
- `python -m pytest tests/test_app_server_request_processors_feedback_processor_rs.py tests/test_app_server_request_processors_feedback_doctor_report_rs.py tests/test_tui_bottom_pane_feedback_view.py tests/test_external_crate_interfaces.py::test_core_plugins_feedback_image_and_escalation_interfaces -q`
  (`22 passed`)
- `python -m py_compile pycodex/feedback/__init__.py pycodex/feedback/feedback_diagnostics.py tests/test_feedback_lib_rs.py tests/test_feedback_feedback_diagnostics_rs.py`
  (passed)
