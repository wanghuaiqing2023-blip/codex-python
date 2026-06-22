# pycodex.execpolicy

This package contains the Python counterpart for Rust execution policy behavior.

## Rust Counterparts

```text
Primary Rust crate: codex-execpolicy
Primary Rust path: codex/codex-rs/execpolicy

Related Rust module: codex-core exec_policy integration
Related Rust path: codex/codex-rs/core/src/exec_policy.rs
```

## Alignment Role

`pycodex.execpolicy` should own command policy decisions, allow/prompt/forbid
classification, prefix-rule matching, and approval requirement rendering that is
not specific to a single runtime entrypoint.

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
execpolicy.decision
execpolicy.prefix_rules
execpolicy.command_parsing_for_policy
execpolicy.approval_requirement
execpolicy.unmatched_command_rendering
```

## Test Source Policy

Prefer Rust tests from `codex-execpolicy` and Rust `core/src/exec_policy*`
tests before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-execpolicy
# Rust module: src/policy.rs
# Rust test: tests::example_test_name
# Contract: execpolicy.decision
```

## Current Movement Status

The former implementation module `pycodex/core/exec_policy.py` was moved to
`pycodex/execpolicy/__init__.py`.

`pycodex/core/exec_policy.py` has been deleted; use `pycodex.execpolicy` directly.

## Rust parity update: amend.rs

`codex-execpolicy/src/amend.rs` is now represented by Python append helpers:

- `blocking_append_allow_prefix_rule(...)` mirrors Rust prefix rule formatting, directory creation, newline insertion, and duplicate suppression.
- `blocking_append_network_rule(...)` mirrors Rust network rule formatting, protocol normalization, decision mapping, host normalization, and empty justification rejection.
- `normalize_network_rule_host(...)`, `NetworkRuleProtocol`, and `AmendError` expose the semantic pieces needed by the append helpers without copying Rust-only file-locking machinery.

Evidence: `tests/test_execpolicy_amend.py` derives from the six Rust unit tests in `amend.rs` plus focused host normalization/empty-justification checks used by that module.

## Rust parity update: executable_name.rs

`codex-execpolicy/src/executable_name.rs` is represented by Python helpers:

- `executable_lookup_key(...)` mirrors platform-specific lookup key behavior: on Windows, lower-case and strip `.exe`, `.cmd`, `.bat`, or `.com`; on non-Windows, preserve the raw executable token.
- `executable_path_lookup_key(...)` mirrors `Path::file_name().and_then(...).map(executable_lookup_key)` by using the final path component and returning `None` when absent.

Evidence: `tests/test_execpolicy_executable_name.py` derives from this module's behavior contract and is included in targeted execpolicy validation.

## Rust parity update: decision.rs

`codex-execpolicy/src/decision.rs` is represented by Python `Decision` behavior:

- `Decision.parse(...)` mirrors Rust `Decision::parse`, accepting only `allow`, `prompt`, and `forbidden`.
- `InvalidDecisionError` preserves the Rust-facing error text shape `invalid decision: <raw>` for rejected values.
- Existing `strongest_decision(...)` preserves Rust derived ordering semantics: `allow < prompt < forbidden`.

Evidence: `tests/test_execpolicy_decision.py` derives from the Rust enum contract and is included in targeted execpolicy validation.

## Rust parity update: error.rs

`codex-execpolicy/src/error.rs` is represented by Python error/location models:

- `TextPosition`, `TextRange`, and `ErrorLocation` mirror Rust value structs.
- `InvalidDecisionError`, `InvalidPatternError`, `InvalidExampleError`, and `InvalidRuleError` preserve Rust Display text for stable error boundaries.
- `ExampleDidNotMatchError` and `ExampleDidMatchError` preserve Rust Display text and `with_location`/`location` semantics for example-match errors.

Evidence: `tests/test_execpolicy_error.py` derives from the Rust error enum contract and is included in targeted execpolicy validation.

## Rust parity update: policy.rs direct API slice

A direct `codex-execpolicy/src/policy.rs` API slice is represented by Python semantic models:

- `PatternToken`, `PrefixPattern`, `PrefixRule`, `NetworkRule`, `RuleMatch`, `Evaluation`, and `Policy` mirror the direct policy/rule value surface needed for module-local behavior tests.
- `Policy.add_prefix_rule(...)`, `Policy.add_network_rule(...)`, `Policy.compiled_network_domains(...)`, `Policy.matches_for_command(...)`, and `Policy.check(...)` cover direct policy mutation/evaluation without claiming parser or host-executable registration parity.
- `Decision.parse(...)` now also accepts an existing `Decision` instance, preserving enum round-trip flow through the Python policy API.

Evidence: `tests/test_execpolicy_policy.py` derives from the policy-local portions of `execpolicy/tests/basic.rs` and targeted policy.rs behavior.

## Rust parity update: rule.rs example validation slice

`codex-execpolicy/src/rule.rs` example validation helpers are represented by Python functions:

- `validate_match_examples(...)` mirrors Rust behavior that every positive example must match at least one policy rule.
- `validate_not_match_examples(...)` mirrors Rust behavior that every negative example must avoid policy rule matches.
- Errors use the Rust-shaped `ExampleDidNotMatchError` and `ExampleDidMatchError` models from the `error.rs` slice.

Evidence: `tests/test_execpolicy_rule.py` derives from the `match_and_not_match_examples_are_enforced` integration behavior and the direct `rule.rs` helper contracts.

## Rust parity update: execpolicycheck.rs format slice

`codex-execpolicy/src/execpolicycheck.rs` JSON formatting is represented by Python helpers:

