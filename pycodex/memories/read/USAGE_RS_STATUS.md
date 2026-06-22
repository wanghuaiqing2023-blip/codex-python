# codex-memories-read src/usage.rs status

Rust coordinate: `codex/codex-rs/memories/read/src/usage.rs`

Python coordinate: `pycodex/memories/read/usage.py`

Status: complete.

Ported public API:

- `MEMORIES_USAGE_METRIC`
- `MemoriesUsageKind`
- `MemoriesUsageKind.as_tag`
- `memories_usage_kinds_from_command`

Ported behavior:

- Returns no usage kinds unless `is_known_safe_command(command)` accepts the command.
- Parses safe commands through the ported `pycodex.shell_command.parse_command` API.
- Classifies `ParsedCommand::Read.path` and `ParsedCommand::Search.path`.
- Ignores `ParsedCommand::ListFiles` and `ParsedCommand::Unknown`.
- Uses Rust substring matching for memory paths:
  `memories/MEMORY.md`, `memories/memory_summary.md`,
  `memories/raw_memories.md`, `memories/rollout_summaries/`, and
  `memories/skills/`.

Rust-derived/source-contract test evidence:

- `tests/test_memories_read_usage_rs.py`

Validation:

- Syntax-only this turn because the full `codex-memories-read` crate functional code is not yet complete:
  `python -m py_compile pycodex/memories/read/usage.py tests/test_memories_read_usage_rs.py`
