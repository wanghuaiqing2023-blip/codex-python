"""Behavior port slice for Rust ``codex-tui::audio_device``.

Upstream source: ``codex/codex-rs/tui/src/audio_device.rs``.

Rust uses ``cpal`` for real device access. Python keeps that platform boundary
explicit by requiring an injected host/device model for behavior tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="audio_device",
    source="codex/codex-rs/tui/src/audio_device.rs",
    status="complete",
)

PREFERRED_INPUT_SAMPLE_RATE = 24_000
PREFERRED_INPUT_CHANNELS = 1


class RealtimeAudioDeviceKind(str, Enum):
    MICROPHONE = "microphone"
    SPEAKER = "speaker"

    def title(self) -> str:
        return "Microphone" if self is RealtimeAudioDeviceKind.MICROPHONE else "Speaker"

    def noun(self) -> str:
        return self.value


@dataclass(frozen=True)
class SupportedStreamConfig:
    sample_rate: int
    channels: int
    sample_format: str


@dataclass(frozen=True)
class SupportedStreamConfigRange:
    min_sample_rate: int
    max_sample_rate: int
    channels: int
    sample_format: str

    def with_sample_rate(self, sample_rate: int) -> SupportedStreamConfig:
        return SupportedStreamConfig(sample_rate=sample_rate, channels=self.channels, sample_format=self.sample_format)


@dataclass
class AudioDevice:
    device_name: str
    input_configs: List[SupportedStreamConfigRange] = field(default_factory=list)
    output_configs: List[SupportedStreamConfigRange] = field(default_factory=list)
    default_input: Optional[SupportedStreamConfig] = None
    default_output: Optional[SupportedStreamConfig] = None
    name_error: Optional[str] = None
    input_configs_error: Optional[str] = None

    def name(self) -> str:
        if self.name_error is not None:
            raise RuntimeError(self.name_error)
        return self.device_name

    def supported_input_configs(self) -> List[SupportedStreamConfigRange]:
        if self.input_configs_error is not None:
            raise RuntimeError(self.input_configs_error)
        return list(self.input_configs)

    def default_input_config(self) -> SupportedStreamConfig:
        if self.default_input is None:
            raise RuntimeError("failed to get default input config")
        return self.default_input

    def default_output_config(self) -> SupportedStreamConfig:
        if self.default_output is None:
            raise RuntimeError("failed to get default output config")
        return self.default_output


@dataclass
class AudioHost:
    input: List[AudioDevice] = field(default_factory=list)
    output: List[AudioDevice] = field(default_factory=list)
    default_input: Optional[AudioDevice] = None
    default_output: Optional[AudioDevice] = None
    input_devices_error: Optional[str] = None
    output_devices_error: Optional[str] = None

    def input_devices(self) -> List[AudioDevice]:
        if self.input_devices_error is not None:
            raise RuntimeError(self.input_devices_error)
        return list(self.input)

    def output_devices(self) -> List[AudioDevice]:
        if self.output_devices_error is not None:
            raise RuntimeError(self.output_devices_error)
        return list(self.output)

    def default_input_device(self) -> Optional[AudioDevice]:
        return self.default_input

    def default_output_device(self) -> Optional[AudioDevice]:
        return self.default_output


_host_factory: Optional[Callable[[], AudioHost]] = None


def set_audio_host_factory(factory: Optional[Callable[[], AudioHost]]) -> None:
    """Install a runtime backend for Rust's `cpal::default_host()` boundary."""

    global _host_factory
    _host_factory = factory


def _kind(kind: Union[RealtimeAudioDeviceKind, str]) -> RealtimeAudioDeviceKind:
    if isinstance(kind, RealtimeAudioDeviceKind):
        return kind
    raw = str(kind).lower()
    if raw in {"microphone", "input"}:
        return RealtimeAudioDeviceKind.MICROPHONE
    if raw in {"speaker", "output"}:
        return RealtimeAudioDeviceKind.SPEAKER
    raise ValueError(f"unknown realtime audio device kind: {kind}")


def _default_host(host: Optional[AudioHost]) -> AudioHost:
    if host is None and _host_factory is not None:
        return _host_factory()
    if host is None:
        raise NotImplementedError("real audio device enumeration requires an injected AudioHost")
    return host


def list_realtime_audio_device_names(kind: Union[RealtimeAudioDeviceKind, str], *, host: Optional[AudioHost] = None) -> List[str]:
    device_names: List[str] = []
    for device in devices(_default_host(host), _kind(kind)):
        try:
            name = device.name()
        except Exception:
            continue
        if name not in device_names:
            device_names.append(name)
    return device_names


def select_configured_input_device_and_config(config: Any, *, host: Optional[AudioHost] = None) -> Tuple[AudioDevice, SupportedStreamConfig]:
    return select_device_and_config(RealtimeAudioDeviceKind.MICROPHONE, config, host=host)


def select_configured_output_device_and_config(config: Any, *, host: Optional[AudioHost] = None) -> Tuple[AudioDevice, SupportedStreamConfig]:
    return select_device_and_config(RealtimeAudioDeviceKind.SPEAKER, config, host=host)


