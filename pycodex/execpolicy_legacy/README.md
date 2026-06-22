# pycodex.execpolicy_legacy

Rust crate: `codex-execpolicy-legacy`

Rust anchor: `codex/codex-rs/execpolicy-legacy`

Status: `complete`

Implemented module contracts:

- `src/sed_command.rs`: safe sed print-command parser for commands shaped like
  `122,202p`, with Rust-shaped `SedCommandNotProvablySafe` errors.
- `src/arg_type.rs`: `ArgType` literal/file/positive-integer/sed validation
  and `might_write_file` behavior, with Rust-shaped error projections for
  literal mismatch, empty file names, invalid positive integers, and unsafe sed
  commands.
- `src/arg_matcher.rs`: `ArgMatcher` variant cardinality, matcher-to-arg-type
  projection, Starlark string-to-literal unpacking, and Rust variant-name
  projection.
- `src/valid_exec.rs`: `ValidExec`, `MatchedArg`, `MatchedOpt`, and
  `MatchedFlag` accepted-exec value objects, including constructor validation,
  write-side-effect detection, and Rust-shaped serialized field names.
- `src/arg_resolver.rs`: positional argument resolution against exact and
  vararg `ArgMatcher` patterns, including prefix/vararg/suffix partitioning and
  Rust-shaped resolver error projections.
- `src/opt.rs`: `Opt` and `OptMeta` command-line option value objects, including
  flag/value metadata, required-option state, Rust display shape, and
  policy-builtin constructor projections.
- `src/program.rs`: `ProgramSpec` option/argument checking, matched/forbidden
  exec projections, required option validation, and example-list verification.
- `src/policy.rs`: policy-level forbidden program/argument matching, program
  spec selection, last-error behavior, and good/bad example aggregation.
- `src/exec_call.rs`: `ExecCall` value object construction, display string, and
  Rust serde-shaped field projection.
- `src/policy_parser.rs`: dependency-light policy DSL parser for the current
  upstream default-policy shape, including `define_program`, `flag`, `opt`,
  forbidden helpers, ARG constants, duplicate option detection, and
  `get_default_policy()`.
- `src/execv_checker.rs`: `ExecvChecker` policy delegation, readable/writeable
  path allow-list validation after cwd-based absolutization, relative-path
  rejection without cwd, and platform-shaped system-path executable selection.
- `src/main.rs`: CLI classification wrapper for `check` and `check-json`,
  Rust-shaped `safe`/`match`/`forbidden`/`unverified` JSON output, custom
  policy loading, and `--require-safe` exit-code behavior.
- `src/error.rs`: all Rust `Error` variants have Python projections with
  stable Rust-style `"type"` discriminants.

Runtime note:

- Full Starlark runtime compatibility beyond the current default-policy DSL
  shape is intentionally not implemented in the dependency-light Python port.
  The Rust-owned current policy DSL, builtins, default policy fixture, CLI
  wrapper, path validation, and error surface are covered by Rust-derived
  tests.
