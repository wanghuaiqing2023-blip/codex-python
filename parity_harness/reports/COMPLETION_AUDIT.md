# Structure Harness Completion Audit

Audit date: 2026-07-23  
Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`

## Proven requirements

| Requirement | Evidence | Status |
| --- | --- | --- |
| Dynamic Cargo inventory | `workspace check`: 119 crates | Proven |
| Exactly one workspace classification | 111 active, 8 deferred, zero workspace errors | Proven |
| Deferred scopes have reasons and no product package | Workspace validator plus deferred counterexamples | Proven |
| Candidate generated for every active scope | 111 active scopes and 111 candidate artifacts | Proven |
| Candidate cannot become accepted automatically | Candidate schema and acceptance regression tests | Proven |
| Reviewed accepted collection for every active scope | 111 accepted directories and 111 policies | Proven |
| Accepted contract integrity | 1027 contracts pass global validation | Proven |
| Full Rust coordinate and source matching | Same-name counterexample plus zero `STR025` in full scan | Proven |
| `mod.rs`, inline module, re-export, Cargo bin | Rust-derived scanner counterexamples | Proven |
| Unique owner and continuous package rules | Duplicate, merge, and scattered-owner counterexamples | Proven |
| Orphan, foreign item, duplicate symbol | Structure capability and inventory counterexamples | Proven |
| `cfg(test)` cannot provide production evidence | Production-anchor counterexample | Proven |
| Missing Rust module cannot be reported verified | Coverage counterexample | Proven |
| Separate ownership and coverage verdicts | CLI and machine-report regressions | Proven |
| Existing four protected scope results | Core/TUI/App Server/App Server Transport regressions | Proven |
| No `pycodex.porting` Harness dependency | Static dependency regression and zero search matches | Proven |
| Per-crate machine-readable results | 107 individually executed non-protected active scopes, 107 reports | Proven |
| Harness test suite | 108 tests and 46 subtests passed | Proven |

## Commands and current results

- `python -B -m parity_harness workspace check`: passed.
- `python -B -m parity_harness contract validate-accepted --scope all`: passed.
- `python -B -m parity_harness audit`: passed.
- `python -B -m pytest parity_harness`: passed.
- `python -B -m parity_harness structure --scope all --gate ownership`:
  correctly failed because current product ownership is not aligned.

The machine-readable aggregate is
`parity_harness/.artifacts/structure/accepted-all-summary.json`. Individual
results are indexed by
`parity_harness/.artifacts/structure/individual-active-index.json`.

## Unmet acceptance conditions

The all-scope ownership gate reports:

- `ownership_verdict: failed`
- `coverage_verdict: partial`
- 43 active scopes with ownership failures.
- 606 foreign items (`STR017`).
- 27 unowned Python production files (`STR019`).
- 455 uncovered Rust modules (`STR015`).

These findings cannot be removed inside this Harness-only task without either
moving product implementations to their Rust-aligned owners or weakening the
contracts. Both are forbidden by the task constraints. The complete scope
summary and migration rule are recorded in `STRUCTURE_DRIFT.md`; every
`STR017` machine finding names the Python owner, symbol, Rust module coordinate,
and Rust source file. The report distinguishes 606 findings from 613 candidate
assignments and marks the 6 multi-owner findings for manual disambiguation.
Each `STR019` finding records the Python production
symbols and any exact Rust module/source symbol matches: 22 files have at least
one navigation candidate and 5 remain without a direct match.

Therefore the Harness construction and evidence objectives are proven, but
the overall goal's requirement that every active scope pass the ownership gate
is not achieved in the current product tree. It must remain open for a later,
explicitly authorized product architecture migration.
