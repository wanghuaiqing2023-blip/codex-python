from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from pycodex.memories.write import (
    MemoryStartupContext,
    PHASE_TWO_DISABLED_FEATURES,
    PhaseTwoClaim,
    STAGE_TWO_MODEL,
    STAGE_TWO_REASONING_EFFORT,
    STAGE_TWO_JOB_LEASE_SECONDS,
    STAGE_TWO_JOB_RETRY_DELAY_SECONDS,
    SpawnedConsolidationAgent,
    Stage1Output,
    emit_phase_two_metrics,
    emit_phase_two_token_usage_metrics,
    memory_root,
    memory_workspace_diff,
    prepare_memory_workspace,
    phase_two_claim,
    phase_two_agent_config,
    phase_two_agent_prompt,
    phase_two_get_watermark,
    phase_two_handle_agent_completion,
    phase_two_is_final_agent_status,
    phase_two_loop_agent,
    phase_two_mark_failed,
    phase_two_mark_succeeded,
    phase_two_run,
    reset_memory_workspace_baseline,
    sync_phase2_workspace_inputs,
)
from pycodex.protocol import AgentStatus, TokenUsage
from pycodex.state import Phase2JobClaimOutcome, Phase2JobClaimed


def memory(thread_id: str, updated_at: datetime, raw: str = "raw", summary: str = "summary") -> Stage1Output:
    return Stage1Output(
        thread_id=thread_id,
        rollout_path=Path(f"/rollouts/{thread_id}.jsonl"),
        source_updated_at=updated_at,
        raw_memory=raw,
        rollout_summary=summary,
        rollout_slug=thread_id,
        cwd=Path("/workspace"),
        git_branch=f"branch-{thread_id}",
    )


def context() -> MemoryStartupContext:
    return MemoryStartupContext(
        thread_manager="thread-manager",
        auth_manager="auth-manager",
        thread_id="thread-1",
        thread=SimpleNamespace(),
        config=SimpleNamespace(),
        source="cli",
        state_db_value={"db": "ok"},
        counters=[],
        histograms=[],
    )


class StateDb:
    def __init__(self, store) -> None:
        self.store = store

    def memories(self):
        return self.store


class Phase2Store:
    def __init__(self, outcome=None) -> None:
        self.outcome = outcome if outcome is not None else Phase2JobClaimed("lease-1", 100)
        self.calls: list[tuple] = []
        self.fail_result = True
        self.succeed_result = True
        self.heartbeat_results: list[object] = [True]
        self.phase2_inputs: list[Stage1Output] = []

    async def try_claim_global_phase2_job(self, worker_id, lease_seconds):
        self.calls.append(("claim", worker_id, lease_seconds))
        return self.outcome

    async def get_phase2_input_selection(self, max_raw_memories, max_unused_days):
        self.calls.append(("inputs", max_raw_memories, max_unused_days))
        return list(self.phase2_inputs[:max_raw_memories])

    async def mark_global_phase2_job_failed(self, token, reason, retry_delay_seconds):
        self.calls.append(("failed", token, reason, retry_delay_seconds))
        return self.fail_result

    async def mark_global_phase2_job_failed_if_unowned(self, token, reason, retry_delay_seconds):
        self.calls.append(("failed_if_unowned", token, reason, retry_delay_seconds))
        return True

    async def mark_global_phase2_job_succeeded(self, token, completion_watermark, selected_outputs):
        self.calls.append(("succeeded", token, completion_watermark, list(selected_outputs)))
        return self.succeed_result

    async def heartbeat_global_phase2_job(self, token, lease_seconds):
        self.calls.append(("heartbeat", token, lease_seconds))
        if not self.heartbeat_results:
            return True
        result = self.heartbeat_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def phase2_context(store: Phase2Store) -> MemoryStartupContext:
    return MemoryStartupContext(
        thread_manager="thread-manager",
        auth_manager="auth-manager",
        thread_id="worker-1",
        thread=SimpleNamespace(),
        config=SimpleNamespace(),
        source="cli",
        state_db_value=StateDb(store),
        counters=[],
        histograms=[],
    )


