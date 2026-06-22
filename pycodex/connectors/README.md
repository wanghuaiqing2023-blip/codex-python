# `pycodex.connectors`

Canonical Python coordinate for behavior aligned with Rust `codex-rs/connectors`.

Core runtime policy and config integration remain in `pycodex.core.connectors`, matching Rust `codex-rs/core/src/connectors.rs`.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/accessible.rs` | `pycodex/connectors/accessible.py` | `complete` | Accessible connector collection, connector-name/description normalization, install URL projection, and plugin display-name union/dedupe behavior are mapped. |
| `src/directory_cache.rs` | `pycodex/connectors/directory_cache.py` | `complete` | Cache key hashing, disk cache path, schema-version validation, invalid/stale cache removal, and JSON connector serialization are mapped. |
| `src/filter.rs` | `pycodex/connectors/filter.py` | `complete` | Disallowed connector filtering, first-party chat disallow list selection, discoverable suggestion filtering, accessible exclusion, and name/id sorting are mapped. |
| `src/lib.rs` | `pycodex/connectors/__init__.py` | `complete` | Directory list pagination, workspace list fallback, hidden app filtering, duplicate app merge, normalization, shared memory cache, and disk-cache read/write handoff are mapped. |
| `src/merge.rs` | `pycodex/connectors/merge.py` | `complete` | Directory/plugin connector merging, placeholder replacement, install URL fallback, accessibility projection, and plugin display-name sorting/dedupe are mapped. |
| `src/metadata.rs` | `pycodex/connectors/metadata.py` | `complete` | Display labels, mention/install slugs, sanitize-name projection, value normalization, and accessibility/name/id ordering are mapped. |

Focused validation passed:

- `python -m pytest tests/test_connectors_rs.py -q --tb=short` -> `11 passed`
- `python -m pytest tests/test_core_connectors.py tests/test_core_mcp_tool_exposure.py tests/test_core_request_plugin_install.py -q --tb=short` -> `59 passed`
- `python -m py_compile pycodex/connectors/__init__.py pycodex/connectors/filter.py pycodex/connectors/directory_cache.py pycodex/connectors/metadata.py pycodex/connectors/merge.py pycodex/connectors/accessible.py tests/test_connectors_rs.py` passed
