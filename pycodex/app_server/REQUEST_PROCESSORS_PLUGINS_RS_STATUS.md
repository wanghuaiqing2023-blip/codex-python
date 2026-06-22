# request_processors/plugins.rs alignment status

Rust source: `codex/codex-rs/app-server/src/request_processors/plugins.rs`

Python module: `pycodex/app_server/request_processors_plugins.py`

Python tests: `tests/test_app_server_request_processors_plugins_rs.py`

Status: `complete`

## Covered behavior

- `PluginRequestProcessor::new` dependency storage and public facade methods
  for list/read/share/install/uninstall request surfaces.
- Effective-plugin change cache clearing boundary for plugin and skill
  managers, best-effort refresh trigger, plus latest-config reload and
  workspace plugin gating fallback.
- `plugin_skills_to_info` conversion, including skill interface projection,
  path forwarding, and disabled-path enabled flag calculation.
- `local_plugin_interface_to_info`, including URL fields that Rust fills as
  `None` and empty remote screenshot URLs.
- Marketplace plugin source conversion for local and git sources.
- Local share-context lookup by local plugin path, with git sources returning
  no context.
- Configured marketplace plugin summary conversion, including source, policy,
  availability, keywords, optional interface, and optional share context.
- Remote installed plugin visible-scope calculation from `RemotePlugin` and
  `PluginSharing` feature flags.
- Share discoverability, update-discoverability, target-role, target, and
  remote principal conversions.
- Client share-target validation rejecting workspace principals with the Rust
  invalid-request error message.

## Intentional boundaries

- Concrete plugin discovery, marketplace sync, remote plugin install/uninstall,
  OAuth login, app-auth probing, and share-service calls remain injected
  runtime boundaries.
- This module intentionally treats extension-heavy work as compatibility
  facade behavior per current project priority; deeper plugin runtime parity is
  tracked under the extension crates rather than this app-server module.

## Validation

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_plugins_rs.py -q`
  -> 12 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_plugins.py tests/test_app_server_request_processors_plugins_rs.py`.
