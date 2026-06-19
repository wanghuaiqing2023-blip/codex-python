# pycodex.codex_backend_openapi_models

Python package for the Rust `codex-backend-openapi-models` crate.

Rust crate: `codex-backend-openapi-models`

Rust path: `codex/codex-rs/codex-backend-openapi-models`

## Alignment Role

This crate contains generated OpenAPI model structs used by backend-client
code. The Python port keeps these models dependency-light and focuses on the
serde-visible behavior used by neighboring crates.

## Certified Modules

- `codex/codex-rs/codex-backend-openapi-models/src/models/additional_rate_limit_details.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/additional_rate_limit_details.py`;
  see `ADDITIONAL_RATE_LIMIT_DETAILS_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_window_snapshot.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/rate_limit_window_snapshot.py`;
  see `RATE_LIMIT_WINDOW_SNAPSHOT_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_details.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/rate_limit_status_details.py`;
  see `RATE_LIMIT_STATUS_DETAILS_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_payload.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/rate_limit_status_payload.py`;
  see `RATE_LIMIT_STATUS_PAYLOAD_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/credit_status_details.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/credit_status_details.py`;
  see `CREDIT_STATUS_DETAILS_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/config_file_response.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/config_file_response.py`;
  see `CONFIG_FILE_RESPONSE_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/git_pull_request.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/git_pull_request.py`;
  see `GIT_PULL_REQUEST_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/external_pull_request_response.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/external_pull_request_response.py`;
  see `EXTERNAL_PULL_REQUEST_RESPONSE_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/task_response.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/task_response.py`;
  see `TASK_RESPONSE_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/code_task_details_response.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/code_task_details_response.py`;
  see `CODE_TASK_DETAILS_RESPONSE_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/task_list_item.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/task_list_item.py`;
  see `TASK_LIST_ITEM_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/paginated_list_task_list_item_.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/paginated_list_task_list_item.py`;
  see `PAGINATED_LIST_TASK_LIST_ITEM_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/models/mod.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/models/__init__.py`;
  see `MODELS_MOD_RS_STATUS.md`.
- `codex/codex-rs/codex-backend-openapi-models/src/lib.rs`
  is mapped to
  `pycodex/codex_backend_openapi_models/__init__.py`;
  see `LIB_RS_STATUS.md`.

## Remaining Rust Modules

None. All known Rust modules in this crate are mapped.
