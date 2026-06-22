# codex-stdio-to-uds src/main.rs status

Rust coordinate: `codex/codex-rs/stdio-to-uds/src/main.rs`

Python coordinate: `pycodex/stdio_to_uds/__init__.py`

Status: `complete`

Behavior contract:

- use the process argument list after argv[0].
- when no socket path is provided, print
  `Usage: codex-stdio-to-uds <socket-path>` to stderr and exit with status 1.
- when more than one argument is provided, print
  `Expected exactly one argument: <socket-path>` to stderr and exit with
  status 1.
- otherwise treat the single argument as the socket path, without option
  parsing, and invoke the library `run` entrypoint.

Evidence:

- `main` mirrors the binary argument count checks and delegates to `run`.
- Dash-prefixed socket paths remain positional arguments, matching Rust's
  `env::args_os().skip(1)` behavior rather than a CLI option parser.

Validation:

- `tests/test_stdio_to_uds_crate.py` covers argument errors, dash-prefixed
  positional paths, and the Rust integration relay behavior where Unix domain
  sockets are available.
