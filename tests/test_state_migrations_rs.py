import pytest

from pycodex.state import (
    GOALS_MIGRATOR,
    LOGS_MIGRATOR,
    MEMORIES_MIGRATOR,
    STATE_MIGRATOR,
    Migrator,
    runtime_goals_migrator,
    runtime_logs_migrator,
    runtime_memories_migrator,
    runtime_migrator,
    runtime_state_migrator,
)


def test_base_migrators_point_to_rust_embedded_directories() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/migrations.rs::{STATE,LOGS,GOALS,MEMORIES}_MIGRATOR
    # Behavior contract: each migrator anchors the embedded SQL directory used
    # by runtime.rs for its corresponding database.
    assert STATE_MIGRATOR == Migrator("./migrations")
    assert LOGS_MIGRATOR == Migrator("./logs_migrations")
    assert GOALS_MIGRATOR == Migrator("./goals_migrations")
    assert MEMORIES_MIGRATOR == Migrator("./memory_migrations")


def test_runtime_migrator_preserves_base_config_except_ignore_missing() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/migrations.rs::runtime_migrator
    # Behavior contract: runtime migrators borrow the same migration set and
    # preserve config while setting ignore_missing=true for newer DB tolerance.
    base = Migrator(
        "./custom",
        ignore_missing=False,
        locking=False,
        no_tx=True,
        table_name="custom_migrations",
        create_schemas=("main", "aux"),
    )

    runtime = runtime_migrator(base)

    assert runtime is not base
    assert runtime == Migrator(
        "./custom",
        ignore_missing=True,
        locking=False,
        no_tx=True,
        table_name="custom_migrations",
        create_schemas=("main", "aux"),
    )
    assert base.ignore_missing is False


def test_runtime_migrator_rejects_non_migrator_values() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/migrations.rs::runtime_migrator
    # Behavior contract: Python keeps the Rust typed boundary explicit for the
    # dependency-light value-object port.
    with pytest.raises(TypeError, match="base must be a Migrator"):
        runtime_migrator(object())  # type: ignore[arg-type]


def test_runtime_migrator_helpers_wrap_the_matching_base_migrators() -> None:
    # Rust crate: codex-state
    # Rust module/items: runtime_state/logs/goals/memories_migrator
    # Behavior contract: each helper wraps the corresponding base migrator.
    assert runtime_state_migrator() == runtime_migrator(STATE_MIGRATOR)
    assert runtime_logs_migrator() == runtime_migrator(LOGS_MIGRATOR)
    assert runtime_goals_migrator() == runtime_migrator(GOALS_MIGRATOR)
    assert runtime_memories_migrator() == runtime_migrator(MEMORIES_MIGRATOR)
