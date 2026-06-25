# Vendored package manifest

This file records third-party packages vendored into `pycodex/vendor`.

No third-party package source has been vendored yet.

## Planned: Textual

- Package: `textual`
- Purpose: Python TUI framework backend for Codex TUI porting.
- License: MIT upstream.
- Source: https://github.com/Textualize/textual
- Package index: https://pypi.org/project/textual/
- Status: planned
- Notes: Textual must be pinned to a specific version before source import.
  Required runtime dependencies, including Rich and any Textual transitive
  dependencies, must be recorded here when vendored.

## Candidate pin set: Python 3.7-compatible Textual stack

- Status: candidate, not yet vendored
- Reason: portability-first Textual stack with explicit Python 3.7 support.
- Plan: see `pycodex/vendor/VENDORING_PLAN.md`.

| Package | Candidate pin | Requires-Python evidence |
|---|---:|---|
| `textual` | `0.43.2` | `>=3.7,<4.0` |
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


## Audit result: Textual 0.43.2 candidate stack

- Status: audited, not yet vendored
- Audit report: `pycodex/vendor/TEXTUAL_0_43_2_AUDIT.md`
- Download cache: `.tmp/textual_vendor_audit`
- Result: candidate pin set is internally consistent for Python 3.7 metadata, but must be vendored with transitive runtime dependencies and license files.

## Source import plan: Textual 0.43.2 candidate stack

- Status: planned, not yet vendored
- Import plan: `pycodex/vendor/VENDOR_IMPORT_PLAN.md`
- Target package root: `pycodex/vendor/_packages`
- Target metadata root: `pycodex/vendor/_dist_info`
- Target license root: `pycodex/vendor/licenses`
- Notes: The plan keeps vendored Textual behind `textual_compat`, keeps Rust `ratatui` semantics behind `ratatui_bridge`, and requires path-integrity checks to prevent accidental imports from globally installed packages.


## Extracted source: Textual 0.43.2 candidate stack

- Status: extracted, not yet wired into TUI runtime
- Extraction report: `pycodex/vendor/TEXTUAL_0_43_2_EXTRACTED.md`
- Machine-readable manifest: `pycodex/vendor/VENDORED_PACKAGES.json`
- Package root: `pycodex/vendor/_packages`
- Metadata root: `pycodex/vendor/_dist_info`
- License root: `pycodex/vendor/licenses`
- Notes: Project code must still use `pycodex.tui.textual_compat`; direct imports from vendored package roots are not the supported TUI boundary.

## Runtime import helper: Textual 0.43.2 candidate stack

- Status: wired behind compatibility boundary
- Helper: `pycodex/vendor/__init__.py`
- Compatibility entrypoint: `pycodex/tui/textual_compat/__init__.py`
- Notes: Added a vendored import helper that prepends `pycodex/vendor/_packages` and verifies imported modules resolve from that tree. `textual_compat` now lazily exposes a conservative Textual/Rich API subset (`App`, `Widget`, `ComposeResult`, containers, events, Rich `Text`/`Style`) without requiring existing TUI modules to change.

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
