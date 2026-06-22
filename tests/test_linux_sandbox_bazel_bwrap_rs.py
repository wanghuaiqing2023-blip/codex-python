from pathlib import Path

from pycodex.linux_sandbox import bazel_bwrap


def test_candidate_disabled_outside_debug_assertions() -> None:
    # Rust source: codex-linux-sandbox/src/bazel_bwrap.rs candidate() returns
    # None under cfg(not(debug_assertions)).
    env = {
        "BAZEL_PACKAGE": "codex/codex-rs/linux-sandbox",
        "RUNFILES_DIR": "/runfiles",
        "CARGO_BIN_EXE_bwrap": "/bin/bwrap",
    }
    assert bazel_bwrap.candidate(env, debug_assertions=False) is None


def test_candidate_requires_bazel_package_and_runfiles_env() -> None:
    # Rust source: candidate() first checks option_env!("BAZEL_PACKAGE") and
    # runfiles_env_present().
    env = {"CARGO_BIN_EXE_bwrap": "/bin/bwrap"}
    assert bazel_bwrap.candidate(env, bazel_package_present=False) is None
    assert bazel_bwrap.candidate(env, bazel_package_present=True) is None


def test_candidate_returns_absolute_bwrap_env_value() -> None:
    # Rust source: absolute CARGO_BIN_EXE_bwrap values are returned directly.
    env = {
        "RUNFILES_DIR": "/runfiles",
        "CARGO_BIN_EXE_bwrap": "/bin/bwrap",
    }
    assert bazel_bwrap.candidate(env, bazel_package_present=True) == Path("/bin/bwrap")


def test_resolve_runfile_prefers_runfiles_roots_with_workspace_prefix(tmp_path: Path) -> None:
    # Rust source: resolve_runfile() probes logical path and
    # TEST_WORKSPACE/logical path under RUNFILES_DIR and TEST_SRCDIR.
    runfiles = tmp_path / "runfiles"
    target = runfiles / "workspace" / "pkg" / "bwrap"
    target.parent.mkdir(parents=True)
    target.write_text("binary", encoding="utf-8")

    env = {
        "RUNFILES_DIR": str(runfiles),
        "TEST_WORKSPACE": "workspace",
    }
    assert bazel_bwrap.resolve_runfile("pkg/bwrap", env) == target


def test_resolve_runfile_uses_manifest_mapping(tmp_path: Path) -> None:
    # Rust source: resolve_runfile() scans RUNFILES_MANIFEST_FILE for
    # "logical_path physical_path" entries.
    physical = tmp_path / "real-bwrap"
    manifest = tmp_path / "MANIFEST"
    manifest.write_text(f"workspace/pkg/bwrap {physical}\n", encoding="utf-8")

    env = {
        "RUNFILES_MANIFEST_FILE": str(manifest),
        "TEST_WORKSPACE": "workspace",
    }
    assert bazel_bwrap.resolve_runfile("pkg/bwrap", env) == physical
