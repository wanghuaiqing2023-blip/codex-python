# codex-login `src/pkce.rs` alignment status

Status: `complete_candidate`

Rust module: `codex/codex-rs/login/src/pkce.rs`

Python module: `pycodex/login/pkce.py`

## Behavior Contract

This module owns PKCE code generation for ChatGPT OAuth:

- Generate 64 random bytes.
- Encode the verifier with URL-safe base64 without padding.
- Compute the S256 challenge as URL-safe base64 without padding over
  `SHA256(verifier)`.
- Return both values as a `PkceCodes` record.

## Python Mapping

- `PkceCodes` mirrors the Rust struct.
- `generate_pkce()` mirrors Rust `generate_pkce()`.
- `code_challenge_for_verifier()` captures the deterministic S256 contract for
  focused parity tests.
- `pycodex.cli.login._build_pkce()` now delegates to this module to avoid a
  duplicate implementation.

## Rust Evidence

`src/pkce.rs` has no Rust unit test module. Python parity coverage in
`tests/test_login_pkce.py` is derived from the Rust source contract:

- `test_code_challenge_for_verifier_matches_rust_s256_contract`
- `test_generate_pkce_uses_64_random_bytes_and_no_padding`
- `test_cli_build_pkce_reuses_login_pkce_module`

## Validation

Actual test execution is deferred by the active crate automation policy until
`codex-login` functional code is complete.
