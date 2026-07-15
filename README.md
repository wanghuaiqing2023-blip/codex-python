# codex-python

Python-first port of OpenAI Codex core runtime.

## Mission

This repository ports the upstream `codex/` implementation into Python with behavior-first parity.
The goal is not a wrapper around the Rust binary, but a Python implementation whose
interfaces, wire formats, and user-visible behavior stay as close as possible.

## Scope

- Port core runtime, CLI, protocol, config, and execution behavior first.
- Keep dependencies minimal; prefer the Python standard library.
- Delay non-core extension layers (MCP/plugin/marketplace/telemetry) until core
  paths are stable.

## What this repository contains

- `codex/` — upstream reference implementation.
- `pycodex/` — Python port.
- `tests/` — parity-focused unit/integration tests.
- `PORTING_STATUS.md` — high-level progress summary.
- `AGENTS.md` — repository instructions and active porting priorities.

## Tech choices

- Runtime code is implemented with standard library modules first (`argparse`, `asyncio`, `dataclasses`, `enum`, `json`, `logging`, `pathlib`, `subprocess`, `typing`, `unittest`, etc.).
- External dependencies are added only when parity cannot be achieved safely/cleanly with stdlib.

## Core architecture mapping

| Upstream reference | Python target |
|---|---|
| `codex/codex-rs/cli` | `pycodex.cli` |
| `codex/codex-rs/core` | `pycodex.core` |
| `codex/codex-rs/protocol` | `pycodex.protocol` |
| `codex/codex-rs/shell-command` | `pycodex.shell_command` |
| `codex/codex-rs/exec` | `pycodex.exec` |
| `codex/codex-rs/login` | `pycodex.login` |

## Quick start

Install and run with the project environment you already use for this repo.

```bash
python -m pycodex --help
```

For non-interactive execution:

```bash
python -m pycodex exec "echo hello"
```

To run core-path smoke suites during porting:

```bash
python -m unittest tests.test_core_smoke_suite tests.test_local_http_core_smoke_suite
python -m unittest discover -s tests -p "*smoke*.py"
```

To run tests:

```bash
python -m unittest discover -s tests
```

## Current progress (snapshot)

- CLI parse/config/protocol foundation is in place.
- Command surface and escalation/client/server flow are being iteratively filled to match Rust parity.
- Shell/socket escalation helpers and super-exec FD transport are actively being aligned.
- `README` and docs are maintained to match current implementation status (not future roadmap).

## Development workflow

1. Read the upstream Rust behavior in `codex/` first.
2. Implement a behavior-focused Python slice in `pycodex/`.
3. Add/update tests in `tests/`.
4. Record meaningful module-status changes in `PORTING_STATUS.md`. Keep
   durable implementation evidence in the owning module's `README.md`,
   Rust-derived tests, or a focused alignment document.

## Notes

- The upstream knowledge graph at `codex/.understand-anything/knowledge-graph.json` is used as a navigation aid to reduce broad source scans.
- This is an ongoing migration project; some areas are intentionally marked as partial/stubs until their dependencies are ready.
- For full instructions, check [AGENTS.md](AGENTS.md).
## Minimal smoke check for first `codex exec`

The default Python `codex exec` path is aligned with upstream Rust's
in-process `codex-exec` runtime. With ChatGPT OAuth already configured:

```bash
python -m pycodex exec "say hello"
```

On Windows PowerShell:

```powershell
python -m pycodex exec "say hello"
```

Expectations:

- Command exits successfully with non-empty output.
- No app-server socket is required for the default exec path.
- ChatGPT OAuth auth uses the ChatGPT Codex backend when no API-key env var is
  selected for the process.

## Minimal smoke check for the explicit local HTTP path

If `PYCODEX_EXEC_LOCAL_HTTP=1` and no app-server is used, run:

```bash
export OPENAI_API_KEY=...
export PYCODEX_EXEC_LOCAL_HTTP=1
python -m pycodex exec "say hello"
```

On Windows PowerShell:

```powershell
$env:OPENAI_API_KEY = "..."
$env:PYCODEX_EXEC_LOCAL_HTTP = "1"
python -m pycodex exec "say hello"
```

Expectations:

- Command exits successfully with non-empty output.
- Request is sent to `/responses` endpoint with `Authorization: Bearer ...` header.
- `x-codex-installation-id` and `x-codex-window-id` are present in request headers.
- Output path is parsed from response body and rendered as plain text.

