"""Prepared parity tests for Rust ``codex-ollama/src/url.rs``.

Pytest is deferred until the full ``codex-ollama`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

from pycodex.ollama.url import base_url_to_host_root, is_openai_compatible_base_url


def test_base_url_to_host_root_matches_rust_cases() -> None:
    # Rust source: url.rs test_base_url_to_host_root.
    assert base_url_to_host_root("http://localhost:11434/v1") == "http://localhost:11434"
    assert base_url_to_host_root("http://localhost:11434") == "http://localhost:11434"
    assert base_url_to_host_root("http://localhost:11434/") == "http://localhost:11434"


def test_base_url_to_host_root_trims_openai_compat_trailing_slashes() -> None:
    # Rust source: trim_end_matches('/') before removing a terminal /v1 segment.
    assert base_url_to_host_root("http://localhost:11434/v1/") == "http://localhost:11434"
    assert base_url_to_host_root("http://localhost:11434///") == "http://localhost:11434"


def test_is_openai_compatible_base_url() -> None:
    # Rust source: is_openai_compatible_base_url trims trailing slash and checks terminal /v1.
    assert is_openai_compatible_base_url("http://localhost:11434/v1")
    assert is_openai_compatible_base_url("http://localhost:11434/v1/")
    assert not is_openai_compatible_base_url("http://localhost:11434")
    assert not is_openai_compatible_base_url("http://localhost:11434/v1/models")
