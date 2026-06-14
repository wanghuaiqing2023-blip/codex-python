# `pycodex.tui.textual_compat`

`textual_compat` is the sole project-facing adapter for vendored Textual.

It answers: how does Python Codex code import and use Textual?

## Responsibilities

- Re-export the approved subset of vendored Textual APIs used by `pycodex.tui`.
- Hide the physical vendored package location from production TUI modules.
- Provide a stable import boundary if the vendored Textual version changes.
- Make unavailable or intentionally unsupported Textual APIs fail explicitly.
- Verify that Textual/Rich modules are loaded from `pycodex/vendor/_packages`,
  not from globally installed site packages.

## Non-goals

- Do not model Rust `ratatui` types here.
- Do not expose the whole Textual package by default.
- Do not allow scattered direct imports from `pycodex.vendor._packages` in TUI
  modules.

## Intended import style

```python
from pycodex.tui.textual_compat import App, Widget, events
```

## Initial approved exports

- `App`
- `Widget`
- `ComposeResult`
- `Container`
- `Horizontal`
- `Vertical`
- `events`
- Rich bridge helpers: `Text`, `Style`

Additional Textual APIs should be added only when a ported TUI module needs
them.
