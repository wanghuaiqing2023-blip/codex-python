# codex-hooks src/registry.rs Status

Rust crate: `codex-hooks`

Rust module: `src/registry.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `HooksConfig` carries the Rust registry configuration shape and default
  values.
- `Hooks::new` registers `legacy_notify` only when `legacy_notify_argv` is
  present, non-empty, and has a non-empty first element.
- `Hooks::new` constructs the engine from the feature flag, trust bypass flag,
  config layer stack, plugin hook sources/warnings, and command shell
  projection.
- `startup_warnings`, preview methods, and run methods delegate to the engine.
- `dispatch` runs after-agent hooks in order, records the aborting hook result,
  and stops before later hooks when `HookResult::FailedAbort` is returned.
- `list_hooks` returns the default outcome when hooks are disabled and forwards
  discovery output when hooks are enabled.
- `command_from_argv` returns `None` for an empty argv or empty program and
  otherwise preserves argv order.

## Rust Evidence

- `codex/codex-rs/hooks/src/registry.rs`
- Registry-visible Rust tests in `codex/codex-rs/hooks/src/engine/mod_tests.rs`
  exercise `list_hooks(...)` for managed and plugin hook entries.
- Source contracts in `Hooks::new`, `Hooks::dispatch`, `list_hooks`, and
  `command_from_argv`.

## Python Evidence

- `tests/test_hooks_registry_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_registry_rs.py -q --tb=short
```

Passed on 2026-06-21 with `7 passed`.