- `format_matches_json(...)` mirrors Rust `ExecPolicyCheckOutput` serde shape with `matchedRules` and optional `decision`.
- Compact output uses JSON without spaces, matching Rust `serde_json::to_string` shape closely enough for semantic parity.
- Pretty output uses indented JSON and preserves camelCase fields including `resolvedProgram`.
- `load_policies(...)` is intentionally explicit `NotImplementedError` until the `PolicyParser`/Starlark loading slice is completed; Python does not fake parser parity.

Evidence: `tests/test_execpolicy_execpolicycheck.py` derives from `execpolicycheck.rs::format_matches_json` and existing CLI output shape tests.

## Rust parity update: lib.rs export surface

`codex-execpolicy/src/lib.rs` public re-export surface is represented at `pycodex.execpolicy` package root:

- Existing implemented objects are exported from the package root with Rust-aligned names where practical.
- `MatchOptions`, `Rule`, `RuleRef`, `PolicyParser`, and `ExecPolicyCheckCommand` now exist as explicit Python interfaces.
- `PolicyParser` and `ExecPolicyCheckCommand.run()` intentionally block on the separate `PolicyParser`/Starlark parser contract instead of faking parser-backed policy loading.

Evidence: `tests/test_execpolicy_lib.py` verifies the package-root export surface and explicit parser/check-command boundaries.

## Rust parity update: main.rs CLI dispatch surface

`codex-execpolicy/src/main.rs` is represented by Python CLI dispatch helpers:

- `ExecPolicyCli` mirrors the single Rust `Cli::Check(ExecPolicyCheckCommand)` enum variant.
- `parse_execpolicy_cli(...)` mirrors the `codex-execpolicy check` argument shape for repeatable rules, pretty output, host-executable resolution flag, and trailing command tokens.
- `run_execpolicy_cli(...)` mirrors Rust `main()` dispatch by calling `ExecPolicyCheckCommand.run()` and therefore remains blocked at parser-backed `load_policies` until the `PolicyParser` slice is completed.

Evidence: `tests/test_execpolicy_main.py` derives from `main.rs` dispatch behavior and `ExecPolicyCheckCommand` clap argument shape.

## Rust parity update: parser.rs restricted prefix/network slice

`codex-execpolicy/src/parser.rs` now has a restricted Python parser slice for the common literal policy-rule subset:

- `PolicyParser.parse(...)` accepts top-level literal `prefix_rule(...)` and `network_rule(...)` calls.
- Prefix parsing supports string tokens, alternative-token lists, default allow decision, explicit decisions, justification, and `match`/`not_match` example validation.
- Network parsing supports protocol parsing, `deny` as the Rust network-rule alias for forbidden, justification validation, and host normalization through `Policy.add_network_rule(...)`.
- `load_policies(...)` now has a real success path for prefix/network policy files and preserves Rust-shaped missing-file/parse context errors.
- `host_executable(...)` remains explicit `NotImplementedError` and is tracked as a separate parser behavior contract.

Evidence: `tests/test_execpolicy_parser.py` derives from parser/policy portions of `codex-execpolicy/tests/basic.rs` and the `execpolicycheck.rs` load path.

## Rust parity update: parser.rs host_executable and policy host-resolution slice

`codex-execpolicy/src/parser.rs` `host_executable(...)` and the corresponding `policy.rs` host-resolution behavior are represented by Python helpers:

- `PolicyParser` now parses `host_executable(name=..., paths=[...])`, validates bare executable names, absolute paths, basename compatibility, de-duplicates paths, and uses last-definition-wins registration.
- `Policy` now exposes `set_host_executable_paths(...)`, `host_executables(...)`, `matches_for_command_with_options(...)`, and `check_with_options(...)` for host executable resolution.
- Host resolution mirrors Rust behavior: exact command-token policy matches win first; otherwise absolute program paths can resolve through basename prefix rules, gated by explicit host executable allowlists when present, and falling back when no mapping exists.

Evidence: `tests/test_execpolicy_host_executable.py` derives from the host-executable group in `codex-execpolicy/tests/basic.rs`.

## Crate promotion: codex-execpolicy complete

`codex-execpolicy` is now marked complete. Covered Rust module-scoped contracts include:

- `amend.rs`: policy append helpers for prefix/network rules.
- `decision.rs`: decision parsing, serialization values, and ordering.
- `error.rs`: error/location models and location attachment semantics.
- `executable_name.rs`: platform-specific executable lookup keys.
- `policy.rs`: direct policy APIs plus host-executable resolution.
- `rule.rs`: pattern/rule models and example validation helpers.
- `parser.rs`: literal policy parser for `prefix_rule`, `network_rule`, and `host_executable` contracts.
- `execpolicycheck.rs`: JSON formatting and policy loading/check success path.
- `lib.rs`: package-root public export surface.
- `main.rs`: standalone CLI dispatch surface.

Final targeted evidence:

```text
python -m pytest tests/test_execpolicy_host_executable.py tests/test_execpolicy_parser.py tests/test_execpolicy_main.py tests/test_execpolicy_lib.py tests/test_execpolicy_execpolicycheck.py tests/test_execpolicy_rule.py tests/test_execpolicy_policy.py tests/test_execpolicy_error.py tests/test_execpolicy_decision.py tests/test_execpolicy_executable_name.py tests/test_execpolicy_amend.py tests/test_core_exec_policy.py tests/test_config_requirements_exec_policy.py tests/test_cli_parser.py -k execpolicy -q
126 passed, 540 deselected, 29 subtests passed
```
