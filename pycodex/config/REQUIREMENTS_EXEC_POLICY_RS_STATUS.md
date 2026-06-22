# codex-config src/requirements_exec_policy.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/config/src/requirements_exec_policy.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/requirements_exec_policy.rs` |
| Python module | `pycodex/config/requirements_exec_policy.py` |
| Python tests | `tests/test_config_requirements_exec_policy.py` |
| Status | `complete_candidate` |

`src/requirements_exec_policy.rs` owns the `[rules]` TOML representation inside `requirements.toml`, conversion to exec-policy prefix rules, and requirements-specific parse errors. The lower-level `codex-execpolicy` parser/evaluator remains a sibling crate boundary.

## Covered Behavior Areas

- `RequirementsExecPolicyToml.prefix_rules` is required to be non-empty.
- Prefix rule patterns reject empty patterns.
- Pattern tokens accept exactly one of `token` or `any_of`.
- Single tokens reject empty or whitespace-only strings.
- `any_of` alternatives reject empty arrays and empty alternatives.
- Empty justifications are rejected.
- Missing decisions are rejected.
- `allow` decisions are rejected for requirements because merged requirements must be restrictive.
- `prompt` and `forbidden` decisions convert to internal exec-policy decisions.
- First-token alternatives expand into one prefix rule per program head.
- `RequirementsExecPolicy` equality uses a sorted policy fingerprint.
- `from_mapping` accepts TOML-like dictionaries with pattern token tables.

## Rust Anchors

- `RequirementsExecPolicy`
- `RequirementsExecPolicyToml`
- `RequirementsExecPolicyPrefixRuleToml`
- `RequirementsExecPolicyPatternTokenToml`
- `RequirementsExecPolicyDecisionToml`
- `RequirementsExecPolicyParseError`
- `RequirementsExecPolicyToml::to_policy`
- `RequirementsExecPolicyToml::to_requirements_policy`
- `parse_pattern_token`

## Remaining Closeout

- Defer pytest until `codex-config` functional code is complete.
