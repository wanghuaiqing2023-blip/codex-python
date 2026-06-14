# `pycodex.tui.ratatui_bridge`

`ratatui_bridge` maps Rust `ratatui` concepts used by `codex-tui` into Python
semantic UI objects backed by `textual_compat` where rendering is needed.

It answers: how do Rust TUI behavior contracts survive the Python port?

## Responsibilities

- Represent Rust `ratatui::style::Style`-like semantics.
- Represent Rust `ratatui::text::{Span, Line, Text}`-like semantics.
- Represent Rust `ratatui::layout::Rect` and small layout helpers.
- Represent Rust `Widget`/`Renderable` behavior contracts as Python protocols
  or dataclasses.
- Convert bridge objects to Textual/Rich renderables only at the edge.

## Initial API

- `Color`, `Modifier`, `Style`
- `Span`, `Line`, `Text`
- `Rect`
- `Renderable`

The bridge intentionally starts small. Add more ratatui concepts only when a
ported Rust module needs them.

## Non-goals

- Do not clone the full ratatui framework.
- Do not implement terminal backend behavior unless a Codex module requires it.
- Do not make Rust-port modules depend directly on vendored Textual internals.

## Relationship to `textual_compat`

```text
Rust codex-tui module semantics
        -> pycodex.tui.ratatui_bridge
        -> pycodex.tui.textual_compat
        -> pycodex.vendor.textual / dependencies
```

The bridge preserves Rust behavior vocabulary. `textual_compat` isolates the
chosen Python UI backend.
