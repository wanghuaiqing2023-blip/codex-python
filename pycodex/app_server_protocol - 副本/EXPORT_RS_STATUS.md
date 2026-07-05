# export.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/export.rs`

Python module: `pycodex/app_server_protocol/export.py`

Status: complete candidate for the Python-carryable export contract.

## Covered

- Public generation surface: `GenerateTsOptions`, `generate_types`,
  `generate_ts`, `generate_ts_with_options`, `generate_json`,
  `generate_json_with_experimental`, and `generate_internal_json_schema`.
- TypeScript post-processing helpers for generated headers, `index.ts`
  contents, trailing whitespace trimming, top-level splitting, type-alias and
  interface field parsing, experimental client-request method filtering, and
  experimental field removal.
- JSON schema post-processing helpers for experimental field/method pruning,
  namespace map detection, definition/reference rewrites, missing-definition
  validation, v2 flattening, discriminator title annotation, and generated type
  removal.
- Deterministic file helpers for TypeScript/JSON discovery and pretty JSON
  writing.

## Intentional Adaptations

- Rust uses `ts-rs` and `schemars` derive macros to emit TypeScript and JSON
  schemas. Python does not reimplement those macro systems; generation
  entrypoints require injected callbacks and raise `NotImplementedError`
  without one.
- Experimental client method/type constants are macro-produced in Rust protocol
  modules. Python export helpers accept explicit method/type inputs and use the
  Python `experimental_api` registry for field metadata.
- Internal helper APIs are exposed from `pycodex.app_server_protocol.export`
  for focused parity validation, while the package root re-exports only the
  Rust crate-root public generation surface.

## Validation

- Light validation only: `py_compile` plus focused export helper smoke.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
