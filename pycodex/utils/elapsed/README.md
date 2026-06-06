# pycodex.utils.elapsed

Python counterpart for the Rust `codex-utils-elapsed` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-elapsed
Rust path: codex/codex-rs/utils/elapsed
Cargo role: compact human-readable duration formatting
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/elapsed/__init__.py` | crate public `format_duration` helper and inline tests |

## Alignment Unit

The acceptance unit is a pure formatting behavior contract:

```text
utils.elapsed.subsecond_millis
utils.elapsed.seconds_two_decimals
utils.elapsed.minutes_zero_padded_seconds
utils.elapsed.duration_millis_truncation
```

## Current Status

Status: module_completed_with_focused_validation.

The Python implementation accepts `datetime.timedelta` as the standard-library
counterpart to Rust `std::time::Duration`, truncates to whole milliseconds like
`Duration::as_millis`, and applies the same three output bands:

```text
< 1 s   -> {milli}ms
< 60 s  -> {sec:.2}s
>= 60 s -> {min}m {sec:02}s
```

Python rejects negative timedeltas as an invalid boundary because Rust
`Duration` is non-negative by construction.

## Test Sources

Primary Python parity tests:

```text
tests/test_utils_elapsed.py
```

Rust source/test anchors:

```text
codex/codex-rs/utils/elapsed/src/lib.rs
```

## Stop Rule

This module contract is complete once `tests/test_utils_elapsed.py` passes.
Do not expand this package into runtime timing, telemetry, or TUI separator
formatting unless a future module slice explicitly targets those owners.