class FeatureSet:
    def __init__(self) -> None:
        self.disabled: list[str] = []

    def disable(self, feature: str) -> bool:
        self.disabled.append(feature)
        return True


class Permissions:
    def __init__(self) -> None:
        self.approval_policy = "on_request"
        self.sandbox_calls: list[tuple] = []
        self.sandbox_policy = None

    def set_legacy_sandbox_policy(self, policy, cwd):
        self.sandbox_calls.append((policy, cwd))
        return True


def agent_config(tmp_path: Path, *, consolidation_model: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        codex_home=tmp_path,
        cwd=tmp_path / "workspace",
        ephemeral=False,
        memories=SimpleNamespace(
            generate_memories=True,
            use_memories=True,
            consolidation_model=consolidation_model,
            max_raw_memories_for_consolidation=20,
            max_unused_days=30,
        ),
        include_apps_instructions=True,
        mcp_servers={"server": object()},
        permissions=Permissions(),
        features=FeatureSet(),
        model="foreground-model",
        model_reasoning_effort="high",
    )


def test_phase_two_get_watermark_uses_latest_memory_timestamp_or_claimed_watermark() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::get_watermark
    # Contract: completion watermark is max(claimed_watermark, latest selected memory source_updated_at timestamp).
    older = memory("old", datetime.fromtimestamp(90, tz=UTC))
    newer = memory("new", datetime.fromtimestamp(130, tz=UTC))

    assert phase_two_get_watermark(100, [older, newer]) == 130
    assert phase_two_get_watermark(140, [older, newer]) == 140
    assert phase_two_get_watermark(77, []) == 77


def test_phase_two_is_final_agent_status_matches_rust_nonfinal_variants() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::is_final_agent_status
    # Contract: only PendingInit, Running, and Interrupted are non-final; every other AgentStatus is final.
    assert not phase_two_is_final_agent_status(AgentStatus.pending_init())
    assert not phase_two_is_final_agent_status(AgentStatus.running())
    assert not phase_two_is_final_agent_status(AgentStatus.interrupted())
    assert phase_two_is_final_agent_status(AgentStatus.completed("done"))
    assert phase_two_is_final_agent_status(AgentStatus.errored("boom"))
    assert phase_two_is_final_agent_status(AgentStatus.shutdown())
    assert phase_two_is_final_agent_status(AgentStatus.not_found())


def test_emit_phase_two_metrics_records_input_and_agent_spawned() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::emit_metrics
    # Contract: positive input count emits input counter and every dispatch emits agent_spawned.
    ctx = context()

    emit_phase_two_metrics(ctx, 3)

    assert ctx.counters == [
        ("codex.memory.phase2.input", 3, ()),
        ("codex.memory.phase2", 1, (("status", "agent_spawned"),)),
    ]

    empty_ctx = context()
    emit_phase_two_metrics(empty_ctx, 0)
    assert empty_ctx.counters == [("codex.memory.phase2", 1, (("status", "agent_spawned"),))]


def test_emit_phase_two_token_usage_metrics_clamps_negative_values() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::emit_token_usage_metrics
    # Contract: token usage histograms mirror Rust token_type tags and clamp negative raw fields to zero.
    ctx = context()

    emit_phase_two_token_usage_metrics(
        ctx,
        TokenUsage(
            input_tokens=-1,
            cached_input_tokens=-2,
            output_tokens=3,
            reasoning_output_tokens=-4,
            total_tokens=5,
        ),
    )

    assert ctx.histograms == [
        ("codex.memory.phase2.token_usage", 5, (("token_type", "total"),)),
        ("codex.memory.phase2.token_usage", 0, (("token_type", "input"),)),
        ("codex.memory.phase2.token_usage", 0, (("token_type", "cached_input"),)),
        ("codex.memory.phase2.token_usage", 3, (("token_type", "output"),)),
        ("codex.memory.phase2.token_usage", 0, (("token_type", "reasoning_output"),)),
    ]


