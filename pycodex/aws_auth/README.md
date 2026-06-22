# pycodex.aws_auth

Python alignment target for Rust crate `codex-aws-auth`.

Rust coordinates:

- `codex/codex-rs/aws-auth/src/config.rs`
- `codex/codex-rs/aws-auth/src/signing.rs`
- `codex/codex-rs/aws-auth/src/lib.rs`

Python mapping:

- `pycodex/aws_auth/config.py`
- `pycodex/aws_auth/signing.py`
- `pycodex/aws_auth/__init__.py`

Current status: complete.

Certified modules:

- `src/config.rs`: complete. The Python module mirrors service-name
  validation, profile/region selection, credential-provider lookup,
  resolved-region lookup, and missing-provider/region error boundaries.
- `src/signing.rs`: complete. The Python module mirrors request signing with
  existing-header preservation, SigV4 authorization/date headers, optional
  session-token forwarding, invalid URI handling, and non-UTF8 header
  rejection.
- `src/lib.rs`: complete. The Python package root mirrors public type/error
  exports, loaded auth context construction, region/service accessors,
  fixed-time/current-time signing, Debug-style credential omission, and
  retryable credential error classification.

Validation:

- Focused crate validation:
  `python -m pytest tests/test_aws_auth_config_rs.py tests/test_aws_auth_signing_rs.py tests/test_aws_auth_lib_rs.py -q`
  -> `15 passed`.
- Syntax validation:
  `python -m py_compile pycodex/aws_auth/__init__.py pycodex/aws_auth/config.py pycodex/aws_auth/signing.py tests/test_aws_auth_config_rs.py tests/test_aws_auth_signing_rs.py tests/test_aws_auth_lib_rs.py`
