from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.memories.write import (
    INTERACTIVE_SESSION_SOURCES,
    MemoryStartupContext,
    PhaseOneJobResult,
    StageOneOutput,
    STAGE_ONE_JOB_LEASE_SECONDS,
    STAGE_ONE_JOB_RETRY_DELAY_SECONDS,
    STAGE_ONE_MODEL,
    STAGE_ONE_REASONING_EFFORT,
    STAGE_ONE_THREAD_SCAN_LIMIT,
    aggregate_phase_one_stats,
    emit_phase_one_metrics,
    is_memory_excluded_contextual_user_fragment,
    phase_one_claim_startup_jobs,
    phase_one_job_run,
    phase_one_mark_failed,
    phase_one_mark_succeeded,
    phase_one_mark_succeeded_no_output,
    phase_one_output_schema,
    phase_one_run,
    phase_one_sample,
    serialize_filtered_rollout_response_items,
)
from pycodex.protocol import TokenUsage


def input_text(text: str) -> dict[str, str]:
    return {"type": "input_text", "text": text}


def message(role: str, content: list[dict[str, str]]) -> dict[str, object]:
    return {"type": "message", "role": role, "content": content}


class StateDb:
    def __init__(self, store) -> None:
        self.store = store

    def memories(self):
        return self.store


class Store:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.claims = ["claim-a"]
        self.succeeded_no_output = True
        self.succeeded = True

    async def claim_stage1_jobs_for_startup(self, thread_id, params):
        self.calls.append(("claim", thread_id, params))
        return self.claims

    async def mark_stage1_job_failed(self, thread_id, ownership_token, reason, retry_delay_seconds):
        self.calls.append(("failed", thread_id, ownership_token, reason, retry_delay_seconds))
        return True

    async def mark_stage1_job_succeeded_no_output(self, thread_id, ownership_token):
        self.calls.append(("no_output", thread_id, ownership_token))
        return self.succeeded_no_output

    async def mark_stage1_job_succeeded(
        self,
        thread_id,
        ownership_token,
        source_updated_at,
        raw_memory,
        rollout_summary,
        rollout_slug,
    ):
        self.calls.append(
            (
                "success",
                thread_id,
                ownership_token,
                source_updated_at,
                raw_memory,
                rollout_summary,
                rollout_slug,
            )
        )
        return self.succeeded


def runtime_context(store=None) -> MemoryStartupContext:
    return MemoryStartupContext(
        thread_manager="thread-manager",
        auth_manager="auth-manager",
        thread_id="worker-1",
        thread=SimpleNamespace(),
        config=SimpleNamespace(model="model"),
        source="cli",
        state_db_value=StateDb(store or Store()),
        counters=[],
        histograms=[],
    )


class StageOneContext:
    def __init__(self) -> None:
        self.timers: list[str] = []
        self.counters: list[tuple] = []
        self.histograms: list[tuple] = []

    def start_timer(self, name: str):
        self.timers.append(name)
        return name

    def counter(self, name: str, inc: int, tags):
        self.counters.append((name, inc, tuple(tags)))

    def histogram(self, name: str, value: int, tags):
        self.histograms.append((name, value, tuple(tags)))


def test_classifies_memory_excluded_fragments() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/phase1.rs::job::tests::classifies_memory_excluded_fragments
    # Contract: AGENTS.md instruction and skill fragments are removed from memory prompt input, while environment/subagent context remains.
    cases = [
        ("# AGENTS.md instructions for /tmp\n\n<INSTRUCTIONS>\nbody\n</INSTRUCTIONS>", True),
        ("<skill>\n<name>demo</name>\n<path>skills/demo/SKILL.md</path>\nbody\n</skill>", True),
        ("<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>", False),
        ('<subagent_notification>{"agent_id":"a","status":"completed"}</subagent_notification>', False),
    ]

    for text, expected in cases:
        assert is_memory_excluded_contextual_user_fragment(input_text(text)) is expected


def test_output_schema_requires_rollout_slug_and_keeps_it_nullable() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/phase1.rs::job::tests::output_schema_requires_rollout_slug_and_keeps_it_nullable
    # Contract: phase-1 output schema requires raw_memory, rollout_summary, rollout_slug and keeps rollout_slug nullable.
    schema = phase_one_output_schema()

    required = sorted(schema["required"])
    rollout_slug_types = sorted(schema["properties"]["rollout_slug"]["type"])

    assert "rollout_slug" in schema["properties"]
    assert required == ["raw_memory", "rollout_slug", "rollout_summary"]
    assert rollout_slug_types == ["null", "string"]
    assert schema["additionalProperties"] is False


