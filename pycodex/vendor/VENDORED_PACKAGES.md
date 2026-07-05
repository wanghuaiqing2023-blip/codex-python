# Vendored package manifest

This file records third-party packages vendored into `pycodex/vendor`.

## Runtime Rich compatibility stack

- Status: extracted and wired behind `pycodex.tui.rich_compat`
- Purpose: provide the conservative Rich subset used by TUI rendering tests and
  the Rust-like `ratatui_bridge`, without importing Rich from global site
  packages.
- Machine-readable manifest: `pycodex/vendor/VENDORED_PACKAGES.json`
- Target package root: `pycodex/vendor/_packages`
- Target metadata root: `pycodex/vendor/_dist_info`
- Target license root: `pycodex/vendor/licenses`
- Notes: Rich values are exposed through `rich_compat`, Rust `ratatui`
  semantics stay behind `ratatui_bridge`, and path-integrity checks prevent
  accidental imports from globally installed packages.

| Package | Candidate pin | Requires-Python evidence |
|---|---:|---|
| `rich` | `13.8.1` | `>=3.7.0` |
| `markdown-it-py` | `2.2.0` | `>=3.7` |
| `mdit-py-plugins` | `0.3.5` | `>=3.7` |
| `linkify-it-py` | `2.0.3` | `>=3.7` |
| `mdurl` | `0.1.2` | `>=3.7` |
| `importlib-metadata` | `6.7.0` | `>=3.7` |
| `typing-extensions` | `4.7.1` | `>=3.7` |
| `pygments` | `2.17.2` | `>=3.7` |
| `uc-micro-py` | `1.0.3` | `>=3.7` |
| `zipp` | `3.15.0` | `>=3.7` |

## Runtime WebSocket protocol implementation

- Package: `websockets`
- Version: `11.0.3`
- Purpose: Replace the Python port's standard-library WebSocket protocol subset
  for the product-critical Responses websocket path while preserving the
  existing Rust-aligned `codex-api::endpoint::responses_websocket` module
  boundary.
- License: BSD-3-Clause upstream.
- Source: https://github.com/python-websockets/websockets
- Package index: https://pypi.org/project/websockets/
- Wheel: `websockets-11.0.3-py3-none-any.whl`
- Wheel SHA256: `6681ba9e7f8f3b19440921e99efbb40fc89f26cd71bf539e45d8c8a25c976dc6`
- License file: `pycodex/vendor/licenses/websockets/LICENSE`
- Import roots: `websockets`
- Status: extracted and wired behind `pycodex.codex_api.endpoint._websocket_client`
- Audit report: `pycodex/vendor/WEBSOCKET_VENDOR_AUDIT.md`
- Notes: The historical Python implementation remains available as a private
  stdlib fallback/testing helper, but the public Responses websocket connect
  path now uses the vendored `websockets` sync client.
