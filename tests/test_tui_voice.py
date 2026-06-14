import base64
from collections import deque

import pytest

from pycodex.tui.voice import (
    MODEL_AUDIO_CHANNELS,
    MODEL_AUDIO_SAMPLE_RATE,
    AppEventSender,
    RealtimeAudioFrame,
    RealtimeAudioPlayer,
    RecordingMeterState,
    VoiceCapture,
    convert_pcm16,
    convert_u16_to_i16_and_peak,
    f32_abs_to_u16,
    f32_to_i16,
    fill_output_f32,
    fill_output_i16,
    fill_output_u16,
    peak_f32,
    peak_i16,
    send_realtime_audio_chunk,
)


def encode_i16(samples):
    payload = b"".join(int(sample).to_bytes(2, "little", signed=True) for sample in samples)
    return base64.b64encode(payload).decode("ascii")


def decode_i16(data):
    raw = base64.b64decode(data)
    return [int.from_bytes(raw[i : i + 2], "little", signed=True) for i in range(0, len(raw), 2)]


def test_convert_pcm16_downmixes_and_resamples_for_model_input_matches_rust():
    assert convert_pcm16(
        [100, 300, 200, 400, 500, 700, 600, 800],
        48_000,
        2,
        24_000,
        1,
    ) == [200, 700]


def test_f32_conversion_and_peak_helpers_match_rust_boundaries():
    assert f32_abs_to_u16(-2.0) == 32_767
    assert f32_abs_to_u16(0.5) == 16_383
    assert f32_to_i16(2.0) == 32_767
    assert f32_to_i16(-2.0) == -32_767
    assert f32_to_i16(0.5) == 16_383
    assert peak_f32([-0.25, 0.75, 0.5]) == 24_575
    assert peak_i16([0, -32_768, 123]) == 32_768


def test_convert_u16_to_i16_and_peak_matches_rust_centering():
    out = []
    peak = convert_u16_to_i16_and_peak([0, 32_768, 65_535], out)
    assert out == [-32_768, 0, 32_767]
    assert peak == 32_768


def test_send_realtime_audio_chunk_encodes_little_endian_model_audio():
    sender = AppEventSender()
    send_realtime_audio_chunk(sender, [1, -2], MODEL_AUDIO_SAMPLE_RATE, MODEL_AUDIO_CHANNELS)
    assert len(sender.chunks) == 1
    chunk = sender.chunks[0]
    assert chunk.sample_rate == MODEL_AUDIO_SAMPLE_RATE
    assert chunk.num_channels == MODEL_AUDIO_CHANNELS
    assert chunk.samples_per_channel == 2
    assert decode_i16(chunk.data) == [1, -2]


def test_send_realtime_audio_chunk_converts_non_model_audio_before_encoding():
    sender = AppEventSender()
    send_realtime_audio_chunk(sender, [100, 300, 200, 400], 48_000, 2)
    assert decode_i16(sender.chunks[0].data) == [200]


def test_send_realtime_audio_chunk_ignores_empty_or_invalid_format():
    sender = AppEventSender()
    send_realtime_audio_chunk(sender, [], MODEL_AUDIO_SAMPLE_RATE, MODEL_AUDIO_CHANNELS)
    send_realtime_audio_chunk(sender, [1], 0, MODEL_AUDIO_CHANNELS)
    send_realtime_audio_chunk(sender, [1], MODEL_AUDIO_SAMPLE_RATE, 0)
    assert sender.chunks == []


def test_realtime_audio_player_enqueue_frame_decodes_converts_and_clear():
    player = RealtimeAudioPlayer(output_sample_rate=24_000, output_channels=1)
    frame = RealtimeAudioFrame(
        data=encode_i16([100, 300, 200, 400]),
        sample_rate=48_000,
        num_channels=2,
    )
    player.enqueue_frame(frame)
    assert list(player.queue) == [200]
    player.clear()
    assert list(player.queue) == []


def test_realtime_audio_player_rejects_invalid_frame_and_odd_bytes():
    player = RealtimeAudioPlayer()
    with pytest.raises(ValueError, match="invalid realtime audio frame format"):
        player.enqueue_frame(RealtimeAudioFrame(data="", sample_rate=0, num_channels=1))
    odd = base64.b64encode(b"x").decode("ascii")
    with pytest.raises(ValueError, match="odd byte length"):
        player.enqueue_frame(RealtimeAudioFrame(data=odd, sample_rate=24_000, num_channels=1))
    with pytest.raises(ValueError, match="failed to decode realtime audio"):
        player.enqueue_frame(RealtimeAudioFrame(data="not base64!", sample_rate=24_000, num_channels=1))


def test_fill_output_helpers_pop_queue_and_default_silence():
    q = deque([1, -2])
    out_i16 = [99, 99, 99]
    fill_output_i16(out_i16, q)
    assert out_i16 == [1, -2, 0]

    q = deque([16_383])
    out_f32 = [9.0, 9.0]
    fill_output_f32(out_f32, q)
    assert out_f32 == [16_383 / 32_767, 0.0]

    q = deque([-32_768, 32_767])
    out_u16 = [9, 9, 9]
    fill_output_u16(out_u16, q)
    assert out_u16 == [0, 65_535, 32_768]


def test_convert_pcm16_channel_mapping_cases():
    assert convert_pcm16([5, 6], 24_000, 1, 24_000, 3) == [5, 5, 5, 6, 6, 6]
    assert convert_pcm16([1, 3, -1, -4], 24_000, 2, 24_000, 1) == [2, -2]
    assert convert_pcm16([1, 2, 3, 4], 24_000, 2, 24_000, 2) == [1, 2, 3, 4]
    assert convert_pcm16([1, 2, 3], 24_000, 3, 24_000, 2) == [1, 2]
    assert convert_pcm16([1, 2], 24_000, 2, 24_000, 4) == [1, 2, 2, 2]
    assert convert_pcm16([1, 2], 24_000, 0, 24_000, 1) == []


def test_recording_meter_state_returns_four_character_history():
    meter = RecordingMeterState.new()
    assert meter.next_text(0) == "...."
    loud = meter.next_text(32_767)
    assert len(loud) == 4
    assert loud.endswith("#")


def test_voice_capture_stop_sets_flag_and_clears_stream():
    capture = VoiceCapture(stream=object(), stopped=False, last_peak=123)
    capture.stop()
    assert capture.stopped_flag() is True
    assert capture.stream is None
    assert capture.last_peak_arc() == 123
    with pytest.raises(NotImplementedError):
        VoiceCapture.start_realtime(config=None, tx=None)
    with pytest.raises(NotImplementedError):
        RealtimeAudioPlayer.start(config=None)
