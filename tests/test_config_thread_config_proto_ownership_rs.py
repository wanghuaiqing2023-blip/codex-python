from __future__ import annotations

import importlib


def test_generated_thread_config_proto_modules_have_distinct_owners() -> None:
    # Rust: config/src/thread_config/remote.rs #[path = "proto/..."] mod proto.
    expected = {
        "proto": ["LoadThreadConfigRequest", "LoadThreadConfigResponse", "WireApi"],
        "proto.thread_config_source": ["Source"],
        "proto.thread_config_loader_client": ["ThreadConfigLoaderClient"],
        "proto.thread_config_loader_server": [
            "ThreadConfigLoader",
            "ThreadConfigLoaderServer",
        ],
    }
    for suffix, symbols in expected.items():
        module = importlib.import_module(
            f"pycodex.config.thread_config.remote.{suffix}"
        )
        for symbol in symbols:
            assert getattr(module, symbol).__module__ == module.__name__


def test_generated_request_preserves_wire_fields() -> None:
    proto = importlib.import_module("pycodex.config.thread_config.remote.proto")
    request = proto.LoadThreadConfigRequest(thread_id="thread-1", cwd="/workspace")

    assert request.to_mapping() == {
        "thread_id": "thread-1",
        "cwd": "/workspace",
    }
    assert (
        proto.WireApi.from_str_name("WIRE_API_RESPONSES")
        is proto.WireApi.RESPONSES
    )
