from __future__ import annotations

import pycodex.utils.sleep_inhibitor as si


class FakeBackend:
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self) -> None:
        self.acquire_calls += 1

    def release(self) -> None:
        self.release_calls += 1


class FakeAssertion:
    def __init__(self) -> None:
        self.release_calls = 0

    def release(self) -> None:
        self.release_calls += 1


class FakePowerRequest:
    def __init__(self) -> None:
        self.release_calls = 0
        self.request_type = si.POWER_REQUEST_SYSTEM_REQUIRED

    def release(self) -> None:
        self.release_calls += 1


def test_sleep_inhibitor_toggles_without_panicking() -> None:
    # Rust: codex-utils-sleep-inhibitor src/lib.rs sleep_inhibitor_toggles_without_panicking.
    backend = FakeBackend()
    inhibitor = si.SleepInhibitor(True, backend)

    inhibitor.set_turn_running(True)
    assert inhibitor.is_turn_running() is True
    assert backend.acquire_calls == 1

    inhibitor.set_turn_running(False)
    assert inhibitor.is_turn_running() is False
    assert backend.release_calls == 1


def test_sleep_inhibitor_disabled_does_not_acquire_but_releases() -> None:
    # Rust: codex-utils-sleep-inhibitor src/lib.rs sleep_inhibitor_disabled_does_not_panic.
    backend = FakeBackend()
    inhibitor = si.SleepInhibitor(False, backend)

    inhibitor.set_turn_running(True)
    assert inhibitor.is_turn_running() is True
    assert backend.acquire_calls == 0
    assert backend.release_calls == 1

    inhibitor.set_turn_running(False)
    assert inhibitor.is_turn_running() is False
    assert backend.release_calls == 2


def test_sleep_inhibitor_multiple_true_calls_delegate_to_backend() -> None:
    # Rust: codex-utils-sleep-inhibitor src/lib.rs sleep_inhibitor_multiple_true_calls_are_idempotent.
    backend = FakeBackend()
    inhibitor = si.SleepInhibitor(True, backend)

    inhibitor.set_turn_running(True)
    inhibitor.set_turn_running(True)

    assert inhibitor.is_turn_running() is True
    assert backend.acquire_calls == 2
    assert backend.release_calls == 0


def test_linux_backend_commands_match_rust_arguments() -> None:
    # Rust: codex-utils-sleep-inhibitor src/linux_inhibitor.rs command builders.
    assert si._linux_backend_command(si.LinuxBackend.SYSTEMD_INHIBIT) == [
        "systemd-inhibit",
        "--what=idle",
        "--mode=block",
        "--who",
        si.APP_ID,
        "--why",
        si.ASSERTION_REASON,
        "--",
        "sleep",
        str(2**31 - 1),
    ]
    assert si._linux_backend_command(si.LinuxBackend.GNOME_SESSION_INHIBIT) == [
        "gnome-session-inhibit",
        "--inhibit",
        "idle",
        "--reason",
        si.ASSERTION_REASON,
        "sleep",
        str(2**31 - 1),
    ]


def test_macos_backend_is_idempotent_and_records_errors() -> None:
    # Rust: codex-utils-sleep-inhibitor src/macos.rs MacSleepInhibitor acquire/release contract.
    created: list[str] = []
    assertion = FakeAssertion()

    def factory(reason: str) -> FakeAssertion:
        created.append(reason)
        return assertion

    backend = si.MacSleepInhibitor(factory)
    backend.acquire()
    backend.acquire()
    assert created == [si.ASSERTION_REASON]
    assert backend.assertion is assertion

    backend.release()
    assert backend.assertion is None
    assert assertion.release_calls == 1

    error = OSError("boom")
    backend = si.MacSleepInhibitor(lambda _reason: (_ for _ in ()).throw(error))
    backend.acquire()
    assert backend.assertion is None
    assert backend.last_error is error


def test_windows_backend_is_idempotent_and_records_errors() -> None:
    # Rust: codex-utils-sleep-inhibitor src/windows_inhibitor.rs WindowsSleepInhibitor acquire/release contract.
    created: list[str] = []
    request = FakePowerRequest()

    def factory(reason: str) -> FakePowerRequest:
        created.append(reason)
        return request

    backend = si.WindowsSleepInhibitor(factory)
    backend.acquire()
    backend.acquire()
    assert created == [si.ASSERTION_REASON]
    assert backend.request is request
    assert request.request_type == si.POWER_REQUEST_SYSTEM_REQUIRED

    backend.release()
    assert backend.request is None
    assert request.release_calls == 1

    error = OSError("PowerCreateRequest failed")
    backend = si.WindowsSleepInhibitor(lambda _reason: (_ for _ in ()).throw(error))
    backend.acquire()
    assert backend.request is None
    assert backend.last_error is error


def test_default_platform_backend_selection(monkeypatch) -> None:
    monkeypatch.setattr(si.sys, "platform", "linux")
    assert isinstance(si.default_platform_backend(), si.LinuxSleepInhibitor)

    monkeypatch.setattr(si.sys, "platform", "darwin")
    assert isinstance(si.default_platform_backend(), si.MacSleepInhibitor)

    monkeypatch.setattr(si.sys, "platform", "win32")
    assert isinstance(si.default_platform_backend(), si.WindowsSleepInhibitor)

    monkeypatch.setattr(si.sys, "platform", "plan9")
    assert isinstance(si.default_platform_backend(), si.DummySleepInhibitor)


def test_iokit_and_dummy_constants() -> None:
    # Rust: codex-utils-sleep-inhibitor src/iokit_bindings.rs and src/dummy.rs.
    assert si.ASSERTION_TYPE_PREVENT_USER_IDLE_SYSTEM_SLEEP == "PreventUserIdleSystemSleep"
    assert si.K_IO_RETURN_SUCCESS == 0
    assert si.K_IOPM_ASSERTION_LEVEL_OFF == 0
    assert si.K_IOPM_ASSERTION_LEVEL_ON == 255

    dummy = si.DummySleepInhibitor()
    assert dummy.acquire() is None
    assert dummy.release() is None
