# pycodex.backend_client

Rust crate: `codex-backend-client`

Rust anchor: `codex/codex-rs/backend-client`

This package mirrors selected dependency-light behavior from the Rust backend
client crate.

## Module Coverage

| Rust module | Python surface | Status | Notes |
|---|---|---|---|
| `src/lib.rs` | `pycodex.backend_client` | complete_slice | Public facade exports the client, request error, task-details models, sibling-turn response, and add-credits enum covered in this slice. |
| `src/types.rs` | `CodeTaskDetailsResponse`, `Turn`, `TurnItem`, content/worklog/error helpers | complete_slice | Task-details JSON deserialization, unified diff extraction, assistant text extraction, user prompt joining, and assistant error summary are covered by Rust-derived tests and fixtures. |
| `src/client.rs` | `Client`, `PathStyle`, rate-limit mapping helpers, endpoint URL/query helpers, add-credits URL/body helpers, auth-provider headers, standard-library transport, custom CA/cookie hooks | complete | Base URL normalization, path-style selection, header projection, auth-provider header injection and explicit account/FedRAMP override ordering, endpoint path/query shaping, create-task response id extraction, rate-limit payload mapping, preferred snapshot selection, request error display/status, JSON decode context, injected/default HTTP execution, custom CA context selection, ChatGPT Cloudflare cookie store hook, and add-credits URL/body helpers are covered by Rust-derived tests. |

## Implementation Notes

- Python uses dependency-light standard-library/injected HTTP transport rather than native async `reqwest`.
- Custom CA and ChatGPT Cloudflare cookie behavior are delegated to the completed `pycodex.codex_client` module contracts.

`codex-backend-client` is strict `complete` for the dependency-light Python port.

## Tests

- `tests/test_backend_client_types_rs.py`
- `tests/test_backend_client_client_rs.py`
