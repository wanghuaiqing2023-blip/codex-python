# PyCodex Alignment Structure

This package is the Python implementation target for the Rust Codex port.

The Python tree should provide a stable context map for both human reviewers
and AI agents. It should mirror the Rust code tree as an alignment coordinate
system, but it must not mechanically copy every Rust file or helper function.

## Alignment Coordinate System

Use this structure when locating or adding Python code:

```text
Rust workspace
  -> Rust crate
    -> Rust module
      -> Rust item/function/type
        -> Rust tests
          -> Python package/module/item/test
```

The regular acceptance unit is a module-scoped behavior contract:

```text
crate decides ownership and dependency context
module provides the default alignment boundary
behavior contract defines what must be preserved
function/type names provide local anchors
tests provide evidence
```

## Python Package Domains

Current and intended package domains:

| Python package | Rust counterpart | Role |
|---|---|---|
| `pycodex.protocol` | `codex-protocol` | Shared data contracts, protocol models, tool names, request/response shapes |
| `pycodex.config` | `codex-config` | Config loading, overrides, policy-facing config structures |
| `pycodex.execpolicy` | `codex-execpolicy` | Command policy decisions, rule matching, approval requirement rendering |
| `pycodex.apply_patch` | `codex-apply-patch` | Patch grammar, parsing, conversion, and apply_patch tool behavior |
| `pycodex.core` | `codex-core` | Agent runtime, turn loop, tool dispatch, event mapping, context assembly |
| `pycodex.exec` | `codex-exec` | Non-interactive exec entrypoint and exec-specific orchestration |
| `pycodex.cli` | `codex-cli` | Top-level command parsing, command dispatch, CLI compatibility shims |
| `pycodex.login` | `codex-login` | Public login/auth import surface and future non-CLI auth behavior home |
| `pycodex.sandboxing` | `codex-sandboxing` | Public sandboxing import surface and future sandboxing behavior home |
| `pycodex.shell_command` | `codex-shell-command` | Shell command parsing, display summaries, safety classification |
| `pycodex.utils_cli` | `codex-utils-cli` and related utility crates | CLI helper behavior |

## Compatibility Shims And Transitional Packages

Some root-level modules remain only to preserve historical import surfaces while
the real implementation is grouped into domain packages:

| Canonical path | Rust counterpart | Status |
|---|---|---|
| `pycodex.config.toml_compat` | `codex-config` support surface | canonical TOML compatibility helper; legacy `pycodex._toml` removed |
| `pycodex.tui` | `codex-tui` | canonical TUI package; legacy root file and CLI submodule removed |

Some domain packages currently act as compatibility packages while deeper code
is still being moved:

| Domain package | Current implementation source | Reason |
|---|---|---|
| `pycodex.login` | `pycodex.cli.login` | Rust has a separate `codex-login` crate; non-CLI auth behavior should eventually live here |
| `pycodex.sandboxing` | `pycodex.core.tool_sandboxing` plus `pycodex.protocol` | Rust has a separate `codex-sandboxing` crate; deeper sandboxing behavior needs a focused alignment pass |
| `pycodex.apply_patch` | `pycodex.apply_patch` | preserve historical core import while apply_patch becomes its own domain package |
| `pycodex.execpolicy` | `pycodex.execpolicy` | preserve historical core import while execpolicy becomes its own domain package |

Future packages may be introduced when the Rust tree justifies them:

```text
pycodex.apply_patch
pycodex.model_provider
pycodex.app_server
pycodex.rollout
pycodex.state
pycodex.extensions
pycodex.platform
```

Do not create a package only because a Rust crate exists. Create or split a
Python package when it improves behavior ownership, dependency clarity, or test
locality.

## Directory README Rule

Each substantial Python package should contain a `README.md` that records:

```text
Rust crate
Rust path
Rust modules covered
Python modules implementing them
alignment unit
Rust test sources
Python test sources
known gaps
```

These README files are local alignment maps. They should stay close to the code
so future debugging starts from the correct Rust source and Rust tests.

## Movement Rule

Do not move existing implementation files in bulk.

Preferred sequence:

```text
1. Add or update the package README.
2. Identify the Rust crate and module evidence.
3. Identify existing Python files and tests.
4. Move only one low-risk module group at a time.
5. Update imports in the same slice.
6. Add Rust-derived test source comments where tests are touched.
```

Full-tree alignment is the strategy. Incremental movement is the execution
method.
