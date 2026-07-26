# Workspace Structure Drift

This report records the structure Harness result for Rust baseline
`1c7832ffa37a3ab56f601497c00bfce120370bf9`. It is evidence of the current
worktree, not permission to weaken accepted contracts or change product code
inside a Harness-only task.

Regenerate the authoritative machine-readable report with:

```powershell
python -B -m parity_harness structure --scope all --gate ownership
```

The detailed result is written to
`parity_harness/.artifacts/structure/accepted-all-summary.json`.

## Current result

- Cargo crates: 119 total, 111 active, 8 deferred.
- Accepted contracts: 1027.
- Ownership: 68 verified scopes, 43 failed scopes.
- Coverage: 55 verified scopes, 56 partial scopes.
- Findings: 455 uncovered Rust modules (`STR015`), 606 foreign items
  (`STR017`), and 27 declared but unowned Python production files (`STR019`).
- Coordinate/source mismatches (`STR025`): zero.
- Duplicate, merged, or scattered accepted owners: zero.

The ownership failures are real architecture debt. Most `STR017` findings are
Python crate-root owners that define items belonging to Rust child modules.
`STR019` findings are Python production files whose current location cannot be
represented by one Rust module-to-file or Rust module-to-continuous-package
contract. Neither class can be made verified without a later product migration.
The machine reports include a structured `migration_plan` for every scope:
606 foreign-item findings are grouped into 117 Python-owner/Rust-owner groups.
They produce 613 symbol assignments because 6 findings have multiple plausible
Rust owners; those symbols are marked `requires_disambiguation` and must not be
assigned automatically. All 27 unowned Python files are listed separately for
ownership review.
Of those files, 22 have at least one exact production-symbol match in the Rust
module graph; the remaining 5 have no direct symbol match and stay explicitly
unresolved. Symbol matches are navigation candidates, never automatic accepted
ownership.

## Ownership failures

| Scope | Foreign items | Unowned Python files | Coverage debt |
| --- | ---: | ---: | ---: |
| analytics | 76 | 0 | 5 |
| api | 0 | 1 | 0 |
| app-server-protocol | 0 | 1 | 6 |
| apply-patch | 14 | 0 | 6 |
| backend-client | 7 | 0 | 2 |
| cli | 0 | 8 | 23 |
| cloud-tasks | 17 | 0 | 2 |
| cloud-tasks-client | 18 | 0 | 1 |
| cloud-tasks-mock-client | 2 | 0 | 1 |
| config | 17 | 0 | 4 |
| core-plugins | 1 | 0 | 25 |
| core-skills | 0 | 2 | 3 |
| exec | 0 | 6 | 3 |
| exec-server | 115 | 0 | 36 |
| execpolicy | 8 | 0 | 9 |
| execpolicy-legacy | 4 | 0 | 13 |
| external-agent-sessions | 13 | 0 | 4 |
| git-utils | 9 | 0 | 7 |
| hooks | 28 | 0 | 23 |
| keyring-store | 1 | 0 | 1 |
| memories-extension | 2 | 0 | 16 |
| memories-write | 30 | 0 | 24 |
| model-provider | 2 | 0 | 0 |
| network-proxy | 105 | 0 | 15 |
| otel | 18 | 0 | 18 |
| protocol | 0 | 1 | 4 |
| realtime-webrtc | 2 | 0 | 1 |
| responses-api-proxy | 10 | 0 | 2 |
| rollout | 33 | 0 | 10 |
| rollout-trace | 24 | 0 | 25 |
| shell-command | 19 | 0 | 6 |
| state | 0 | 1 | 3 |
| thread-store | 10 | 0 | 17 |
| uds | 2 | 0 | 1 |
| utils-cli | 2 | 0 | 6 |
| utils-pty | 0 | 1 | 9 |
| utils-readiness | 1 | 0 | 1 |
| utils-sandbox-summary | 0 | 1 | 3 |
| utils-sleep-inhibitor | 9 | 0 | 5 |
| utils-stream-parser | 2 | 0 | 7 |
| utils-string | 1 | 0 | 2 |
| web-search-extension | 2 | 0 | 5 |
| windows-sandbox | 2 | 5 | 32 |

## Protected scopes

- `core`: ownership verified, coverage verified, 254 contracts.
- `tui`: ownership verified, coverage verified, 294 contracts.
- `app-server`: ownership verified, coverage verified, 60 contracts.
- `app-server-transport`: ownership verified, coverage partial, 3 contracts
  and 10 explicitly retained uncovered Rust modules.

These four accepted collections were not regenerated or weakened by this work.

## Deferred crates

The eight deferred crates have no Python product package at this baseline:
`app-server-daemon`, `app_test_support`, `chatgpt`, `core_test_support`,
`extension-api`, `mcp`, `mcp-server`, and `mcp_test_support`. Their complete
reviewed reasons remain in `contracts/workspace.json` and in the generated
machine report.

## Follow-up migration rule

For each failed scope, move existing implementations to the Python owner that
corresponds to the Rust child module, keep parent `__init__.py` files limited to
their Rust parent API and proven re-exports, and remove split helper files only
after callers and tests use the aligned owner. Do not add compatibility facades
unless a Rust `pub use` proves the same public boundary.
