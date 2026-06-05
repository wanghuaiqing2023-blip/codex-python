# PORTING_PROJECT_PRINCIPLES.md

Updated: 2026-06-05

This document records the highest-level porting principles for the Rust Codex
to PyCodex migration. It supersedes earlier mainline-first and function-table
thinking when those conflict with the principles below.

## 1. Project Mission

PyCodex is a behavior-preserving Python port of the upstream Rust Codex project.

The goal is not to translate Rust code line by line. The goal is to preserve
the core logic, public behavior, data contracts, error semantics, and common
user-facing experience of Rust Codex in a Python implementation.

Python implementation should remain dependency-light. Prefer the Python
standard library unless a dependency is clearly necessary and approved.

## 2. Source Of Truth

Rust Codex is the behavioral source of truth.

The authoritative evidence order is:

| Level | Evidence | Purpose |
|---|---|---|
| A | Cargo workspace and crate `Cargo.toml` files | crate boundaries and direct crate dependencies |
| B | Rust `mod`, `pub mod`, `use`, and `pub use` declarations | crate-internal module structure and visibility |
| C | Rust public APIs, important internal items, trait impls, and runtime registration points | behavior contracts and dynamic anchors |
| D | Rust unit tests, integration tests, fixtures, and generated outputs | behavioral verification |
| E | knowledge graph | navigation aid only |

Knowledge graphs are useful indexes. They are not final authority for behavior
or dependency claims.

## 3. Alignment Coordinates

The alignment target is the whole Rust code tree, not only one execution
mainline.

Use this coordinate system:

```text
Rust workspace
  -> Rust crate
    -> Rust module
      -> Rust item/function/type
        -> Rust tests
          -> Python package/module/item/test
```

This gives both humans and AI a stable shared map.

Important distinction:

```text
containment structure = mostly a tree
dependency structure = directed graph
runtime dispatch = dynamic graph
```

Do not collapse these into a single mainline.

## 4. Crate, Module, And Behavior Contract

A Rust crate is a precise Cargo dependency unit. It is not automatically a
single behavior module.

A Rust module is a language-level namespace declared by `mod` or `pub mod`.
It is usually the best default boundary for behavior alignment, but it is not
automatically the final behavior boundary.

The regular minimum alignment and acceptance unit is:

```text
module-scoped behavior contract
```

In practical terms:

```text
crate decides ownership and dependency context
module provides the default alignment boundary
behavior contract defines what must be preserved
function/type names provide local anchors
tests provide evidence
```

Function-level alignment is allowed for pure functions, public APIs, or small
well-tested units, but it is not the default minimum unit. Whole-crate alignment
is usually too coarse.

## 5. Mainline Role

Execution mainlines are validation paths, not the primary architecture source.

Correct use:

```text
mainline discovers runtime gaps
module contracts solve the gaps
mainline validates module collaboration
```

Incorrect use:

```text
follow the mainline and implement whatever appears next
```

The earlier mainline-first approach helped expose reachable behavior, but it
must not define module boundaries or final porting scope by itself.

## 6. Python Structure Should Carry Alignment Information

Where practical, Python directory and file structure should encode the Rust
counterpart structure.

Recommended pattern:

```text
pycodex/<package>/
  README.md
  <module>.py
```

Each package README should identify:

```text
Rust crate
Rust path
Rust modules covered
Python modules implementing them
alignment unit
known gaps
test sources
```

This makes the repository itself a shared context map for both human reviewers
and AI agents.

Python structure should not mechanically copy Rust structure. Rust modules may
be merged or split in Python when that is more idiomatic, but the reorganization
must be documented close to the code.

## 7. Tests And Evidence

Testing should primarily reuse or derive from Rust's own tests.

Preferred test source order:

| Priority | Source | Use |
|---|---|---|
| 1 | Rust unit tests in `#[cfg(test)] mod tests` or `src/*_tests.rs` | Python parity tests |
| 2 | Rust integration tests in `tests/` or `tests/suite/` | Python integration tests |
| 3 | Rust source behavior contracts | inferred parity tests |
| 4 | targeted golden tests | selected stable modules with serializable input/output |
| 5 | Python regression and project-policy tests | protect local implementation choices |

Python tests should include source comments when possible:

```python
# Source: rust_test_migrated
# Rust crate: codex-shell-command
# Rust module: src/parse_command.rs
# Rust test: tests::quoted_command_is_parsed_correctly
# Contract: shell.display.parse
```

Tests written only from Python behavior must not be treated as Rust parity
proof unless they are tied back to Rust source, Rust tests, or a documented
behavior contract.

## 8. Golden Tests

Golden tests are useful but not the default first step.

A golden test means:

```text
a specific Rust Codex version acts as the reference body
the Rust implementation produces expected output for controlled input
Python must match that expected output after normalization
```

Golden output is not eternal truth. It is a versioned behavior snapshot.

Golden tests are best for stable, serializable modules such as:

```text
shell command parsing
exec policy decisions
protocol serialization
config override parsing
apply_patch parsing
event mapping
tool name normalization
```

Golden tests are expensive for complex runtime paths because they often require
Rust harnesses, controlled environment setup, mock model providers, or output
normalization. Therefore, prefer Rust test migration first and use targeted
golden tests only where they provide high value.

## 9. Legacy Ledgers

Earlier ledgers such as `PORTING_ALIGNMENT_LEDGER.md` and
`PORTING_FUNCTION_MAPPING.md` were created before this strategy was settled.

They may contain useful historical notes, but they are deprecated and must not
be treated as authoritative alignment sources.

Future authoritative alignment information should be organized as:

```text
crate/module dependency map
module-scoped behavior contracts
Python package README mapping files
test source comments
```

## 10. Future Work Standard

Before implementing or judging a porting task, answer:

```text
Which Rust crate owns this behavior?
Which Rust module defines the behavior boundary?
Which Rust public API or important internal item anchors it?
Which Rust tests or fixtures describe the behavior?
Which Python package/module should carry it?
Which Python tests prove parity?
```

If these cannot be answered, the task is not yet well-scoped.

This rule is intended to reduce repeated scanning, avoid accidental duplicate
implementations, and keep behavior differences local and explainable.
