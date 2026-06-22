# codex-state `src/model/mod.rs`

Status: `complete`

Python module: `pycodex/state/model/__init__.py`

## Scope

This pass mirrors the Rust model aggregation module:

- Declares the Python package as the canonical aggregation point for the
  `codex-state/src/model/*` modules.
- Re-exports the public Rust model surface from `agent_job`, `backfill_state`,
  `graph`, `log`, `memories`, `thread_goal`, and `thread_metadata`.
- Preserves crate-private helper visibility as Python package exports where
  neighboring Python state modules need row conversion and timestamp helpers.

## Rust Evidence

- Rust module: `codex/codex-rs/state/src/model/mod.rs`
- Rust source declares seven child modules and re-exports public plus
  `pub(crate)` row/helper surfaces.

## Python Evidence

- `pycodex.state.model` imports and exposes the corresponding Python model
  modules and row/helper surfaces.
- `pycodex.state` package-root imports continue to re-export the model package
  surface needed by already ported state modules.

## Deferred

- Runtime persistence, SQLite queries, extraction, and DB mutation remain owned
  by `runtime/*`, `extract.rs`, and `log_db.rs`, not by this aggregation module.

## Validation

Formal parity validation:

```text
python -m pytest tests\test_state_model_mod_rs.py -q
# 3 passed

python -m py_compile pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_model_mod_rs.py
```

Coverage verifies Rust public `pub use` anchors, crate-private row/helper
anchors retained for neighboring Python state modules, and `__all__` export
membership for the required aggregation surface.
