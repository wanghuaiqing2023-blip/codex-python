# protocol/v2/plugin.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/plugin.rs`

Python module: `pycodex/app_server_protocol/plugin.py`

Status: complete for the module-scoped app-server protocol data contract.

## Covered

- Skills and hooks list params/responses, including default empty cwd lists and
  force-reload serialization behavior.
- Marketplace add/remove/upgrade params/responses and marketplace load/upgrade
  error payloads.
- Plugin list, installed, read, skill-read, install, uninstall, and
  skills-config write params/responses.
- Plugin sharing save/update/list/checkout/delete payloads, share targets,
  principals, discoverability, principal types, and roles.
- Skill metadata/interface/dependencies/tool dependencies, skill scopes,
  plugin sources, plugin marketplace entries, plugin summaries/details,
  plugin interfaces, plugin auth/install/availability policies, and
  skills-changed notification payloads.

## Intentional Adaptations

- Plugin discovery, marketplace synchronization, remote sharing, install and
  uninstall side effects, skill scanning, and hook execution remain outside the
  protocol module boundary.
- Hook metadata enum fields and `AppSummary` payloads remain JSON-compatible
  protocol values where their runtime owners are neighboring modules.
- The `PluginAvailability` parser accepts Rust's upstream `"ENABLED"` alias
  and serializes it as `"AVAILABLE"`.

## Validation

- `python -m py_compile pycodex/app_server_protocol/plugin.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered skills params defaults, plugin source variants,
  marketplace entry null path, plugin interface local/remote assets, ignored
  legacy `forceRemoteSync` fields, marketplace-kind filters, plugin
  availability alias/defaults, sharing payloads, install/uninstall payloads,
  and package exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
