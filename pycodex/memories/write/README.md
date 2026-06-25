# pycodex.memories.write

Rust crate: `codex-memories-write`
Rust path: `codex/codex-rs/memories/write`

This package carries dependency-light Python projections of selected write-path
memory helpers.

## Module Coverage

| Rust module | Python surface | Status | Notes |
|---|---|---|---|
| `src/storage.rs` | `pycodex.memories.write` | complete_slice | `Stage1Output` field projection, memory artifact paths, layout creation, rollout summary file stem generation, canonical summary syncing/pruning, and `raw_memories.md` rebuild shape are covered by Rust-derived tests. |
| `src/prompts.rs` | `pycodex.memories.write` | complete_slice | Stage-one rollout input prompt rendering, model-context-window token budget selection, default rollout limit fallback, and consolidation prompt extension/diff block rendering are covered by Rust-derived tests. |
| `src/guard.rs` | `pycodex.memories.write` | complete_slice | Rate-limit snapshot startup gating, AuthManager/backend-client fallback behavior, codex-limit snapshot selection, primary/secondary window threshold checks, missing-window allowance, and reached-limit hard blocking are covered by Rust-derived tests. |
| `src/control.rs` | `pycodex.memories.write` | complete_slice | Memory root clearing preserves the root directory, removes nested contents, and rejects symlinked roots on Unix-compatible hosts with Rust-derived tests. |
| `src/workspace.rs` | `pycodex.memories.write` | complete_slice | Memory workspace preparation, generated diff cleanup, git-baseline reset with Rust/gix-style raw blob identity on Windows, bounded diff rendering, and UTF-8 byte-boundary truncation are covered by Rust-derived tests. |
| `src/extensions/*` | `pycodex.memories.write` | complete_slice | Ad-hoc extension instruction seeding and old resource pruning are covered by Rust-derived tests. |
| `src/start.rs` | `pycodex.memories.write` | complete_slice | Startup eligibility gates, memory root creation, ad-hoc instruction seeding, rate-limit skip accounting, and phase call ordering are covered by Rust-derived tests/source contracts. |
| `src/phase1.rs` | `pycodex.memories.write` | complete_slice | Phase-1 output schema, rollout item filtering, contextual fragment exclusion, secret redaction before serialization, `job::sample` default real JSONL rollout loading plus prompt/schema/output parsing, `job::run` sample-result branching, job/token stats aggregation, metrics emission, startup job claiming, run-level orchestration, and DB result persistence helpers are covered by Rust-derived tests. |
| `src/phase2.rs` | `pycodex.memories.write` | complete_slice | Phase-2 run orchestration, workspace input sync, watermark selection, final agent status classification, dispatch metrics, token usage metrics, global claim mapping, DB failed/succeeded persistence helpers, consolidation agent config/prompt helpers, heartbeat loop errors, and completion handling for ownership confirmation, baseline reset, success/failure, token usage, and shutdown are covered by Rust-derived tests/source contracts. |
| `src/runtime.rs` | `pycodex.memories.write` | complete_slice | `MemoryStartupContext`, `StageOneRequestContext`, telemetry delegation, live thread service-tier projection, model-info lookup, reasoning-summary fallback/override, detached memory turn metadata, stage-one stream event handling, consolidation agent spawn options, submit-error cleanup, and shutdown handoff/timeout projection are covered by Rust-derived tests/source contracts. |
| `src/lib.rs` | `pycodex.memories.write` | complete | Public storage, prompt, guard, control, workspace, extension, startup, phase, runtime, and path helpers are projected through the package facade. |

## Native Runtime Differences

The Python port intentionally does not embed Rust's exact live `ModelClient::new`
network stream execution, native `codex_backend_client::Client::from_auth`
transport identity, Tokio task scheduling identity, native `CodexThread`
consolidation runtime object identity, or live heartbeat race timing. Those are
non-blocking implementation differences for this dependency-light port.
Rollout JSONL loading delegates to the completed `pycodex.rollout` port rather
than reimplementing Rust Tokio file-reader identity inside
`pycodex.memories.write`.

`codex-memories-write` is `complete` for the dependency-light Python projection.

## Tests

- `tests/test_memories_write_storage_rs.py`
- `tests/test_memories_write_prompts_rs.py`
- `tests/test_memories_write_guard_rs.py`
- `tests/test_memories_write_control_rs.py`
- `tests/test_memories_write_workspace_rs.py`
- `tests/test_memories_write_extensions_rs.py`
- `tests/test_memories_write_start_rs.py`
- `tests/test_memories_write_phase1_rs.py`
- `tests/test_memories_write_phase2_rs.py`
- `tests/test_memories_write_runtime_rs.py`
