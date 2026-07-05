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
  use `pycodex.tui.rich_compat` for Rich values and
  `pycodex.tui.ratatui_bridge` for Rust-like TUI semantics.
- Do not silently fall back to globally installed packages when a vendored
  package is expected; ambiguous imports make porting behavior hard to audit.
