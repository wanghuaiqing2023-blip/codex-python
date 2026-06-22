"""Rust-derived tests for ``codex-thread-store/src/store.rs`` and ``src/error.rs``."""

from pycodex.protocol import ThreadId
from pycodex.thread_store import ThreadStore, ThreadStoreError


def test_thread_store_protocol_exposes_rust_trait_surface() -> None:
    # Rust crate/module: codex-thread-store src/store.rs.
    # Rust anchor: trait ThreadStore. Behavior contract: Python Protocol exposes
    # the same storage-neutral async operation names, including defaulted Rust
    # pagination/search operations.
    expected_methods = {
        "create_thread",
        "resume_thread",
        "append_items",
        "persist_thread",
        "flush_thread",
        "shutdown_thread",
        "discard_thread",
        "load_history",
        "read_thread",
        "read_thread_by_rollout_path",
        "list_threads",
        "search_threads",
        "list_turns",
        "list_items",
        "update_thread_metadata",
        "archive_thread",
        "unarchive_thread",
    }

    assert expected_methods <= set(ThreadStore.__dict__)
    for method_name in expected_methods:
        assert callable(getattr(ThreadStore, method_name))


def test_thread_store_error_variants_match_rust_messages_and_fields() -> None:
    # Rust crate/module: codex-thread-store src/error.rs.
    # Rust anchor: enum ThreadStoreError display strings and variant fields.
    thread_id = ThreadId.new()

    not_found = ThreadStoreError.thread_not_found(thread_id)
    assert not_found.kind == "thread_not_found"
    assert not_found.fields == {"thread_id": thread_id}
    assert str(not_found) == f"thread {thread_id} not found"

    invalid = ThreadStoreError.invalid_request("bad cursor")
    assert invalid.kind == "invalid_request"
    assert invalid.fields == {"message": "bad cursor"}
    assert str(invalid) == "invalid thread-store request: bad cursor"

    conflict = ThreadStoreError.conflict("live writer exists")
    assert conflict.kind == "conflict"
    assert conflict.fields == {"message": "live writer exists"}
    assert str(conflict) == "thread-store conflict: live writer exists"

    unsupported = ThreadStoreError.unsupported("list_items")
    assert unsupported.kind == "unsupported"
    assert unsupported.fields == {"operation": "list_items"}
    assert str(unsupported) == "thread-store unsupported operation: list_items"

    internal = ThreadStoreError.internal("sqlite unavailable")
    assert internal.kind == "internal"
    assert internal.fields == {"message": "sqlite unavailable"}
    assert str(internal) == "thread-store internal error: sqlite unavailable"
