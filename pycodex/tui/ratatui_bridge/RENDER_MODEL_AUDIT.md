# Render model unification audit

Date: 2026-06-13

## Scope

This note records the migration away from local temporary render models toward shared ratatui semantic bridge types.

Rust owners:

- `codex-tui::render::renderable`
- `codex-tui::pager_overlay`
- `codex-tui::chatwidget::rendering`

Python modules involved:

- `pycodex/tui/render/renderable.py`
- `pycodex/tui/pager_overlay.py`
- `pycodex/tui/chatwidget/rendering.py`
- `pycodex/tui/ratatui_bridge/{layout.py,buffer.py,renderable.py}`

## Decision

Use shared `ratatui_bridge` primitives for generic render geometry and buffer semantics.

Completed in this migration:

- `render.renderable` now imports shared `ratatui_bridge.Rect` and `ratatui_bridge.Buffer` instead of defining local recording models.
- `pager_overlay` now imports shared `ratatui_bridge.Rect` instead of defining a local rectangle DTO.
- `chatwidget.rendering` now imports shared `ratatui_bridge.Rect` and reuses `render.renderable.EmptyRenderable`, `FlexRenderable`, `InsetRenderable`, and `Insets` instead of defining local temporary renderable layout classes.

## Remaining local models

Some modules still define local `Span`/`Line` or backend classes. Those are not automatically temporary render shims:

- `custom_terminal.py` and `test_backend.py` model terminal/backend behavior and are not replaced by `ratatui_bridge.Buffer` in this slice.
- `diff_render.py`, composer footer/history search, and similar modules use local `Span`/`Line` as domain output records; they should be migrated only when their Rust module boundary is ported or when a concrete renderer consumes them.
- `chatwidget.rendering.RenderLog` remains module-owned evidence for composition side effects; it is not a ratatui buffer replacement.

## Follow-up

Run targeted parity tests for the touched modules before relying on this migration broadly:

- `tests/test_tui_render_renderable.py`
- `tests/test_tui_ratatui_bridge.py`
- `tests/test_tui_pager_overlay.py`
- `tests/test_tui_chatwidget_rendering.py`
