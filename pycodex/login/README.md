# pycodex.login

This package contains the Python public import surface for the Rust `codex-login`
crate.

## Rust Counterpart

```text
Rust crate: codex-login
Rust path: codex/codex-rs/login
```

## Alignment Role

`pycodex.login` should own authentication/account persistence behavior that is
not merely a CLI command surface.

The current implementation is still provided by `pycodex.cli.login`, and this
package currently re-exports that implementation to preserve the public import
shape while the tree is being reorganized.

## Rust Module Areas

Typical Rust sources to inspect before changing this package:

```text
codex/codex-rs/login/src/lib.rs
codex/codex-rs/login/src/**/*.rs
```

Related CLI command behavior may also involve:

```text
codex/codex-rs/cli/src/main.rs
```

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
login.auth_file
login.auth_mode_resolution
login.chatgpt_oauth_flow
login.account_display
```

## Test Source Policy

Prefer Rust login tests and Rust source behavior before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-login
# Rust module: src/lib.rs
# Rust test: tests::example_test_name
# Contract: login.auth_file
```

## Current Movement Status

The former root module `pycodex/login.py` has been moved to this package as
`pycodex/login/__init__.py`.

The concrete implementation still lives in `pycodex.cli.login`; future work may
move non-CLI authentication logic from `pycodex.cli.login` into this package and
leave CLI-only command handling under `pycodex.cli`.
