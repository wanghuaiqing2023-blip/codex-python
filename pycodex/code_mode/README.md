# pycodex.code_mode

Rust crate: `codex-code-mode`

Rust anchor: `codex/codex-rs/code-mode`

This package mirrors the public crate interface exported from Rust
`codex-code-mode/src/lib.rs`.

Status: `complete` for the dependency-light Python port.

Implemented module contracts:

- `src/lib.rs` crate-root public constants and re-export surface.
- `src/description.rs` pure description helpers, exec pragma parsing,
  identifier normalization, nested-tool filtering, TypeScript sample/schema
  rendering, namespace grouping, MCP shared type rendering, and deferred-tool
  guidance.
- `src/response.rs` image-detail wire values, `DEFAULT_IMAGE_DETAIL`, and
  function-call output content item tagged shapes.
- `src/runtime/mod.rs` public request/response/outcome model surface:
  execute/wait request shapes, runtime response variants, wait and
  execute-to-pending outcomes, Rust external tagged enum input projection,
  nested tool-call ownership fields, and wait-outcome to runtime-response
  conversion.
- `src/service.rs` dependency-light public service facade: service
  construction, monotonic cell id allocation, missing-cell wait provenance,
  callback result coercion, and terminal execute response forwarding to
  completed execute-to-pending outcomes.
- `src/runtime/value.rs` dependency-light output helpers: text serialization,
  image URL/object/MCP block parsing, `auto`/`low`/`high`/`original` image
  details, invalid-shape error text, and stack-preferring error text.
- `src/runtime/timers.rs` dependency-light timer helpers: set-timeout delay
  normalization, clear-timeout id no-op/error boundaries, fractional
  truncation, and `u64::MAX` clamping.
- `src/runtime/callbacks.rs` dependency-light callback helpers: tool callback
  data parsing, nested tool-call event shaping, text/image/notify/yield event
  projection, and exit sentinel handling.
- `src/runtime/globals.rs` dependency-light global registration projection:
  removed host globals, helper names, `tools` callback-data indexes, and
  ordered `ALL_TOOLS` metadata.
- `src/runtime/module_loader.rs` dependency-light module-loader state/error
  projection: main module origin, unsupported import errors, completion-state
  shapes, exit-sentinel rejection handling, and stack-preferring error text.

Non-blocking runtime notes:

- Concrete `src/service.rs` session control and non-helper `src/runtime/*`
  internals depend on the Rust V8 runtime, Tokio control loop, and live
  isolate lifecycle. Python keeps dependency-light service/callback/value/timer
  global-registration, and module-loader state/error helpers in
  `pycodex.core.tools.code_mode`; the concrete V8 execution runtime remains an
  optional operational/runtime check rather than a crate-completion blocker.
