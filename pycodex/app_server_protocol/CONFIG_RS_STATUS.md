# protocol/v2/config.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/config.rs`

Python module: `pycodex/app_server_protocol/config.py`

Status: `complete-candidate`

## Behavior Contract

- Mirrors v2 config layer source variants and precedence ordering.
- Mirrors sandbox workspace-write, tool, analytics, app defaults, app tool,
  app, apps, forced workspace IDs, and effective config payloads.
- Mirrors config layer metadata/layers, read params/responses, write params and
  responses, merge/write status enums, overridden metadata, and write error
  codes.
- Mirrors managed config requirements, including computer-use, managed hooks,
  configured hook handlers, network requirements, domain/unix-socket
  permissions, and residency requirements.
- Mirrors external-agent config migration payloads, import/detect params and
  responses, config edit payloads, text positions/ranges, and warning
  notifications.
- Preserves important serde/default behavior: camelCase layer tags,
  snake_case config fields, flattened analytics/apps maps, default-enabled app
  config values, singleton-or-list ChatGPT workspace IDs, PascalCase hook
  buckets, and config layer source precedence.

## Evidence

- Source reviewed: `protocol/v2/config.rs`.
- Module boundary confirmed through `protocol/v2/mod.rs` declaring and exporting
  `config`.
- Python implementation added in `config.py` and exported from package
  `__init__.py`.
- Light validation run on 2026-06-17:
  - `python -m py_compile pycodex/app_server_protocol/config.py pycodex/app_server_protocol/__init__.py`
  - module-local smoke covering layer precedence, config read params,
    app defaults, effective config extra fields, write responses, merge
    strategy, and warning text ranges.
  - package export smoke for top-level config protocol imports.

Full crate tests are deferred until the crate's functional modules are complete,
per project instruction.
