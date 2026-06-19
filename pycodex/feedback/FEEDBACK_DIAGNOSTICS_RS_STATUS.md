# feedback/src/feedback_diagnostics.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/feedback/src/feedback_diagnostics.rs`

Python target:

- `pycodex/feedback/feedback_diagnostics.py`

Implemented behavior:

- `FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME`
- `FeedbackDiagnostic`
- `FeedbackDiagnostics.new`
- `FeedbackDiagnostics.collect_from_env`
- `FeedbackDiagnostics.collect_from_pairs`
- `FeedbackDiagnostics.is_empty`
- `FeedbackDiagnostics.attachment_text`

Notes:

- Python keeps `collect_from_pairs` public so the Rust module's private helper
  can be covered directly by parity tests.
- Proxy environment variables are reported in Rust's fixed key order and values
  are preserved verbatim.
- `FeedbackDiagnostics.to_json_text` remains as a Python compatibility helper
  for the pre-existing local package surface; it is not part of the Rust module.

Validation:

- `python -m pytest tests/test_feedback_feedback_diagnostics_rs.py -q`
  (`4 passed`)
- `python -m py_compile pycodex/feedback/feedback_diagnostics.py pycodex/feedback/__init__.py tests/test_feedback_feedback_diagnostics_rs.py`
  (passed)
