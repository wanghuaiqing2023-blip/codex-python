# pycodex.utils_cli

This package contains Python counterparts for small CLI utility behavior.

## Rust Counterparts

```text
Primary Rust crate: codex-utils-cli
Primary Rust path: codex/codex-rs/utils/cli

Related utility crates may include:
- codex-utils-path
- codex-utils-string
- codex-utils-home-dir
- codex-utils-sandbox-summary
```

## Alignment Role

`pycodex.utils_cli` should own small reusable CLI helpers that are not specific
to a single command or runtime package.

Avoid growing this package into a cross-domain logic bucket. If behavior belongs
to config, protocol, exec, or core, keep it in that domain package.

## Alignment Unit

The default acceptance unit is a small module-scoped behavior contract.

Initial contract areas:

```text
utils_cli.resume_command
utils_cli.output_formatting
utils_cli.small_cli_helpers
```

## Test Source Policy

Prefer Rust utility crate tests before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-utils-cli
# Rust module: src/lib.rs
# Rust test: tests::example_test_name
# Contract: utils_cli.resume_command
```

## Current Movement Status

No code movement is required for the first structural pass. This README is the
local map for future utility alignment.
