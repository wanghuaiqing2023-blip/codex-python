from __future__ import annotations

from types import SimpleNamespace
import pytest

from pycodex.core.state import TaskKind
from pycodex.core.tasks.compact import CompactTask, CompactTaskPlan
from pycodex.features import Feature
from pycodex.protocol.user_input import UserInput


class ProviderInfo:
    def __init__(self, supports_remote: bool) -> None:
        self.supports_remote = supports_remote

    def supports_remote_compaction(self) -> bool:
        return self.supports_remote


class Features:
    def __init__(self, enabled: set[Feature]) -> None:
        self.enabled_features = enabled

    def enabled(self, feature: Feature) -> bool:
        return feature in self.enabled_features


def context(*, supports_remote: bool, remote_v2: bool = False, prompt: str = "compact now") -> SimpleNamespace:
    return SimpleNamespace(
        provider=SimpleNamespace(info=lambda: ProviderInfo(supports_remote)),
        features=Features({Feature.REMOTE_COMPACTION_V2} if remote_v2 else set()),
        compact_prompt=lambda: prompt,
    )


def test_compact_task_identity_matches_rust_session_task_contract() -> None:
    # Rust source: codex-rs/core/src/tasks/compact.rs
    # Contract: CompactTask::kind and span_name.
    task = CompactTask()

    assert task.kind() == TaskKind.COMPACT
    assert task.span_name() == "session_task.compact"


def test_compact_task_local_plan_builds_synthesized_user_input() -> None:
    # Rust source: CompactTask::run local branch constructs UserInput::Text
    # from ctx.compact_prompt() and emits the "local" manual metric.
    plan = CompactTask().plan(context(supports_remote=False, prompt="summarize this"))

    assert plan == CompactTaskPlan(
        strategy="local",
        metric_kind="local",
        manual=True,
        input=(UserInput.text_input("summarize this"),),
    )
    assert plan.input[0].text_elements == ()


def test_compact_task_remote_plan_uses_remote_metric_without_local_input() -> None:
    # Rust source: CompactTask::run remote branch selects compact_remote and
    # emits the "remote" manual metric without synthesizing local prompt input.
    plan = CompactTask().plan(context(supports_remote=True, remote_v2=False))

    assert plan == CompactTaskPlan(strategy="remote", metric_kind="remote", manual=True)


def test_compact_task_remote_v2_plan_wins_when_feature_enabled() -> None:
    # Rust source: CompactTask::run remote-v2 branch is selected only when the
    # provider supports remote compaction and RemoteCompactionV2 is enabled.
    plan = CompactTask().plan(context(supports_remote=True, remote_v2=True))

    assert plan == CompactTaskPlan(strategy="remote_v2", metric_kind="remote_v2", manual=True)


@pytest.mark.asyncio
async def test_compact_task_run_emits_metric_before_local_runner() -> None:
    # Rust source: CompactTask::run local branch emits compact metric before
    # invoking compact::run_compact_task with synthesized prompt input.
    calls: list[tuple[object, ...]] = []
    session = SimpleNamespace(emit_compact_metric=lambda kind, manual: calls.append(("metric", kind, manual)))

    class Runner:
        async def run_local(self, received_session: object, received_ctx: object, input: tuple[UserInput, ...]) -> None:
            calls.append(("local", received_session, received_ctx, input))

    ctx = context(supports_remote=False, prompt="compact prompt")

    result = await CompactTask().run(session, ctx, Runner())

    assert result is None
    assert calls[0] == ("metric", "local", True)
    assert calls[1] == ("local", session, ctx, (UserInput.text_input("compact prompt"),))


@pytest.mark.asyncio
async def test_compact_task_run_selects_remote_v2_runner() -> None:
    # Rust source: CompactTask::run remote_v2 branch emits the "remote_v2"
    # metric and delegates to compact_remote_v2::run_remote_compact_task.
    calls: list[tuple[object, ...]] = []
    session = SimpleNamespace(emit_compact_metric=lambda kind, manual: calls.append(("metric", kind, manual)))

    class Runner:
        def run_remote_v2(self, received_session: object, received_ctx: object) -> None:
            calls.append(("remote_v2", received_session, received_ctx))

    ctx = context(supports_remote=True, remote_v2=True)

    await CompactTask().run(session, ctx, Runner())

    assert calls == [
        ("metric", "remote_v2", True),
        ("remote_v2", session, ctx),
    ]
