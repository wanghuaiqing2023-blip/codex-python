from __future__ import annotations

import importlib


def test_child_module_items_have_rust_aligned_python_owners() -> None:
    # Rust: codex-responses-api-proxy/src/lib.rs declares private dump and
    # read_api_key modules; their production items must not be flattened into
    # the crate root.
    dump = importlib.import_module("pycodex.responses_api_proxy.dump")
    read_api_key = importlib.import_module(
        "pycodex.responses_api_proxy.read_api_key"
    )

    assert dump.ExchangeDumper.__module__ == dump.__name__
    assert dump.ResponseBodyDump.__module__ == dump.__name__
    assert read_api_key.read_auth_header_with.__module__ == read_api_key.__name__
    assert read_api_key.validate_auth_header_bytes.__module__ == read_api_key.__name__


def test_private_child_items_are_not_crate_root_exports() -> None:
    from pycodex import responses_api_proxy

    for name in (
        "AUTH_HEADER_PREFIX",
        "BUFFER_SIZE",
        "ExchangeDump",
        "ExchangeDumper",
        "REDACTED_HEADER_VALUE",
        "ResponseBodyDump",
        "read_auth_header_with",
        "validate_auth_header_bytes",
    ):
        assert name not in responses_api_proxy.__all__
