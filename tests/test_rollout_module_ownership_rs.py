import importlib

import pytest

from pycodex.login.auth.default_client import create_client as login_create_client
from pycodex.state import StateRuntime


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("", "SESSIONS_SUBDIR"),
        ("config", "RolloutConfigView"),
        ("config", "RolloutConfig"),
        ("default_client", "create_client"),
        ("list", "ThreadListConfig"),
        ("list", "get_threads"),
        ("metadata", "extract_metadata_from_rollout"),
        ("policy", "is_persisted_rollout_item"),
        ("recorder", "RolloutRecorder"),
        ("search", "search_rollout_paths"),
        ("session_index", "append_thread_name"),
        ("sqlite_metrics", "sqlite_metrics_recorder"),
        ("state_db", "StateDbHandle"),
        ("state_db", "sqlite_telemetry_recorder"),
        ("state_db", "try_init"),
        ("state_db", "get_state_db"),
        ("state_db", "reconcile_rollout"),
        ("state_db", "list_threads_db"),
    ],
)
def test_rollout_item_has_rust_aligned_owner(
    module_name: str,
    symbol: str,
) -> None:
    """Rust source: codex-rollout module graph rooted at src/lib.rs."""
    suffix = f".{module_name}" if module_name else ""
    module = importlib.import_module(f"pycodex.rollout{suffix}")
    item = getattr(module, symbol)
    if module_name == "default_client":
        assert item is login_create_client
        return
    if module_name == "state_db" and symbol == "StateDbHandle":
        assert item is StateRuntime
        return
    if callable(item):
        assert item.__module__ == module.__name__


@pytest.mark.parametrize(
    "symbol",
    [
        "RolloutConfigView",
        "ThreadListConfig",
        "StateDbHandle",
        "sqlite_telemetry_recorder",
    ],
)
def test_rollout_lib_reexports_rust_public_api(symbol: str) -> None:
    """Rust source: codex-rollout/src/lib.rs public re-exports."""
    rollout = importlib.import_module("pycodex.rollout")
    assert hasattr(rollout, symbol)
