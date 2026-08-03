# Structure Harness Completion Audit

Audit date: 2026-07-30
Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`

## Proven requirements

| Requirement | Evidence | Status |
| --- | --- | --- |
| Dynamic Cargo inventory | `workspace check`: 119 crates | Proven |
| Exactly one workspace classification | 119 active, zero deferred, zero workspace errors | Proven |
| Deferred-scope validation remains enforced | Workspace validator counterexamples | Proven |
| Candidate generated for every active scope | 119 active scopes and canonical candidate artifacts | Proven |
| Candidate cannot become accepted automatically | Candidate schema and acceptance regression tests | Proven |
| Reviewed accepted collection for every active scope | 119 accepted directories and 119 policies | Proven |
| Accepted contract integrity | 1,560 contracts pass global validation | Proven |
| Full Rust coordinate and source matching | Same-name counterexample plus zero `STR025` in full scan | Proven |
| `mod.rs`, inline module, re-export, Cargo bin | Rust-derived scanner counterexamples | Proven |
| Unique owner and continuous package rules | Duplicate, merge, and scattered-owner counterexamples | Proven |
| Orphan, foreign item, duplicate symbol | Structure capability and inventory counterexamples | Proven |
| `cfg(test)` cannot provide production evidence | Production-anchor counterexample | Proven |
| Missing Rust module cannot be reported verified | Coverage counterexample | Proven |
| Separate ownership and coverage verdicts | CLI and machine-report regressions | Proven |
| No `pycodex.porting` Harness dependency | Static dependency regression and zero search matches | Proven |
| Per-crate machine-readable results | All 119 active scopes represented in the aggregate report | Proven |
| All-scope structure gate | Ownership and coverage verified with zero findings | Proven |
| Harness test suite | 116 tests passed | Proven |

## Commands and current results

- `python -B -m parity_harness workspace check`: passed.
- `python -B -m parity_harness contract validate-accepted --scope all`: passed.
- `python -B -m parity_harness audit`: passed.
- `python -m pytest parity_harness`: passed.
- `python -B -m parity_harness structure --scope all --gate ownership`:
  passed with `ownership_verdict: verified` and
  `coverage_verdict: verified`.

The machine-readable aggregate is
`parity_harness/.artifacts/structure/accepted-all-summary.json`. Individual
scope results are embedded in that aggregate and written beside it.

## Acceptance Boundary

The structure Harness objective is achieved for the fixed baseline:

- 119 of 119 active scopes are structurally verified.
- No orphan Python production files, foreign items, duplicate/scattered owners,
  or uncovered Rust modules are currently reported.
- The former eight deferred scopes are now active and included in the same
  checks.

This is an architecture result, not a declaration of whole-product behavioral
parity. All workspace scopes are structurally `accepted`, but behavioral parity
still requires Rust source, runtime-anchor, and Rust-derived test evidence at
the owning module boundary.
