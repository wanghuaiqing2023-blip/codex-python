from __future__ import annotations

from pathlib import Path
import json
import sys

from pycodex.app_server_protocol.jsonrpc_lite import JSONRPCErrorError
from pycodex.exec_server import (
    CODEX_FS_HELPER_ARG1,
    ExecServerRuntimePaths,
    FS_WRITE_FILE_METHOD,
    FileSystemSandboxContext,
    FsSandboxCommandOutput,
    FsHelperPayload,
    FsHelperResponse,
    FsWriteFileParams,
    FsWriteFileResponse,
    FsHelperRequest,
    FsSandboxExecRequest,
    FileSystemSandboxRunner,
    add_helper_runtime_permissions,
    helper_env_from_vars,
    helper_env_key_is_allowed,
    helper_read_roots,
    sandbox_cwd,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    PermissionProfile,
)
from pycodex.utils.absolute_path import AbsolutePathBuf


def _restricted_policy(entries: list[FileSystemSandboxEntry]) -> FileSystemSandboxPolicy:
    return FileSystemSandboxPolicy.restricted(entries)


def _path_entry(path: AbsolutePathBuf, access: FileSystemAccessMode) -> FileSystemSandboxEntry:
    return FileSystemSandboxEntry(FileSystemPath.explicit_path(path.as_path()), access)


def _special_entry(value: FileSystemSpecialPath, access: FileSystemAccessMode) -> FileSystemSandboxEntry:
    return FileSystemSandboxEntry(FileSystemPath.special(value), access)


def _sandbox_context_with_cwd(policy: FileSystemSandboxPolicy, cwd: AbsolutePathBuf) -> FileSystemSandboxContext:
    return FileSystemSandboxContext.from_permission_profile_with_cwd(
        PermissionProfile.from_runtime_permissions(policy, NetworkSandboxPolicy.RESTRICTED),
        cwd,
    )


def test_helper_permissions_enable_minimal_reads_for_restricted_profiles(tmp_path: Path) -> None:
    # Rust crate/module/tests:
    # codex-exec-server/src/fs_sandbox.rs
    # helper_permissions_enable_minimal_reads_for_restricted_profile and
    # helper_permissions_enable_minimal_reads_for_restricted_profile_with_writes.
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path)
    policy = _restricted_policy([])

    updated = add_helper_runtime_permissions(policy, [], cwd.as_path())

    assert updated.include_platform_defaults()

    writable = cwd.join("writable")
    policy_with_write = _restricted_policy([_path_entry(writable, FileSystemAccessMode.WRITE)])
    updated_with_write = add_helper_runtime_permissions(policy_with_write, [], cwd.as_path())

    assert updated_with_write.include_platform_defaults()
    assert updated_with_write.can_write_path_with_cwd(writable.as_path(), cwd.as_path())


def test_helper_permissions_preserve_writes_and_add_helper_read_roots(tmp_path: Path) -> None:
    # Rust test: helper_permissions_preserve_existing_writes.
    codex_self_exe = tmp_path / "bin" / "codex"
    codex_self_exe.parent.mkdir()
    runtime_paths = ExecServerRuntimePaths.new(codex_self_exe, None)
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    writable = cwd.join("writable")
    policy = _restricted_policy([_path_entry(writable, FileSystemAccessMode.WRITE)])
    readable = AbsolutePathBuf.from_absolute_path(codex_self_exe.parent)

    updated = add_helper_runtime_permissions(policy, helper_read_roots(runtime_paths), cwd.as_path())

    assert updated.can_read_path_with_cwd(readable.as_path(), cwd.as_path())
    assert updated.can_write_path_with_cwd(writable.as_path(), cwd.as_path())


