from __future__ import annotations

import io
import os
import shutil
import time
import uuid
from pathlib import Path

import pytest

from pycodex.core.windows_sandbox import run_setup_refresh_with_extra_read_roots
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    ManagedFileSystemPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
)
from pycodex.windows_sandbox.elevated_impl import (
    ElevatedSandboxProfileCaptureRequest,
    run_windows_sandbox_capture_for_permission_profile,
)
from pycodex.windows_sandbox.identity import sandbox_setup_is_complete
from pycodex.windows_sandbox.elevated.ipc_framed import read_frame, write_frame
from pycodex.windows_sandbox.elevated.runner_client import RunnerTransport
from pycodex.windows_sandbox.elevated.runner_pipe import connect_pipe, pipe_pair
from pycodex.windows_sandbox.unified_exec.backends.windows_common import RunnerBackedPopen
from pycodex.windows_sandbox.unified_exec import (
    spawn_windows_sandbox_session_elevated_for_permission_profile,
)


def capture_permission_profile(
    permission_profile,
    permission_profile_cwd,
    codex_home,
    command,
    cwd,
    env_map,
    timeout_ms,
    *,
    use_private_desktop,
    proxy_enforced,
    additional_deny_read_paths=(),
    additional_deny_write_paths=(),
):
    return run_windows_sandbox_capture_for_permission_profile(
        ElevatedSandboxProfileCaptureRequest(
            permission_profile,
            Path(permission_profile_cwd),
            Path(codex_home),
            tuple(command),
            Path(cwd),
            env_map,
            timeout_ms,
            use_private_desktop,
            proxy_enforced,
            deny_read_paths_override=tuple(
                Path(path) for path in additional_deny_read_paths
            ),
            deny_write_paths_override=tuple(
                Path(path) for path in additional_deny_write_paths
            ),
        )
    )


def spawn_permission_profile_session(
    permission_profile,
    permission_profile_cwd,
    codex_home,
    command,
    cwd,
    env_map,
    *,
    stdin_open,
    tty,
    merge_stderr=True,
    use_private_desktop,
    proxy_enforced,
    additional_deny_read_paths=(),
    additional_deny_write_paths=(),
):
    return spawn_windows_sandbox_session_elevated_for_permission_profile(
        permission_profile,
        permission_profile_cwd,
        codex_home,
        command,
        cwd,
        env_map,
        None,
        None,
        False,
        None,
        additional_deny_read_paths,
        additional_deny_write_paths,
        tty,
        stdin_open,
        use_private_desktop,
    )


def test_runner_frames_round_trip_binary_safe_json() -> None:
    # Rust source: elevated::ipc_framed::tests::framed_round_trip.
    from pycodex.windows_sandbox.elevated.ipc_framed import (
        FramedMessage,
        IPC_PROTOCOL_VERSION,
        Message,
        OutputPayload,
        OutputStream,
        decode_bytes,
        encode_bytes,
    )

    stream = io.BytesIO()
    message = FramedMessage(
        IPC_PROTOCOL_VERSION,
        Message.output(OutputPayload(encode_bytes("你好".encode()), OutputStream.STDOUT)),
    )
    write_frame(stream, message)
    stream.seek(0)

    decoded = read_frame(stream)
    assert decoded is not None
    assert decoded.version == IPC_PROTOCOL_VERSION
    assert decoded.message.type == "output"
    assert isinstance(decoded.message.payload, OutputPayload)
    assert decoded.message.payload.stream is OutputStream.STDOUT
    assert decode_bytes(decoded.message.payload.data_b64) == "你好".encode()


def test_spawn_request_frame_serializes_rust_schema(tmp_path: Path) -> None:
    # Rust source: elevated::ipc_framed::tests::spawn_request_serializes_permission_profile.
    from pycodex.windows_sandbox.elevated.ipc_framed import (
        FramedMessage,
        IPC_PROTOCOL_VERSION,
        Message,
        SpawnReady,
        SpawnRequest,
        read_frame,
        write_frame,
    )

    request = SpawnRequest(
        command=("cmd.exe", "/c", "ver"),
        cwd=tmp_path,
        env={},
        permission_profile=PermissionProfile.read_only(),
        permission_profile_cwd=tmp_path,
        codex_home=tmp_path / "sandbox",
        real_codex_home=tmp_path / "home",
        cap_sids=("S-1-15-3-1024-1",),
        timeout_ms=1000,
        tty=False,
        stdin_open=False,
        use_private_desktop=False,
    )
    stream = io.BytesIO()
    write_frame(
        stream,
        FramedMessage(IPC_PROTOCOL_VERSION, Message.spawn_request(request)),
    )
    raw = stream.getvalue()
    payload_length = int.from_bytes(raw[:4], "little")
    encoded = __import__("json").loads(raw[4 : 4 + payload_length])
    assert encoded["version"] == 2
    assert encoded["type"] == "spawn_request"
    assert encoded["payload"]["permission_profile"]["type"] == "managed"
    assert "policy_json_or_preset" not in encoded["payload"]
    assert "sandbox_policy_cwd" not in encoded["payload"]

    stream.seek(0)
    decoded = read_frame(stream)
    assert decoded is not None
    assert isinstance(decoded.message.payload, SpawnRequest)
    assert decoded.message.payload.permission_profile == PermissionProfile.read_only()
    assert decoded.message.payload.permission_profile_cwd == tmp_path


