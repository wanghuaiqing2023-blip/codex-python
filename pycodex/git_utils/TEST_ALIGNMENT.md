# pycodex.git_utils Test Alignment

Updated: 2026-06-15

This file records Rust-derived test-source mapping for the Python counterpart
of the Rust `codex-git-utils` crate.

## Rust Test Inventory

| Rust source | Rust test count | Contract area | Python target |
|---|---:|---|---|
| `codex/codex-rs/git-utils/src/info.rs` | 3 | `git_utils.info` | `tests/test_core_git_info.py` |
| `codex/codex-rs/git-utils/src/branch.rs` | 3 | `git_utils.branch` | `tests/test_core_git_info.py` |
| `codex/codex-rs/git-utils/src/apply.rs` | 10 | `git_utils.apply` | pending focused test/audit |

## Completed Source Comment Batch: info.rs

| Contract | Rust source/test | Python target |
|---|---|---|
| `git_utils.info.canonicalize_git_remote_url` | `info.rs::tests::canonicalize_git_remote_url_normalizes_github_variants`; `info.rs::tests::canonicalize_git_remote_url_handles_ghe_without_lowercasing_path`; `info.rs::tests::canonicalize_git_remote_url_rejects_non_repository_values` | `tests/test_core_git_info.py::CoreGitInfoTests.test_canonicalize_git_remote_url_matches_upstream_cases` |

## Completed Source Comment Batch: branch.rs

| Contract | Rust source/test | Python target |
|---|---|---|
| `git_utils.branch.merge_base_with_head` | `branch.rs::tests::merge_base_returns_shared_commit` | `tests/test_core_git_info.py::CoreGitInfoTests.test_merge_base_returns_shared_commit` |
| `git_utils.branch.merge_base_with_head` | `branch.rs::tests::merge_base_prefers_upstream_when_remote_ahead` | `tests/test_core_git_info.py::CoreGitInfoTests.test_merge_base_prefers_upstream_when_remote_ahead` |
| `git_utils.branch.merge_base_with_head` | `branch.rs::tests::merge_base_returns_none_when_branch_missing` | `tests/test_core_git_info.py::CoreGitInfoTests.test_merge_base_returns_none_when_branch_missing` |

## Completed Source Comment Batch: apply.rs parser slice

| Contract | Rust source/test | Python target |
|---|---|---|
| `git_utils.apply.extract_paths_from_patch` | `apply.rs::tests::extract_paths_handles_quoted_headers`; `apply.rs::tests::extract_paths_ignores_dev_null_header`; `apply.rs::tests::extract_paths_unescapes_c_style_in_quoted_headers` | `tests/test_core_git_info.py::CoreGitInfoTests.test_extract_paths_from_patch_matches_rust_header_cases` |
| `git_utils.apply.parse_git_apply_output` | `apply.rs::tests::parse_output_unescapes_quoted_paths` | `tests/test_core_git_info.py::CoreGitInfoTests.test_parse_git_apply_output_unescapes_quoted_paths` |

## Completed Source Comment Batch: apply.rs repository scenarios

| Contract | Rust source/test | Python target |
|---|---|---|
| `git_utils.apply.apply_git_patch` | `apply.rs::tests::apply_add_success` | `tests/test_core_git_info.py::CoreGitInfoTests.test_apply_git_patch_add_success` |
| `git_utils.apply.apply_git_patch` | `apply.rs::tests::apply_modify_conflict`; `apply.rs::tests::apply_modify_skipped_missing_index` | `tests/test_core_git_info.py::CoreGitInfoTests.test_apply_git_patch_reports_conflict_and_missing_index_failures` |
| `git_utils.apply.apply_git_patch` | `apply.rs::tests::apply_then_revert_success`; `apply.rs::tests::revert_preflight_does_not_stage_index` | `tests/test_core_git_info.py::CoreGitInfoTests.test_apply_git_patch_revert_and_revert_preflight` |
| `git_utils.apply.apply_git_patch` | `apply.rs::tests::preflight_blocks_partial_changes` | `tests/test_core_git_info.py::CoreGitInfoTests.test_apply_git_patch_preflight_blocks_partial_changes` |

## Validation

- `python -m pytest tests/test_core_git_info.py -q`
  - `17 passed, 7 subtests passed`

## Next Migration Targets

- No known remaining `codex-git-utils` module-scoped migration target is open.
  Future work should only be added when upstream Rust changes introduce new
  tests or behavior contracts.
