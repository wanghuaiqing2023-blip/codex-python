import pytest

from pycodex.bwrap import (
    BWRAP_UNAVAILABLE_MESSAGE,
    NON_LINUX_MESSAGE,
    build_bwrap_main_plan,
    run_bwrap_main,
)


def test_non_linux_branch_panics_like_rust() -> None:
    # Rust: codex-bwrap/src/main.rs cfg(not(target_os = "linux")).
    plan = build_bwrap_main_plan(["bwrap"], target_os="windows", bwrap_available=True)

    assert plan.branch == "unsupported_os"
    assert plan.message == NON_LINUX_MESSAGE

    with pytest.raises(RuntimeError, match="only supported on Linux"):
        run_bwrap_main(["bwrap"], target_os="darwin", bwrap_available=True)


def test_linux_without_bwrap_available_panics_with_build_message() -> None:
    # Rust: codex-bwrap/src/main.rs cfg(all(target_os = "linux", not(bwrap_available))).
    plan = build_bwrap_main_plan(["bwrap"], target_os="linux", bwrap_available=False)

    assert plan.branch == "unavailable"
    assert "bubblewrap is not available in this build" in plan.message
    assert "libcap headers" in plan.message

    with pytest.raises(RuntimeError) as exc_info:
        run_bwrap_main(["bwrap"], target_os="linux", bwrap_available=False)

    assert str(exc_info.value) == BWRAP_UNAVAILABLE_MESSAGE


def test_linux_available_branch_passes_null_free_argv_to_runner() -> None:
    # Rust: codex-bwrap/src/main.rs cfg(all(target_os = "linux", bwrap_available)).
    calls: list[tuple[str | bytes, ...]] = []

    def runner(argv: tuple[str | bytes, ...]) -> int:
        calls.append(argv)
        return 17

    assert run_bwrap_main(["bwrap", "--version"], target_os="linux", bwrap_available=True, runner=runner) == 17
    assert calls == [("bwrap", "--version")]


def test_linux_available_branch_rejects_embedded_nul_like_cstring() -> None:
    with pytest.raises(RuntimeError, match="failed to convert argv to CString"):
        build_bwrap_main_plan(["bwrap", "bad\x00arg"], target_os="linux", bwrap_available=True)

    with pytest.raises(RuntimeError, match="failed to convert argv to CString"):
        build_bwrap_main_plan([b"bwrap", b"bad\x00arg"], target_os="linux", bwrap_available=True)


def test_linux_available_branch_requires_runner() -> None:
    with pytest.raises(RuntimeError, match="runner is not available"):
        run_bwrap_main(["bwrap"], target_os="linux", bwrap_available=True)
