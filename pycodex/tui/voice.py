from __future__ import annotations

import base64
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Iterable, MutableSequence, Sequence

MODEL_AUDIO_SAMPLE_RATE = 24_000
MODEL_AUDIO_CHANNELS = 1
_I16_MAX = 32_767
_U16_MIDPOINT = 32_768


@dataclass
class ThreadRealtimeAudioChunk:
    data: str
    sample_rate: int
    num_channels: int
    samples_per_channel: int | None = None
    item_id: Any | None = None


@dataclass
class RealtimeAudioFrame:
    data: str
    sample_rate: int
    num_channels: int


@dataclass
class AppEventSender:
    chunks: list[ThreadRealtimeAudioChunk] = field(default_factory=list)

    def realtime_conversation_audio(self, chunk: ThreadRealtimeAudioChunk) -> None:
        self.chunks.append(chunk)

    def send(self, chunk: ThreadRealtimeAudioChunk) -> None:
        self.realtime_conversation_audio(chunk)


@dataclass
class VoiceCapture:
    stream: Any | None = None
    stopped: bool = False
    last_peak: int = 0

    @classmethod
    def start_realtime(cls, config: Any, tx: Any) -> "VoiceCapture":
        raise NotImplementedError(
            "realtime input device capture is a cpal/platform boundary and is not implemented in Python"
        )

    def stop(self) -> None:
        self.stopped = True
        self.stream = None

    def stopped_flag(self) -> bool:
        return self.stopped

    def last_peak_arc(self) -> int:
        return self.last_peak


class RecordingMeterState:
    SYMBOLS = (".", ":", "-", "=", "+", "*", "#")

    def __init__(self) -> None:
        self.history: Deque[str] = deque([self.SYMBOLS[0]] * 4, maxlen=4)
        self.noise_ema = 0.02
        self.env = 0.0

    @classmethod
    def new(cls) -> "RecordingMeterState":
        return cls()

    def next_text(self, peak: int) -> str:
        latest_peak = float(peak) / float(_I16_MAX)
        if latest_peak > self.env:
            self.env = 0.80 * latest_peak + 0.20 * self.env
        else:
            self.env = 0.25 * latest_peak + 0.75 * self.env

        rms_approx = self.env * 0.7
        self.noise_ema = 0.95 * self.noise_ema + 0.05 * rms_approx
        ref_level = max(self.noise_ema, 0.01)
        fast_signal = 0.8 * latest_peak + 0.2 * self.env
        target = 2.0
        raw = max(fast_signal / (ref_level * target), 0.0)
        compressed = min(math.log1p(raw) / math.log1p(1.6), 1.0)
        idx = round(compressed * (len(self.SYMBOLS) - 1))
        idx = max(0, min(idx, len(self.SYMBOLS) - 1))
        self.history.append(self.SYMBOLS[idx])
        return "".join(self.history)


def _rust_trunc(value: float) -> int:
    return int(value)


def _unsigned_abs_i16(value: int) -> int:
    return 32_768 if value == -32_768 else abs(value)


def _i16_wrap(value: int) -> int:
    return ((int(value) + 2**15) % 2**16) - 2**15


def _sample_bytes_le(sample: int) -> bytes:
    return int(_i16_wrap(sample)).to_bytes(2, "little", signed=True)


def _get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def f32_abs_to_u16(value: float) -> int:
    scaled = _rust_trunc(min(abs(float(value)), 1.0) * float(_I16_MAX))
    return max(scaled, 0)


def f32_to_i16(sample: float) -> int:
    clamped = max(-1.0, min(float(sample), 1.0))
    return _i16_wrap(_rust_trunc(clamped * float(_I16_MAX)))


def peak_f32(samples: Iterable[float]) -> int:
    peak = 0.0
    for sample in samples:
        peak = max(peak, abs(float(sample)))
    return f32_abs_to_u16(peak)


def peak_i16(samples: Iterable[int]) -> int:
    peak = 0
    for sample in samples:
        peak = max(peak, _unsigned_abs_i16(_i16_wrap(sample)))
    return peak


def convert_u16_to_i16_and_peak(samples: Iterable[int], out: MutableSequence[int] | None = None) -> int:
    target = out if out is not None else []
    peak = 0
    for sample in samples:
        value = _i16_wrap(int(sample) - _U16_MIDPOINT)
        peak = max(peak, _unsigned_abs_i16(value))
        target.append(value)
    return peak


def send_realtime_audio_chunk(tx: Any, samples: Sequence[int], sample_rate: int, channels: int) -> None:
    if not samples or sample_rate == 0 or channels == 0:
        return

    if sample_rate == MODEL_AUDIO_SAMPLE_RATE and channels == MODEL_AUDIO_CHANNELS:
        converted = list(samples)
    else:
        converted = convert_pcm16(
            samples,
            sample_rate,
            channels,
            MODEL_AUDIO_SAMPLE_RATE,
            MODEL_AUDIO_CHANNELS,
        )
    if not converted:
        return

    payload = b"".join(_sample_bytes_le(sample) for sample in converted)
    chunk = ThreadRealtimeAudioChunk(
        data=base64.b64encode(payload).decode("ascii"),
        sample_rate=MODEL_AUDIO_SAMPLE_RATE,
        num_channels=MODEL_AUDIO_CHANNELS,
        samples_per_channel=len(converted) // MODEL_AUDIO_CHANNELS,
        item_id=None,
    )
    if hasattr(tx, "realtime_conversation_audio"):
        tx.realtime_conversation_audio(chunk)
    elif hasattr(tx, "send"):
        tx.send(chunk)
    else:
        tx.append(chunk)


