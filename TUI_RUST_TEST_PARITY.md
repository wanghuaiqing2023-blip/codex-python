# TUI Rust Parity

This page is the stable entry point for TUI parity evidence. It does not track
individual porting turns.

## Authority

- Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`
- Rust crate: `codex/codex-rs/tui`
- Python package: `pycodex/tui`
- Accepted ownership contracts:
  `parity_harness/contracts/accepted/tui/`
- TUI framework notes: `pycodex/tui/README.md`
- Product-flow checklist:
  [TUI_SESSION_REGRESSION_CHECKLIST.md](TUI_SESSION_REGRESSION_CHECKLIST.md)

The supported Python UI is the Rust-aligned terminal TUI. Terminal adapters may
translate console details, but slash commands, composer behavior, active views,
history, approvals, and rendering remain owned by their Rust modules.

## Structure Gate

```powershell
python -B -m parity_harness contract validate-accepted --scope tui
python -B -m parity_harness structure --scope tui --gate ownership
```

## Focused Tests

```powershell
python -m pytest pycodex/tui/tests -q
python -m pytest tests/e2e/tui -q
```

The E2E suite uses deterministic fixtures by default. Native Rust/ConPTY and
live OAuth comparisons are opt-in because they require a local Rust executable
or credentials; their gates are documented in the session checklist.

## Acceptance

A TUI parity claim requires:

1. The owning Rust module and runtime anchor.
2. Rust tests, fixtures, source contract, or stable native behavior.
3. The matching Python owner and Rust-derived tests.
4. Product-path evidence when behavior crosses composer, dispatch, active view,
   history, or terminal rendering boundaries.

Similar screenshots or Python-only tests are not sufficient parity evidence.
