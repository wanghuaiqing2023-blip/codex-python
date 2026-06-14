# Vendored Python packages

This directory is reserved for source-vendored third-party Python packages used
by `pycodex`.

## Policy

- Vendored packages must be pinned to an explicit upstream version.
- Each package must preserve its upstream license and include source/version
  provenance in `VENDORED_PACKAGES.md`.
- Transitive runtime dependencies must be vendored or intentionally routed
  through a documented compatibility boundary.
- Project code should not import vendored UI packages directly. For TUI code,
  use `pycodex.tui.textual_compat` and `pycodex.tui.ratatui_bridge`.
- Do not silently fall back to globally installed packages when a vendored
  package is expected; ambiguous imports make porting behavior hard to audit.

## Planned packages

Textual will be vendored here as the Python TUI framework source of truth for
Codex TUI work, with its required runtime dependencies recorded and pinned.
