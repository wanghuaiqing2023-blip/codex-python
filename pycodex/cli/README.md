# pycodex.cli

This package contains Python counterparts for Rust top-level CLI behavior.

## Rust Counterpart

```text
Primary Rust crate: codex-cli
Primary Rust path: codex/codex-rs/cli
```

## Alignment Role

`pycodex.cli` should own top-level command parsing, command dispatch, command
surface compatibility, login/features/update command shims, and user-facing
CLI exit messages.

It should delegate runtime behavior to `pycodex.exec`, `pycodex.core`,
`pycodex.config`, and other domain packages.

## Rust Module Areas

Typical Rust module counterparts include:

```text
codex/codex-rs/cli/src/main.rs
codex/codex-rs/cli/tests/
```

Related command crates may include:

```text
codex/codex-rs/login
codex/codex-rs/features
codex/codex-rs/tui
```

## Python Modules

Current Python implementation files include:

| Python module/file | Role |
|---|---|
| `pycodex/cli/parser.py` | top-level parser and command dispatch |
| `pycodex/cli/login.py` | login/logout/status command behavior and auth persistence |
| `pycodex/cli/features.py` | features command behavior |
| `pycodex/cli/app_exit.py` | user-facing app-exit formatting |
| `pycodex/tui/__init__.py` | canonical TUI entrypoint compatibility behavior |

`pycodex/tui.py` has been replaced by the canonical `pycodex/tui/` package. `pycodex/cli/tui.py` has been deleted; use `pycodex.tui` directly.

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
cli.top_level_parser
cli.command_dispatch
cli.app_exit
cli.login_command
cli.features_command
```

## Test Source Policy

Prefer Rust CLI tests and command-surface source behavior before
Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-cli
# Rust module: src/main.rs
# Rust test: tests::example_test_name
# Contract: cli.top_level_parser
```

## Current Movement Status

No code movement is required for the first structural pass. This README is the
local map for future CLI alignment.
