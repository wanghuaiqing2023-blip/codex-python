# codex-aws-auth src/config.rs status

Rust source:

- `codex/codex-rs/aws-auth/src/config.rs`

Python target:

- `pycodex/aws_auth/config.py`

Status: complete.

Implemented contract:

- `load_sdk_config(...)` rejects empty service names before loading config.
- Explicit profile and region are carried into the loaded config.
- A dependency-light environment-backed credentials provider is exposed when
  `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are available.
- `resolved_region(...)` and `credentials_provider(...)` preserve the Rust
  missing-region and missing-provider error boundaries.

Python adaptation:

- Rust uses the AWS SDK default loader. Python intentionally avoids a new
  third-party AWS dependency and keeps a small standard-library config object;
  full SigV4 behavior remains owned by the pending `src/signing.rs` module.

Validation:

- Syntax-only while the crate remains partial:
  `python -m py_compile pycodex/aws_auth/__init__.py pycodex/aws_auth/config.py tests/test_aws_auth_config_rs.py`
