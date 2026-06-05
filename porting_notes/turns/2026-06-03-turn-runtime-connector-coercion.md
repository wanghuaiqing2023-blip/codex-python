# Core turn-runtime connector coercion normalization

## Goal segment
- Preserve upstream-compatible behavior on the core user-turn execution path while keeping parsing and model-sampling behavior stable.

## Decision
- Move connector coercion support for object-like connectors into `pycodex/core/connectors.py`.
- Keep `turn_runtime` focused on orchestration and avoid duplicating connector normalization logic.

## Rationale
- Several tests and likely runtime callers pass `SimpleNamespace` connectors to `with_app_enabled_state`.
- Previous logic could reject these because `AppInfo.from_mapping` requires a mapping.
- Centralizing coercion in `_coerce_app_info` aligns with Rust-like ownership of connector parsing responsibilities and avoids future drift in other call sites.

## Compatibility behavior
- Accept object inputs by:
  - using `to_mapping()` when available and mapping-like, else
  - reading `__dict__`/public attributes (including `id`, `name`, `description`, `labels`, `is_enabled`, etc.),
  - constructing an `AppInfo`-compatible mapping with reasonable `id`/`name` fallback.
- Behavior remains unchanged for existing mapping-based connectors.
