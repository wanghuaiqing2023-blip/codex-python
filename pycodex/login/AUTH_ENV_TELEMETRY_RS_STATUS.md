# auth_env_telemetry.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/auth_env_telemetry.rs`

Python module: `pycodex/login/auth_env_telemetry.py`

Status: `complete`

Aligned behavior:

- `AuthEnvTelemetry` mirrors the Rust struct fields and default values.
- `to_otel_metadata()` preserves all telemetry fields in a metadata object.
- `collect_auth_env_telemetry()` detects the OpenAI API key, Codex API key,
  Codex API key enablement flag, provider-specific key presence, and refresh
  token URL override presence.
- Provider environment key names are bucketed as `"configured"` instead of
  exposing the configured key name, matching Rust's leak-prevention behavior.
- `env_var_present()` treats missing variables as false, empty/blank values as
  false, populated values as true, and non-Unicode lookup failures as present.

Validation:

- Not run in this turn; current automation defers actual test execution until the crate functional code is complete.
