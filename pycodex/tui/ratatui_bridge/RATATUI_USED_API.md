# codex-tui used ratatui API coverage

Status: complete_slice
Date: 2026-06-13

This ledger scopes `pycodex.tui.ratatui_bridge` to the ratatui APIs that are actually referenced by the upstream Rust `codex-rs/tui` crate. It is intentionally not a full ratatui clone.

Source scan used for this slice:

```powershell
rg "use ratatui|ratatui::" codex/codex-rs/tui/src
```

The scan output was grouped by ratatui area and then compared against the current Python bridge.

## Coverage summary

| Rust API area | Rust API / item examples | Python bridge target | Status | Notes |
| --- | --- | --- | --- | --- |
| `ratatui::layout::Rect` | `Rect`, `Rect::new`, `area`, `intersection`, `right`, `bottom` style geometry behavior | `pycodex.tui.ratatui_bridge.layout.Rect` | covered | Current bridge has constructor, `new`, `right`, `bottom`, `is_empty`, `area`, `intersection`, `inset`, `inner`, `clamp_size`. |
| `ratatui::buffer::Buffer` | `Buffer`, `Buffer::empty`, setting spans/lines/text into a rectangular area | `pycodex.tui.ratatui_bridge.buffer.Buffer` | partial | Current bridge covers semantic cell storage and text writes. Still needs ratatui-like indexing and styling mutation helpers if Rust modules require exact `buf[(x, y)]` or style APIs. |
| `ratatui::buffer::Cell` | `Cell`, `Cell::symbol`, cell symbol/style mutations | `pycodex.tui.ratatui_bridge.buffer.Cell` | partial | Current bridge has symbol/style storage and constructors. Add ratatui-like mutation/accessor methods only when a ported module needs them. |
| `ratatui::style::Style` | `Style`, `Style::default`, `Style::reset`, patching/styling text | `pycodex.tui.ratatui_bridge.style.Style` | partial | Current bridge covers default style, fg/bg/modifiers, patching, and Rich conversion. `Style::reset` should be added when needed. |
| `ratatui::style::Color` | `Color`, `Color::Reset`, `Color::Rgb`, `Color::Indexed`, named colors such as `Cyan`, `LightBlue` | `pycodex.tui.ratatui_bridge.style.Color` | partial | Current bridge supports reset/rgb/indexed/named semantic colors and Rust-like constants such as `Color.Cyan`, `Color.LightBlue`, and `Color.Reset`. |
| `ratatui::style::Modifier` | `Modifier::BOLD`, `Modifier::REVERSED` | `pycodex.tui.ratatui_bridge.style.Modifier` | covered | Current bridge covers the modifier values used by TUI text/style code. |
| `ratatui::text::Span` | `Span`, `Span::width`, styled/plain spans | `pycodex.tui.ratatui_bridge.text.Span` | partial | Current bridge covers raw/styled spans, width, plain text, and Rich conversion. Stylize trait sugar is intentionally not cloned unless required. |
| `ratatui::text::Line` | `Line`, `Line::from`, collections of spans | `pycodex.tui.ratatui_bridge.text.Line` | partial | Current bridge covers raw/styled/from_spans, width, plain text, and Rich conversion. Exact Rust conversion overloads can be added per module. |
| `ratatui::text::Text` | `Text`, multi-line text payloads | `pycodex.tui.ratatui_bridge.text.Text` | partial | Current bridge covers raw/from_lines, plain lines, width, and Rich conversion. |
| `ratatui::layout::Alignment` | `Alignment` for paragraph/widget alignment | `pycodex.tui.ratatui_bridge.layout.Alignment` | covered | Semantic left/center/right alignment model used by `Paragraph`. |
| `ratatui::layout::Constraint` | `Constraint`, layout sizing rules | `pycodex.tui.ratatui_bridge.layout.Constraint` | partial | Covers length/percentage/ratio/min/max/fill as a portable semantic model. Solver edge cases should be tightened against selected Rust module tests. |
| `ratatui::layout::Direction` | horizontal/vertical layout direction | `pycodex.tui.ratatui_bridge.layout.Direction` | covered | Horizontal/vertical split direction. |
| `ratatui::layout::Layout` | split areas by constraints/direction | `pycodex.tui.ratatui_bridge.layout.Layout` | partial | Provides deterministic portable splitting for codex-tui ports. Not a full clone of ratatui internal constraint solver. |
| `ratatui::layout::Margin` | inset/outer margin model | `pycodex.tui.ratatui_bridge.layout.Margin` | covered | `Rect.inner(Margin)` is supported. |
| `ratatui::layout::Offset` | relative position offset | `pycodex.tui.ratatui_bridge.layout.Offset` | covered | Semantic offset dataclass. |
| `ratatui::layout::Position` | terminal position | `pycodex.tui.ratatui_bridge.layout.Position` | covered | Semantic position dataclass with `new`. |
| `ratatui::layout::Size` | `Size`, `Size::new` | `pycodex.tui.ratatui_bridge.layout.Size` | covered | Semantic size dataclass with `new`. |
| `ratatui::widgets::Paragraph` | paragraph widget render behavior | `pycodex.tui.ratatui_bridge.widgets.Paragraph` | partial | Renders text into `Buffer`, with style, alignment, wrapping, and optional block. More Rust edge cases can be added per module. |
| `ratatui::widgets::Wrap` | paragraph wrapping option | `pycodex.tui.ratatui_bridge.widgets.Wrap` | partial | Supports trim flag and width-based wrapping. |
| `ratatui::widgets::Clear` | clear a region before rendering overlays/popups | `pycodex.tui.ratatui_bridge.widgets.Clear` | covered | Fills a region with blank cells. |
| `ratatui::widgets::Block` | widget border/title/background container | `pycodex.tui.ratatui_bridge.widgets.Block` | partial | Covers border/title rendering, inner area semantics, side-specific borders, and unicode border variants. |
| `ratatui::widgets::Borders` | border side flags | `pycodex.tui.ratatui_bridge.widgets.Borders` | covered | Supports none/all and left/right/top/bottom bitflags with Rust-like aliases. |
| `ratatui::widgets::BorderType` | border style variants | `pycodex.tui.ratatui_bridge.widgets.BorderType` | covered | Supports plain/rounded/double/thick semantic variants with unicode border glyphs. |
| `ratatui::widgets::Widget` | render trait | `pycodex.tui.ratatui_bridge.widgets.Widget` / `renderable.Renderable` | partial | Python protocols capture the render contract. Rust trait method names should be adapted per module as needed. |
| `ratatui::widgets::WidgetRef` | by-reference widget render trait | `pycodex.tui.ratatui_bridge.widgets.WidgetRef` | partial | Protocol plus `render_ref` helper covers by-reference render dispatch. |
| `ratatui::widgets::StatefulWidgetRef` | stateful by-reference widget render trait | `pycodex.tui.ratatui_bridge.widgets.StatefulWidgetRef` | partial | Protocol plus `render_stateful_ref` helper covers stateful render dispatch. |
| `ratatui::backend::Backend` | backend trait, `flush`, drawing surface | `pycodex.tui.ratatui_bridge.backend.Backend` | complete_slice | Protocol covers semantic buffer-backed backend shape plus draw/flush/cursor-position lifecycle, diff/full-redraw command generation, previous-buffer compatibility checks, and previous-buffer invalidation state for product-path adapters. The bridge includes a minimal ANSI draw primitive for hybrid terminal adapters, not a full terminal backend clone. |
| `ratatui::backend::CrosstermBackend` | real terminal backend | `pycodex.tui.ratatui_bridge.backend.CrosstermBackend` | backend/test-only | Placeholder preserves type boundary and explicitly raises for runtime-specific side effects. |
| `ratatui::backend::TestBackend` | test buffer backend | `pycodex.tui.ratatui_bridge.backend.TestBackend` | complete_slice | Buffer-backed semantic backend for parity-style rendering; applies diff draw commands and records flush/draw counts. |
| Python hybrid ANSI draw primitive | product-path adapter output for buffer diffs | `pycodex.tui.ratatui_bridge.backend.AnsiBackend` / `draw_buffer_to_ansi` | complete_slice | Writes cursor/style/clear ANSI for `DrawCommand` values, chooses full redraw vs same-area diff for live buffers, and keeps a semantic buffer for tests. This is narrower than Rust `CrosstermBackend` and exists to let Python runtime adapters consume the same frame/diff lifecycle. |
| `ratatui::backend::WindowSize` | terminal pixel/cell size data | `pycodex.tui.ratatui_bridge.backend.WindowSize` | partial | Stores cell size and optional pixel size. |
| `ratatui::Terminal` | terminal wrapper, `Terminal::new` | `pycodex.tui.ratatui_bridge.backend.Terminal` | complete_slice | Semantic wrapper over bridge backend with current/previous buffers, `draw`, diff flushing, resize handling, frame cursor-position handoff, and backend accessors. |
| `ratatui::crossterm::*` | raw mode, execute, terminal/style commands | `pycodex.tui.ratatui_bridge.crossterm` | backend/test-only | Clear/attribute/color command values are modeled. Raw mode and command execution explicitly raise because the terminal runtime owns real terminal side effects. |
| `ratatui::prelude::*` | broad re-export use sites | resolved per module | n/a | `prelude::*` is not an implementation target. Each imported symbol must map to one of the concrete APIs above. |

