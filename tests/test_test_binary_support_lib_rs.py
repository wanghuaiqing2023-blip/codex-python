from pathlib import Path
import os

import pytest

from pycodex.arg0 import (
    APPLY_PATCH_ARG0,
    CODEX_CORE_APPLY_PATCH_ARG1,
    CODEX_FS_HELPER_ARG1,
    CODEX_LINUX_SANDBOX_ARG0,
)
from pycodex.test_binary_support import (
    TestBinaryDispatchGuard,
    TestBinaryDispatchMode,
    configure_test_binary_dispatch,
)


def test_configure_dispatch_arg0_only_invokes_arg0_handler(tmp_path: Path) -> None:
    # Rust crate: codex-test-binary-support
    # Rust module: lib.rs
    # Rust branch: TestBinaryDispatchMode::DispatchArg0Only
    # Contract: delegate to codex_arg0::arg0_dispatch and return no guard.
    calls: list[list[str]] = []

    guard = configure_test_binary_dispatch(
        "codex-test",
        lambda exe_name, argv1: TestBinaryDispatchMode.DISPATCH_ARG0_ONLY,
        argv=[APPLY_PATCH_ARG0, "payload"],
        handlers={"apply_patch": lambda args: calls.append(args)},
        current_exe=tmp_path / "codex",
    )

    assert guard is None
    assert calls == [["payload"]]


def test_configure_skip_returns_none_without_handler_call(tmp_path: Path) -> None:
    # Rust crate: codex-test-binary-support
    # Rust module: lib.rs
    # Rust branch: TestBinaryDispatchMode::Skip
    # Contract: return None without configuring aliases.
    calls: list[list[str]] = []

    guard = configure_test_binary_dispatch(
        "codex-test",
        lambda exe_name, argv1: TestBinaryDispatchMode.SKIP,
        argv=[APPLY_PATCH_ARG0, "payload"],
        handlers={"apply_patch": lambda args: calls.append(args)},
        current_exe=tmp_path / "codex",
    )

    assert guard is None
    assert calls == []


def test_configure_install_aliases_uses_temporary_codex_home_and_restores_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Rust crate: codex-test-binary-support
    # Rust module: lib.rs
    # Rust branch: TestBinaryDispatchMode::InstallAliases
    # Contract: create temporary CODEX_HOME, install arg0 aliases, then restore CODEX_HOME.
    current_exe = tmp_path / "codex"
    current_exe.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "previous"))
    monkeypatch.setenv("PATH", "original-path")

    seen: list[tuple[str, str | None]] = []

    guard = configure_test_binary_dispatch(
        "codex-test",
        lambda exe_name, argv1: seen.append((exe_name, argv1)) or TestBinaryDispatchMode.INSTALL_ALIASES,
        argv=[str(tmp_path / "test-binary"), "regular"],
        current_exe=current_exe,
    )
    assert isinstance(guard, TestBinaryDispatchGuard)
    try:
        assert seen == [("test-binary", "regular")]
        assert guard.paths.codex_self_exe == current_exe
        home = Path(guard._codex_home.name)
        assert home.name.startswith("codex-test")
        assert home.exists()
        path_entry = Path(os.environ["PATH"].split(os.pathsep, 1)[0])
        assert path_entry.parent == home / "tmp" / "arg0"
        assert os.environ["PATH"].endswith(f"{os.pathsep}original-path")
        assert os.environ["CODEX_HOME"] == str(tmp_path / "previous")
    finally:
        home = Path(guard._codex_home.name)
        guard.close()
    assert not home.exists()


def test_classifier_receives_exe_name_and_optional_argv1(tmp_path: Path) -> None:
    # Rust crate: codex-test-binary-support
    # Rust module: lib.rs
    # Rust code: exe_name from argv0 file_name and argv1 as optional string.
    calls: list[tuple[str, str | None]] = []

    configure_test_binary_dispatch(
        "codex-test",
        lambda exe_name, argv1: calls.append((exe_name, argv1)) or TestBinaryDispatchMode.SKIP,
        argv=[str(tmp_path / CODEX_LINUX_SANDBOX_ARG0)],
        current_exe=tmp_path / "codex",
    )

    assert calls == [(CODEX_LINUX_SANDBOX_ARG0, None)]


def test_classify_must_return_dispatch_mode(tmp_path: Path) -> None:
    # Rust has a typed enum return; Python rejects accidental non-mode values.
    with pytest.raises(TypeError, match="classify must return TestBinaryDispatchMode"):
        configure_test_binary_dispatch(
            "codex-test",
            lambda exe_name, argv1: "InstallAliases",  # type: ignore[return-value]
            argv=["codex", CODEX_FS_HELPER_ARG1],
            current_exe=tmp_path / "codex",
        )


def test_core_style_classifier_routes_special_argv1_values(tmp_path: Path) -> None:
    # Rust usage in core/tests/suite/mod.rs dispatches special argv1 values through arg0 only.
    calls: list[tuple[str, list[str]]] = []

    def classify(exe_name: str, argv1: str | None) -> TestBinaryDispatchMode:
        if argv1 in {CODEX_CORE_APPLY_PATCH_ARG1, CODEX_FS_HELPER_ARG1}:
            return TestBinaryDispatchMode.DISPATCH_ARG0_ONLY
        return TestBinaryDispatchMode.SKIP

    handlers = {
        "core_apply_patch": lambda args: calls.append(("core_apply_patch", args)),
        "fs_helper": lambda args: calls.append(("fs_helper", args)),
    }

    configure_test_binary_dispatch(
        "codex-test",
        classify,
        argv=["codex", CODEX_CORE_APPLY_PATCH_ARG1, "diff"],
        handlers=handlers,
        current_exe=tmp_path / "codex",
    )
    configure_test_binary_dispatch(
        "codex-test",
        classify,
        argv=["codex", CODEX_FS_HELPER_ARG1, "serve"],
        handlers=handlers,
        current_exe=tmp_path / "codex",
    )

    assert calls == [("core_apply_patch", ["diff"]), ("fs_helper", ["serve"])]
