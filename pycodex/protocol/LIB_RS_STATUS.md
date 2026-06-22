# codex-protocol src/lib.rs status

Status: complete_slice

Rust owner: `codex-protocol`
Rust module: `codex/codex-rs/protocol/src/lib.rs`
Python package root: `pycodex/protocol/__init__.py`

## Behavior Contract

Rust `src/lib.rs` owns the crate-root module graph and the root re-export
surface for the private identifier/path modules:

- `pub use agent_path::AgentPath`
- `pub use session_id::SessionId`
- `pub use thread_id::ThreadId`
- `pub use tool_name::ToolName`

It also declares the public protocol modules used by downstream crates:
`account`, `auth`, `approvals`, `config_types`, `dynamic_tools`, `error`,
`exec_output`, `items`, `mcp`, `mcp_approval_meta`, `memory_citation`,
`models`, `network_policy`, `num_format`, `openai_models`, `parse_command`,
`permissions`, `plan_tool`, `protocol`, `request_permissions`,
`request_user_input`, `shell_environment`, and `user_input`.

## Python Mapping

`pycodex.protocol` mirrors the crate-root surface through package-level
imports in `pycodex/protocol/__init__.py`. The root re-exports expose
`AgentPath`, `SessionId`, `ThreadId`, and `ToolName`, while public Rust
modules map to Python sibling modules. Rust `permissions.rs` is intentionally
merged into `pycodex/protocol/models.py` because the Python permission model
shares dataclass and serializer ownership with the Rust `models.rs` contract.

## Evidence

- Rust source inspected: `codex/codex-rs/protocol/src/lib.rs`.
- Python root surface inspected: `pycodex/protocol/__init__.py`.
- Module behavior is export-surface only; no new functionality was required.
- Validation deferred by current crate automation rule until
  `codex-protocol` functional module code is complete.
