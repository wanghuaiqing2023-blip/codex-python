# protocol/v2/permissions.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/permissions.rs`

Python module: `pycodex/app_server_protocol/permissions.py`

Status: `complete-candidate`

## Behavior Contract

- Mirrors v2 network approval protocol/context payloads and bridges them to
  `pycodex.protocol.approvals`.
- Mirrors additional network/filesystem permission overlays, request permission
  profiles, additional/granted permission profiles, active permission profiles,
  and permission profile list params/responses.
- Mirrors filesystem access modes, special path variants, filesystem path
  variants, and sandbox entries, including the
  `current_working_directory` alias for `project_roots`.
- Mirrors v2 `SandboxPolicy` serde shape with camelCase variant tags and
  defaulted network/workspace fields, while bridging to the core legacy
  `pycodex.protocol.models.SandboxPolicy`.
- Mirrors transparent exec policy amendments, network policy amendments, grant
  scopes, and permissions approval params/responses.
- Preserves Rust's rejection of restricted legacy read-only access fields in v2
  sandbox policy deserialization.

## Evidence

- Source reviewed: `protocol/v2/permissions.rs`.
- Module boundary confirmed through `protocol/v2/mod.rs` declaring and exporting
  `permissions`.
- Python implementation added in `permissions.py` and exported from package
  `__init__.py`.
- Light validation run on 2026-06-17:
  - `python -m py_compile pycodex/app_server_protocol/permissions.py`
  - `python -m py_compile pycodex/app_server_protocol/__init__.py`
  - module-local smoke covering camelCase wire shape, core sandbox bridge,
    filesystem permission bridge, approval response defaults, and legacy
    restricted read-only rejection.

Full crate tests are deferred until the crate's functional modules are complete,
per project instruction.
