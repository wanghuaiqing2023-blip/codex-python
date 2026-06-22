# codex-execpolicy test alignment

Status: complete

This package maps Rust `codex-execpolicy` behavior into `pycodex.execpolicy` while keeping compatibility with the older `pycodex.core.exec_policy` facade.

## Rust-derived module coverage

| Rust module | Python target | Python tests | Status | Notes |
| --- | --- | --- | --- | --- |
| `codex-execpolicy/src/amend.rs` | `pycodex.execpolicy` | `tests/test_execpolicy_amend.py` | complete_slice | Covers Rust append helpers for prefix and network rules, directory creation, newline insertion, duplicate suppression, wildcard rejection, host normalization, and empty justification rejection. Python intentionally omits Rust advisory file locking because writes are synchronous local file operations in this port. |
| `codex-execpolicy/src/executable_name.rs` | `pycodex.execpolicy` | `tests/test_execpolicy_executable_name.py` | complete_slice | Covers platform-specific executable lookup keys and path basename lookup behavior. |
| `codex-execpolicy/src/decision.rs` | `pycodex.execpolicy` | `tests/test_execpolicy_decision.py` | complete_slice | Covers Decision parse, string values, invalid-decision error text, and Rust derived ordering semantics. |
| `codex-execpolicy/src/error.rs` | `pycodex.execpolicy` | `tests/test_execpolicy_error.py` | complete_slice | Covers error location structs, stable Display text, and with_location/location behavior for example errors. |
| `codex-execpolicy/src/policy.rs` direct API slice | `pycodex.execpolicy` | `tests/test_execpolicy_policy.py` | complete_slice | Covers direct prefix/network rule mutation, compiled network domain ordering/override behavior, direct command checks, heuristic fallback matches, and local InvalidPattern/InvalidRule boundaries. Parser and host-executable registration remain separate slices. |
| `codex-execpolicy/src/rule.rs` example validation slice | `pycodex.execpolicy` | `tests/test_execpolicy_rule.py` | complete_slice | Covers validate_match_examples and validate_not_match_examples behavior for positive/negative examples using direct Policy matching and Rust-shaped example errors. |
| `codex-execpolicy/src/execpolicycheck.rs` format slice | `pycodex.execpolicy` | `tests/test_execpolicy_execpolicycheck.py` | complete_slice | Covers format_matches_json compact/pretty JSON output, optional decision omission for empty matches, optional prefix-rule fields, and strictest-decision aggregation. `load_policies` remains explicit blocked pending PolicyParser parity. |
| `codex-execpolicy/src/lib.rs` | `pycodex.execpolicy` | `tests/test_execpolicy_lib.py` | complete_slice | Covers package-root public export surface and explicit blocked scaffolds for PolicyParser/check-command parser-backed loading. |
| `codex-execpolicy/src/main.rs` | `pycodex.execpolicy` | `tests/test_execpolicy_main.py` | complete_slice | Covers single check subcommand dispatch, repeatable rules, flags, trailing command tokens, and parser-backed missing-file reporting. |
| `codex-execpolicy/src/parser.rs` restricted prefix/network slice | `pycodex.execpolicy` | `tests/test_execpolicy_parser.py` | complete_slice | Covers literal prefix_rule/network_rule parsing, alternatives, justifications, match/not_match validation, network deny alias, and load_policies success path. |
| `codex-execpolicy/src/parser.rs` host_executable slice + `policy.rs` host resolution | `pycodex.execpolicy` | `tests/test_execpolicy_host_executable.py` | complete_slice | Covers host_executable validation/registration, last-definition-wins, basename rule resolution, explicit allowlists including empty/mismatched lists, fallback without mapping, and exact-match precedence. |
| `codex-execpolicy` decision/policy command surface | `pycodex.execpolicy` and compatibility facade | `tests/test_core_exec_policy.py`, `tests/test_config_requirements_exec_policy.py` | complete_slice | Existing Rust-derived tests cover policy decision rendering, prefix-rule amendments, command parsing, and config approval requirement adaptation. |

## Current crate status

`codex-execpolicy` is `complete`. All Rust module-scoped behavior contracts represented in this package have dedicated Python parity tests, and final targeted crate/CLI evidence passed:

```text
126 passed, 540 deselected, 29 subtests passed
```