def test_runner_backed_popen_resize_uses_shared_ipc_frame(monkeypatch) -> None:
    # Rust owner: elevated::ipc_framed::Message::Resize.
    from pycodex.windows_sandbox.elevated.ipc_framed import FramedMessage, ResizePayload

    sent: list[FramedMessage] = []
    process = object.__new__(RunnerBackedPopen)
    process._tty = True
    monkeypatch.setattr(process, "_send", sent.append)

    process.resize(120, 42)

    assert len(sent) == 1
    assert sent[0].version == 2
    assert sent[0].message.type == "resize"
    assert sent[0].message.payload == ResizePayload(rows=42, cols=120)


def test_runner_pipe_pair_uses_rust_name_shape() -> None:
    # Rust source: elevated::runner_pipe::pipe_pair.
    pipe_in, pipe_out = pipe_pair()

    assert pipe_in.startswith(r"\\.\pipe\codex-runner-")
    assert pipe_in.endswith("-in")
    assert pipe_out == pipe_in.removesuffix("-in") + "-out"


def test_runner_pipe_rejects_unexpected_client_pid(monkeypatch) -> None:
    # Rust source: elevated::runner_pipe::connect_pipe.
    import pycodex.windows_sandbox.elevated.runner_pipe as runner_pipe

    monkeypatch.setattr(runner_pipe, "_connect_named_pipe", lambda _handle: None)
    monkeypatch.setattr(runner_pipe, "_named_pipe_client_pid", lambda _handle: 17)

    with pytest.raises(PermissionError, match="17.*42"):
        connect_pipe(object(), 42)


def test_runner_transport_sends_request_and_accepts_spawn_ready(tmp_path: Path) -> None:
    # Rust source: elevated::runner_client::RunnerTransport.
    from pycodex.windows_sandbox.elevated.ipc_framed import (
        FramedMessage,
        IPC_PROTOCOL_VERSION,
        Message,
        SpawnReady,
        SpawnRequest,
    )

    request = SpawnRequest(
        command=("cmd.exe", "/c", "ver"),
        cwd=tmp_path,
        env={},
        permission_profile=PermissionProfile.read_only(),
        permission_profile_cwd=tmp_path,
        codex_home=tmp_path / "sandbox",
        real_codex_home=tmp_path / "home",
        cap_sids=("S-1-15-3-1024-1",),
        timeout_ms=None,
        tty=False,
        stdin_open=False,
        use_private_desktop=False,
    )
    writer = io.BytesIO()
    ready = io.BytesIO()
    write_frame(
        ready,
        FramedMessage(
            IPC_PROTOCOL_VERSION,
            Message.spawn_ready(SpawnReady(process_id=123)),
        ),
    )
    ready.seek(0)
    transport = RunnerTransport(writer, ready)

    transport.send_spawn_request(request)
    transport.read_spawn_ready()

    writer.seek(0)
    frame = read_frame(writer)
    assert frame is not None
    assert frame.message.type == "spawn_request"
    assert frame.message.payload == request


def _native_elevated_enabled() -> bool:
    return (
        os.name == "nt"
        and os.environ.get("PYCODEX_RUN_NATIVE_ELEVATED_SANDBOX_TESTS") == "1"
        and sandbox_setup_is_complete(Path.home() / ".codex")
    )


