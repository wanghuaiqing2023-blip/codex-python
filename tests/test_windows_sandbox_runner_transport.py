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
from pycodex.windows_sandbox.elevated import run_elevated_capture, spawn_elevated_popen
from pycodex.windows_sandbox.identity import sandbox_setup_is_complete
from pycodex.windows_sandbox.runner_transport import RunnerBackedPopen, read_frame, write_frame


def test_runner_frames_round_trip_binary_safe_json() -> None:
    # Rust owners: windows-sandbox-rs::ipc_framed and elevated::runner_client.
    stream = io.BytesIO()
    write_frame(stream, {"type": "output", "data": "5L2g5aW9"})
    stream.seek(0)

    assert read_frame(stream) == {"type": "output", "data": "5L2g5aW9"}


def test_runner_backed_popen_resize_uses_shared_ipc_frame(monkeypatch) -> None:
    # Rust owner: elevated::ipc_framed::Message::Resize.
    sent: list[dict[str, object]] = []
    process = object.__new__(RunnerBackedPopen)
    process._tty = True
    monkeypatch.setattr(process, "_send", lambda message: sent.append(dict(message)))

    process.resize(120, 42)

    assert sent == [{"type": "resize", "cols": 120, "rows": 42}]


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
        return run_elevated_capture(
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
        result = run_elevated_capture(
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
        result = run_elevated_capture(
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
        result = run_elevated_capture(
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
        result = run_elevated_capture(
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

        result = run_elevated_capture(
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
        result = run_elevated_capture(
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

        process = spawn_elevated_popen(
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
