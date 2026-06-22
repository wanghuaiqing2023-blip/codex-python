# codex-execpolicy-legacy test alignment

Rust crate: `codex-execpolicy-legacy`

Rust path: `codex/codex-rs/execpolicy-legacy`

Python package: `pycodex/execpolicy_legacy`

Status: `complete`

## Module Mapping

- `src/sed_command.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/arg_type.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/arg_matcher.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/valid_exec.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/arg_resolver.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/opt.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/program.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/policy.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/exec_call.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/policy_parser.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/execv_checker.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/main.rs` -> `pycodex/execpolicy_legacy/__init__.py`
- `src/error.rs` -> `pycodex/execpolicy_legacy/__init__.py`

## Rust Behavior Covered

`tests/test_execpolicy_legacy_sed_command_rs.py` covers:

- `tests/suite/parse_sed_command.rs::parses_simple_print_command`
- `tests/suite/parse_sed_command.rs::rejects_malformed_print_command`
- source contract from `src/sed_command.rs` requiring a trailing `p`, one comma,
  and two `u64` numeric bounds.
- `tests/suite/sed.rs::test_sed_reject_dangerous_command` error projection for
  unsafe sed substitution commands.

`tests/test_execpolicy_legacy_arg_type_rs.py` covers:

- `ArgType::Literal` exact-value validation and
  `Error::LiteralValueDidNotMatch`, source-contract derived and tied to
  `tests/suite/literal.rs`.
- `ArgType::{ReadableFile,WriteableFile}` empty-name rejection with
  `Error::EmptyFileName`.
- `ArgType::PositiveInteger` Rust `u64` validation and nonzero requirement,
  source-contract derived and tied to `tests/suite/head.rs`.
- `ArgType::SedCommand` delegation to `parse_sed_command`.
- `ArgType::might_write_file` returning true only for `WriteableFile` and
  `Unknown`.

`tests/test_execpolicy_legacy_arg_matcher_rs.py` covers:

- `ArgMatcher::cardinality` and `ArgMatcherCardinality::is_exact`.
- `ArgMatcher::arg_type` projection to `ArgType`, including readable varargs
  becoming `ReadableFile` and unverified varargs becoming `Unknown`.
- Rust `UnpackValue` behavior where Starlark strings unpack as
  `ArgMatcher::Literal`.
- Rust variant-name projection for status/debug mapping.

`tests/test_execpolicy_legacy_valid_exec_rs.py` covers:

- `ValidExec::new` defaulting flags/opts to empty vectors, preserving matched
  positional arguments, and copying prioritized system paths.
- `MatchedArg::new` and `MatchedOpt::new` validating through `ArgType` before
  storing index/name/value/type fields.
- `MatchedOpt::name` and `MatchedFlag::new` value-object behavior.
- `ValidExec::might_write_files` checking both matched options and positional
  arguments for write-capable `ArgType` values.
- Rust serde field shape for `ValidExec`, `MatchedArg`, `MatchedOpt`, and
  `MatchedFlag`, including raw `type` fields in serialized mapping output.

`tests/test_execpolicy_legacy_arg_resolver_rs.py` covers:

- `resolve_observed_args_with_patterns` prefix/vararg/suffix matching for
  `ARG_RFILES + ARG_WFILE`, tied to `tests/suite/cp.rs`.
- Zero-or-more varargs accepting no positional args, tied to
  `tests/suite/ls.rs`.
- Prefix plus zero-or-more varargs for the `rg` default policy fixture.
- Propagation of `ArgType` validation errors from `MatchedArg::new`, tied to
  `tests/suite/literal.rs`.
- Resolver errors for `NotEnoughArgs`, `VarargMatcherDidNotMatchAnything`,
  `UnexpectedArguments`, `MultipleVarargPatterns`, and exact-prefix
  `RangeEndOutOfBounds`.

`tests/test_execpolicy_legacy_opt_rs.py` covers:

- `Opt::new` storing option name, metadata, and required state, plus
  `Opt::name`.
- `OptMeta::Flag` and `OptMeta::Value` projections.
- `policy_parser.rs` builtin projections for `flag(name)` and
  `opt(name, type, required=None|Some(true))` without implementing Starlark
  evaluation.
- `ArgMatcher::arg_type` projection when an option is built from matcher input.
- Rust display shape `opt(-a)`.

`tests/test_execpolicy_legacy_program_rs.py` covers:

- `ProgramSpec::new` required-option derivation from allowed option map keys.
- `ProgramSpec::check` option scanning, flags, value options, positional args,
  and `ValidExec` assembly, tied to `tests/suite/{ls,head}.rs`.
- Unknown option, bundled option rejection, missing option value,
  option-followed-by-option, double-dash rejection, and sorted missing required
  options.
- `MatchedExec::{Match, Forbidden}` and `Forbidden::Exec` projections.
- `verify_should_match_list` and `verify_should_not_match_list` result shapes.

`tests/test_execpolicy_legacy_policy_rs.py` covers:

- `Policy::new` forbidden substring regex construction using escaped
  substrings.
- `Policy::check` forbidden program regex and forbidden arg checks before spec
  dispatch.
- Multi-spec selection order and Rust's last-error behavior when all specs
  fail.
