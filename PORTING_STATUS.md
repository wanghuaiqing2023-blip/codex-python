# Porting Status

This page is a current snapshot, not a migration log. Git history is the
archive for earlier states.

Snapshot date: 2026-07-30

## Fixed Baseline

- Rust commit: `1c7832ffa37a3ab56f601497c00bfce120370bf9`
- Rust source: `codex/codex-rs`
- Python source: `pycodex`
- Architecture authority: `parity_harness/contracts/workspace.json` and
  `parity_harness/contracts/accepted/`

## Current Structure Snapshot

- Workspace inventory: `verified` for 119 active scopes; no scope is deferred.
- Workspace classification: all 119 scopes are `accepted`; none remains
  `partial`.
- Accepted contract integrity: `verified` for 1,560 reviewed module contracts
  across all 119 scopes.
- The all-scope structure gate is green: both `ownership_verdict` and
  `coverage_verdict` are `verified`, with no current structure findings.
- The eight formerly deferred areas now have active Python owners and reviewed
  contracts: app-server daemon, app/core/MCP test support, ChatGPT, extension
  API, Codex MCP, and MCP server.

`ownership_verdict` and `coverage_verdict` are deliberately independent:
correct ownership does not imply behavioral parity, and structural coverage
does not prove that every Rust behavior and test scenario is implemented.
The detailed machine-readable result is generated at
`parity_harness/.artifacts/structure/accepted-all-summary.json`.

## Behavioral Status

- Workspace `accepted` records structural contract acceptance. It does not
  claim that every Rust behavior and test scenario has a Python parity proof.
- A green architecture gate and an all-accepted workspace classification must
  not be presented as whole-product behavioral parity.
- Optional native Rust/ConPTY and live OAuth E2E paths depend on local
  executables, credentials, and environment gates.

Use the Harness output and module-local Rust-derived tests for exact current
evidence.

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
- Keep workspace dispositions synchronized with structure ownership and
  coverage evidence.
- Keep structural acceptance separate from whole-product behavioral parity.
- Keep module evidence in accepted contracts, Rust-derived tests, and the
  owning module documentation.
- Do not add per-turn pass counts or chronological completion notes.
