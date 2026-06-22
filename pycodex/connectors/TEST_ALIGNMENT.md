# codex-connectors test alignment

Rust crate: `codex-connectors`

Python package: `pycodex/connectors`

Status: `complete`

## Certified Modules

- `codex/codex-rs/connectors/src/accessible.rs` -> `pycodex/connectors/accessible.py`
- `codex/codex-rs/connectors/src/directory_cache.rs` -> `pycodex/connectors/directory_cache.py`
- `codex/codex-rs/connectors/src/filter.rs` -> `pycodex/connectors/filter.py`
- `codex/codex-rs/connectors/src/lib.rs` -> `pycodex/connectors/__init__.py`
- `codex/codex-rs/connectors/src/merge.rs` -> `pycodex/connectors/merge.py`
- `codex/codex-rs/connectors/src/metadata.rs` -> `pycodex/connectors/metadata.py`

## Rust Tests And Contracts

- Rust `src/filter.rs` tests are migrated in `tests/test_connectors_rs.py`.
- Rust `src/merge.rs` tests are migrated in `tests/test_connectors_rs.py` and reinforced by `tests/test_core_connectors.py`.
- Rust `src/lib.rs` directory/cache tests are migrated in `tests/test_connectors_rs.py`.
- Rust `src/directory_cache.rs` has no direct inline tests; it is covered through Rust `src/lib.rs` disk-cache tests and source-contract tests in `tests/test_connectors_rs.py`.
- Rust `src/accessible.rs` has no direct inline tests; it is covered by source-contract tests through `tests/test_core_connectors.py`.
- Rust `src/metadata.rs` has no direct inline tests; it is covered by source-contract tests through `tests/test_core_connectors.py` and `tests/test_connectors_rs.py`.

## Python Tests

- `tests/test_connectors_rs.py`
- `tests/test_core_connectors.py`
- `tests/test_core_mcp_tool_exposure.py`
- `tests/test_core_request_plugin_install.py`

## Validation

- `python -m pytest tests/test_connectors_rs.py -q --tb=short` (`11 passed`)
- `python -m pytest tests/test_core_connectors.py tests/test_core_mcp_tool_exposure.py tests/test_core_request_plugin_install.py -q --tb=short` (`59 passed`)
- `python -m py_compile pycodex/connectors/__init__.py pycodex/connectors/filter.py pycodex/connectors/directory_cache.py pycodex/connectors/metadata.py pycodex/connectors/merge.py pycodex/connectors/accessible.py tests/test_connectors_rs.py` passed

## Remaining Gaps

No known crate-local gaps. Core runtime policy and config behavior that consumes connectors belongs to Rust `codex-rs/core/src/connectors.rs` and remains tracked under `pycodex.core.connectors`, not this crate.
