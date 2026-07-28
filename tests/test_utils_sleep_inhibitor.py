from __future__ import annotations

import pycodex.utils.sleep_inhibitor as si
from pycodex.utils.sleep_inhibitor.dummy import SleepInhibitor as DummySleepInhibitor
from pycodex.utils.sleep_inhibitor.linux_inhibitor import (
    APP_ID,
    ASSERTION_REASON as LINUX_ASSERTION_REASON,
    LinuxBackend,
    LinuxSleepInhibitor,
    _backend_command,
)
from pycodex.utils.sleep_inhibitor.macos import (
    ASSERTION_REASON as MACOS_ASSERTION_REASON,
    ASSERTION_TYPE_PREVENT_USER_IDLE_SYSTEM_SLEEP,
    MacSleepInhibitor,
)
from pycodex.utils.sleep_inhibitor.macos.iokit import (
    kIOPMAssertionLevelOff,
    kIOPMAssertionLevelOn,
    kIOReturnSuccess,
)
from pycodex.utils.sleep_inhibitor.windows_inhibitor import (
    ASSERTION_REASON as WINDOWS_ASSERTION_REASON,
    POWER_REQUEST_SYSTEM_REQUIRED,
    WindowsSleepInhibitor,
)


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
        self.request_type = POWER_REQUEST_SYSTEM_REQUIRED

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
    assert _backend_command(LinuxBackend.SYSTEMD_INHIBIT) == [
        "systemd-inhibit",
        "--what=idle",
        "--mode=block",
        "--who",
        APP_ID,
        "--why",
        LINUX_ASSERTION_REASON,
        "--",
        "sleep",
        str(2**31 - 1),
    ]
    assert _backend_command(LinuxBackend.GNOME_SESSION_INHIBIT) == [
        "gnome-session-inhibit",
        "--inhibit",
        "idle",
        "--reason",
        LINUX_ASSERTION_REASON,
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

    backend = MacSleepInhibitor(factory)
    backend.acquire()
    backend.acquire()
    assert created == [MACOS_ASSERTION_REASON]
    assert backend.assertion is assertion

    backend.release()
    assert backend.assertion is None
    assert assertion.release_calls == 1

    error = OSError("boom")
    backend = MacSleepInhibitor(lambda _reason: (_ for _ in ()).throw(error))
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

    backend = WindowsSleepInhibitor(factory)
    backend.acquire()
    backend.acquire()
    assert created == [WINDOWS_ASSERTION_REASON]
    assert backend.request is request
    assert request.request_type == POWER_REQUEST_SYSTEM_REQUIRED

    backend.release()
    assert backend.request is None
    assert request.release_calls == 1

    error = OSError("PowerCreateRequest failed")
    backend = WindowsSleepInhibitor(lambda _reason: (_ for _ in ()).throw(error))
    backend.acquire()
    assert backend.request is None
    assert backend.last_error is error


def test_default_platform_backend_selection(monkeypatch) -> None:
    monkeypatch.setattr(si.sys, "platform", "linux")
    assert isinstance(si._default_platform_backend(), LinuxSleepInhibitor)

    monkeypatch.setattr(si.sys, "platform", "darwin")
    assert isinstance(si._default_platform_backend(), MacSleepInhibitor)

    monkeypatch.setattr(si.sys, "platform", "win32")
    assert isinstance(si._default_platform_backend(), WindowsSleepInhibitor)

    monkeypatch.setattr(si.sys, "platform", "plan9")
    assert isinstance(si._default_platform_backend(), DummySleepInhibitor)


def test_iokit_and_dummy_constants() -> None:
    # Rust: codex-utils-sleep-inhibitor src/iokit_bindings.rs and src/dummy.rs.
    assert ASSERTION_TYPE_PREVENT_USER_IDLE_SYSTEM_SLEEP == "PreventUserIdleSystemSleep"
    assert kIOReturnSuccess == 0
    assert kIOPMAssertionLevelOff == 0
    assert kIOPMAssertionLevelOn == 255

    dummy = DummySleepInhibitor()
    assert dummy.acquire() is None
    assert dummy.release() is None