def test_serializes_memory_rollout_with_agents_removed_but_environment_kept() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/phase1.rs::tests::serializes_memory_rollout_with_agents_removed_but_environment_kept
    # Contract: memory rollout serialization strips AGENTS/skill user fragments, drops empty user messages, and preserves environment/subagent context.
    mixed_contextual_message = message(
        "user",
        [
            input_text("# AGENTS.md instructions for /tmp\n\n<INSTRUCTIONS>\nbody\n</INSTRUCTIONS>"),
            input_text("<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>"),
        ],
    )
    skill_message = message(
        "user",
        [input_text("<skill>\n<name>demo</name>\n<path>skills/demo/SKILL.md</path>\nbody\n</skill>")],
    )
    subagent_message = message(
        "user",
        [input_text('<subagent_notification>{"agent_id":"a","status":"completed"}</subagent_notification>')],
    )

    serialized = serialize_filtered_rollout_response_items(
        [
            {"kind": "response_item", "item": mixed_contextual_message},
            {"kind": "response_item", "item": skill_message},
            {"kind": "response_item", "item": subagent_message},
        ]
    )

    assert json.loads(serialized) == [
        message("user", [input_text("<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>")]),
        subagent_message,
    ]


def test_serializes_memory_rollout_redacts_secrets_before_prompt_upload() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/phase1.rs::tests::serializes_memory_rollout_redacts_secrets_before_prompt_upload
    # Contract: serialized rollout prompt input is secret-redacted before upload.
    serialized = serialize_filtered_rollout_response_items(
        [
            {
                "kind": "response_item",
                "item": {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": {"body": '{"token":"sk-abcdefghijklmnopqrstuvwxyz123456"}', "success": True},
                },
            }
        ]
    )

    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in serialized
    assert "[REDACTED_SECRET]" in serialized


