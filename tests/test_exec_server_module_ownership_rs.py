import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("client", "ExecServerClient"),
        ("client.http_client.response_body_stream", "HttpResponseBodyStream"),
        ("client.http_client.reqwest_http_client", "ReqwestHttpClient"),
        ("client.http_client.rpc_http_client", "HTTP_BODY_DELTA_CHANNEL_CAPACITY"),
        ("client_api", "ExecServerClientConnectOptions"),
        ("client_transport", "ENVIRONMENT_CLIENT_NAME"),
        ("connection", "JsonRpcConnection"),
        ("environment", "Environment"),
        ("environment_provider", "EnvironmentDefault"),
        ("environment_toml", "EnvironmentToml"),
        ("environment_toml.option_duration_secs", "deserialize"),
        ("fs_helper", "FsHelperRequest"),
        ("fs_helper_main", "main"),
        ("fs_sandbox", "FileSystemSandboxRunner"),
        ("local_file_system", "DirectFileSystem"),
        ("local_process", "LocalProcess"),
        ("process", "ExecProcess"),
        ("process_id", "ProcessId"),
        ("protocol", "ExecParams"),
        ("protocol.base64_bytes", "serialize"),
        ("relay", "run_multiplexed_environment"),
        ("relay_proto.generated", "RelayMessageFrame"),
        ("relay_proto.generated.relay_message_frame", "Body"),
        ("remote", "EnvironmentRegistryClient"),
        ("remote_file_system", "RemoteFileSystemBoundary"),
        ("remote_process", "RemoteExecProcess"),
        ("rpc", "RpcClient"),
        ("runtime_paths", "ExecServerRuntimePaths"),
        ("sandboxed_file_system", "SandboxedFileSystem"),
        ("server", "run_main"),
        ("server.file_system_handler", "FileSystemHandler"),
        ("server.handler", "ExecServerHandler"),
        ("server.process_handler", "ProcessHandler"),
        ("server.processor", "ConnectionProcessor"),
        ("server.registry", "build_router"),
        ("server.session_registry", "SessionRegistry"),
        ("server.transport", "ExecServerListenTransport"),
    ],
)
def test_exec_server_item_has_rust_aligned_owner(
    module_name: str, symbol: str
) -> None:
    """Rust source: codex-exec-server module graph rooted at src/lib.rs."""
    module = importlib.import_module(f"pycodex.exec_server.{module_name}")
    item = getattr(module, symbol)
    if callable(item):
        assert item.__module__ == module.__name__


def test_crate_root_reexports_rust_public_surface() -> None:
    root = importlib.import_module("pycodex.exec_server")
    client = importlib.import_module("pycodex.exec_server.client")
    process = importlib.import_module("pycodex.exec_server.process")
    protocol = importlib.import_module("pycodex.exec_server.protocol")

    assert root.ExecServerClient is client.ExecServerClient
    assert root.ExecProcess is process.ExecProcess
    assert root.ExecParams is protocol.ExecParams

