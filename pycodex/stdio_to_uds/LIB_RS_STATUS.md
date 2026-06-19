# codex-stdio-to-uds src/lib.rs status

Rust coordinate: `codex/codex-rs/stdio-to-uds/src/lib.rs`

Python coordinate: `pycodex/stdio_to_uds/__init__.py`

Status: `complete`

Behavior contract:

- connect to the Unix domain socket at the requested path.
- relay stdin to the socket and socket output to stdout concurrently.
- flush stdout after socket output reaches EOF.
- wrap stdin-to-socket copy failures with a focused copy error.
- after stdin EOF, half-close the socket writer and ignore only the benign
  `NotConnected` shutdown race described by the Rust source.
- wrap connection and relay failures with user-facing context.

Evidence:

- `run` maps the public async library entrypoint.
- `_connect_unix_socket` mirrors the UDS connect boundary and connection error
  context.
- `_copy_file_to_writer` mirrors the stdin-to-socket copy loop and copy failure
  context.
- `_shutdown_socket_writer` mirrors the Rust shutdown handling that tolerates
  `ErrorKind::NotConnected` while surfacing other shutdown errors.

Validation:

- Deferred by project policy until all `codex-stdio-to-uds` functional modules
  are complete. Remaining module: `src/main.rs`.