def test_helper_env_preserves_allowlist_without_leaking_secrets() -> None:
    # Rust test: helper_env_preserves_path_for_system_bwrap_discovery_without_leaking_secrets.
    env = helper_env_from_vars(
        [
            ("PATH", "/usr/bin:/bin"),
            ("TMPDIR", "/tmp/codex"),
            ("TMP", "/tmp"),
            ("TEMP", "/tmp"),
            ("HOME", "/home/user"),
            ("OPENAI_API_KEY", "secret"),
            ("HTTPS_PROXY", "http://proxy.example"),
        ]
    )

    assert env == {
        "PATH": "/usr/bin:/bin",
        "TMPDIR": "/tmp/codex",
        "TMP": "/tmp",
        "TEMP": "/tmp",
    }
    assert helper_env_key_is_allowed("PATH") is True
    assert helper_env_key_is_allowed("OPENAI_API_KEY") is False


def test_sandbox_cwd_uses_context_cwd(tmp_path: Path) -> None:
    # Rust test: sandbox_cwd_uses_context_cwd.
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path)
    policy = _restricted_policy(
        [_special_entry(FileSystemSpecialPath.project_roots(), FileSystemAccessMode.WRITE)]
    )
    sandbox_context = _sandbox_context_with_cwd(policy, cwd)

    assert sandbox_cwd(sandbox_context) == cwd


def test_sandbox_cwd_rejects_dynamic_profile_without_context_cwd() -> None:
    # Rust test: sandbox_cwd_rejects_cwd_dependent_profile_without_context_cwd.
    policy = _restricted_policy(
        [_special_entry(FileSystemSpecialPath.project_roots(), FileSystemAccessMode.WRITE)]
    )
    sandbox_context = FileSystemSandboxContext.from_permission_profile(
        PermissionProfile.from_runtime_permissions(policy, NetworkSandboxPolicy.RESTRICTED)
    )

    err = sandbox_cwd(sandbox_context)

    assert isinstance(err, JSONRPCErrorError)
    assert err.message == "file system sandbox context with dynamic permissions requires cwd"


def test_helper_permissions_include_helper_read_root_without_additional_permissions(tmp_path: Path) -> None:
    # Rust test: helper_permissions_include_helper_read_root_without_additional_permissions.
    codex_self_exe = tmp_path / "bin" / "codex"
    codex_self_exe.parent.mkdir()
    runtime_paths = ExecServerRuntimePaths.new(codex_self_exe, None)
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    policy = _restricted_policy([])
    readable = AbsolutePathBuf.from_absolute_path(codex_self_exe.parent)

    updated = add_helper_runtime_permissions(policy, helper_read_roots(runtime_paths), cwd.as_path())

    assert updated.can_read_path_with_cwd(readable.as_path(), cwd.as_path())


def test_helper_permissions_include_linux_sandbox_alias_parent(tmp_path: Path) -> None:
    # Rust test: helper_permissions_include_linux_sandbox_alias_parent.
    codex_self_exe = tmp_path / "bin" / "codex"
    codex_linux_sandbox_exe = tmp_path / "aliases" / "codex-linux-sandbox"
    codex_self_exe.parent.mkdir()
    codex_linux_sandbox_exe.parent.mkdir()
    runtime_paths = ExecServerRuntimePaths.new(codex_self_exe, codex_linux_sandbox_exe)
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    policy = _restricted_policy([])
    codex_parent = AbsolutePathBuf.from_absolute_path(tmp_path / "bin")
    alias_parent = AbsolutePathBuf.from_absolute_path(tmp_path / "aliases")

    updated = add_helper_runtime_permissions(policy, helper_read_roots(runtime_paths), cwd.as_path())

    assert updated.can_read_path_with_cwd(codex_parent.as_path(), cwd.as_path())
    assert updated.can_read_path_with_cwd(alias_parent.as_path(), cwd.as_path())


