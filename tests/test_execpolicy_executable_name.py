"""Rust-derived tests for codex-execpolicy/src/executable_name.rs."""

from __future__ import annotations

import os
from pathlib import Path

from pycodex.execpolicy import executable_lookup_key, executable_path_lookup_key


def test_executable_lookup_key_matches_target_platform_suffix_rules():
    """Rust: executable_lookup_key lowercases and strips known suffixes on Windows only."""
    if os.name == "nt":
        assert executable_lookup_key("Git.EXE") == "git"
        assert executable_lookup_key("NPM.CMD") == "npm"
        assert executable_lookup_key("BUILD.BAT") == "build"
        assert executable_lookup_key("PING.COM") == "ping"
        assert executable_lookup_key("python") == "python"
    else:
        assert executable_lookup_key("Git.EXE") == "Git.EXE"
        assert executable_lookup_key("NPM.CMD") == "NPM.CMD"
        assert executable_lookup_key("python") == "python"


def test_executable_path_lookup_key_uses_final_component():
    """Rust: executable_path_lookup_key maps Path::file_name through executable_lookup_key."""
    if os.name == "nt":
        assert executable_path_lookup_key(Path("C:/tools/RG.EXE")) == "rg"
    else:
        assert executable_path_lookup_key(Path("/usr/bin/RG.EXE")) == "RG.EXE"


def test_executable_path_lookup_key_returns_none_for_empty_basename():
    """Rust: executable_path_lookup_key returns None when Path::file_name is absent."""
    assert executable_path_lookup_key(Path("/")) is None
