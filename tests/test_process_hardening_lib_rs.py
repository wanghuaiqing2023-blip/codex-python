import os

import pytest

import pycodex.process_hardening as process_hardening
from pycodex.process_hardening import (
    PRCTL_FAILED_EXIT_CODE,
    PTRACE_DENY_ATTACH_FAILED_EXIT_CODE,
    SET_RLIMIT_CORE_FAILED_EXIT_CODE,
    env_keys_with_prefix,
    pre_main_hardening,
    pre_main_hardening_bsd,
    pre_main_hardening_linux,
    pre_main_hardening_macos,
    pre_main_hardening_windows,
    remove_env_vars_with_prefix,
    set_core_file_size_limit_to_zero,
)


def test_env_keys_with_prefix_handles_non_utf8_entries() -> None:
    # Rust: process-hardening/src/lib.rs::tests::env_keys_with_prefix_handles_non_utf8_entries.
    non_utf8_key1 = b"R\xd6DBURK"
    non_utf8_key2 = b"LD_\xf0"
    non_utf8_value = b"\xf0\x9f\x92\xa9"

    keys = env_keys_with_prefix(
        [
            (non_utf8_key1, non_utf8_value),
            (non_utf8_key2, non_utf8_value),
        ],
        b"LD_",
    )

    assert keys == [non_utf8_key2]


def test_env_keys_with_prefix_filters_only_matching_keys() -> None:
    # Rust: process-hardening/src/lib.rs::tests::env_keys_with_prefix_filters_only_matching_keys.
    vars = [
        (b"PATH", b"/usr/bin"),
        (b"LD_TEST", b"1"),
        (b"DYLD_FOO", b"bar"),
    ]

    keys = env_keys_with_prefix(vars, b"LD_")

    assert keys == [b"LD_TEST"]


def test_env_keys_with_prefix_preserves_string_keys() -> None:
    keys = env_keys_with_prefix(
        [
            ("PATH", "/bin"),
            ("LD_LIBRARY_PATH", "/tmp"),
        ],
        b"LD_",
    )

    assert keys == ["LD_LIBRARY_PATH"]


def test_remove_env_vars_with_prefix_removes_only_matching_text_env(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_env = {"PATH": "/bin", "LD_PRELOAD": "x", "DYLD_FOO": "y"}
    monkeypatch.setattr(process_hardening.os, "environ", fake_env)
    monkeypatch.delattr(process_hardening.os, "environb", raising=False)

    remove_env_vars_with_prefix(b"LD_")

    assert fake_env == {"PATH": "/bin", "DYLD_FOO": "y"}


def test_pre_main_hardening_dispatches_by_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(process_hardening.platform, "system", lambda: "Linux")
    monkeypatch.setattr(process_hardening, "pre_main_hardening_linux", lambda: calls.append("linux"))
    monkeypatch.setattr(process_hardening, "pre_main_hardening_macos", lambda: calls.append("macos"))
    monkeypatch.setattr(process_hardening, "pre_main_hardening_bsd", lambda: calls.append("bsd"))
    monkeypatch.setattr(process_hardening, "pre_main_hardening_windows", lambda: calls.append("windows"))

    pre_main_hardening()

    assert calls == ["linux"]

    calls.clear()
    monkeypatch.setattr(process_hardening.platform, "system", lambda: "Darwin")
    pre_main_hardening()
    assert calls == ["macos"]

    calls.clear()
    monkeypatch.setattr(process_hardening.platform, "system", lambda: "OpenBSD")
    pre_main_hardening()
    assert calls == ["bsd"]

    calls.clear()
    monkeypatch.setattr(process_hardening.platform, "system", lambda: "Windows")
    pre_main_hardening()
    assert calls == ["windows"]


def test_platform_hardening_sequences_are_monkeypatch_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bytes | None]] = []
    monkeypatch.setattr(process_hardening, "disable_process_dumping", lambda: calls.append(("dump", None)))
    monkeypatch.setattr(process_hardening, "deny_debugger_attach_macos", lambda: calls.append(("ptrace", None)))
    monkeypatch.setattr(process_hardening, "set_core_file_size_limit_to_zero", lambda: calls.append(("rlimit", None)))
    monkeypatch.setattr(process_hardening, "remove_env_vars_with_prefix", lambda prefix: calls.append(("env", prefix)))

    pre_main_hardening_linux()
    assert calls == [("dump", None), ("rlimit", None), ("env", b"LD_")]

    calls.clear()
    pre_main_hardening_bsd()
    assert calls == [("rlimit", None), ("env", b"LD_")]

    calls.clear()
    pre_main_hardening_macos()
    assert calls == [("ptrace", None), ("rlimit", None), ("env", b"DYLD_")]

    calls.clear()
    assert pre_main_hardening_windows() is None
    assert calls == []


def test_failure_exit_codes_match_rust(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_hardening, "disable_process_dumping", lambda: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(SystemExit) as linux_exit:
        pre_main_hardening_linux()
    assert linux_exit.value.code == PRCTL_FAILED_EXIT_CODE

    monkeypatch.setattr(process_hardening, "deny_debugger_attach_macos", lambda: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(SystemExit) as macos_exit:
        pre_main_hardening_macos()
    assert macos_exit.value.code == PTRACE_DENY_ATTACH_FAILED_EXIT_CODE


def test_set_core_file_size_limit_to_zero_maps_resource_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResource:
        RLIMIT_CORE = object()

        @staticmethod
        def setrlimit(_kind: object, _limits: tuple[int, int]) -> None:
            raise OSError("boom")

    monkeypatch.setattr(process_hardening, "resource", FakeResource)

    with pytest.raises(SystemExit) as exc_info:
        set_core_file_size_limit_to_zero()

    assert exc_info.value.code == SET_RLIMIT_CORE_FAILED_EXIT_CODE


def test_import_is_portable_when_os_has_no_environb() -> None:
    assert isinstance(os.environ, dict | os._Environ)
