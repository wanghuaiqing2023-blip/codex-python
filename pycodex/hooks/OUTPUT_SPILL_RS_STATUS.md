# codex-hooks src/output_spill.rs Status

Rust crate: `codex-hooks`

Rust module: `src/output_spill.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `HookOutputSpiller.new()` uses the OS temp directory plus `hook_outputs` as
  the default root.
- `maybe_spill_text(...)` returns text inline when its approximate token count
  is at or below `2_500`.
- Oversized text is written in full under
  `<output_dir>/<thread_id>/<uuid>.txt`.
- The model-visible replacement is the standard formatted truncation preview
  plus `Full hook output saved to: <path>`.
- Directory or write failures fall back to standard formatted token truncation
  without a saved-path footer.
- `maybe_spill_texts(...)` and `maybe_spill_prompt_fragments(...)` preserve
  input order; prompt fragment spilling rewrites only `text` and keeps
  `hook_run_id`.

## Rust Evidence

- `codex/codex-rs/hooks/src/output_spill.rs`
- `codex/codex-rs/hooks/src/output_spill_tests.rs`
- Rust tests:
  - `small_hook_output_remains_inline`
  - `large_hook_output_spills_to_file`

## Python Evidence

- `tests/test_hooks_output_spill_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_output_spill_rs.py -q --tb=short
```

Passed on 2026-06-21 with `4 passed`.
