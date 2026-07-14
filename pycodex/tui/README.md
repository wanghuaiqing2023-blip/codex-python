# pycodex.tui

Rust crate: `codex-tui`

Immutable Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`

## Product architecture

The supported product path is the real terminal TUI. The project does not
maintain a Textual path.

```text
event_stream
  -> tui/app runtime
  -> chat_composer / active BottomPaneView
  -> Frame / Buffer render
  -> custom_terminal diff/flush
  -> terminal scrollback + live viewport
```

Rust module behavior contracts own user-visible behavior. Python-only terminal
adapters may translate ANSI, Windows console, or hybrid scrollback concerns,
but they do not own slash commands, selection, approvals, model/reasoning
state, history, or resize semantics.

## Current evidence

- `tui_alignment.py` binds every module owner and adapter responsibility to the
  fixed Rust baseline; `tests/test_tui_alignment.py` guards the mapping.
- `APPROVAL_ALIGNMENT.md` records the typed request, active-view, decision,
  replay, interruption, session-grant, and Windows Terminal acceptance paths.
- `chatwidget::command_lifecycle` keeps running commands as mutable active
  cells and commits exactly one finalized typed history cell.
- `app::resize_reflow`, bottom-pane footprint projection, and
  `custom_terminal` clear the previous active footprint before rendering the
  finalized history cell.
- `shell_command` and unified execution share the typed command-history path;
  terminal runtime contains no command-specific history projection branch.
- Rust-derived owner tests cover normal/IME input, slash discovery and
  dispatch, active views, structured history, streaming, approval, resize,
  scrollback, and transcript overlay behavior.

Further changes require an observable fixed-baseline behavior difference or a
module-scoped contract gap. File splitting by itself is not a parity goal.
