# pycodex.config

This package contains Python counterparts for Rust configuration behavior.

## Rust Counterparts

```text
Primary Rust crate: codex-config
Primary Rust path: codex/codex-rs/config

Related Rust crates:
- codex-execpolicy
- codex-features
- codex-model-provider-info
```

## Alignment Role

`pycodex.config` should own configuration parsing, overrides, config data
contracts, and policy-facing config decisions that are not specific to one
runtime entrypoint.

Typical Rust module counterparts include:

```text
codex/codex-rs/config/src/overrides.rs
codex/codex-rs/config/src/config_toml.rs
codex/codex-rs/config/src/types.rs
codex/codex-rs/config/src/profile_toml.rs
codex/codex-rs/config/src/permissions_toml.rs
codex/codex-rs/config/src/merge.rs
codex/codex-rs/config/src/strict_config.rs
```

## Python Modules

Current Python implementation files:

| Python module/file | Role |
|---|---|
| `pycodex/config/overrides.py` | config override parsing and CLI override representation |
| `pycodex/config/schema.py` | config schema fixture canonicalization and write helper |
| `pycodex/config/toml_compat.py` | dependency-light TOML compatibility parser used by config-facing code |

`pycodex/_toml.py` has been deleted; use `pycodex.config.toml_compat` directly.

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
config.overrides
config.toml_loading
config.merge
config.profile
config.permissions
config.strict_config
```

## Test Source Policy

Prefer Rust config tests and fixtures before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-config
# Rust module: src/overrides.rs
# Rust test: tests::example_test_name
# Contract: config.overrides
```

## Current Movement Status

No code movement is required for the first structural pass. This README is the
local map for future config alignment.
