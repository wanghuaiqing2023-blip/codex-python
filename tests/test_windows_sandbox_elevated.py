from __future__ import annotations

from pathlib import Path
from io import BytesIO

from pycodex.protocol import PermissionProfile
from pycodex.windows_sandbox import elevated
from pycodex.windows_sandbox.identity import SandboxCreds


class _RunnerProcess:
    def __init__(self) -> None:
        self.stdout = BytesIO(b"ok")
        self.returncode = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def close(self):
        return None


def test_elevated_capture_uses_identity_user_restriction_and_process(tmp_path: Path, monkeypatch) -> None:
    # Rust owners: elevated_impl -> identity -> command_runner::win.
    calls: list[str] = []
    monkeypatch.setattr(elevated, "setup_mismatch_reason", lambda *_args: None)
    monkeypatch.setattr(elevated, "select_identity", lambda *_args: SandboxCreds("offline", "secret"))
    monkeypatch.setattr(
        elevated,
        "run_setup_helper",
        lambda payload, *, elevate: calls.append(f"setup:{payload.refresh_only}:{elevate}"),
    )
    monkeypatch.setattr(elevated, "_capability_sid_texts", lambda *_args: ("S-1-5-21-1",))
    def spawn_runner(credentials, *_args, **kwargs):
        calls.append(f"runner:{credentials.username}:{kwargs['tty']}:{kwargs['stdin_open']}")
        return _RunnerProcess()

    monkeypatch.setattr(elevated, "spawn_runner_popen", spawn_runner)
    result = elevated.run_elevated_capture(
        PermissionProfile.read_only(),
        tmp_path,
        tmp_path / "home",
        ("cmd.exe", "/c", "echo ok"),
        tmp_path,
        {},
        1000,
        use_private_desktop=True,
        proxy_enforced=False,
    )
    assert result.stdout == b"ok"
    assert calls == ["setup:True:False", "runner:offline:False:False"]
