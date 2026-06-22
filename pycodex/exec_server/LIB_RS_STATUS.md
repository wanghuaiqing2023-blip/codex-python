# codex-exec-server/src/lib.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/lib.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

Rust `src/lib.rs` owns the crate-root module declarations and public facade.
It does not define runtime behavior directly; it re-exports sibling module
types, constants, traits, and entrypoints for downstream crates such as
`codex-core` and `codex-app-server-client`.

The Python port mirrors the crate-root facade by exposing the Rust `pub use`
surface at package root and pinning it in `__all__`:

- client exports: `ExecServerClient`, `ExecServerError`,
  `HttpResponseBodyStream`, and `ReqwestHttpClient`;
- client API exports: `ExecServerClientConnectOptions`, `HttpClient`, and
  `RemoteExecServerConnectArgs`;
- filesystem exports: `CopyOptions`, `CreateDirectoryOptions`,
  `ExecutorFileSystem`, `FileMetadata`, `FileSystemResult`,
  `FileSystemSandboxContext`, `ReadDirectoryEntry`, and `RemoveOptions`;
- environment exports: `CODEX_EXEC_SERVER_URL_ENV_VAR`, `Environment`,
  `EnvironmentManager`, `LOCAL_ENVIRONMENT_ID`, `REMOTE_ENVIRONMENT_ID`,
  `DefaultEnvironmentProvider`, and `EnvironmentProvider`;
- fs-helper exports: `CODEX_FS_HELPER_ARG1` and `run_fs_helper_main`;
- process exports: `ExecBackend`, `ExecProcess`, `ExecProcessEvent`,
  `ExecProcessEventReceiver`, `StartedExecProcess`, and `ProcessId`;
- protocol exports for process, filesystem, HTTP, initialize, and notification
  dataclasses/enums;
- remote/runtime/server exports: `RemoteEnvironmentConfig`,
  `run_remote_environment`, `ExecServerRuntimePaths`, `DEFAULT_LISTEN_URL`,
  `ExecServerListenUrlParseError`, and `run_main`.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/lib.rs`
- Python module: `pycodex/exec_server/__init__.py`
- Python tests: `tests/test_exec_server_lib_rs.py`

## Validation

```text
python -m pytest tests/test_exec_server_lib_rs.py -q --tb=short
3 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_lib_rs.py

$files = Get-ChildItem tests -Filter 'test_exec_server_*.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short
254 passed, 1 skipped
```

Crate-level note: `codex-exec-server` is complete for the dependency-light
Python port. Concrete Axum/tungstenite websocket runtime identity, rendezvous
service integration, exact reqwest custom-CA/TLS timing, Windows
ConPTY/job-object process-tree behavior, and unbounded live remote/runtime
orchestration remain optional operational checks, not crate-completion
blockers.
