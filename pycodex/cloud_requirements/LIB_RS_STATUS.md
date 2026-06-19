# codex-cloud-requirements src/lib.rs status

Rust coordinate: `codex/codex-rs/cloud-requirements/src/lib.rs`

Python coordinate: `pycodex/cloud_requirements/__init__.py`

Status: `complete`

Behavior contract:

- fetch cloud-hosted `requirements.toml` only for Codex-backend
  business/enterprise auth.
- parse non-empty cloud requirements through the same configuration
  requirements representation used by `codex-config`.
- fail closed for eligible accounts when fetch, auth recovery, timeout, or parse
  failures occur.
- read/write signed local cache files scoped to auth identity and TTL.
- expose loader factory functions matching Rust crate-root API names.

Evidence:

- `CloudRequirementsService` implements timeout wrapping, eligibility checks,
  cache-first loading, retryable request failures, unauthorized auth recovery,
  parse error mapping, and signed cache writes.
- `BackendRequirementsFetcher` uses the real Rust endpoint split:
  `/api/codex/config/requirements` for Codex API style URLs and
  `/wham/config/requirements` for ChatGPT backend-api style URLs.
- `parse_cloud_requirements(...)` uses `ConfigRequirementsToml.from_toml` and
  temporarily resolves relative path requirements from the provided base dir,
  matching Rust's `AbsolutePathBufGuard` usage.
- HMAC/base64 cache helpers mirror Rust signature verification semantics.

Validation:

- `python -m pytest tests/test_cloud_requirements_lib_rs.py -q` (`12 passed`)
- `python -m py_compile pycodex/cloud_requirements/__init__.py tests/test_cloud_requirements_lib_rs.py` (passed)
