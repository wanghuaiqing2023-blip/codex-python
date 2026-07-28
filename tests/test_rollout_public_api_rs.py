from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.rollout.config import RolloutConfig, RolloutConfigView
from pycodex.rollout.list import ThreadListConfig, ThreadListLayout
from pycodex.rollout.sqlite_metrics import SqliteMetricsRecorder
from pycodex.rollout.state_db import (
    StateDbHandle,
    get_state_db,
    reconcile_rollout,
    sqlite_telemetry_recorder,
    try_init,
)
from pycodex.state import StateRuntime
from pycodex.state import get_backfill_state
from pycodex.state.model.backfill_state import BackfillStatus


def test_rollout_config_implements_rollout_config_view(tmp_path: Path) -> None:
    """Rust source: codex-rollout/src/config.rs RolloutConfigView impl."""
    config = RolloutConfig(
        codex_home=tmp_path / "codex",
        sqlite_home=tmp_path / "sqlite",
        cwd=tmp_path,
        model_provider_id="openai",
        generate_memories=True,
    )

    assert isinstance(config, RolloutConfigView)
    assert RolloutConfig.from_view(config) == config


def test_thread_list_config_matches_rust_fields(tmp_path: Path) -> None:
    """Rust source: codex-rollout/src/list.rs ThreadListConfig."""
    config = ThreadListConfig(
        allowed_sources=(),
        model_providers=("openai",),
        cwd_filters=(tmp_path,),
        default_provider="openai",
        layout=ThreadListLayout.FLAT,
    )

    assert config.model_providers == ("openai",)
    assert config.cwd_filters == (tmp_path,)
    assert config.layout is ThreadListLayout.FLAT


def test_state_db_handle_and_telemetry_reexport_real_owners() -> None:
    """Rust source: codex-rollout/src/state_db.rs public aliases."""

    class Metrics:
        def counter(self, *args):
            return args

        def record_duration(self, *args):
            return args

    assert StateDbHandle is StateRuntime
    assert isinstance(sqlite_telemetry_recorder(Metrics(), "codex_cli_rs"), SqliteMetricsRecorder)


@pytest.mark.asyncio
async def test_try_init_completes_backfill_and_get_state_db_reopens(
    tmp_path: Path,
) -> None:
    """Rust source: state_db.rs try_init/get_state_db startup contract."""
    config = RolloutConfig(
        codex_home=tmp_path / "codex",
        sqlite_home=tmp_path / "sqlite",
        cwd=tmp_path,
        model_provider_id="openai",
        generate_memories=False,
    )

    runtime = await try_init(config)
    assert isinstance(runtime, StateRuntime)
    state = await get_backfill_state(runtime.state_db)
    assert state.status is BackfillStatus.COMPLETE
    await runtime.close()

    reopened = await get_state_db(config)
    assert isinstance(reopened, StateRuntime)
    await reopened.close()


@pytest.mark.asyncio
async def test_reconcile_rollout_none_context_is_noop(tmp_path: Path) -> None:
    """Rust source: state_db.rs reconcile_rollout returns for None context."""
    await reconcile_rollout(
        None,
        tmp_path / "missing.jsonl",
        "openai",
        None,
        (),
        None,
        None,
    )
