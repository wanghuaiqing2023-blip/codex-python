# codex-cloud-requirements test alignment

Rust crate: `codex-cloud-requirements`

Python package: `pycodex/cloud_requirements`

Status: `complete`

Certified modules:

- `codex/codex-rs/cloud-requirements/src/lib.rs` -> `pycodex/cloud_requirements/__init__.py`

Rust behavior covered by `tests/test_cloud_requirements_lib_rs.py`:

- auth eligibility skips non-backend, non-business, and team-like plans while
  allowing business, enterprise CBP usage-based, and enterprise plans.
- cloud requirements TOML parsing treats missing, blank, comment-only, and empty
  requirements as no requirements.
- valid TOML maps through `ConfigRequirementsToml`, invalid enum values surface
  parse failures, and parse errors use the Rust workspace-managed-policy
  message prefix.
- relative filesystem deny-read globs resolve from the requirements base dir.
- service fetch skips ineligible auth without calling the fetcher.
- retryable fetch failures retry until success and stop after the Rust maximum
  attempt count with request-failed status.
- unauthorized fetch failures use auth recovery when available and otherwise
  surface the Rust generic auth recovery message.
- signed cache writes include identity/content/expiry, valid caches are reused,
  tampered or expired caches are ignored, and signature helpers round-trip.
- `cloud_requirements_loader(...)` exposes a shared loader facade over the
  service future.

Validation:

- `python -m pytest tests/test_cloud_requirements_lib_rs.py -q` (`12 passed`)
- `python -m py_compile pycodex/cloud_requirements/__init__.py tests/test_cloud_requirements_lib_rs.py` (passed)