def preferred_input_config(device: AudioDevice) -> SupportedStreamConfig:
    candidates = []
    try:
        supported_configs = device.supported_input_configs()
    except Exception as exc:
        raise RuntimeError(f"failed to enumerate input audio configs: {exc}") from exc
    for range_ in supported_configs:
        sample_format_rank = {"i16": 0, "u16": 1, "f32": 2}.get(str(range_.sample_format).lower())
        if sample_format_rank is None:
            continue
        sample_rate = preferred_input_sample_rate(range_)
        sample_rate_penalty = abs(sample_rate - PREFERRED_INPUT_SAMPLE_RATE)
        channel_penalty = abs(range_.channels - PREFERRED_INPUT_CHANNELS)
        candidates.append(((sample_rate_penalty, channel_penalty, sample_format_rank), range_.with_sample_rate(sample_rate)))
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    try:
        return device.default_input_config()
    except Exception as exc:
        raise RuntimeError("failed to get default input config") from exc


def select_device_and_config(
    kind: Union[RealtimeAudioDeviceKind, str],
    config: Any,
    *,
    host: Optional[AudioHost] = None,
) -> Tuple[AudioDevice, SupportedStreamConfig]:
    audio_host = _default_host(host)
    device_kind = _kind(kind)
    name = configured_name(device_kind, config)
    selected = find_device_by_name(audio_host, device_kind, name) if name is not None else None
    if selected is None:
        selected = default_device(audio_host, device_kind)
    if selected is None:
        raise RuntimeError(missing_device_error(device_kind, name))
    stream_config = preferred_input_config(selected) if device_kind is RealtimeAudioDeviceKind.MICROPHONE else default_config(selected, device_kind)
    return selected, stream_config


def configured_name(kind: Union[RealtimeAudioDeviceKind, str], config: Any) -> Optional[str]:
    realtime_audio = _get(config, "realtime_audio", config)
    key = "microphone" if _kind(kind) is RealtimeAudioDeviceKind.MICROPHONE else "speaker"
    value = _get(realtime_audio, key)
    return None if value is None else str(value)


def find_device_by_name(host: AudioHost, kind: Union[RealtimeAudioDeviceKind, str], name: Optional[str]) -> Optional[AudioDevice]:
    if name is None:
        return None
    try:
        device_list = devices(host, _kind(kind))
    except Exception:
        return None
    for device in device_list:
        try:
            if device.name() == name:
                return device
        except Exception:
            continue
    return None


def devices(host: AudioHost, kind: Union[RealtimeAudioDeviceKind, str]) -> List[AudioDevice]:
    device_kind = _kind(kind)
    try:
        if device_kind is RealtimeAudioDeviceKind.MICROPHONE:
            return host.input_devices()
        return host.output_devices()
    except Exception as exc:
        noun = "input" if device_kind is RealtimeAudioDeviceKind.MICROPHONE else "output"
        raise RuntimeError(f"failed to enumerate {noun} audio devices: {exc}") from exc


def default_device(host: AudioHost, kind: Union[RealtimeAudioDeviceKind, str]) -> Optional[AudioDevice]:
    return host.default_input_device() if _kind(kind) is RealtimeAudioDeviceKind.MICROPHONE else host.default_output_device()


def default_config(device: AudioDevice, kind: Union[RealtimeAudioDeviceKind, str]) -> SupportedStreamConfig:
    try:
        if _kind(kind) is RealtimeAudioDeviceKind.MICROPHONE:
            return device.default_input_config()
        return device.default_output_config()
    except Exception as exc:
        noun = "input" if _kind(kind) is RealtimeAudioDeviceKind.MICROPHONE else "output"
        raise RuntimeError(f"failed to get default {noun} config") from exc


def preferred_input_sample_rate(range_: SupportedStreamConfigRange) -> int:
    min_rate = range_.min_sample_rate
    max_rate = range_.max_sample_rate
    if min_rate <= PREFERRED_INPUT_SAMPLE_RATE <= max_rate:
        return PREFERRED_INPUT_SAMPLE_RATE
    if PREFERRED_INPUT_SAMPLE_RATE < min_rate:
        return min_rate
    return max_rate


def missing_device_error(kind: Union[RealtimeAudioDeviceKind, str], configured_name: Optional[str]) -> str:
    device_kind = _kind(kind)
    if device_kind is RealtimeAudioDeviceKind.MICROPHONE and configured_name is not None:
        return f"configured microphone `{configured_name}` was unavailable and no default input audio device was found"
    if device_kind is RealtimeAudioDeviceKind.SPEAKER and configured_name is not None:
        return f"configured speaker `{configured_name}` was unavailable and no default output audio device was found"
    if device_kind is RealtimeAudioDeviceKind.MICROPHONE:
        return "no input audio device available"
    return "no output audio device available"


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


__all__ = [
    "AudioDevice",
    "AudioHost",
    "PREFERRED_INPUT_CHANNELS",
    "PREFERRED_INPUT_SAMPLE_RATE",
    "RUST_MODULE",
    "RealtimeAudioDeviceKind",
    "SupportedStreamConfig",
    "SupportedStreamConfigRange",
    "configured_name",
    "default_config",
    "default_device",
    "devices",
    "find_device_by_name",
    "list_realtime_audio_device_names",
    "missing_device_error",
    "preferred_input_config",
    "preferred_input_sample_rate",
    "select_configured_input_device_and_config",
    "select_configured_output_device_and_config",
    "select_device_and_config",
    "set_audio_host_factory",
]