- `Error::NoSpecForProgram`.
- `check_each_good_list_individually` and `check_each_bad_list_individually`
  aggregation, tied to `tests/suite/{good,bad}.rs`.

`tests/test_execpolicy_legacy_exec_call_rs.py` covers:

- `ExecCall::new` copying the program and args into owned strings.
- `Display` formatting with one literal space before each arg and no shell
  quoting.
- Rust serde field shape for `program` and `args`.

`tests/test_execpolicy_legacy_policy_parser_rs.py` covers:

- `PolicyParser::new` and `PolicyParser::parse` for the policy DSL shape used
  by current upstream `src/default.policy`.
- ARG constants, `define_program`, `flag`, `opt`, `forbid_substrings`, and
  `forbid_program_regex` builtin behavior.
- Duplicate option-name rejection in `define_program`.
- Extended-dialect policy expression shape used by Rust's
  `Dialect::Extended`/f-string setup: locals, list concatenation, f-string
  strings, positional first argument, and `required=None` defaulting to false.
- `get_default_policy()` reading the upstream Rust `default.policy` fixture and
  producing a policy whose good/bad example lists pass.
- Representative default-policy behavior for `head`, `sed`, and `rg`, tied to
  Rust suite expectations.

`tests/test_execpolicy_legacy_execv_checker_rs.py` covers:

- `ExecvChecker::match` direct delegation to `Policy::check`.
- `ExecvChecker::check` readable/writeable file validation against caller
  supplied canonical folder allow-lists, tied to
  `src/execv_checker.rs::test_check_valid_input_files`.
- `ensure_absolute_path` relative path handling with `cwd`, plus
  `Error::CannotCheckRelativePath` when `cwd` is absent.
- Directory arguments accepted when they are exactly the readable/writeable
  roots, and parent-of-root arguments rejected using component-aware path
  containment.
- `is_executable_file`-driven system-path replacement, preserving the original
  program when no system path qualifies on Unix-like platforms.

`tests/test_execpolicy_legacy_main_rs.py` covers:

- `main.rs::check_command` result classification for safe, match, forbidden,
  and unverified outcomes.
- `MATCHED_BUT_WRITES_FILES_EXIT_CODE`, `MIGHT_BE_SAFE_EXIT_CODE`, and
  `FORBIDDEN_EXIT_CODE` under `--require-safe`.
- Rust-shaped CLI JSON output for `ValidExec`, `ArgType`, `Forbidden`, and
  tagged `Output` variants.
- `Command::CheckJson` JSON decoding and `--policy` file loading through
  `PolicyParser::new(policy_source, file_contents)`.
- `Command::Check` missing-command stderr/exit behavior.

`tests/test_execpolicy_legacy_error_rs.py` covers:

- The complete `src/error.rs` variant inventory and stable `"type"` serde tag
  names for Python projections.
- `CannotCanonicalizePath` display-string error projection shape used by Rust
  `serde_with::DisplayFromStr`.

## Validation

```text
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py tests/test_execpolicy_legacy_opt_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py tests/test_execpolicy_legacy_opt_rs.py tests/test_execpolicy_legacy_program_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py tests/test_execpolicy_legacy_opt_rs.py tests/test_execpolicy_legacy_program_rs.py tests/test_execpolicy_legacy_policy_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py tests/test_execpolicy_legacy_opt_rs.py tests/test_execpolicy_legacy_program_rs.py tests/test_execpolicy_legacy_policy_rs.py tests/test_execpolicy_legacy_exec_call_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py tests/test_execpolicy_legacy_opt_rs.py tests/test_execpolicy_legacy_program_rs.py tests/test_execpolicy_legacy_policy_rs.py tests/test_execpolicy_legacy_exec_call_rs.py tests/test_execpolicy_legacy_policy_parser_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_execv_checker_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py tests/test_execpolicy_legacy_opt_rs.py tests/test_execpolicy_legacy_program_rs.py tests/test_execpolicy_legacy_policy_rs.py tests/test_execpolicy_legacy_exec_call_rs.py tests/test_execpolicy_legacy_policy_parser_rs.py tests/test_execpolicy_legacy_execv_checker_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_main_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_error_rs.py -q --tb=short
python -m pytest tests/test_execpolicy_legacy_sed_command_rs.py tests/test_execpolicy_legacy_arg_type_rs.py tests/test_execpolicy_legacy_arg_matcher_rs.py tests/test_execpolicy_legacy_valid_exec_rs.py tests/test_execpolicy_legacy_arg_resolver_rs.py tests/test_execpolicy_legacy_opt_rs.py tests/test_execpolicy_legacy_program_rs.py tests/test_execpolicy_legacy_policy_rs.py tests/test_execpolicy_legacy_exec_call_rs.py tests/test_execpolicy_legacy_policy_parser_rs.py tests/test_execpolicy_legacy_execv_checker_rs.py tests/test_execpolicy_legacy_main_rs.py tests/test_execpolicy_legacy_error_rs.py -q --tb=short
```

## Runtime Notes

- Full Starlark runtime compatibility beyond the current upstream
  `default.policy` DSL shape is a dependency-heavy implementation difference,
  not an open module-local behavior gap for the active Python port.
