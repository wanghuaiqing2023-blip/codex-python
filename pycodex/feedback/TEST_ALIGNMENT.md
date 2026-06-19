# codex-feedback test alignment

Rust crate: `codex-feedback`

Python package: `pycodex/feedback`

Status: `complete`

Module mapping:

- `codex/codex-rs/feedback/src/feedback_diagnostics.rs` ->
  `pycodex/feedback/feedback_diagnostics.py` (`complete`)
- `codex/codex-rs/feedback/src/lib.rs` -> `pycodex/feedback/__init__.py`
  (`complete`)

Rust behavior covered by `tests/test_feedback_feedback_diagnostics_rs.py`:

- `collect_from_pairs_reports_raw_values_and_attachment`
- `collect_from_pairs_ignores_absent_values`
- `collect_from_pairs_preserves_whitespace_and_empty_values`
- `collect_from_pairs_reports_values_verbatim`

Rust behavior covered by `tests/test_feedback_lib_rs.py`:

- `ring_buffer_drops_front_when_full`
- `metadata_layer_records_tags_from_feedback_target`
- `feedback_attachments_gate_connectivity_diagnostics`
- `upload_tags_include_client_tags_and_preserve_reserved_fields`
- `display_classification` and upload event shaping source contract

Validation:

- `python -m pytest tests/test_feedback_lib_rs.py tests/test_feedback_feedback_diagnostics_rs.py -q`
  (`9 passed`)
- `python -m pytest tests/test_feedback_feedback_diagnostics_rs.py -q`
  (`4 passed`)
- `python -m py_compile pycodex/feedback/feedback_diagnostics.py pycodex/feedback/__init__.py tests/test_feedback_feedback_diagnostics_rs.py`
  (passed)
- `python -m pytest tests/test_app_server_request_processors_feedback_processor_rs.py tests/test_app_server_request_processors_feedback_doctor_report_rs.py tests/test_tui_bottom_pane_feedback_view.py tests/test_external_crate_interfaces.py::test_core_plugins_feedback_image_and_escalation_interfaces -q`
  (`22 passed`)
