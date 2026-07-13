from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from pycodex.windows_sandbox import (
    LocalSid,
    add_allow_ace,
    create_process_as_user_capture,
    create_process_as_user_popen,
    create_readonly_token_with_caps_from,
    create_workspace_write_token_with_caps_from,
    get_current_token_for_restriction,
    make_env_block,
)


import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows process APIs")


def test_environment_block_is_case_insensitively_sorted_and_double_terminated() -> None:
    # Rust owner: codex-windows-sandbox::process::make_env_block.
    block = make_env_block({"z": "last", "A": "first", "a": "second"})
    assert block[:].startswith("A=first\0a=second\0z=last\0")
    assert block[:].endswith("\0\0")


def test_restricted_token_launches_child_with_unicode_environment(tmp_path: Path) -> None:
    # Rust owner: codex-windows-sandbox::process::create_process_as_user.
    command = [
        sys.executable,
        "-c",
        "import os,sys;sys.stdout.buffer.write(os.environ['PYCODEX_NATIVE_VALUE'].encode('utf-8'))",
    ]
    env = dict(os.environ)
    env["PYCODEX_NATIVE_VALUE"] = "native-你好"
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-401") as capability:
            with create_readonly_token_with_caps_from(base, [capability]) as restricted:
                result = create_process_as_user_capture(restricted, command, tmp_path, env, 10_000)

    assert result.exit_code == 0
    assert result.stdout.decode("utf-8") == "native-你好"
    assert result.stderr == b""
    assert not result.timed_out


def test_restricted_process_timeout_is_structured(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "import time;time.sleep(5)"]
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-402") as capability:
            with create_readonly_token_with_caps_from(base, [capability]) as restricted:
                result = create_process_as_user_capture(restricted, command, tmp_path, os.environ, 50)

    assert result.timed_out
    assert result.exit_code == 192


def test_restricted_token_denies_ungranted_file_write(tmp_path: Path) -> None:
    # Security evidence: this is a real child process, not a policy simulation.
    target = tmp_path / "must-not-exist.txt"
    command = [sys.executable, "-c", f"open({str(target)!r}, 'w').write('unsafe')"]
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-403") as capability:
            with create_readonly_token_with_caps_from(base, [capability]) as restricted:
                result = create_process_as_user_capture(restricted, command, tmp_path, os.environ, 10_000)

    assert result.exit_code != 0
    assert not target.exists()


def test_restricted_process_can_launch_on_private_desktop(tmp_path: Path) -> None:
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-404") as capability:
            with create_readonly_token_with_caps_from(base, [capability]) as restricted:
                result = create_process_as_user_capture(
                    restricted,
                    [sys.executable, "-c", "print('private-desktop-ok')"],
                    tmp_path,
                    os.environ,
                    10_000,
                    use_private_desktop=True,
                )

    assert result.exit_code == 0
    assert b"private-desktop-ok" in result.stdout


def test_timeout_terminates_restricted_process_tree(tmp_path: Path) -> None:
    # Python backend adapter evidence for Rust process-lifetime ownership:
    # closing/terminating a sandbox execution must not leave descendants alive.
    marker = tmp_path / "timeout-child-survived.txt"
    child = (
        "import pathlib,time;"
        "time.sleep(1);"
        f"pathlib.Path({str(marker)!r}).write_text('escaped', encoding='utf-8')"
    )
    parent = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable, '-c', {child!r}]);"
        "time.sleep(10)"
    )
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-405") as capability:
            add_allow_ace(tmp_path, capability)
            with create_workspace_write_token_with_caps_from(base, [capability]) as restricted:
                result = create_process_as_user_capture(
                    restricted,
                    [sys.executable, "-c", parent],
                    tmp_path,
                    os.environ,
                    150,
                )

    assert result.timed_out
    time.sleep(1.2)
    assert not marker.exists()


def test_cancellation_terminates_restricted_process_tree(tmp_path: Path) -> None:
    marker = tmp_path / "cancelled-child-survived.txt"
    child = (
        "import pathlib,time;"
        "time.sleep(1);"
        f"pathlib.Path({str(marker)!r}).write_text('escaped', encoding='utf-8')"
    )
    parent = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable, '-c', {child!r}]);"
        "time.sleep(10)"
    )
    started = time.monotonic()
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-406") as capability:
            add_allow_ace(tmp_path, capability)
            with create_workspace_write_token_with_caps_from(base, [capability]) as restricted:
                result = create_process_as_user_capture(
                    restricted,
                    [sys.executable, "-c", parent],
                    tmp_path,
                    os.environ,
                    10_000,
                    is_cancelled=lambda: time.monotonic() - started >= 0.15,
                )

    assert result.cancelled
    assert result.exit_code == 1
    time.sleep(1.2)
    assert not marker.exists()


def test_restricted_popen_streams_output_and_accepts_stdin(tmp_path: Path) -> None:
    # Product anchor for unified_exec: restricted Popen-compatible session.
    command = [
        sys.executable,
        "-c",
        "import sys; line=sys.stdin.buffer.readline(); sys.stdout.buffer.write(b'got:'+line); sys.stdout.flush()",
    ]
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-407") as capability:
            with create_readonly_token_with_caps_from(base, [capability]) as restricted:
                process = create_process_as_user_popen(
                    restricted,
                    command,
                    tmp_path,
                    os.environ,
                    stdin_open=True,
                )
                assert process.stdin is not None
                process.stdin.write(b"hello\n")
                process.stdin.flush()
                assert process.wait(timeout=10) == 0
                assert process.stdout.read() == b"got:hello\n"
                process.close()


def test_restricted_conpty_streams_output_and_accepts_stdin(tmp_path: Path) -> None:
    # Rust owner: codex-windows-sandbox::conpty and unified_exec::legacy.
    # Product evidence: tty=true is backed by a pseudo console, not anonymous pipes.
    command = [
        sys.executable,
        "-c",
        "import sys; line=sys.stdin.readline(); print('tty:'+line.strip(), flush=True)",
    ]
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-408") as capability:
            with create_readonly_token_with_caps_from(base, [capability]) as restricted:
                process = create_process_as_user_popen(
                    restricted,
                    command,
                    tmp_path,
                    os.environ,
                    stdin_open=True,
                    tty=True,
                )
                assert process.stdin is not None
                process.stdin.write(b"hello\n")
                process.stdin.flush()
                assert process.wait(timeout=10) == 0
                output = process.stdout.read().replace(b"\r\n", b"\n")
                assert b"tty:hello\n" in output
                process.close()
