# codex-core-api src/lib.rs status

Rust coordinate: `codex/codex-rs/core-api/src/lib.rs`

Python coordinate: `pycodex/core_api/__init__.py`

Status: `complete`

Behavior contract:

- provide the public facade for thread management APIs built on `codex-core`.
- re-export Rust `pub use` symbols from app-server protocol, arg0, config, core, exec-server, extension-api, features, login, model-provider, models-manager, protocol, and absolute-path crates.
- keep this module as a facade only; concrete neighboring crate behavior remains owned by those packages.

Evidence:

- `tests/test_core_api_lib_rs.py` checks facade importability, identity for existing Python counterparts, and explicit placeholders for neighboring concrete types not yet implemented.