def test_sandbox_exec_request_carries_helper_env(tmp_path: Path) -> None:
    # Rust test: sandbox_exec_request_carries_helper_env.
    codex_self_exe = tmp_path / "bin" / "codex"
    codex_self_exe.parent.mkdir()
    runtime_paths = ExecServerRuntimePaths.new(codex_self_exe, codex_self_exe)
    runner = FileSystemSandboxRunner(runtime_paths, helper_env={"PATH": "/bin"})
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    policy = _restricted_policy([_path_entry(cwd, FileSystemAccessMode.WRITE)])
    sandbox_context = _sandbox_context_with_cwd(policy, cwd)
    permission_profile = PermissionProfile.from_runtime_permissions(policy, NetworkSandboxPolicy.RESTRICTED)

    request = runner.sandbox_exec_request(permission_profile, cwd, sandbox_context)

    assert request.argv == [str(runtime_paths.codex_self_exe), CODEX_FS_HELPER_ARG1]
    assert request.env.get("PATH") == "/bin"
    assert request.cwd == cwd


def test_runner_run_encodes_request_and_decodes_ok_response(tmp_path: Path) -> None:
    # Rust: codex-exec-server/src/fs_sandbox.rs::FileSystemSandboxRunner::run
    # Contract: run prepares the fs-helper command, writes a JSON
    # FsHelperRequest, and decodes FsHelperResponse::Ok from stdout.
    calls = []

    async def command_runner(command, request_json):
        calls.append((command, request_json))
        response = FsHelperResponse.ok(FsHelperPayload.write_file(FsWriteFileResponse()))
        return FsSandboxCommandOutput(
            0,
            json.dumps(response.to_mapping()).encode("utf-8"),
            b"",
        )

    codex_self_exe = tmp_path / "bin" / "codex"
    codex_self_exe.parent.mkdir()
    runtime_paths = ExecServerRuntimePaths.new(codex_self_exe, None)
    runner = FileSystemSandboxRunner(runtime_paths, helper_env={"PATH": "/bin"}, command_runner=command_runner)
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    policy = _restricted_policy([_path_entry(cwd, FileSystemAccessMode.WRITE)])
    sandbox_context = _sandbox_context_with_cwd(policy, cwd)
    request = FsHelperRequest.write_file(FsWriteFileParams(str(tmp_path / "file"), ""))

    result = __import__("asyncio").run(runner.run(sandbox_context, request))

    assert result == FsHelperPayload.write_file(FsWriteFileResponse())
    command, request_json = calls[0]
    assert command.argv == [str(codex_self_exe), CODEX_FS_HELPER_ARG1]
    assert command.cwd == cwd
    assert command.env == {"PATH": "/bin"}
    assert json.loads(request_json) == request.to_mapping()


def test_runner_run_returns_helper_error_response(tmp_path: Path) -> None:
    # Rust: fs_sandbox.rs::run_command
    # Contract: FsHelperResponse::Error is returned as the JSON-RPC helper
    # error, not wrapped as a transport failure.
    async def command_runner(_command, _request_json):
        response = FsHelperResponse.error(JSONRPCErrorError(code=-32600, message="bad helper request"))
        return FsSandboxCommandOutput(0, json.dumps(response.to_mapping()).encode("utf-8"), b"")

    codex_self_exe = tmp_path / "bin" / "codex"
    codex_self_exe.parent.mkdir()
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    policy = _restricted_policy([_path_entry(cwd, FileSystemAccessMode.WRITE)])
    runner = FileSystemSandboxRunner(
        ExecServerRuntimePaths.new(codex_self_exe, None),
        command_runner=command_runner,
    )

    result = __import__("asyncio").run(
        runner.run(_sandbox_context_with_cwd(policy, cwd), FsHelperRequest.write_file(FsWriteFileParams("x", "")))
    )

    assert isinstance(result, JSONRPCErrorError)
    assert result.code == -32600
    assert result.message == "bad helper request"