@dataclass
class RealtimeAudioPlayer:
    output_sample_rate: int = MODEL_AUDIO_SAMPLE_RATE
    output_channels: int = MODEL_AUDIO_CHANNELS
    queue: Deque[int] = field(default_factory=deque)
    stream: Any | None = None

    @classmethod
    def start(cls, config: Any) -> "RealtimeAudioPlayer":
        raise NotImplementedError(
            "realtime output device playback is a cpal/platform boundary and is not implemented in Python"
        )

    def enqueue_frame(self, frame: Any) -> None:
        num_channels = int(_get_field(frame, "num_channels", 0) or 0)
        sample_rate = int(_get_field(frame, "sample_rate", 0) or 0)
        if num_channels == 0 or sample_rate == 0:
            raise ValueError("invalid realtime audio frame format")

        data = _get_field(frame, "data", "")
        try:
            raw = base64.b64decode(data, validate=True)
        except Exception as exc:  # pragma: no cover - exact exception type varies by payload
            raise ValueError(f"failed to decode realtime audio: {exc}") from exc
        if len(raw) % 2 != 0:
            raise ValueError("realtime audio frame had odd byte length")

        pcm = [int.from_bytes(raw[i : i + 2], "little", signed=True) for i in range(0, len(raw), 2)]
        converted = convert_pcm16(
            pcm,
            sample_rate,
            num_channels,
            self.output_sample_rate,
            self.output_channels,
        )
        if converted:
            self.queue.extend(converted)

    def clear(self) -> None:
        self.queue.clear()


def _queue_pop(queue: Any) -> int | None:
    if hasattr(queue, "popleft"):
        try:
            return queue.popleft()
        except IndexError:
            return None
    try:
        return queue.pop(0)
    except IndexError:
        return None


def fill_output_i16(output: MutableSequence[int], queue: Any) -> None:
    for index in range(len(output)):
        sample = _queue_pop(queue)
        output[index] = 0 if sample is None else _i16_wrap(sample)


def fill_output_f32(output: MutableSequence[float], queue: Any) -> None:
    for index in range(len(output)):
        sample = _queue_pop(queue)
        output[index] = 0.0 if sample is None else float(_i16_wrap(sample)) / float(_I16_MAX)


def fill_output_u16(output: MutableSequence[int], queue: Any) -> None:
    for index in range(len(output)):
        sample = _queue_pop(queue)
        if sample is None:
            output[index] = _U16_MIDPOINT
        else:
            output[index] = max(0, min(int(_i16_wrap(sample)) + _U16_MIDPOINT, 65_535))


def convert_pcm16(
    input_samples: Sequence[int],
    input_sample_rate: int,
    input_channels: int,
    output_sample_rate: int,
    output_channels: int,
) -> list[int]:
    if not input_samples or input_channels == 0:
        return []

    in_channels = int(input_channels)
    out_channels = int(output_channels)
    in_frames = len(input_samples) // in_channels
    if in_frames == 0:
        return []

    if input_sample_rate == output_sample_rate:
        out_frames = in_frames
    else:
        out_frames = max((in_frames * int(output_sample_rate)) // int(input_sample_rate), 1)

    out: list[int] = []
    for out_frame_idx in range(out_frames):
        if out_frames <= 1 or in_frames <= 1:
            src_frame_idx = 0
        else:
            src_frame_idx = (out_frame_idx * (in_frames - 1)) // (out_frames - 1)
        start = src_frame_idx * in_channels
        src = [_i16_wrap(sample) for sample in input_samples[start : start + in_channels]]

        if in_channels == 1 and out_channels == 1:
            out.append(src[0])
        elif in_channels == 1:
            out.extend(src[0] for _ in range(out_channels))
        elif out_channels == 1:
            total = sum(src)
            out.append(_i16_wrap(int(total / in_channels)))
        elif in_channels == out_channels:
            out.extend(src[:out_channels])
        elif in_channels > out_channels:
            out.extend(src[:out_channels])
        else:
            out.extend(src)
            if src:
                out.extend(src[-1] for _ in range(out_channels - in_channels))
    return out


__all__ = [
    "MODEL_AUDIO_CHANNELS",
    "MODEL_AUDIO_SAMPLE_RATE",
    "AppEventSender",
    "RealtimeAudioFrame",
    "RealtimeAudioPlayer",
    "RecordingMeterState",
    "ThreadRealtimeAudioChunk",
    "VoiceCapture",
    "convert_pcm16",
    "convert_u16_to_i16_and_peak",
    "f32_abs_to_u16",
    "f32_to_i16",
    "fill_output_f32",
    "fill_output_i16",
    "fill_output_u16",
    "peak_f32",
    "peak_i16",
    "send_realtime_audio_chunk",
]
