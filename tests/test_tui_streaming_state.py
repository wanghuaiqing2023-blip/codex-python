"""Parity tests for ``codex-tui/src/streaming/mod.rs``."""

from __future__ import annotations

from dataclasses import dataclass

from pycodex.tui.streaming import StreamState, test_cwd


@dataclass
class FakeCollector:
    cleared: bool = False

    def clear(self) -> None:
        self.cleared = True


def test_drain_n_clamps_to_available_lines() -> None:
    # Rust: streaming::tests::drain_n_clamps_to_available_lines
    state = StreamState.new(None, test_cwd(), collector=FakeCollector())
    state.enqueue(["one"], enqueued_at=10.0)

    assert state.drain_n(8) == ["one"]
    assert state.is_idle() is True


def test_step_drains_one_queued_line_from_front() -> None:
    # Rust source: StreamState::step pops from VecDeque front and returns a Vec.
    state = StreamState.new(None, test_cwd(), collector=FakeCollector())
    state.enqueue(["one", "two"], enqueued_at=10.0)

    assert state.step() == ["one"]
    assert state.step() == ["two"]
    assert state.step() == []


def test_clear_resets_collector_queue_and_delta_flag() -> None:
    # Rust source: StreamState::clear clears collector, queue, and has_seen_delta.
    collector = FakeCollector()
    state = StreamState.new(None, test_cwd(), collector=collector)
    state.has_seen_delta = True
    state.enqueue(["one"], enqueued_at=10.0)

    state.clear()

    assert collector.cleared is True
    assert state.is_idle() is True
    assert state.has_seen_delta is False


def test_clear_queue_keeps_collector_and_delta_flag() -> None:
    # Rust source: StreamState::clear_queue only clears queued lines.
    state = StreamState.new(None, test_cwd(), collector=FakeCollector())
    state.has_seen_delta = True
    state.enqueue(["one"], enqueued_at=10.0)

    state.clear_queue()

    assert state.is_idle() is True
    assert state.has_seen_delta is True


def test_queued_len_and_oldest_queued_age_track_fifo_head() -> None:
    # Rust source: queued_len returns depth; oldest_queued_age uses the front line.
    state = StreamState.new(None, test_cwd(), collector=FakeCollector())
    state.enqueue(["old", "new"], enqueued_at=10.0)

    assert state.queued_len() == 2
    assert state.oldest_queued_age(12.5) == 2.5
    assert state.oldest_queued_age(8.0) == 0.0


def test_drain_n_zero_and_negative_do_not_drain() -> None:
    # Rust source: drain(..0) drains no lines; Python clamps negative input to the same safe boundary.
    state = StreamState.new(None, test_cwd(), collector=FakeCollector())
    state.enqueue(["one", "two"], enqueued_at=10.0)

    assert state.drain_n(0) == []
    assert state.drain_n(-1) == []
    assert state.queued_len() == 2
