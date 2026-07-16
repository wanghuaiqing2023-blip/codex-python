# `src/config_manager_service.rs` Alignment Status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/config_manager_service.rs`
- `codex/codex-rs/app-server/src/config_manager_service_tests.rs`

Python mapping:

- `pycodex/app_server/config_manager_service.py`
- `tests/test_app_server_config_manager_service_rs.py`

Mapped behavior contract:

- `ConfigManagerError` write-code extraction.
- `ConfigManagerService.read(...)`, `read_requirements(...)`,
  `write_value(...)`, `batch_write(...)`, and injected-layer
  `apply_edits(...)` projection.
- User-config path restriction, expected-version conflict handling, default
  user config path selection, and legacy `profile` / `profiles.*` write
  rejection.
- Fresh user-layer loading before each mutation and atomic persistence through
  the core config edit engine, including preservation of unrelated values
  written after the service was created.
- JSON-null clear semantics, keyPath parsing, quoted and escaped keyPath
  segments, nested value lookup through tables and arrays, clear no-op behavior,
  replace/upsert merge semantics, and effective-layer override metadata.
- Protocol-layer/source conversion for read origins, optional layer inclusion,
  and override message text for app-server protocol responses.

Deferred dependency/runtime boundaries:

- Rust's comment/order-preserving TOML document edits, exact `ConfigEdit`
  line/column tracking, and the full set of parser/persistence error details.
- Core config validation, managed policy validation, feature requirement
  validation, reserved built-in provider checks, and selected-profile config
  file loading.
- Thread-agnostic versus cwd-aware config loading remains owned by
  `pycodex.app_server.config_manager` and lower config loaders; this module uses
  an injected `ConfigLayerStack` to keep the module boundary local.

Validation:

- 2026-06-19: `python -m pytest tests/test_app_server_config_manager_service_rs.py -q`
  -> 15 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/config_manager_service.py tests/test_app_server_config_manager_service_rs.py`.
- 2026-07-16: config writes reload the latest user layer and persist to disk;
  the in-process TUI request handle routes through `ConfigRequestProcessor`
  before this service and the core config editor. Focused module and restart
  validation passed.
