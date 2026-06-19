# `codex-state/src/model/memories.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/model/memories.rs`
- Public model anchors:
  - `Stage1Output`
  - `Stage1JobClaimOutcome`
  - `Stage1JobClaim`
  - `Stage1StartupClaimParams`
  - `Phase2JobClaimOutcome`

This module owns memory extraction model payloads and claim outcomes. Runtime
memory-store behavior belongs to `src/runtime/memories.rs` and is intentionally
not included in this module pass.

## Python mapping

- Module: `pycodex/state/model/memories.py`
- Re-exported through `pycodex/state/model/__init__.py` and `pycodex/state/__init__.py`.

The Python port mirrors Rust value shapes with frozen dataclasses and string
enums, normalizes path fields to `pathlib.Path`, normalizes datetimes to UTC,
and enforces Rust integer-domain constraints for `usize` and `i64` fields.
`ThreadMetadata` is kept as a pass-through interface constraint in
`Stage1JobClaim.thread` until the neighboring Rust module is ported.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_memories_model_rs.py -q
# 6 passed

python -m py_compile pycodex\state\model\memories.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_memories_model_rs.py
```

Coverage includes `Stage1Output` path/datetime normalization, stage-1
non-claimed outcomes plus claimed ownership-token shape, `Stage1JobClaim`,
`Stage1StartupClaimParams`, phase-2 outcomes plus claimed watermark shape, and
Rust-compatible scalar-domain validation.

## Remaining crate work

Other `codex-state` modules remain open for focused formal validation before
the crate can be promoted from `implemented_candidate` to strict `complete`.