def test_sync_phase2_workspace_inputs_syncs_current_selection_and_prunes_extensions(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::sync_phase2_workspace_inputs
    # Contract: phase2 sync writes rollout summaries/raw memories using the selected memory count, then prunes old extension resources.
    root = tmp_path / "memories"
    now = datetime.fromtimestamp(1_775_476_799, tz=UTC)
    selected = [
        memory("a", now, raw="raw A", summary="summary A"),
        memory("b", datetime.fromtimestamp(1_775_476_900, tz=UTC), raw="raw B", summary="summary B"),
    ]
    resources = root / "extensions" / "chronicle" / "resources"
    resources.mkdir(parents=True)
    (root / "extensions" / "chronicle" / "instructions.md").write_text("instructions", encoding="utf-8")
    old_resource = resources / "2026-04-06T11-59-59-abcd-old.md"
    old_resource.write_text("old", encoding="utf-8")

    asyncio.run(sync_phase2_workspace_inputs(root, selected))

    raw_memories = (root / "raw_memories.md").read_text(encoding="utf-8")
    summaries = sorted(path.read_text(encoding="utf-8") for path in (root / "rollout_summaries").glob("*.md"))
    assert "raw A" in raw_memories
    assert "raw B" in raw_memories
    assert len(summaries) == 2
    assert any("summary A" in summary for summary in summaries)
    assert any("summary B" in summary for summary in summaries)
    assert not old_resource.exists()


def test_phase_two_claim_maps_rust_outcomes_and_records_claim_metric() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::job::claim
    # Contract: claimed phase2 jobs emit a claimed counter and skipped Rust outcomes map to stable reason strings.
    store = Phase2Store(Phase2JobClaimed("lease-1", 321))
    ctx = phase2_context(store)

    claim = asyncio.run(phase_two_claim(ctx))

    assert claim == PhaseTwoClaim(token="lease-1", watermark=321)
    assert store.calls == [("claim", "worker-1", STAGE_TWO_JOB_LEASE_SECONDS)]
    assert ctx.counters == [("codex.memory.phase2", 1, (("status", "claimed"),))]

    for outcome, expected in [
        (Phase2JobClaimOutcome.SKIPPED_RETRY_UNAVAILABLE, "skipped_retry_unavailable"),
        (Phase2JobClaimOutcome.SKIPPED_COOLDOWN, "skipped_cooldown"),
        (Phase2JobClaimOutcome.SKIPPED_RUNNING, "skipped_running"),
    ]:
        skipped_ctx = phase2_context(Phase2Store(outcome))
        assert asyncio.run(phase_two_claim(skipped_ctx)) == expected
        assert skipped_ctx.counters == []


def test_phase_two_failed_uses_strict_update_then_unowned_fallback() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::job::failed
    # Contract: phase2 failure records a reason counter; if strict ownership update returns false, Rust tries the unowned fallback update.
    store = Phase2Store()
    store.fail_result = False
    ctx = phase2_context(store)
    claim = PhaseTwoClaim(token="lease-1", watermark=100)

    asyncio.run(phase_two_mark_failed(ctx, ctx.state_db(), claim, "failed_agent"))

    assert ctx.counters == [("codex.memory.phase2", 1, (("status", "failed_agent"),))]
    assert store.calls == [
        ("failed", "lease-1", "failed_agent", STAGE_TWO_JOB_RETRY_DELAY_SECONDS),
        ("failed_if_unowned", "lease-1", "failed_agent", STAGE_TWO_JOB_RETRY_DELAY_SECONDS),
    ]


def test_phase_two_succeed_records_reason_counter_and_persists_watermark_selection() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::job::succeed
    # Contract: phase2 success records the reason counter and delegates completion watermark plus selected outputs to the state runtime.
    store = Phase2Store()
    ctx = phase2_context(store)
    claim = PhaseTwoClaim(token="lease-1", watermark=100)
    selected = [memory("a", datetime.fromtimestamp(120, tz=UTC))]

    assert asyncio.run(phase_two_mark_succeeded(ctx, ctx.state_db(), claim, 120, selected, "succeeded")) is True

    assert ctx.counters == [("codex.memory.phase2", 1, (("status", "succeeded"),))]
    assert store.calls == [("succeeded", "lease-1", 120, selected)]

    store.succeed_result = False
    assert asyncio.run(phase_two_mark_succeeded(ctx, ctx.state_db(), claim, 121, [], "succeeded")) is False


def test_phase_two_agent_config_hardens_consolidation_worker(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::agent::get_config
    # Contract: phase2 consolidation agent config is cloned, rooted at memories/, ephemeral, memory-recursion disabled, no apps/MCP/plugins/collab recursion, approval never, workspace-write/no-network sandbox, and stage-two model defaults.
    cfg = agent_config(tmp_path)

    hardened = phase_two_agent_config(cfg)

    assert hardened is not cfg
    root = tmp_path / "memories"
    assert hardened.cwd == root
    assert hardened.ephemeral is True
    assert hardened.memories.generate_memories is False
    assert hardened.memories.use_memories is False
    assert hardened.include_apps_instructions is False
    assert hardened.mcp_servers == {}
    assert hardened.permissions.approval_policy == "never"
    assert hardened.permissions.sandbox_calls == [
        (
            {
                "type": "workspace_write",
                "writable_roots": [root],
                "network_access": False,
                "exclude_tmpdir_env_var": True,
                "exclude_slash_tmp": True,
            },
            root,
        )
    ]
    assert hardened.permissions.sandbox_policy["network_access"] is False
    assert hardened.permissions.sandbox_policy["writable_roots"] == [root]
    assert hardened.features.disabled == list(PHASE_TWO_DISABLED_FEATURES)
    assert hardened.model == STAGE_TWO_MODEL
    assert hardened.model_reasoning_effort == STAGE_TWO_REASONING_EFFORT

    assert cfg.cwd == tmp_path / "workspace"
    assert cfg.memories.generate_memories is True
    assert cfg.permissions.approval_policy == "on_request"


def test_phase_two_agent_config_uses_configured_model_and_prompt_text(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::agent::{get_config,get_prompt}
    # Contract: configured consolidation_model overrides the stage-two default and get_prompt returns a single text UserInput containing the consolidation prompt.
    cfg = agent_config(tmp_path, consolidation_model="custom-consolidator")

    hardened = phase_two_agent_config(cfg)
    prompt = phase_two_agent_prompt(tmp_path / "memories")

    assert hardened.model == "custom-consolidator"
    assert len(prompt) == 1
    assert prompt[0].type == "text"
    assert "phase2_workspace_diff.md" in (prompt[0].text or "")
    assert "memories" in (prompt[0].text or "")


def test_phase_two_run_tracks_workspace_diff_spawns_agent_and_resets_baseline(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/phase2.rs::run and src/startup_tests.rs::memories_startup_phase2_tracks_workspace_diff_across_runs
    # Contract: phase2 run claims the global job, prepares the memory workspace, syncs DB-selected inputs,
    # writes a workspace diff for the consolidation agent prompt, handles a completed agent, resets the
    # workspace baseline, and marks the job succeeded with the new selected-output watermark.
    async def scenario() -> tuple[str, Phase2Store, MemoryStartupContext, list[tuple], Path]:
        cfg = agent_config(tmp_path)
        cfg.memories.max_raw_memories_for_consolidation = 1
        cfg.memories.max_unused_days = 14
        root = memory_root(tmp_path)
        older = memory(
            "rollout-a",
            datetime.fromtimestamp(1_800_000_000, tz=UTC),
            raw="raw memory A",
            summary="rollout summary A",
        )
        newer = memory(
            "rollout-b",
            datetime.fromtimestamp(1_800_000_300, tz=UTC),
            raw="raw memory B",
            summary="rollout summary B",
        )

        await prepare_memory_workspace(root)
        await sync_phase2_workspace_inputs(root, [older])
        await reset_memory_workspace_baseline(root)

        store = Phase2Store(Phase2JobClaimed("lease-1", 1_799_999_000))
        store.phase2_inputs = [newer]
        ctx = phase2_context(store)
        spawned: list[tuple] = []
        shutdowns: list[SpawnedConsolidationAgent] = []

        async def spawn(config_arg, prompt):
            prompt_list = list(prompt)
            diff_path = root / "phase2_workspace_diff.md"
            spawned.append((config_arg, prompt_list, diff_path.read_text(encoding="utf-8")))
            thread = Phase2Thread([AgentStatus.completed("done")])
            return SpawnedConsolidationAgent("agent-thread", thread)

        async def shutdown(agent):
            shutdowns.append(agent)

        ctx.spawn_consolidation_agent = spawn
        ctx.shutdown_consolidation_agent = shutdown

        result = await phase_two_run(ctx, cfg)
        spawned.append(("shutdowns", list(shutdowns)))
        return result, store, ctx, spawned, root

    result, store, ctx, spawned, root = asyncio.run(scenario())

    assert result == "completed"
    assert store.calls == [
        ("claim", "worker-1", STAGE_TWO_JOB_LEASE_SECONDS),
        ("inputs", 1, 14),
        ("heartbeat", "lease-1", STAGE_TWO_JOB_LEASE_SECONDS),
        ("succeeded", "lease-1", 1_800_000_300, store.phase2_inputs),
    ]
    config_arg, prompt, rendered_diff = spawned[0]
    assert config_arg.cwd == root
    assert len(prompt) == 1
    assert "phase2_workspace_diff.md" in (prompt[0].text or "")
    assert "raw_memories.md" in rendered_diff
    assert "raw memory B" in rendered_diff
    assert "raw memory A" in rendered_diff
    assert spawned[1][0] == "shutdowns"
    assert len(spawned[1][1]) == 1
    assert ("codex.memory.phase2.input", 1, ()) in ctx.counters
    assert ("codex.memory.phase2", 1, (("status", "agent_spawned"),)) in ctx.counters
    assert ("codex.memory.phase2", 1, (("status", "succeeded"),)) in ctx.counters

    raw_memories = (root / "raw_memories.md").read_text(encoding="utf-8")
    summaries = sorted(path.read_text(encoding="utf-8") for path in (root / "rollout_summaries").glob("*.md"))
    assert "raw memory B" in raw_memories
    assert "raw memory A" not in raw_memories
    assert len(summaries) == 1
    assert "rollout summary B" in summaries[0]
    assert "git_branch: branch-rollout-b" in summaries[0]
    assert not (root / "phase2_workspace_diff.md").exists()
    assert not asyncio.run(memory_workspace_diff(root)).has_changes()


class Phase2Thread:
    def __init__(self, statuses, token_usage: TokenUsage | None = None) -> None:
        self.statuses = list(statuses)
        self.token_usage = token_usage
        self.shutdowns = 0

    async def agent_status(self):
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    async def token_usage_info(self):
        if self.token_usage is None:
            return None
        return SimpleNamespace(total_token_usage=self.token_usage)

    async def shutdown_and_wait(self):
        self.shutdowns += 1


def test_phase_two_loop_agent_maps_heartbeat_loss_and_failure_to_errored_status() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::agent::loop_agent
    # Contract: while status is non-final, heartbeat false or error breaks the loop with Rust-shaped errored messages.
    lost_store = Phase2Store()
    lost_store.heartbeat_results = [False]
    lost_status = asyncio.run(
        phase_two_loop_agent(StateDb(lost_store), "lease-1", Phase2Thread([AgentStatus.running()]))
    )

    assert lost_status == AgentStatus.errored("lost global phase-2 ownership during heartbeat")
    assert lost_store.calls == [("heartbeat", "lease-1", STAGE_TWO_JOB_LEASE_SECONDS)]

    failing_store = Phase2Store()
    failing_store.heartbeat_results = [RuntimeError("db down")]
    failed_status = asyncio.run(
        phase_two_loop_agent(StateDb(failing_store), "lease-1", Phase2Thread([AgentStatus.running()]))
    )

    assert failed_status == AgentStatus.errored("phase-2 heartbeat update failed: db down")


def test_phase_two_handle_completed_agent_confirms_ownership_resets_and_succeeds(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::agent::handle
    # Contract: completed agents emit token usage, confirm ownership by heartbeat, reset the memory workspace baseline, mark success, then request shutdown.
    store = Phase2Store()
    store.heartbeat_results = [True]
    ctx = phase2_context(store)
    shutdowns: list[SpawnedConsolidationAgent] = []

    async def shutdown(agent):
        shutdowns.append(agent)

    ctx.shutdown_consolidation_agent = shutdown
    resets: list[Path] = []

    async def reset(root):
        resets.append(Path(root))

    claim = PhaseTwoClaim(token="lease-1", watermark=100)
    selected = [memory("a", datetime.fromtimestamp(120, tz=UTC))]
    thread = Phase2Thread(
        [AgentStatus.completed("done")],
        TokenUsage(total_tokens=9, input_tokens=4, cached_input_tokens=1, output_tokens=5, reasoning_output_tokens=2),
    )
    agent = SpawnedConsolidationAgent("agent-thread", thread)

    status = asyncio.run(
        phase_two_handle_agent_completion(
            ctx,
            claim,
            120,
            selected,
            tmp_path / "memories",
            agent,
            reset_workspace_baseline_func=reset,
        )
    )

    assert status == AgentStatus.completed("done")
    assert store.calls == [
        ("heartbeat", "lease-1", STAGE_TWO_JOB_LEASE_SECONDS),
        ("succeeded", "lease-1", 120, selected),
    ]
    assert resets == [tmp_path / "memories"]
    assert shutdowns == [agent]
    assert ("codex.memory.phase2", 1, (("status", "succeeded"),)) in ctx.counters
    assert ("codex.memory.phase2.token_usage", 9, (("token_type", "total"),)) in ctx.histograms


def test_phase_two_handle_completed_agent_does_not_reset_or_succeed_after_lost_lock(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::agent::handle
    # Contract: completed agents do not reset the workspace baseline or mark success if the final ownership heartbeat returns false.
    store = Phase2Store()
    store.heartbeat_results = [False]
    ctx = phase2_context(store)
    resets: list[Path] = []
    agent = SpawnedConsolidationAgent("agent-thread", Phase2Thread([AgentStatus.completed("done")]))

    asyncio.run(
        phase_two_handle_agent_completion(
            ctx,
            PhaseTwoClaim(token="lease-1", watermark=100),
            120,
            [],
            tmp_path / "memories",
            agent,
            reset_workspace_baseline_func=lambda root: resets.append(Path(root)),
        )
    )

    assert store.calls == [("heartbeat", "lease-1", STAGE_TWO_JOB_LEASE_SECONDS)]
    assert resets == []
    assert ctx.counters == []


def test_phase_two_handle_failed_agent_and_confirm_ownership_error_mark_failures(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase2.rs::agent::handle
    # Contract: non-completed final statuses mark failed_agent; heartbeat errors before workspace commit mark failed_confirm_ownership.
    failed_store = Phase2Store()
    failed_ctx = phase2_context(failed_store)
    agent = SpawnedConsolidationAgent("agent-thread", Phase2Thread([AgentStatus.errored("boom")]))

    asyncio.run(
        phase_two_handle_agent_completion(
            failed_ctx,
            PhaseTwoClaim(token="lease-1", watermark=100),
            120,
            [],
            tmp_path / "memories",
            agent,
            final_status=AgentStatus.errored("boom"),
        )
    )

    assert failed_store.calls == [("failed", "lease-1", "failed_agent", STAGE_TWO_JOB_RETRY_DELAY_SECONDS)]
    assert failed_ctx.counters == [("codex.memory.phase2", 1, (("status", "failed_agent"),))]

    ownership_store = Phase2Store()
    ownership_store.heartbeat_results = [RuntimeError("db down")]
    ownership_ctx = phase2_context(ownership_store)

    asyncio.run(
        phase_two_handle_agent_completion(
            ownership_ctx,
            PhaseTwoClaim(token="lease-2", watermark=100),
            120,
            [],
            tmp_path / "memories",
            SpawnedConsolidationAgent("agent-thread", Phase2Thread([AgentStatus.completed("done")])),
        )
    )

    assert ownership_store.calls == [
        ("heartbeat", "lease-2", STAGE_TWO_JOB_LEASE_SECONDS),
        ("failed", "lease-2", "failed_confirm_ownership", STAGE_TWO_JOB_RETRY_DELAY_SECONDS),
    ]
    assert ownership_ctx.counters == [("codex.memory.phase2", 1, (("status", "failed_confirm_ownership"),))]
