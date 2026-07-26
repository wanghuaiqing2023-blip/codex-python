# codex-python

Python port of OpenAI Codex, aligned to the vendored Rust implementation in
`codex/`.

## Project Rules

Rust is the behavioral source of truth. Changes should preserve the Rust crate,
module, item, test, and Python counterpart relationship instead of introducing
Python-only shortcuts.

- Repository instructions: [AGENTS.md](AGENTS.md)
- Porting methodology: [PORTING_PROJECT_PRINCIPLES.md](PORTING_PROJECT_PRINCIPLES.md)
- Current snapshot: [PORTING_STATUS.md](PORTING_STATUS.md)
- Crate structure entry point: [CRATE_COMPLETION_STATUS.md](CRATE_COMPLETION_STATUS.md)
- Non-workspace Rust packages: [PORTING_NON_WORKSPACE_RUST_PACKAGES.md](PORTING_NON_WORKSPACE_RUST_PACKAGES.md)

## Layout

| Path | Purpose |
| --- | --- |
| `codex/` | Fixed upstream Rust reference |
| `pycodex/` | Python implementation |
| `tests/` | Unit, integration, and E2E tests |
| `parity_harness/` | Independent executable architecture contracts |

## Run

```powershell
python -m pycodex
python -m pycodex exec "say hello"
```

## Architecture Checks

```powershell
python -B -m parity_harness workspace check
python -B -m parity_harness contract validate-accepted --scope all
python -B -m parity_harness structure --scope all --gate ownership
python -B -m parity_harness audit
```

Generated contract candidates are review artifacts. Accepted ownership lives
under `parity_harness/contracts/accepted/` and must not be overwritten by a
generator.

## Tests

```powershell
python -m pytest -q
python -m pytest tests/e2e -q
```

Some native Rust/ConPTY E2E tests require explicit environment gates. See
[TUI_RUST_TEST_PARITY.md](TUI_RUST_TEST_PARITY.md) and
[TUI_SESSION_REGRESSION_CHECKLIST.md](TUI_SESSION_REGRESSION_CHECKLIST.md).

## Reference Material

The root OpenAI and Anthropic reference articles are retained as methodology
references. They do not replace Rust source, executable contracts, or tests as
parity evidence.
