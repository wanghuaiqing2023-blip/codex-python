def test_metrics_rs_owns_memories_usage_metric_and_usage_reexports_it() -> None:
    from pycodex.memories.read import metrics
    from pycodex.memories.read import usage

    assert metrics.MEMORIES_USAGE_METRIC == "codex.memories.usage"
    assert usage.MEMORIES_USAGE_METRIC is metrics.MEMORIES_USAGE_METRIC