def test_phase_one_sample_builds_strict_prompt_streams_and_redacts_output(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::job::sample
    # Contract: sample loads serialized memory rollout content into a strict stage-one Prompt, streams it, and redacts parsed StageOneOutput fields.
    ctx = runtime_context()
    config = SimpleNamespace()
    usage = TokenUsage(total_tokens=9, input_tokens=5, output_tokens=4)
    captured: dict[str, object] = {}

    async def stream(config_arg, prompt, stage_arg):
        captured["config"] = config_arg
        captured["prompt"] = prompt
        captured["stage"] = stage_arg
        return (
            json.dumps(
                {
                    "raw_memory": "raw sk-abcdefghijklmnopqrstuvwxyz123456",
                    "rollout_summary": "summary token: abcdefghijklmnop",
                    "rollout_slug": "slug-secret=abcdefghijklmnop",
                }
            ),
            usage,
        )

    ctx.stream_stage_one_prompt = stream
    model_info = SimpleNamespace(effective_context_window_percent=100, resolved_context_window=lambda: 20_000)
    stage = SimpleNamespace(model_info=model_info)
    rollout_path = tmp_path / "rollout.jsonl"
    rollout_cwd = tmp_path / "workspace"
    rust_system_prompt = (
        Path(__file__).resolve().parents[1]
        / "codex"
        / "codex-rs"
        / "memories"
        / "write"
        / "templates"
        / "memories"
        / "stage_one_system.md"
    ).read_text(encoding="utf-8")

    output, returned_usage = asyncio.run(
        phase_one_sample(
            ctx,
            config,
            rollout_path,
            rollout_cwd,
            stage,
            rollout_items=[
                {"kind": "response_item", "item": message("user", [input_text("<environment_context>kept</environment_context>")])},
                {
                    "kind": "response_item",
                    "item": message("user", [input_text("# AGENTS.md instructions for /tmp\n<INSTRUCTIONS>drop</INSTRUCTIONS>")]),
                },
                {
                    "kind": "response_item",
                    "item": {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": {"body": "sk-abcdefghijklmnopqrstuvwxyz123456", "success": True},
                    },
                },
            ],
        )
    )

    prompt = captured["prompt"]
    assert captured == {"config": config, "prompt": prompt, "stage": stage}
    assert prompt.base_instructions.text == rust_system_prompt
    assert prompt.output_schema == phase_one_output_schema()
    assert prompt.output_schema_strict is True
    assert len(prompt.input) == 1
    assert prompt.input[0].role == "user"
    prompt_text = prompt.input[0].content[0].text
    assert "rollout.jsonl" in prompt_text
    assert "workspace" in prompt_text
    assert "<environment_context>kept</environment_context>" in prompt_text
    assert "AGENTS.md instructions" not in prompt_text
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in prompt_text
    assert "[REDACTED_SECRET]" in prompt_text
    assert output.raw_memory == "raw [REDACTED_SECRET]"
    assert output.rollout_summary == "summary token: [REDACTED_SECRET]"
    assert output.rollout_slug == "slug-secret=[REDACTED_SECRET]"
    assert returned_usage is usage


def test_phase_one_sample_uses_rollout_loader_tuple_shape(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::job::sample and RolloutRecorder::load_rollout_items
    # Contract: sample consumes the first element of the rollout-loader tuple before serializing response items.
    ctx = runtime_context()
    captured: dict[str, object] = {}
    loaded_paths: list[Path] = []

    async def loader(path: Path):
        loaded_paths.append(path)
        return ([{"kind": "response_item", "item": message("assistant", [input_text("assistant memory")])}], "ignored", "ignored")

    async def stream(_config, prompt, _stage):
        captured["prompt_text"] = prompt.input[0].content[0].text
        return json.dumps({"raw_memory": "raw", "rollout_summary": "summary", "rollout_slug": None}), None

    ctx.stream_stage_one_prompt = stream
    stage = SimpleNamespace(
        model_info=SimpleNamespace(effective_context_window_percent=100, resolved_context_window=lambda: None)
    )
    rollout_path = tmp_path / "rollout.jsonl"

    output, token_usage = asyncio.run(
        phase_one_sample(
            ctx,
            SimpleNamespace(),
            rollout_path,
            tmp_path,
            stage,
            rollout_loader=loader,
        )
    )

    assert loaded_paths == [rollout_path]
    assert "assistant memory" in captured["prompt_text"]
    assert output.raw_memory == "raw"
    assert output.rollout_summary == "summary"
    assert output.rollout_slug is None
    assert token_usage is None


def test_phase_one_sample_loads_real_rollout_jsonl_by_default(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::job::sample calling codex-rollout::RolloutRecorder::load_rollout_items
    # Contract: sample uses the Rust-owned rollout loader by default, consuming real JSONL rollout files and serialized response items.
    rollout_path = tmp_path / "rollout.jsonl"
    rollout_path.write_text(
        "\n".join(
            [
                json.dumps({"type": "response_item", "payload": message("assistant", [input_text("memory from file")])}),
                json.dumps({"type": "response_item", "payload": {"type": "ghost_snapshot"}}),
                "{not-json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    ctx = runtime_context()
    captured: dict[str, object] = {}

    async def stream(_config, prompt, _stage):
        captured["prompt_text"] = prompt.input[0].content[0].text
        return json.dumps({"raw_memory": "raw", "rollout_summary": "summary", "rollout_slug": "slug"}), None

    ctx.stream_stage_one_prompt = stream
    stage = SimpleNamespace(
        model_info=SimpleNamespace(effective_context_window_percent=100, resolved_context_window=lambda: None)
    )

    output, token_usage = asyncio.run(
        phase_one_sample(
            ctx,
            SimpleNamespace(),
            rollout_path,
            tmp_path,
            stage,
        )
    )

    assert "memory from file" in captured["prompt_text"]
    assert "ghost_snapshot" not in captured["prompt_text"]
    assert output == StageOneOutput("raw", "summary", "slug")
    assert token_usage is None


def test_phase_one_sample_rejects_unknown_stage_one_output_fields(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::StageOneOutput
    # Contract: StageOneOutput is deserialized with deny_unknown_fields semantics.
    ctx = runtime_context()

    async def stream(_config, _prompt, _stage):
        return json.dumps({"raw_memory": "raw", "rollout_summary": "summary", "rollout_slug": None, "extra": True}), None

    ctx.stream_stage_one_prompt = stream
    stage = SimpleNamespace(
        model_info=SimpleNamespace(effective_context_window_percent=100, resolved_context_window=lambda: None)
    )

    with pytest.raises(ValueError, match="unknown fields"):
        asyncio.run(
            phase_one_sample(
                ctx,
                SimpleNamespace(),
                tmp_path / "rollout.jsonl",
                tmp_path,
                stage,
                rollout_items=[],
            )
        )


def test_count_outcomes_sums_token_usage_across_all_jobs() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/phase1.rs::tests::count_outcomes_sums_token_usage_across_all_jobs
    # Contract: phase-1 stats count outcomes and add token usage across successful/no-output jobs.
    counts = aggregate_phase_one_stats(
        [
            PhaseOneJobResult(
                "succeeded_with_output",
                TokenUsage(
                    input_tokens=10,
                    cached_input_tokens=2,
                    output_tokens=3,
                    reasoning_output_tokens=1,
                    total_tokens=13,
                ),
            ),
            PhaseOneJobResult(
                "succeeded_no_output",
                TokenUsage(
                    input_tokens=7,
                    cached_input_tokens=1,
                    output_tokens=2,
                    reasoning_output_tokens=0,
                    total_tokens=9,
                ),
            ),
            PhaseOneJobResult("failed", None),
        ]
    )

    assert counts.claimed == 3
    assert counts.succeeded_with_output == 1
    assert counts.succeeded_no_output == 1
    assert counts.failed == 1
    assert counts.total_token_usage == TokenUsage(
        input_tokens=17,
        cached_input_tokens=3,
        output_tokens=5,
        reasoning_output_tokens=1,
        total_tokens=22,
    )


def test_count_outcomes_keeps_usage_empty_when_no_job_reports_it() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/phase1.rs::tests::count_outcomes_keeps_usage_empty_when_no_job_reports_it
    # Contract: aggregate stats keeps total_token_usage empty when no job reports token usage.
    counts = aggregate_phase_one_stats(
        [
            PhaseOneJobResult("succeeded_with_output", None),
            PhaseOneJobResult("failed", None),
        ]
    )

    assert counts.claimed == 2
    assert counts.total_token_usage is None


def test_emit_phase_one_metrics_matches_rust_counters_and_token_histograms() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::emit_metrics
    # Contract: phase-1 metrics emit claimed/succeeded/output/no-output/failed counters and token usage histograms with Rust token_type labels.
    stage = StageOneContext()
    counts = PhaseOneJobResult(
        "succeeded_with_output",
        TokenUsage(input_tokens=7, cached_input_tokens=2, output_tokens=3, reasoning_output_tokens=1, total_tokens=10),
    )
    stats = aggregate_phase_one_stats([counts, PhaseOneJobResult("succeeded_no_output", None), PhaseOneJobResult("failed", None)])

    emit_phase_one_metrics(stage, stats)

    assert stage.counters == [
        ("codex.memory.phase1", 3, (("status", "claimed"),)),
        ("codex.memory.phase1", 1, (("status", "succeeded"),)),
        ("codex.memory.phase1.output", 1, ()),
        ("codex.memory.phase1", 1, (("status", "succeeded_no_output"),)),
        ("codex.memory.phase1", 1, (("status", "failed"),)),
    ]
    assert stage.histograms == [
        ("codex.memory.phase1.token_usage", 10, (("token_type", "total"),)),
        ("codex.memory.phase1.token_usage", 7, (("token_type", "input"),)),
        ("codex.memory.phase1.token_usage", 2, (("token_type", "cached_input"),)),
        ("codex.memory.phase1.token_usage", 3, (("token_type", "output"),)),
        ("codex.memory.phase1.token_usage", 1, (("token_type", "reasoning_output"),)),
    ]


def test_phase_one_claim_startup_jobs_builds_rust_params_and_returns_claims() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::claim_startup_jobs
    # Contract: phase1 startup claims use interactive session sources and stage-one scan/lease constants, returning None on DB unavailability or DB errors.
    store = Store()
    ctx = runtime_context(store)
    memories_config = SimpleNamespace(
        max_rollouts_per_startup=7,
        max_rollout_age_days=30,
        min_rollout_idle_hours=6,
    )

    claims = asyncio.run(phase_one_claim_startup_jobs(ctx, memories_config))

    assert claims == ["claim-a"]
    _, worker_id, params = store.calls[0]
    assert worker_id == "worker-1"
    assert params.scan_limit == STAGE_ONE_THREAD_SCAN_LIMIT
    assert params.max_claimed == 7
    assert params.max_age_days == 30
    assert params.min_rollout_idle_hours == 6
    assert params.allowed_sources == INTERACTIVE_SESSION_SOURCES
    assert params.lease_seconds == STAGE_ONE_JOB_LEASE_SECONDS

    missing_db = MemoryStartupContext(
        thread_manager="thread-manager",
        auth_manager="auth-manager",
        thread_id="worker-1",
        thread=SimpleNamespace(),
        config=SimpleNamespace(model="model"),
        source="cli",
        state_db_value=None,
        counters=[],
        histograms=[],
    )
    assert asyncio.run(phase_one_claim_startup_jobs(missing_db, memories_config)) is None


def test_phase_one_run_skips_after_empty_claims_and_uses_default_model() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::run and build_request_context
    # Contract: phase1 run builds one request context, starts the e2e timer, claims jobs, emits skipped_no_candidates for empty claims, and does not invoke job sampling.
    store = Store()
    store.claims = []
    ctx = runtime_context(store)
    stage = StageOneContext()
    calls: list[tuple] = []

    async def stage_context(config, model_name, reasoning_effort):
        calls.append((config, model_name, reasoning_effort))
        return stage

    ctx.stage_one_request_context = stage_context
    config = SimpleNamespace(
        memories=SimpleNamespace(
            extract_model=None,
            max_rollouts_per_startup=2,
            max_rollout_age_days=30,
            min_rollout_idle_hours=6,
        )
    )

    stats = asyncio.run(phase_one_run(ctx, config, job_runner=lambda *_: (_ for _ in ()).throw(AssertionError("unused"))))

    assert stats == aggregate_phase_one_stats([])
    assert calls == [(config, STAGE_ONE_MODEL, STAGE_ONE_REASONING_EFFORT)]
    assert stage.timers == ["codex.memory.phase1.e2e_ms"]
    assert stage.counters == [("codex.memory.phase1", 1, (("status", "skipped_no_candidates"),))]


def test_phase_one_run_runs_claimed_jobs_and_emits_aggregate_metrics() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::{run,run_jobs,aggregate_stats,emit_metrics}
    # Contract: phase1 run executes claimed jobs with the shared stage-one context, aggregates outcomes, and emits Rust-shaped counters/histograms.
    store = Store()
    store.claims = ["claim-a", "claim-b"]
    ctx = runtime_context(store)
    stage = StageOneContext()
    ctx.stage_one_request_context = lambda config, model_name, reasoning_effort: stage
    config = SimpleNamespace(
        memories=SimpleNamespace(
            extract_model="custom-extractor",
            max_rollouts_per_startup=2,
            max_rollout_age_days=30,
            min_rollout_idle_hours=6,
        )
    )
    job_calls: list[tuple] = []

    async def job_runner(run_context, run_config, claim, stage_one_context):
        job_calls.append((run_context, run_config, claim, stage_one_context))
        if claim == "claim-a":
            return PhaseOneJobResult("succeeded_with_output", TokenUsage(total_tokens=5, input_tokens=3, output_tokens=2))
        return PhaseOneJobResult("failed", None)

    stats = asyncio.run(phase_one_run(ctx, config, job_runner=job_runner))

    assert stats.claimed == 2
    assert stats.succeeded_with_output == 1
    assert stats.failed == 1
    assert [call[2] for call in job_calls] == ["claim-a", "claim-b"]
    assert all(call[0] is ctx and call[1] is config and call[3] is stage for call in job_calls)
    assert stage.counters == [
        ("codex.memory.phase1", 2, (("status", "claimed"),)),
        ("codex.memory.phase1", 1, (("status", "succeeded"),)),
        ("codex.memory.phase1.output", 1, ()),
        ("codex.memory.phase1", 1, (("status", "failed"),)),
    ]
    assert ("codex.memory.phase1.token_usage", 5, (("token_type", "total"),)) in stage.histograms


def test_phase_one_job_run_persists_sample_output_with_source_timestamp(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::job::run
    # Contract: non-empty StageOneOutput is persisted through result::success with claimed thread id, lease, updated_at timestamp, slug, and token usage.
    store = Store()
    ctx = runtime_context(store)
    usage = TokenUsage(total_tokens=12, input_tokens=7, output_tokens=5)
    updated_at = datetime.fromtimestamp(1_700_000_123, UTC)
    claim = SimpleNamespace(
        thread=SimpleNamespace(
            id="thread-a",
            rollout_path=tmp_path / "rollout.jsonl",
            cwd=tmp_path / "workspace",
            updated_at=updated_at,
        ),
        ownership_token="lease-a",
    )
    calls: list[tuple] = []

    async def sample_runner(run_context, run_config, rollout_path, rollout_cwd, stage_one_context):
        calls.append((run_context, run_config, rollout_path, rollout_cwd, stage_one_context))
        return StageOneOutput("raw", "summary", "slug"), usage

    config = SimpleNamespace()
    stage = StageOneContext()
    result = asyncio.run(phase_one_job_run(ctx, config, claim, stage, sample_runner=sample_runner))

    assert result == PhaseOneJobResult("succeeded_with_output", usage)
    assert calls == [(ctx, config, tmp_path / "rollout.jsonl", tmp_path / "workspace", stage)]
    assert store.calls[-1] == ("success", "thread-a", "lease-a", 1_700_000_123, "raw", "summary", "slug")


def test_phase_one_job_run_marks_no_output_for_empty_model_fields(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::job::run
    # Contract: empty raw_memory or rollout_summary skips persistence and marks the job as succeeded_no_output while preserving token usage.
    store = Store()
    ctx = runtime_context(store)
    usage = TokenUsage(total_tokens=3)
    claim = {
        "thread": {
            "id": "thread-empty",
            "rollout_path": tmp_path / "rollout.jsonl",
            "cwd": tmp_path,
            "updated_at": 1_700_000_124,
        },
        "ownership_token": "lease-empty",
    }

    async def sample_runner(*_args):
        return StageOneOutput("", "summary", None), usage

    result = asyncio.run(phase_one_job_run(ctx, SimpleNamespace(), claim, StageOneContext(), sample_runner=sample_runner))

    assert result == PhaseOneJobResult("succeeded_no_output", usage)
    assert store.calls[-1] == ("no_output", "thread-empty", "lease-empty")


def test_phase_one_job_run_marks_failed_when_sample_errors(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::job::run
    # Contract: sample errors are recorded through result::failed and produce a failed JobResult without token usage.
    store = Store()
    ctx = runtime_context(store)
    claim = SimpleNamespace(
        thread=SimpleNamespace(
            id="thread-failed",
            rollout_path=tmp_path / "rollout.jsonl",
            cwd=tmp_path,
            updated_at=1_700_000_125,
        ),
        ownership_token="lease-failed",
    )

    async def sample_runner(*_args):
        raise RuntimeError("sample exploded")

    result = asyncio.run(phase_one_job_run(ctx, SimpleNamespace(), claim, StageOneContext(), sample_runner=sample_runner))

    assert result == PhaseOneJobResult("failed", None)
    assert store.calls[-1] == (
        "failed",
        "thread-failed",
        "lease-failed",
        "sample exploded",
        STAGE_ONE_JOB_RETRY_DELAY_SECONDS,
    )


def test_phase_one_result_markers_match_rust_db_calls_and_outcomes() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/phase1.rs::job::result::{failed,no_output,success}
    # Contract: failed records retry delay and ignores DB errors; no-output/success map truthy DB updates to Rust JobOutcome variants.
    store = Store()
    ctx = runtime_context(store)

    asyncio.run(phase_one_mark_failed(ctx, "thread-a", "lease-a", "model error"))
    assert store.calls[-1] == ("failed", "thread-a", "lease-a", "model error", STAGE_ONE_JOB_RETRY_DELAY_SECONDS)

    assert asyncio.run(phase_one_mark_succeeded_no_output(ctx, "thread-a", "lease-a")) == "succeeded_no_output"
    assert store.calls[-1] == ("no_output", "thread-a", "lease-a")
    store.succeeded_no_output = False
    assert asyncio.run(phase_one_mark_succeeded_no_output(ctx, "thread-a", "lease-a")) == "failed"

    assert (
        asyncio.run(
            phase_one_mark_succeeded(
                ctx,
                "thread-a",
                "lease-a",
                123,
                "raw",
                "summary",
                "slug",
            )
        )
        == "succeeded_with_output"
    )
    assert store.calls[-1] == ("success", "thread-a", "lease-a", 123, "raw", "summary", "slug")
    store.succeeded = False
    assert asyncio.run(phase_one_mark_succeeded(ctx, "thread-a", "lease-a", 123, "raw", "summary", None)) == "failed"