@pytest.mark.skipif(not _native_elevated_enabled(), reason="requires provisioned native elevated sandbox")
def test_native_elevated_runner_enforces_filesystem_stderr_timeout_and_tty() -> None:
    # Fixed Rust owners: elevated::runner_client, command_runner::win,
    # process, conpty, and spawn_prep. This is real OS enforcement evidence.
    home = Path.home() / ".codex"
    root = Path.cwd() / ".tmp" / f"native-elevated-test-{uuid.uuid4().hex}"
    workspace = root / "workspace"
    external = root / "external"
    workspace.mkdir(parents=True)
    external.mkdir()
    env = dict(os.environ)
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "WS_PROXY", "WSS_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "ws_proxy", "wss_proxy",
    ):
        env.pop(key, None)
    python = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "python.exe"

    def capture(
        profile: PermissionProfile,
        code: str,
        timeout_ms: int = 15_000,
        *,
        deny_read: tuple[Path, ...] = (),
        deny_write: tuple[Path, ...] = (),
    ):
        return capture_permission_profile(
            profile,
            workspace,
            home,
            (str(python), "-c", code),
            workspace,
            env,
            timeout_ms,
            use_private_desktop=True,
            proxy_enforced=False,
            additional_deny_read_paths=deny_read,
            additional_deny_write_paths=deny_write,
        )

    try:
        denied_read_only = workspace / "read-only-denied.txt"
        result = capture(
            PermissionProfile.read_only(),
            f"from pathlib import Path;Path({str(denied_read_only)!r}).write_text('bad')",
        )
        assert result.exit_code != 0
        assert not denied_read_only.exists()

        allowed = workspace / "allowed.txt"
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;Path({str(allowed)!r}).write_text('ok')",
        )
        assert result.exit_code == 0
        assert allowed.read_text() == "ok"

        powershell_allowed = workspace / "powershell-allowed.txt"
        result = capture_permission_profile(
            PermissionProfile.workspace_write(), workspace, home,
            (
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"Set-Content -LiteralPath {str(powershell_allowed)!r} -Value ok",
            ),
            workspace, env, 15_000, use_private_desktop=True, proxy_enforced=False,
        )
        assert result.exit_code == 0 and powershell_allowed.read_text().strip() == "ok"

        denied_external = external / "denied.txt"
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;Path({str(denied_external)!r}).write_text('bad')",
        )
        assert result.exit_code != 0
        assert not denied_external.exists()

        cmd_denied_external = external / "cmd-denied.txt"
        result = capture_permission_profile(
            PermissionProfile.workspace_write(), workspace, home,
            ("cmd.exe", "/d", "/c", f"echo bad>\"{cmd_denied_external}\""),
            workspace, env, 15_000, use_private_desktop=True, proxy_enforced=False,
        )
        assert result.exit_code != 0 and not cmd_denied_external.exists()

        relative_escape = Path("..") / "external" / "relative-denied.txt"
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;Path({str(relative_escape)!r}).write_text('bad')",
        )
        assert result.exit_code != 0 and not (external / "relative-denied.txt").exists()

        if external.drive:
            unc_external = (
                "\\\\localhost\\" + external.drive[0] + "$\\"
                + str(external).removeprefix(external.anchor).replace("/", "\\")
                + r"\unc-denied.txt"
            )
            result = capture(
                PermissionProfile.workspace_write(),
                f"from pathlib import Path;Path({unc_external!r}).write_text('bad')",
            )
            assert result.exit_code != 0 and not (external / "unc-denied.txt").exists()

        secret = workspace / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;print(Path({str(secret)!r}).read_text())",
            deny_read=(secret,),
        )
        assert result.exit_code != 0 and b"secret" not in result.stdout
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;print(Path({str(secret)!r}).read_text())",
        )
        assert result.exit_code == 0 and b"secret" in result.stdout

        missing_denied = workspace / "materialized-deny-read"
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;print(list(Path({str(missing_denied)!r}).iterdir()))",
            deny_read=(missing_denied,),
        )
        assert missing_denied.is_dir() and result.exit_code != 0

        readonly_subpath = workspace / "read-only-subpath"
        readonly_subpath.mkdir()
        denied_subpath_file = readonly_subpath / "denied.txt"
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;Path({str(denied_subpath_file)!r}).write_text('bad')",
            deny_write=(readonly_subpath,),
        )
        assert result.exit_code != 0 and not denied_subpath_file.exists()

        mixed_case_allowed = workspace / "MiXeD-Case.txt"
        device_allowed = "\\\\?\\" + str(mixed_case_allowed)
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;Path({device_allowed!r}).write_text('ok')",
        )
        assert result.exit_code == 0 and mixed_case_allowed.read_text() == "ok"

        case_variant = str(workspace).upper() + "\\case-variant.txt"
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;Path({case_variant!r}).write_text('ok')",
        )
        assert result.exit_code == 0 and (workspace / "case-variant.txt").read_text() == "ok"

        device_external = "\\\\?\\" + str(external / "device-denied.txt")
        result = capture(
            PermissionProfile.workspace_write(),
            f"from pathlib import Path;Path({device_external!r}).write_text('bad')",
        )
        assert result.exit_code != 0 and not (external / "device-denied.txt").exists()

        network_probe = (
            "import socket;"
            "connection=socket.create_connection(('1.1.1.1',443),3);"
            "connection.close();print('NETWORK_OK')"
        )
        result = capture(PermissionProfile.read_only(), network_probe)
        assert result.exit_code != 0 and b"NETWORK_OK" not in result.stdout
        network_enabled_profile = PermissionProfile.managed(
            PermissionProfile.read_only().file_system,
            NetworkSandboxPolicy.ENABLED,
        )
        result = capture(network_enabled_profile, network_probe)
        assert result.exit_code == 0 and b"NETWORK_OK" in result.stdout

        extra_read_root = external / "extra-read-root"
        extra_read_root.mkdir()
        extra_read_secret = extra_read_root / "secret.txt"
        extra_read_secret.write_text("EXTRA_READ_OK", encoding="utf-8")
        explicit_read_profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.minimal()),
                        FileSystemAccessMode.READ,
                    ),
                    FileSystemSandboxEntry(
                        FileSystemPath.explicit_path(extra_read_root),
                        FileSystemAccessMode.READ,
                    ),
                )
            ),
            NetworkSandboxPolicy.RESTRICTED,
        )
        run_setup_refresh_with_extra_read_roots(
            explicit_read_profile,
            workspace,
            workspace,
            env,
            home,
            (extra_read_root,),
        )
        result = capture_permission_profile(
            explicit_read_profile,
            workspace,
            home,
            ("cmd.exe", "/d", "/c", f"type {extra_read_secret}"),
            workspace,
            env,
            15_000,
            use_private_desktop=True,
            proxy_enforced=False,
        )
        assert result.exit_code == 0 and b"EXTRA_READ_OK" in result.stdout
        extra_read_denied = extra_read_root / "write-denied.txt"
        result = capture_permission_profile(
            explicit_read_profile,
            workspace,
            home,
            ("cmd.exe", "/d", "/c", f"echo bad>{extra_read_denied}"),
            workspace,
            env,
            15_000,
            use_private_desktop=True,
            proxy_enforced=False,
        )
        assert result.exit_code != 0 and not extra_read_denied.exists()

        junction = workspace / "external-junction"
        junction_result = os.system(f'cmd.exe /d /c mklink /J "{junction}" "{external}" >nul')
        if junction_result == 0:
            junction_escape = junction / "junction-denied.txt"
            result = capture(
                PermissionProfile.workspace_write(),
                f"from pathlib import Path;Path({str(junction_escape)!r}).write_text('bad')",
            )
            assert result.exit_code != 0 and not (external / "junction-denied.txt").exists()

        result = capture_permission_profile(
            PermissionProfile.read_only(), workspace, home,
            ("cmd.exe", "/c", "echo OUT & echo ERR 1>&2"), workspace, env, 15_000,
            use_private_desktop=True, proxy_enforced=False,
        )
        assert b"OUT" in result.stdout
        assert b"ERR" in result.stderr

        result = capture(
            PermissionProfile.read_only(),
            "import os;os.write(1,b'A'*1000000);os.write(2,b'B'*800000)",
        )
        assert result.exit_code == 0
        assert result.stdout == b"A" * 1_000_000
        assert result.stderr == b"B" * 800_000

        result = capture(PermissionProfile.read_only(), "import time;time.sleep(30)", 200)
        assert result.timed_out and result.exit_code == 192

        cancel_started = time.monotonic()
        result = capture_permission_profile(
            PermissionProfile.read_only(), workspace, home,
            (str(python), "-c", "import time;time.sleep(30)"), workspace, env, 15_000,
            use_private_desktop=True, proxy_enforced=False,
            is_cancelled=lambda: time.monotonic() - cancel_started >= 0.2,
        )
        assert result.cancelled and not result.timed_out and result.exit_code == 1

        descendant_marker = workspace / "descendant-survived.txt"
        child_code = f"import time;from pathlib import Path;time.sleep(1);Path({str(descendant_marker)!r}).write_text('escaped')"
        parent_code = f"import subprocess,time;subprocess.Popen([{str(python)!r},'-c',{child_code!r}]);time.sleep(30)"
        result = capture(PermissionProfile.workspace_write(), parent_code, 200)
        assert result.timed_out
        time.sleep(1.2)
        assert not descendant_marker.exists()

        process = spawn_permission_profile_session(
            PermissionProfile.read_only(), workspace, home,
            (
                str(python),
                "-c",
                "import os,sys;line=sys.stdin.readline();size=os.get_terminal_size();"
                "print(f'TTY:{line.strip()}:{size.columns}x{size.lines}',flush=True)",
            ),
            workspace, env, stdin_open=True, tty=True, use_private_desktop=True, proxy_enforced=False,
        )
        assert process.stdin is not None
        process.resize(91, 33)
        process.stdin.write(b"hello\n")
        process.stdin.flush()
        assert process.wait(15) == 0
        assert b"TTY:hello:91x33" in process.stdout.read()
        process.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)
