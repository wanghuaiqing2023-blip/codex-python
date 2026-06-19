# codex-aws-auth src/signing.rs status

Rust source:

- `codex/codex-rs/aws-auth/src/signing.rs`

Python target:

- `pycodex/aws_auth/signing.py`

Status: complete.

Implemented contract:

- `sign_request(...)` converts header values to UTF-8 text before signing and
  rejects non-UTF8 header values.
- The signed request preserves the original URL and pre-existing headers.
- SigV4 signing adds deterministic `Authorization` and `x-amz-date` headers for
  a fixed timestamp.
- Session-token credentials add `x-amz-security-token` and include that header
  in the signed-header list.
- Invalid URI and missing signing parameter paths map to signing-module error
  variants.
- `header_value(...)` mirrors the Rust test helper's case-insensitive lookup
  and UTF-8-only value extraction.

Python adaptation:

- Rust delegates canonical request construction to `aws_sigv4`. Python uses a
  standard-library SigV4 implementation (`hashlib`, `hmac`, and `urllib.parse`)
  so the port remains dependency-light while preserving the module behavior
  needed by the crate tests.

Validation:

- Syntax-only while the crate remains partial:
  `python -m py_compile pycodex/aws_auth/__init__.py pycodex/aws_auth/config.py pycodex/aws_auth/signing.py tests/test_aws_auth_config_rs.py tests/test_aws_auth_signing_rs.py`
