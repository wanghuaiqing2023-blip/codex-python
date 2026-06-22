# `codex-state/src/model/graph.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/model/graph.rs`
- Public anchor: `DirectionalThreadSpawnEdgeStatus`

The Rust module owns the persisted status values attached to directional
thread-spawn edges. Runtime graph mutations and SQLite persistence belong to
`src/runtime/threads.rs` and are intentionally outside this module pass.

## Python mapping

- Module: `pycodex/state/model/graph.py`
- Re-exported through `pycodex/state/model/__init__.py` and
  `pycodex/state/__init__.py`.

The Python enum preserves Rust's `snake_case` `AsRefStr`/`Display` wire values:
`open` and `closed`. `as_ref()` and `__str__()` both expose the persisted
string, and `parse()` mirrors Rust `EnumString`-style conversion for callers
that receive persisted strings.

## Validation

```powershell
python -m py_compile pycodex\state\model\graph.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_graph_rs.py
python -m pytest tests\test_state_graph_rs.py -q
```

Result on 2026-06-17: `4 passed`. Re-run during status correction also passed:

```text
python -m pytest tests\test_state_graph_rs.py -q
4 passed

python -m py_compile pycodex\state\model\graph.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_graph_rs.py
```

Formal parity tests cover persisted wire values, Rust-like `as_ref()`, Rust
`Display` parity through `str(status)`, parsing accepted values, and unknown
value rejection.

## Remaining crate work

No known gaps for `src/model/graph.rs`. `codex-state` remains pending focused
full-crate validation before strict crate-complete promotion.
