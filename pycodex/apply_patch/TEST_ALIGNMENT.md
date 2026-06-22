# codex-apply-patch test alignment

## lib.rs

- `APPLY_PATCH_TOOL_INSTRUCTIONS` and `CODEX_CORE_APPLY_PATCH_ARG1` public constants -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_apply_patch_crate_public_constants_match_rust`.

Status: `complete_slice`; crate-owned public constants are exposed from `pycodex.apply_patch` and checked against the Rust surface contract.

## parser.rs

- `parse_patch`, `Hunk`, `UpdateFileChunk`, marker handling, add/delete/update/move hunks, first update chunk without explicit `@@`, and multiple hunk parsing -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_parse_patch_parses_multiple_hunk_variants` and `test_parse_patch_update_chunks_match_upstream_leniency`.
- Boundary and hunk parse errors, empty update hunks, invalid update chunk lines, and EOF marker validation -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_parse_patch_reports_boundary_and_hunk_errors` and `test_streaming_patch_parser_finish_and_errors`.
- Lenient heredoc wrapper parsing and environment-id preamble parsing/error behavior -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_parse_patch_accepts_lenient_heredoc_wrappers` and `test_parse_patch_reads_environment_id_preamble`.
- Relative/absolute hunk path handling and hunk path resolution semantics -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_verify_apply_patch_args_reads_files_and_resolves_paths`, `test_apply_patch_handler_move_update_reports_original_path_like_rust`, and `test_file_paths_for_action_includes_move_destination_like_rust`.

Status: `complete_slice`; parser public type/marker/grammar behavior is covered at the Python parser API and verified-args boundary.

## lib.rs

- `apply_patch` / `apply_hunks` successful add/update/delete/move application and user-facing summary output -> `tests/test_core_suite_apply_patch_cli.py::CoreSuiteApplyPatchCliTests::test_apply_patch_cli_multiple_operations_integration`, `test_apply_patch_cli_multiple_chunks`, `test_apply_patch_cli_moves_file_to_new_directory`, `test_apply_patch_cli_updates_file_appends_trailing_newline`, `test_apply_patch_cli_insert_only_hunk_modifies_file`, and `test_apply_patch_cli_move_overwrites_existing_destination`.
- `apply_hunks` validation/error boundaries for invalid hunks, missing context, missing targets, empty patches, directory deletion, path traversal, and side-effect-free verification failure -> `tests/test_core_suite_apply_patch_cli.py::CoreSuiteApplyPatchCliTests::test_apply_patch_cli_rejects_invalid_hunk_header`, `test_apply_patch_cli_reports_missing_context`, `test_apply_patch_cli_reports_missing_target_file`, `test_apply_patch_cli_delete_missing_file_reports_error`, `test_apply_patch_cli_rejects_empty_patch`, `test_apply_patch_cli_delete_directory_reports_verification_error`, `test_apply_patch_cli_rejects_path_traversal_outside_workspace`, and `test_apply_patch_cli_verification_failure_has_no_side_effects`.

Status: `complete_slice`; filesystem application and user-facing summary/error behavior is covered through the direct Python apply-patch disk path.

## standalone_executable.rs

- `run_main` one-argument/stdin selection, empty-stdin usage exit, extra-argument rejection, non-UTF8 argument rejection, and successful patch application -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_apply_patch_standalone_run_main_argument_and_stdin_contract`.

Status: `complete_slice`; standalone executable argument/input dispatch behavior is covered with a process-shaped Python semantic adapter.

## invocation.rs

- `maybe_parse_apply_patch` literal `apply_patch`/`applypatch`, Unix shell variants (`bash`, `zsh`, `sh`), PowerShell `-Command`/`-NoProfile`, and `cmd /c` heredoc plus `cd <path> &&` workdir extraction -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_maybe_parse_apply_patch_accepts_literal_invocations`, `test_maybe_parse_apply_patch_accepts_shell_heredoc_invocations`, and `test_maybe_parse_apply_patch_accepts_cd_prefixed_heredoc`.

Status: `complete_slice`; invocation shell classification and supported heredoc extraction variants are covered.

## seek_sequence.rs

- Exact/rstrip/trim/fuzzy Unicode punctuation line matching -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_derive_new_contents_from_chunks_matches_upstream_search_leniency`.
- Defensive pattern-longer-than-input no-panic behavior and EOF-first matching -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_derive_new_contents_from_chunks_matches_seek_sequence_defensive_edges`.

Status: `complete_slice`; sequence seeking behavior is covered through the public chunk-to-content derivation path.

## streaming_parser.rs

- `StreamingPatchParser::push_delta` complete-line streaming for add/delete/update hunks, update move paths, and environment-id preamble tolerance -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_streaming_patch_parser_streams_complete_lines_before_end_patch` and `test_streaming_patch_parser_update_move_and_environment_id`.
- Large patch split-by-character monotonic hunk growth and operation ordering -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_streaming_patch_parser_large_patch_split_by_character`.
- Indented update markers, bare empty update lines, CRLF behavior, finish-without-final-newline, missing end marker, and update-hunk error boundaries -> `tests/test_core_apply_patch.py::CoreApplyPatchTests::test_streaming_patch_parser_preserves_update_line_edge_cases` and `test_streaming_patch_parser_finish_and_errors`.

Status: `complete_slice`; streaming patch preview parser behavior is covered at the public parser API boundary.
