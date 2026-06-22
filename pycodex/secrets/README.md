# pycodex.secrets

Rust crate: `codex-secrets`

Rust anchor: `codex/codex-rs/secrets`

Module map:

- `codex/codex-rs/secrets/src/sanitizer.rs` ->
  `pycodex/secrets/sanitizer.py` (`complete_candidate`)
- `codex/codex-rs/secrets/src/lib.rs` ->
  `pycodex/secrets/__init__.py` (`complete_candidate`)
- `codex/codex-rs/secrets/src/local.rs` ->
  `pycodex/secrets/local.py` (`complete_candidate`)

The current Python package exposes the Rust secret-redaction helper and public
manager/type surface. Local encrypted storage is implemented in `local.py`
using the existing keyring-store abstraction and standard-library authenticated
file encryption.
