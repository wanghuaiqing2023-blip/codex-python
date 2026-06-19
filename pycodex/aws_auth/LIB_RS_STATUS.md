# codex-aws-auth src/lib.rs status

Rust source:

- `codex/codex-rs/aws-auth/src/lib.rs`

Python target:

- `pycodex/aws_auth/__init__.py`

Status: complete.

Implemented contract:

- The package root exports the Rust crate's public auth config, request,
  signed-request, context, and error surface.
- `AwsAuthContext.load(...)` composes config loading, credentials-provider
  lookup, resolved-region lookup, and trimmed service-name storage.
- `region()` and `service()` expose the loaded context state.
- `sign(...)` and `sign_at(...)` provide current-time and fixed-time signing
  through the `src/signing.rs` helper.
- Debug/repr output includes region and service while omitting credentials.
- `is_retryable(...)` mirrors Rust retry classification: provider errors and
  provider timeouts are retryable; deterministic auth/config/signing failures
  are not.

Validation:

- Focused crate validation:
  `python -m pytest tests/test_aws_auth_config_rs.py tests/test_aws_auth_signing_rs.py tests/test_aws_auth_lib_rs.py -q`
  -> `15 passed`.
- Syntax validation:
  `python -m py_compile pycodex/aws_auth/__init__.py pycodex/aws_auth/config.py pycodex/aws_auth/signing.py tests/test_aws_auth_config_rs.py tests/test_aws_auth_signing_rs.py tests/test_aws_auth_lib_rs.py`
