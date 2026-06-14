from pycodex.tui.tui.frame_rate_limiter import MIN_FRAME_INTERVAL
from pycodex.tui.tui.frame_requester import (
    DrawChannel,
    FrameRequester,
    test_coalesces_mixed_immediate_and_delayed_requests,
    test_coalesces_multiple_requests_into_single_draw,
    test_limits_draw_notifications_to_120fps,
    test_multiple_delayed_requests_coalesce_to_earliest,
    test_rate_limit_clamps_early_delayed_requests,
    test_rate_limit_does_not_delay_future_draws,
    test_schedule_frame_immediate_triggers_once,
    test_schedule_frame_in_triggers_at_delay,
)


def test_schedule_frame_immediate_triggers_once_matches_rust() -> None:
    # Rust: tui/frame_requester.rs test_schedule_frame_immediate_triggers_once
    assert test_schedule_frame_immediate_triggers_once()


def test_schedule_frame_in_triggers_at_delay_matches_rust() -> None:
    # Rust: test_schedule_frame_in_triggers_at_delay
    assert test_schedule_frame_in_triggers_at_delay()


def test_coalesces_multiple_requests_into_single_draw_matches_rust() -> None:
    # Rust: test_coalesces_multiple_requests_into_single_draw
    assert test_coalesces_multiple_requests_into_single_draw()


def test_coalesces_mixed_immediate_and_delayed_requests_matches_rust() -> None:
    # Rust: test_coalesces_mixed_immediate_and_delayed_requests
    assert test_coalesces_mixed_immediate_and_delayed_requests()


def test_limits_draw_notifications_to_120fps_matches_rust() -> None:
    # Rust: test_limits_draw_notifications_to_120fps
    assert test_limits_draw_notifications_to_120fps()


def test_rate_limit_clamps_early_delayed_requests_matches_rust() -> None:
    # Rust: test_rate_limit_clamps_early_delayed_requests
    assert test_rate_limit_clamps_early_delayed_requests()


def test_rate_limit_does_not_delay_future_draws_matches_rust() -> None:
    # Rust: test_rate_limit_does_not_delay_future_draws
    assert test_rate_limit_does_not_delay_future_draws()


def test_multiple_delayed_requests_coalesce_to_earliest_matches_rust() -> None:
    # Rust: test_multiple_delayed_requests_coalesce_to_earliest
    assert test_multiple_delayed_requests_coalesce_to_earliest()


def test_shared_draw_channel_receives_scheduler_notifications() -> None:
    channel = DrawChannel()
    requester = FrameRequester.new(channel)

    requester.schedule_frame()
    requester.scheduler.advance_by(1)

    assert channel.recv_count() == 1


def test_test_dummy_is_noop_like_rust_helper() -> None:
    requester = FrameRequester.test_dummy()

    requester.schedule_frame()
    requester.scheduler.advance_by(MIN_FRAME_INTERVAL)

    assert requester.scheduler.draw_tx.recv_count() == 0
