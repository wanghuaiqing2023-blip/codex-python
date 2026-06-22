# codex-config `src/thread_config.rs` alignment

Status: `complete_candidate`

Rust owner: `codex-config`

Rust module: `codex/codex-rs/config/src/thread_config.rs`

Python module: `pycodex/config/thread_config.py`

Python tests: `tests/test_config_thread_config.py`

## Behavior Contract

`src/thread_config.rs` owns the thread-scoped config source model, load error
taxonomy, loader trait surface, static/noop loaders, session/user source
conversion, and session config projection into an ordinary config layer.

The Python port mirrors the module-scoped contract:

- `ThreadConfigContext` carries optional thread id and cwd.
- `SessionThreadConfig`, `UserThreadConfig`, and `ThreadConfigSource` preserve
  the Rust session/user source split.
- `ThreadConfigLoadErrorCode` and `ThreadConfigLoadError` preserve the stable
  categories, message display, `code()`, and `status_code()` accessors.
- `ThreadConfigLoader.load_config_layers()` applies the Rust source-to-layer
  conversion flow.
- `StaticThreadConfigLoader` returns its configured source list without using
  caller context.
- `NoopThreadConfigLoader` returns no sources.
- User thread config currently emits no TOML-backed layer.
- Empty session thread config emits no layer.
- Non-empty session thread config emits a `SessionFlags` config layer with
  `model_provider`, `model_providers`, and sorted feature booleans.

## Notes

This file tracks only the Rust root module `src/thread_config.rs`. The Rust
submodule `src/thread_config/remote.rs` owns the concrete remote/gRPC loader,
proto conversion, and timeout/status mapping behavior; those remain a separate
module boundary even though the Python compatibility file currently houses
lightweight remote helpers in the same `.py` file.

## Validation

Not run in this turn. Current automation defers actual pytest execution until
`codex-config` functional code is complete.
