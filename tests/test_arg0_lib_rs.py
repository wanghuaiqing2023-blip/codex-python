from __future__ import annotations

import os
from pathlib import Path

import pytest

from pycodex.arg0 import (
    APPLY_PATCH_ARG0,
    CODEX_CORE_APPLY_PATCH_ARG1,
    CODEX_FS_HELPER_ARG1,
    CODEX_LINUX_SANDBOX_ARG0,
    EXECVE_WRAPPER_ARG0,
    ILLEGAL_ENV_VAR_PREFIX,
    LOCK_FILENAME,
    MISSPELLED_APPLY_PATCH_ARG0,
    Arg0DispatchPaths,
    Arg0PathEntryGuard,
    arg0_dispatch,
    janitor_cleanup,
    linux_sandbox_exe_path,
    load_dotenv,
    prepend_path_entry_for_codex_aliases,
    set_filtered,
    try_lock_dir,
)


def test_linux_sandbox_exe_path_prefers_codex_linux_sandbox_alias(tmp_path: Path) -> None:
    # Rust: codex-arg0/src/lib.rs test linux_sandbox_exe_path_prefers_codex_linux_sandbox_alias.
    alias_path = tmp_path / CODEX_LINUX_SANDBOX_ARG0
    current_exe = tmp_path / "codex"
    temp_dir = _temporary_directory_like(tmp_path)
    lock_file = (tmp_path / LOCK_FILENAME).open("w+b")
    guard = Arg0PathEntryGuard(
        temp_dir,
        lock_file,
        Arg0DispatchPaths(
            codex_self_exe=current_exe,
            codex_linux_sandbox_exe=alias_path,
            main_execve_wrapper_exe=None,
        ),
    )
    try:
        assert linux_sandbox_exe_path(guard, current_exe) == alias_path
    finally:
        guard.close()


def test_janitor_skips_dirs_without_lock_file(tmp_path: Path) -> None:
    # Rust: codex-arg0/src/lib.rs test janitor_skips_dirs_without_lock_file.
    directory = tmp_path / "no-lock"
    directory.mkdir()

    janitor_cleanup(tmp_path)

    assert directory.exists()


def test_janitor_skips_dirs_with_held_lock(tmp_path: Path) -> None:
    # Rust: codex-arg0/src/lib.rs test janitor_skips_dirs_with_held_lock.
    directory = tmp_path / "locked"
    directory.mkdir()
    (directory / LOCK_FILENAME).write_bytes(b"lock")
    held_lock = try_lock_dir(directory)
    assert held_lock is not None
    try:
        janitor_cleanup(tmp_path)
        assert directory.exists()
    finally:
        held_lock.close()


def test_janitor_removes_dirs_with_unlocked_lock(tmp_path: Path) -> None:
    # Rust: codex-arg0/src/lib.rs test janitor_removes_dirs_with_unlocked_lock.
    directory = tmp_path / "stale"
    directory.mkdir()
    (directory / LOCK_FILENAME).write_bytes(b"lock")

    janitor_cleanup(tmp_path)

    assert not directory.exists()


def test_set_filtered_skips_codex_prefixed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: set_filtered rejects any key whose uppercase form starts with CODEX_.
    monkeypatch.delenv("CODEX_SECRET", raising=False)
    monkeypatch.delenv("codex_lower_secret", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    set_filtered(
        [
            ("CODEX_SECRET", "blocked"),
            ("codex_lower_secret", "blocked"),
            ("OPENAI_API_KEY", "allowed"),
        ]
    )

    assert os.environ.get("CODEX_SECRET") is None
    assert os.environ.get("codex_lower_secret") is None
    assert os.environ["OPENAI_API_KEY"] == "allowed"
    assert ILLEGAL_ENV_VAR_PREFIX == "CODEX_"


def test_load_dotenv_reads_codex_home_env_and_filters_codex_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Rust: load_dotenv reads ~/.codex/.env via find_codex_home and applies set_filtered.
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "NORMAL=value",
                "CODEX_BLOCKED=secret",
                "QUOTED=\"two words\"",
                "# ignored",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("NORMAL", raising=False)
    monkeypatch.delenv("CODEX_BLOCKED", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)

    load_dotenv(tmp_path)

    assert os.environ["NORMAL"] == "value"
    assert os.environ["QUOTED"] == "two words"
    assert os.environ.get("CODEX_BLOCKED") is None


def test_prepend_path_entry_for_codex_aliases_creates_aliases_and_prepends_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Rust: prepend_path_entry_for_codex_aliases creates CODEX_HOME-scoped aliases and prepends PATH.
    current_exe = tmp_path / "codex"
    current_exe.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PATH", "original-path")

    guard = prepend_path_entry_for_codex_aliases(codex_home=tmp_path, current_exe=current_exe)
    path_entry = Path(os.environ["PATH"].split(os.pathsep, 1)[0])
    try:
        assert path_entry.parent == tmp_path / "tmp" / "arg0"
        assert path_entry.exists()
        assert (path_entry / LOCK_FILENAME).exists()
        if os.name == "nt":
            assert (path_entry / f"{APPLY_PATCH_ARG0}.bat").exists()
            assert (path_entry / f"{MISSPELLED_APPLY_PATCH_ARG0}.bat").exists()
        else:
            assert (path_entry / APPLY_PATCH_ARG0).is_symlink()
            assert (path_entry / MISSPELLED_APPLY_PATCH_ARG0).is_symlink()
        assert guard.paths.codex_self_exe == current_exe
        assert os.environ["PATH"].endswith(f"{os.pathsep}original-path")
    finally:
        guard.close()


def test_arg0_dispatch_invokes_special_process_handlers(tmp_path: Path) -> None:
    # Rust: arg0_dispatch branches on argv0/argv1 aliases before regular startup.
    calls: list[tuple[str, list[str]]] = []

    def record(name: str):
        def handler(args: list[str]) -> None:
            calls.append((name, args))

        return handler

    handlers = {
        "execve_wrapper": record("execve_wrapper"),
        "linux_sandbox": record("linux_sandbox"),
        "apply_patch": record("apply_patch"),
        "fs_helper": record("fs_helper"),
        "core_apply_patch": record("core_apply_patch"),
    }

    assert arg0_dispatch([EXECVE_WRAPPER_ARG0, "file", "arg"], handlers, tmp_path) is None
    assert arg0_dispatch([CODEX_LINUX_SANDBOX_ARG0, "--flag"], handlers, tmp_path) is None
    assert arg0_dispatch([APPLY_PATCH_ARG0, "patch"], handlers, tmp_path) is None
    assert arg0_dispatch(["codex", CODEX_FS_HELPER_ARG1, "serve"], handlers, tmp_path) is None
    assert arg0_dispatch(["codex", CODEX_CORE_APPLY_PATCH_ARG1, "diff"], handlers, tmp_path) is None

    assert calls == [
        ("execve_wrapper", ["file", "arg"]),
        ("linux_sandbox", ["--flag"]),
        ("apply_patch", ["patch"]),
        ("fs_helper", ["serve"]),
        ("core_apply_patch", ["diff"]),
    ]


class _temporary_directory_like:
    def __init__(self, path: Path) -> None:
        self.name = str(path)

    def cleanup(self) -> None:
        pass
