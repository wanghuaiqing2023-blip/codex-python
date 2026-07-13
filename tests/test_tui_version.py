from pycodex import __version__
from pycodex.tui.version import CODEX_CLI_VERSION


def test_codex_cli_version_matches_workspace_package_version():
    # Rust: codex-tui, version.rs, CODEX_CLI_VERSION = env!("CARGO_PKG_VERSION").
    assert CODEX_CLI_VERSION == __version__
