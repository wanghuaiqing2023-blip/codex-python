# `pycodex.tui.ratatui_bridge`

`ratatui_bridge` maps Rust `ratatui` concepts used by `codex-tui` into Python
semantic UI objects backed by `rich_compat` where Rich rendering is needed.

It answers: how do Rust TUI behavior contracts survive the Python port?

## Responsibilities

- Represent Rust `ratatui::style::Style`-like semantics.
- Represent Rust `ratatui::text::{Span, Line, Text}`-like semantics.
- Represent Rust `ratatui::layout::Rect` and small layout helpers.
- Represent Rust `Widget`/`Renderable` behavior contracts as Python protocols
  or dataclasses.
- Provide a minimal Rust-like `Frame` / `Buffer` / `Terminal.draw` lifecycle
  with current/previous buffer diffing and previous-buffer invalidation state
  for terminal product adapters.
- Carry `Frame.set_cursor_position` through `Terminal.draw` to the backend so
  cursor placement belongs to the shared frame lifecycle.
- Convert bridge objects to Rich renderables only at the edge.

## Initial API

- `Color`, `Modifier`, `Style`
- `Span`, `Line`, `Text`
- `Rect`, `Size`
- `Renderable`, `Widget`, `WidgetRef`, `StatefulWidgetRef`
- `DrawCommand`, `diff_buffers`, `full_redraw_commands`, `FrameBufferState`,
  `requires_full_redraw`, `Backend`, `Frame`, `draw_buffer_to_ansi`,
  `Terminal`, `TestBackend`, `AnsiBackend`

The bridge intentionally starts small. Add more ratatui concepts only when a
ported Rust module needs them.

## Non-goals

- Do not clone the full ratatui framework.
- Do not clone full terminal backend behavior. The bridge may provide semantic
  diff/backend primitives needed by Codex's hybrid terminal path, including the
  minimal ANSI draw primitive consumed by runtime adapters.
- Do not make Rust-port modules depend directly on vendored UI internals.

## Relationship to `rich_compat`

```text
Rust codex-tui module semantics
        -> pycodex.tui.ratatui_bridge
        -> pycodex.tui.rich_compat
        -> pycodex.vendor rich dependency
```

The bridge preserves Rust behavior vocabulary. `rich_compat` isolates the
vendored Rich dependency used for tests and non-terminal renderable conversion.
