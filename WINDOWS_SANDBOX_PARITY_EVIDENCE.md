# Windows Sandbox Parity Evidence

## Current Contract

- Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`
- Rust crate: `codex/codex-rs/windows-sandbox-rs`
- Python package: `pycodex/windows_sandbox`
- Accepted contracts: 54
- Ownership verdict: `verified`
- Coverage verdict: `verified`

The accepted contracts under
`parity_harness/contracts/accepted/windows-sandbox/` identify the exact Rust
coordinate, unique Python owner, production anchors, and fixture references.
Candidates are not accepted evidence.

## Alignment Result

The original coverage list mixed four distinct situations:

- behavior flattened into the wrong parent owner
- one Rust package scattered across Python files
- implemented behavior missing its production call-chain wiring
- genuinely missing behavior

Alignment moved existing behavior to Rust-owned module-files or continuous
packages, added missing coherent modules, connected them through the public CLI
and conversation-session paths, and removed obsolete flat owners. It did not
use compatibility facades to hide old imports.

The resulting structure covers command-runner and setup binaries, audit and ACL
handling, ConPTY, elevated IPC, unified-exec backends, WFP setup, process
attributes, helper materialization, and Windows utility modules.

## Reproducible Evidence

```powershell
python -B -m parity_harness contract validate-accepted --scope windows-sandbox
python -B -m parity_harness structure --scope windows-sandbox --gate ownership
python -m pytest pycodex/windows_sandbox/tests -q
python -m pytest tests/e2e/windows_sandbox -q
python -m pycodex --help
```

The E2E path must exercise public entry points rather than injected helpers:

```text
CLI sandbox command -> native Windows Sandbox -> child stdout/stderr/exit code
conversation session -> exec tool -> Core runtime -> Windows Sandbox -> reply
```

## Known Follow-up Boundary

Native behavior remains the final authority for process identity, filesystem
isolation, network policy, process-tree termination, terminal I/O, and stderr
forwarding. A passing injected test is insufficient if the public native
entrypoint behaves differently.

See [WINDOWS_SANDBOX_ALIGNMENT.md](WINDOWS_SANDBOX_ALIGNMENT.md) for ownership
rules and
[WINDOWS_SANDBOX_MANUAL_ACCEPTANCE.md](WINDOWS_SANDBOX_MANUAL_ACCEPTANCE.md)
for host-level acceptance.