def test_runner_run_maps_nonzero_status_and_invalid_json(tmp_path: Path) -> None:
    # Rust: fs_sandbox.rs::run_command/json_error
    # Contract: non-zero helper status and invalid stdout JSON become
    # internal JSON-RPC errors with Rust message prefixes.
    codex_self_exe = tmp_path / "bin" / "codex"
    codex_self_exe.parent.mkdir()
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    policy = _restricted_policy([_path_entry(cwd, FileSystemAccessMode.WRITE)])
    sandbox_context = _sandbox_context_with_cwd(policy, cwd)
    request = FsHelperRequest.write_file(FsWriteFileParams("x", ""))

    async def fail_runner(_command, _request_json):
        return FsSandboxCommandOutput(2, b"", b"nope\n", "exit status: 2")

    failed = __import__("asyncio").run(
        FileSystemSandboxRunner(
            ExecServerRuntimePaths.new(codex_self_exe, None),
            command_runner=fail_runner,
        ).run(sandbox_context, request)
    )
    assert isinstance(failed, JSONRPCErrorError)
    assert failed.message == "fs sandbox helper failed with status exit status: 2: nope"

    async def bad_json_runner(_command, _request_json):
        return FsSandboxCommandOutput(0, b"{", b"")

    decoded = __import__("asyncio").run(
        FileSystemSandboxRunner(
            ExecServerRuntimePaths.new(codex_self_exe, None),
            command_runner=bad_json_runner,
        ).run(sandbox_context, request)
    )
    assert isinstance(decoded, JSONRPCErrorError)
    assert decoded.message.startswith("failed to encode or decode fs sandbox helper message:")


def test_runner_run_rejects_empty_sandbox_command(tmp_path: Path) -> None:
    # Rust: fs_sandbox.rs::spawn_command
    # Contract: an empty transformed sandbox command returns invalid_request.
    class EmptyCommandRunner(FileSystemSandboxRunner):
        def sandbox_exec_request(self, _permission_profile, cwd, _sandbox_context):
            return type("Command", (), {"argv": [], "cwd": cwd, "env": {}, "arg0": None})()

    cwd = AbsolutePathBuf.from_absolute_path(tmp_path / "workspace")
    policy = _restricted_policy([_path_entry(cwd, FileSystemAccessMode.WRITE)])
    codex_self_exe = tmp_path / "bin" / "codex"
    codex_self_exe.parent.mkdir()
    runner = EmptyCommandRunner(ExecServerRuntimePaths.new(codex_self_exe, None), command_runner=lambda *_: None)

    result = __import__("asyncio").run(
        runner.run(_sandbox_context_with_cwd(policy, cwd), FsHelperRequest.write_file(FsWriteFileParams("x", "")))
    )

    assert isinstance(result, JSONRPCErrorError)
    assert result.code == -32600
    assert result.message == "fs sandbox command was empty"


def test_run_command_spawns_helper_subprocess_and_decodes_stdout(tmp_path: Path) -> None:
    # Rust: fs_sandbox.rs::run_command/spawn_command
    # Contract: when no injected runner is used, the helper command is spawned
    # with piped stdin/stdout/stderr, receives the JSON request bytes, and
    # returns FsHelperResponse::Ok from stdout.
    helper_code = (
        "import json,sys;"
        "request=json.loads(sys.stdin.buffer.read());"
        "assert request['operation']=='fs/writeFile';"
        "sys.stdout.write(json.dumps({'status':'ok','payload':"
        "{'operation':'fs/writeFile','response':{}}},separators=(',',':')))"
    )
    cwd = AbsolutePathBuf.from_absolute_path(tmp_path)
    command = FsSandboxExecRequest(
        [sys.executable, "-c", helper_code],
        cwd,
        {},
    )
    request = FsHelperRequest.write_file(FsWriteFileParams(str(tmp_path / "file"), ""))
    request_json = json.dumps(request.to_mapping(), separators=(",", ":")).encode("utf-8")
    runner = FileSystemSandboxRunner(ExecServerRuntimePaths.new(sys.executable, None))

    result = __import__("asyncio").run(runner.run_command(command, request_json))

    assert result == FsHelperPayload.write_file(FsWriteFileResponse())
