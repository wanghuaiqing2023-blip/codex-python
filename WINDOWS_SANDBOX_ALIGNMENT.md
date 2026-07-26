# Windows Sandbox Alignment

## Baseline

- Rust commit: `1c7832ffa37a3ab56f601497c00bfce120370bf9`
- Rust crate: `codex/codex-rs/windows-sandbox-rs`
- Python package: `pycodex/windows_sandbox`
- Accepted contracts:
  `parity_harness/contracts/accepted/windows-sandbox/`

The vendored Rust source is the behavior authority. Approval labels alone are
not enforcement; the selected profile must reach the native sandbox process,
ACL, WFP, ConPTY, and child-process boundaries.

## Ownership

One Rust module may own one Python module-file or one continuous package.
Important package boundaries include:

- command-runner and setup binaries under `pycodex/windows_sandbox/bin/`
- ConPTY under `pycodex/windows_sandbox/conpty/`
- elevated IPC under `pycodex/windows_sandbox/elevated/`
- unified execution under `pycodex/windows_sandbox/unified_exec/`
- WFP behavior under `pycodex/windows_sandbox/wfp/`
- root ACL, audit, process, and utility modules alongside the Rust root modules

Flat compatibility owners removed during alignment must not be reintroduced.

## Product Paths

Validation must cover both direct and conversational paths:

```text
python -m pycodex sandbox
  -> CLI profile selection
  -> Windows sandbox setup
  -> command runner
  -> native child process
```

```text
python -m pycodex
  -> conversation session
  -> tool approval
  -> Core execution
  -> Windows Sandbox
  -> visible tool result
```

## Structure And Tests

```powershell
python -B -m parity_harness contract validate-accepted --scope windows-sandbox
python -B -m parity_harness structure --scope windows-sandbox --gate ownership
python -m pytest pycodex/windows_sandbox/tests tests/e2e/windows_sandbox -q
```

The structure gate proves ownership and coverage. It does not replace native
execution, process-tree termination, network isolation, stderr forwarding, or
conversation-session E2E evidence.

## Completion Rule

Windows Sandbox remains aligned only while:

1. Accepted contracts resolve to unique production owners.
2. Read-only, workspace-write, and danger-full-access profiles reach the native
   enforcement layer.
3. Approval reuse is limited to an equivalent permission profile.
4. Timeouts terminate descendants.
5. Native and conversation-session E2E tests pass or report explicit,
   reproducible environment debt.

See [WINDOWS_SANDBOX_MANUAL_ACCEPTANCE.md](WINDOWS_SANDBOX_MANUAL_ACCEPTANCE.md)
for manual checks and
[WINDOWS_SANDBOX_PARITY_EVIDENCE.md](WINDOWS_SANDBOX_PARITY_EVIDENCE.md) for
the durable evidence summary.
