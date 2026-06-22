# codex-config `src/thread_config/remote.rs` alignment

Status: `complete_candidate`

Rust owner: `codex-config`

Rust module: `codex/codex-rs/config/src/thread_config/remote.rs`

Python module: `pycodex/config/thread_config.py`

Python tests: `tests/test_config_thread_config.py`

## Behavior Contract

`src/thread_config/remote.rs` owns the remote thread-config loader boundary,
request timeout metadata, remote status mapping, proto source conversion,
session config conversion, model provider conversion, model-provider auth
conversion, and parse-failure taxonomy.

The Python port mirrors the module-scoped contract with a dependency-light
compatibility boundary:

- `RemoteThreadConfigLoader.new()` preserves endpoint construction.
- `RemoteThreadConfigLoader.load()` supports an injected async or sync client
  boundary for deterministic tests and dependency-light use.
- `load_thread_config_request()` carries `thread_id`, `cwd`, and the Rust
  5-second gRPC timeout metadata shape.
- `remote_status_to_error()` maps auth failures to `Auth`, deadline failures
  to `Timeout`, and all other remote failures to `RequestFailed`.
- `thread_config_source_from_proto()` converts session and user sources and
  fails closed when the source payload is absent.
- `session_thread_config_from_proto()` converts model provider lists/maps and
  sorted feature booleans into `SessionThreadConfig`.
- `model_provider_from_proto()` preserves provider fields, accepts only the
  `responses` wire API, and rejects missing ids, omitted wire APIs, and
  unknown wire APIs.
- `model_provider_auth_from_proto()` rejects zero timeouts and non-absolute
  cwd values while preserving command, args, timeout, refresh interval, and
  cwd fields.

## Notes

The Python port intentionally does not implement a concrete tonic/gRPC client.
The core behavior contract is preserved through an injectable client boundary
and pure conversion helpers. This keeps the port dependency-light while still
matching the Rust module's request, error, and conversion semantics.

## Validation

Not run in this turn. Current automation defers actual pytest execution until
`codex-config` functional code is complete.