## Current bridge target

The bridge should cover only the APIs needed by selected `codex-rs/tui` modules. For now, the useful next implementation order is:

1. Tighten `Layout` solver behavior against selected Rust module tests as needed.
2. Add side-specific `Borders` flags only when codex-tui modules require them.
3. Add widget adapter helpers around `WidgetRef` / `StatefulWidgetRef` only when selected modules need Rust trait-shape parity.
4. Keep real crossterm/raw-terminal side effects deferred to terminal runtime/custom-terminal integration; the bridge only owns semantic/test backend behavior.

## Rule for future bridge work

Do not implement ratatui APIs just because upstream ratatui has them. Implement an API here only when:

- it is referenced by `codex-rs/tui`, and
- a selected Python porting module needs the behavior, and
- the behavior can be represented as a portable semantic model without leaking Rust framework types.




## Rich handoff

Status: complete_slice

`pycodex.tui.ratatui_bridge.rich_adapter` is the official handoff from portable ratatui semantics to vendored Rich renderables. It converts `Span`, `Line`, `Text`, `Cell`, and `Buffer` into Rich `Text`, provides plain buffer snapshots, and supports rendering bridge-style objects into a fresh `Buffer` before conversion. Real terminal I/O remains owned by the terminal runtime/custom-terminal boundary while preserving ratatui-style layout/render behavior in Python.

## Surface completion note

Status: complete_slice

The bridge now has a closed semantic surface for the codex-tui-used ratatui categories tracked here, excluding intentional real-terminal side effects. Remaining `partial` rows mean ratatui edge-case behavior should be tightened against selected Rust module tests, not that the import/API boundary is absent.
