# codex-aws-auth test alignment

Rust crate: `codex-aws-auth`

Python package: `pycodex/aws_auth`

Status: `complete`

Module mapping:

- `codex/codex-rs/aws-auth/src/config.rs` -> `pycodex/aws_auth/config.py` (`complete`)
- `codex/codex-rs/aws-auth/src/signing.rs` -> `pycodex/aws_auth/signing.py` (`complete`)
- `codex/codex-rs/aws-auth/src/lib.rs` -> `pycodex/aws_auth/__init__.py` (`complete`)

Rust-derived/source-contract coverage for `src/config.rs`:

- `load_sdk_config(...)` rejects an empty/blank service name with the Rust
  display message.
- Profile and explicit region are preserved in the loaded SDK config.
- Environment credentials are exposed through `credentials_provider(...)`.
- Environment region fallback is exposed through `resolved_region(...)`.
- Missing credentials provider and missing region raise the Rust config-module
  error variants.

Rust-derived/source-contract coverage for `src/signing.rs`:

- `sign_request(...)` preserves the original URL and existing headers.
- Fixed-time signing adds an `AWS4-HMAC-SHA256` authorization header and
  deterministic `x-amz-date`.
- Credentials with a session token add `x-amz-security-token` and include it
  in the signed-header list.
- Invalid request URIs and missing signing params map to signing-module errors.
- Non-UTF8 header values are rejected before signing.

Rust-derived/source-contract coverage for `src/lib.rs`:

- `AwsAuthContext.sign_at(...)` delegates credential lookup and signing while
  preserving the Rust test request behavior.
- Credentials with a session token forward the token into the signed request.
- `AwsAuthContext.load(...)` rejects an empty service and trims service names
  in the loaded context.
- `region()` and `service()` expose loaded context state without exposing
  credentials through debug/repr output.
- Credential provider errors/timeouts are retryable; deterministic auth and
  signing errors are not retryable.

Validation:

- Focused crate validation:
  `python -m pytest tests/test_aws_auth_config_rs.py tests/test_aws_auth_signing_rs.py tests/test_aws_auth_lib_rs.py -q`
  -> `15 passed`.
- Syntax validation:
  `python -m py_compile pycodex/aws_auth/__init__.py pycodex/aws_auth/config.py pycodex/aws_auth/signing.py tests/test_aws_auth_config_rs.py tests/test_aws_auth_signing_rs.py tests/test_aws_auth_lib_rs.py`
