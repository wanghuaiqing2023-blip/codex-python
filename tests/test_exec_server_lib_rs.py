"""Rust-derived tests for ``codex-exec-server/src/lib.rs``."""

from __future__ import annotations

import pycodex.exec_server as exec_server


def test_crate_root_reexports_rust_public_facade() -> None:
    # Rust crate/module: codex-exec-server/src/lib.rs
    # Contract: crate root publicly re-exports the sibling module APIs used by
    # codex-core and app-server-client.
    rust_public_exports = {
        "CODEX_EXEC_SERVER_URL_ENV_VAR",
        "CODEX_FS_HELPER_ARG1",
        "CopyOptions",
        "CreateDirectoryOptions",
        "DEFAULT_LISTEN_URL",
        "DefaultEnvironmentProvider",
        "Environment",
        "EnvironmentManager",
        "EnvironmentProvider",
        "ExecBackend",
        "ExecClosedNotification",
        "ExecEnvPolicy",
        "ExecExitedNotification",
        "ExecOutputDeltaNotification",
        "ExecOutputStream",
        "ExecParams",
        "ExecProcess",
        "ExecProcessEvent",
        "ExecProcessEventReceiver",
        "ExecResponse",
        "ExecServerClient",
        "ExecServerClientConnectOptions",
        "ExecServerError",
        "ExecServerListenUrlParseError",
        "ExecServerRuntimePaths",
        "ExecutorFileSystem",
        "FileMetadata",
        "FileSystemResult",
        "FileSystemSandboxContext",
        "FsCopyParams",
        "FsCopyResponse",
        "FsCreateDirectoryParams",
        "FsCreateDirectoryResponse",
        "FsGetMetadataParams",
        "FsGetMetadataResponse",
        "FsReadDirectoryEntry",
        "FsReadDirectoryParams",
        "FsReadDirectoryResponse",
        "FsReadFileParams",
        "FsReadFileResponse",
        "FsRemoveParams",
        "FsRemoveResponse",
        "FsWriteFileParams",
        "FsWriteFileResponse",
        "HttpClient",
        "HttpHeader",
        "HttpRequestBodyDeltaNotification",
        "HttpRequestParams",
        "HttpRequestResponse",
        "HttpResponseBodyStream",
        "InitializeParams",
        "InitializeResponse",
        "LOCAL_ENVIRONMENT_ID",
        "LOCAL_FS",
        "LocalFileSystem",
        "ProcessId",
        "ProcessOutputChunk",
        "REMOTE_ENVIRONMENT_ID",
        "ReadDirectoryEntry",
        "ReadParams",
        "ReadResponse",
        "RemoteEnvironmentConfig",
        "RemoteExecServerConnectArgs",
        "RemoveOptions",
        "ReqwestHttpClient",
        "StartedExecProcess",
        "TerminateParams",
        "TerminateResponse",
        "WriteParams",
        "WriteResponse",
        "WriteStatus",
        "run_fs_helper_main",
        "run_main",
        "run_remote_environment",
    }

    assert rust_public_exports <= set(exec_server.__all__)
    for name in rust_public_exports:
        assert hasattr(exec_server, name), name


def test_crate_root_reexport_identity_for_cross_module_anchors() -> None:
    # Rust crate/module: codex-exec-server/src/lib.rs
    # Contract: public names are canonical crate-root exports, not alternate
    # compatibility aliases with different behavior.
    assert exec_server.ExecServerClient.__module__ == "pycodex.exec_server"
    assert exec_server.ExecServerRuntimePaths.__module__ == "pycodex.exec_server"
    assert exec_server.ProcessId.__module__ == "pycodex.exec_server"
    assert exec_server.ReqwestHttpClient.__module__ == "pycodex.exec_server"
    assert exec_server.HttpResponseBodyStream.__module__ == "pycodex.exec_server"
    assert isinstance(exec_server.LOCAL_FS, exec_server.LocalFileSystem)


def test_crate_root_reexported_constants_match_rust_values() -> None:
    # Rust crate/module: codex-exec-server/src/lib.rs re-exporting constants
    # from environment, fs_helper, and server modules.
    assert exec_server.CODEX_EXEC_SERVER_URL_ENV_VAR == "CODEX_EXEC_SERVER_URL"
    assert exec_server.CODEX_FS_HELPER_ARG1 == "--codex-run-as-fs-helper"
    assert exec_server.LOCAL_ENVIRONMENT_ID == "local"
    assert exec_server.REMOTE_ENVIRONMENT_ID == "remote"
    assert exec_server.DEFAULT_LISTEN_URL == "ws://127.0.0.1:0"
