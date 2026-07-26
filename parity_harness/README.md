# Rust/Python Parity Harness

This directory is an independent architecture and evidence Harness for the
Codex Rust-to-Python port. It does not provide product implementations or read
architecture data from `pycodex/`.

## Authority

- `contracts/workspace.json` pins the Rust baseline and classifies every Cargo
  crate as accepted, partial, or deferred.
- `contracts/accepted/<scope>/` contains reviewed module-owner contracts.
- `contracts/accepted/<scope>.policy.json` records honest Rust and Python
  coverage debt.
- `contracts/generated/` contains disposable review candidates only.

A candidate path, matching filename, or Python-only test is navigation
evidence, not parity. Candidate generation never writes accepted contracts.

## Commands

```powershell
python -B -m parity_harness workspace check
python -B -m parity_harness contract generate --scope core
python -B -m parity_harness contract validate-accepted --scope all
python -B -m parity_harness structure --scope core --gate ownership
python -B -m parity_harness structure --scope all --gate ownership
python -B -m parity_harness audit
python -B -m unittest discover -s parity_harness/tests -v
```

`structure` reports `ownership_verdict` and `coverage_verdict` separately.
Partial crates pass the ownership gate only when every existing Python file has
one reviewed owner or a justified intentional-adapter boundary. Declaring an
existing Python production file in `uncovered_python_files` records ownership
drift and does not make the ownership gate pass. Missing Rust ports remain
visible as partial coverage. Deferred crates have a reviewed reason and no
fabricated Python owner.

Each structure run writes a detailed machine-readable summary to
`.artifacts/structure/accepted-<scope>-summary.json`. The summary includes every
active crate's contract count, ownership and coverage verdicts, uncovered Rust
modules, orphan Python files, duplicate or scattered owners, foreign items,
intentional adapters, and the reviewed reasons for deferred crates. Failed
scopes also include a structured `migration_plan`: foreign symbols are grouped
by Python owner and authoritative Rust module/source, while unowned Python
files receive a separate review action.

## Contract checks

The structure layer checks full Cargo coordinates, inline modules, `mod.rs`,
bins, re-exports, unique owners, bounded module-packages, anchors, foreign
items, fixture paths, optional dependency boundaries, restricted decisions,
and opt-in orphan candidates. Non-production exclusions require a real path and
a reason.

Dynamic, outcome, and independent acceptance commands remain separate evidence
layers. They must not be presented as product parity unless a real Rust/Python
scenario supplies both sides of the evidence.
