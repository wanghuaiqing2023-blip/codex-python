# codex-state `src/model/thread_metadata.rs`

Status: `complete`

Python module: `pycodex/state/model/thread_metadata.py`

## Scope

This pass mirrors the Rust model contract for thread metadata without pulling
in SQLite runtime stores or rollout extraction:

- `SortKey`, `SortDirection`, `Anchor`, `ThreadsPage`, and
  `ExtractionOutcome`.
- `ThreadMetadata` and `ThreadMetadataBuilder`.
- `ThreadRow` to `ThreadMetadata` conversion.
- `anchor_from_item`, epoch-second/millisecond conversion helpers, lossy
  `ReasoningEffort` row parsing, and `BackfillStats`.

## Rust Evidence

- Rust module: `codex/codex-rs/state/src/model/thread_metadata.rs`
- Rust tests:
  - `thread_row_parses_reasoning_effort`
  - `thread_row_ignores_unknown_reasoning_effort_values`

## Python Evidence

- `ThreadRow.to_thread_metadata()` preserves empty `preview` and
  `first_user_message` as `None`, parses known reasoning effort strings, and
  ignores unknown reasoning effort strings.
- `epoch_millis_to_datetime()` preserves Rust's legacy behavior where values
  older than 2020 when interpreted as milliseconds are treated as
  second-precision rows.
- `ThreadMetadata.diff_fields()` intentionally mirrors Rust's field list,
  including the omission of `thread_source`.

## Deferred

- SQLite query/upsert behavior remains owned by `runtime/threads.rs` and other
  runtime store modules.
- Rollout item extraction and mutation remains owned by `extract.rs`.

## Validation

Formal parity validation:

```text
python -m pytest tests\test_state_thread_metadata_model_rs.py -q
# 9 passed

python -m py_compile pycodex\state\model\thread_metadata.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_thread_metadata_model_rs.py
```

Coverage includes Rust's known/unknown reasoning-effort tests, row conversion
of optional/empty fields, builder defaults, Git-field preservation,
`diff_fields` omission of `thread_source`, anchors, epoch helpers, invalid
row fields, usize-like counters, and invalid timestamp handling.
