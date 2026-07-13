from __future__ import annotations

import os

import pytest

from pycodex.windows_sandbox import LaunchDesktop


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows desktop APIs")


def test_interactive_desktop_name_matches_rust() -> None:
    # Rust owner: codex-windows-sandbox::desktop::LaunchDesktop::prepare(false).
    with LaunchDesktop.prepare(False) as desktop:
        assert desktop.startup_name == "Winsta0\\Default"


def test_private_desktop_is_created_with_codex_prefix() -> None:
    # Rust owner: codex-windows-sandbox::desktop::PrivateDesktop::create.
    with LaunchDesktop.prepare(True) as desktop:
        assert desktop.startup_name.startswith("Winsta0\\CodexSandboxDesktop-")
