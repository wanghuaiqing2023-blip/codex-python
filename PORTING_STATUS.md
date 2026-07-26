# Porting Status

This page is a current snapshot, not a migration log. Git history is the
archive for earlier states.

## Fixed Baseline

- Rust commit: `1c7832ffa37a3ab56f601497c00bfce120370bf9`
- Rust source: `codex/codex-rs`
- Python source: `pycodex`
- Architecture authority: `parity_harness/contracts/workspace.json` and
  `parity_harness/contracts/accepted/`

## Current Structure Snapshot

As of 2026-07-26:

- Workspace inventory: `verified` for 119 crates, with 111 active and 8
  explicitly deferred.
- Core ownership and TUI ownership have accepted module contracts.
- Windows Sandbox ownership and coverage are `verified`.
- The all-scope ownership gate is not green. Its latest run reports real
  ownership and coverage findings in crates outside the already-verified
  scopes. The detailed machine-readable result is generated at
  `parity_harness/.artifacts/structure/accepted-all-summary.json`.

`ownership_verdict` and `coverage_verdict` are deliberately independent:
correct ownership does not imply that every Rust module has been ported.

## Main Coverage Debt

- Several non-core crates remain `partial`; their missing Rust modules must not
  be hidden with empty contracts or fabricated owners.
- Some crates still contain orphan Python files, missing Rust-to-Python owner
  mappings, or item-level ownership findings.
- Optional native Rust/ConPTY and live OAuth E2E paths depend on local
  executables, credentials, and environment gates.

Use the Harness output for exact current counts. Do not copy transient totals
into this page.

## Stable Verification

```powershell
python -B -m parity_harness workspace check
python -B -m parity_harness contract validate-accepted --scope all
python -B -m parity_harness structure --scope all --gate ownership
python -B -m parity_harness audit
python -m pytest tests/e2e -q
python -m pycodex --help
```

For a single crate, replace `all` with its workspace contract name:

```powershell
python -B -m parity_harness structure --scope core --gate ownership
```

## Status Rules

- Update this file only when the baseline, verification workflow, or major
  project-wide status changes.
- Keep module evidence in accepted contracts, Rust-derived tests, and the
  owning module documentation.
- Do not add per-turn pass counts or chronological completion notes.
