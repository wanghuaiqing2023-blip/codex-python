"""Thread realtime protocol types ported from ``protocol/v2/realtime.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import (
    RealtimeConversationVersion,
    RealtimeOutputModality,
    RealtimeVoice,
    RealtimeVoicesList,
)

JsonValue = Any
UNSET = object()


@dataclass(frozen=True)
class ThreadRealtimeAudioChunk:
    data: str
    sample_rate: int
    num_channels: int
    samples_per_channel: int | None = None
    item_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _ensure_str(self.data, "data"))
        object.__setattr__(self, "sample_rate", _ensure_u32(self.sample_rate, "sample_rate"))
        object.__setattr__(self, "num_channels", _ensure_u16(self.num_channels, "num_channels"))
        object.__setattr__(
            self,
            "samples_per_channel",
            _optional_u32(self.samples_per_channel, "samples_per_channel"),
        )
        object.__setattr__(self, "item_id", _optional_str(self.item_id, "item_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeAudioChunk":
        _ensure_mapping(value, "ThreadRealtimeAudioChunk")
        return cls(
            data=_ensure_str(value["data"], "data"),
            sample_rate=_ensure_u32(_pick(value, "sample_rate", "sampleRate"), "sample_rate"),
            num_channels=_ensure_u16(_pick(value, "num_channels", "numChannels"), "num_channels"),
            samples_per_channel=_optional_u32(
                _pick(value, "samples_per_channel", "samplesPerChannel"),
                "samples_per_channel",
            ),
            item_id=_optional_str(_pick(value, "item_id", "itemId"), "item_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": self.data,
            "sample_rate": self.sample_rate,
            "num_channels": self.num_channels,
            "samples_per_channel": self.samples_per_channel,
            "item_id": self.item_id,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": self.data,
            "sampleRate": self.sample_rate,
            "numChannels": self.num_channels,
            "samplesPerChannel": self.samples_per_channel,
            "itemId": self.item_id,
        }


@dataclass(frozen=True)
class ThreadRealtimeStartTransport:
    type: str
    sdp: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_str(self.type, "type"))
        if self.type == "websocket":
            if self.sdp is not None:
                raise ValueError("websocket transport must not include sdp")
            return
        if self.type == "webrtc":
            object.__setattr__(self, "sdp", _ensure_str(self.sdp, "sdp"))
            return
        raise ValueError(f"unknown realtime transport type: {self.type}")

    @classmethod
    def websocket(cls) -> "ThreadRealtimeStartTransport":
        return cls("websocket")

    @classmethod
    def webrtc(cls, sdp: str) -> "ThreadRealtimeStartTransport":
        return cls("webrtc", sdp=sdp)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeStartTransport":
        _ensure_mapping(value, "ThreadRealtimeStartTransport")
        transport_type = _ensure_str(value["type"], "type")
        if transport_type == "websocket":
            return cls.websocket()
        if transport_type == "webrtc":
            return cls.webrtc(_ensure_str(value["sdp"], "sdp"))
        raise ValueError(f"unknown realtime transport type: {transport_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "webrtc":
            result["sdp"] = self.sdp
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class ThreadRealtimeStartParams:
    thread_id: str
    output_modality: RealtimeOutputModality | str
    prompt: str | None | object = UNSET
    realtime_session_id: str | None = None
    transport: ThreadRealtimeStartTransport | Mapping[str, JsonValue] | None = None
    voice: RealtimeVoice | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "output_modality", _output_modality(self.output_modality))
        object.__setattr__(self, "prompt", _double_option_str(self.prompt, "prompt"))
        object.__setattr__(self, "realtime_session_id", _optional_str(self.realtime_session_id, "realtime_session_id"))
        object.__setattr__(self, "transport", _optional_transport(self.transport))
        object.__setattr__(self, "voice", _optional_voice(self.voice))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeStartParams":
        _ensure_mapping(value, "ThreadRealtimeStartParams")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            output_modality=_output_modality(_pick(value, "output_modality", "outputModality")),
            prompt=_double_option_str(_pick(value, "prompt", default=UNSET), "prompt"),
            realtime_session_id=_optional_str(
                _pick(value, "realtime_session_id", "realtimeSessionId"),
                "realtime_session_id",
            ),
            transport=_optional_transport(_pick(value, "transport")),
            voice=_optional_voice(_pick(value, "voice")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"thread_id": self.thread_id, "output_modality": self.output_modality.value}
        _put_if_set(result, "prompt", self.prompt)
        _put_optional(result, "realtime_session_id", self.realtime_session_id)
        _put_optional(result, "transport", None if self.transport is None else self.transport.to_mapping())
        _put_optional(result, "voice", None if self.voice is None else self.voice.value)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"threadId": self.thread_id, "outputModality": self.output_modality.value}
        _put_if_set(result, "prompt", self.prompt)
        _put_optional(result, "realtimeSessionId", self.realtime_session_id)
        _put_optional(result, "transport", None if self.transport is None else self.transport.to_camel_mapping())
        _put_optional(result, "voice", None if self.voice is None else self.voice.value)
        return result


@dataclass(frozen=True)
class ThreadRealtimeStartResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ThreadRealtimeStartResponse":
        if value is not None:
            _ensure_mapping(value, "ThreadRealtimeStartResponse")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class ThreadRealtimeAppendAudioParams:
    thread_id: str
    audio: ThreadRealtimeAudioChunk | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "audio", _audio_chunk(self.audio))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeAppendAudioParams":
        _ensure_mapping(value, "ThreadRealtimeAppendAudioParams")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"), audio=_audio_chunk(value["audio"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "audio": self.audio.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "audio": self.audio.to_camel_mapping()}


class ThreadRealtimeAppendAudioResponse(ThreadRealtimeStartResponse):
    pass


@dataclass(frozen=True)
class ThreadRealtimeAppendTextParams:
    thread_id: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "text", _ensure_str(self.text, "text"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeAppendTextParams":
        _ensure_mapping(value, "ThreadRealtimeAppendTextParams")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"), text=_ensure_str(value["text"], "text"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "text": self.text}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "text": self.text}


class ThreadRealtimeAppendTextResponse(ThreadRealtimeStartResponse):
    pass


@dataclass(frozen=True)
class ThreadRealtimeStopParams:
    thread_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeStopParams":
        _ensure_mapping(value, "ThreadRealtimeStopParams")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id}


class ThreadRealtimeStopResponse(ThreadRealtimeStartResponse):
    pass


class ThreadRealtimeListVoicesParams(ThreadRealtimeStartResponse):
    pass


@dataclass(frozen=True)
class ThreadRealtimeListVoicesResponse:
    voices: RealtimeVoicesList | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "voices", _voices_list(self.voices))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeListVoicesResponse":
        _ensure_mapping(value, "ThreadRealtimeListVoicesResponse")
        return cls(voices=_voices_list(value["voices"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"voices": self.voices.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class ThreadRealtimeStartedNotification:
    thread_id: str
    realtime_session_id: str | None
    version: RealtimeConversationVersion | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "realtime_session_id", _optional_str(self.realtime_session_id, "realtime_session_id"))
        object.__setattr__(self, "version", _version(self.version))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeStartedNotification":
        _ensure_mapping(value, "ThreadRealtimeStartedNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            realtime_session_id=_optional_str(
                _pick(value, "realtime_session_id", "realtimeSessionId"),
                "realtime_session_id",
            ),
            version=_version(value["version"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "realtime_session_id": self.realtime_session_id, "version": self.version.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "realtimeSessionId": self.realtime_session_id, "version": self.version.value}


@dataclass(frozen=True)
class ThreadRealtimeItemAddedNotification:
    thread_id: str
    item: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeItemAddedNotification":
        _ensure_mapping(value, "ThreadRealtimeItemAddedNotification")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"), item=value["item"])

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "item": self.item}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "item": self.item}


@dataclass(frozen=True)
class ThreadRealtimeTranscriptDeltaNotification:
    thread_id: str
    role: str
    delta: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "role", _ensure_str(self.role, "role"))
        object.__setattr__(self, "delta", _ensure_str(self.delta, "delta"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeTranscriptDeltaNotification":
        _ensure_mapping(value, "ThreadRealtimeTranscriptDeltaNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            role=_ensure_str(value["role"], "role"),
            delta=_ensure_str(value["delta"], "delta"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "role": self.role, "delta": self.delta}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "role": self.role, "delta": self.delta}


@dataclass(frozen=True)
class ThreadRealtimeTranscriptDoneNotification:
    thread_id: str
    role: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "role", _ensure_str(self.role, "role"))
        object.__setattr__(self, "text", _ensure_str(self.text, "text"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeTranscriptDoneNotification":
        _ensure_mapping(value, "ThreadRealtimeTranscriptDoneNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            role=_ensure_str(value["role"], "role"),
            text=_ensure_str(value["text"], "text"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "role": self.role, "text": self.text}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "role": self.role, "text": self.text}


@dataclass(frozen=True)
class ThreadRealtimeOutputAudioDeltaNotification:
    thread_id: str
    audio: ThreadRealtimeAudioChunk | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "audio", _audio_chunk(self.audio))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeOutputAudioDeltaNotification":
        _ensure_mapping(value, "ThreadRealtimeOutputAudioDeltaNotification")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"), audio=_audio_chunk(value["audio"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "audio": self.audio.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "audio": self.audio.to_camel_mapping()}


@dataclass(frozen=True)
class ThreadRealtimeSdpNotification:
    thread_id: str
    sdp: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "sdp", _ensure_str(self.sdp, "sdp"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeSdpNotification":
        _ensure_mapping(value, "ThreadRealtimeSdpNotification")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"), sdp=_ensure_str(value["sdp"], "sdp"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "sdp": self.sdp}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "sdp": self.sdp}


@dataclass(frozen=True)
class ThreadRealtimeErrorNotification:
    thread_id: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeErrorNotification":
        _ensure_mapping(value, "ThreadRealtimeErrorNotification")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"), message=_ensure_str(value["message"], "message"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "message": self.message}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "message": self.message}


@dataclass(frozen=True)
class ThreadRealtimeClosedNotification:
    thread_id: str
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "reason", _optional_str(self.reason, "reason"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ThreadRealtimeClosedNotification":
        _ensure_mapping(value, "ThreadRealtimeClosedNotification")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"), reason=_optional_str(value.get("reason"), "reason"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "reason": self.reason}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "reason": self.reason}


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_u32(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**32 - 1:
        raise TypeError(f"{field_name} must be an unsigned 32-bit integer")
    return value


def _optional_u32(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    return _ensure_u32(value, field_name)


def _ensure_u16(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**16 - 1:
        raise TypeError(f"{field_name} must be an unsigned 16-bit integer")
    return value


def _double_option_str(value: JsonValue, field_name: str) -> str | None | object:
    if value is UNSET or value is None:
        return value
    return _ensure_str(value, field_name)


def _output_modality(value: JsonValue) -> RealtimeOutputModality:
    if isinstance(value, RealtimeOutputModality):
        return value
    if isinstance(value, str):
        return RealtimeOutputModality(value)
    raise TypeError("output_modality must be a RealtimeOutputModality or string")


def _optional_voice(value: JsonValue) -> RealtimeVoice | None:
    if value is None:
        return None
    if isinstance(value, RealtimeVoice):
        return value
    if isinstance(value, str):
        return RealtimeVoice(value)
    raise TypeError("voice must be a RealtimeVoice, string, or None")


def _version(value: JsonValue) -> RealtimeConversationVersion:
    if isinstance(value, RealtimeConversationVersion):
        return value
    if isinstance(value, str):
        return RealtimeConversationVersion(value)
    raise TypeError("version must be a RealtimeConversationVersion or string")


def _audio_chunk(value: JsonValue) -> ThreadRealtimeAudioChunk:
    if isinstance(value, ThreadRealtimeAudioChunk):
        return value
    if isinstance(value, Mapping):
        return ThreadRealtimeAudioChunk.from_mapping(value)
    raise TypeError("audio must be a ThreadRealtimeAudioChunk or mapping")


def _optional_transport(value: JsonValue) -> ThreadRealtimeStartTransport | None:
    if value is None:
        return None
    if isinstance(value, ThreadRealtimeStartTransport):
        return value
    if isinstance(value, Mapping):
        return ThreadRealtimeStartTransport.from_mapping(value)
    raise TypeError("transport must be a ThreadRealtimeStartTransport, mapping, or None")


def _voices_list(value: JsonValue) -> RealtimeVoicesList:
    if isinstance(value, RealtimeVoicesList):
        return value
    if isinstance(value, Mapping):
        return RealtimeVoicesList.from_mapping(value)
    raise TypeError("voices must be a RealtimeVoicesList or mapping")


def _put_optional(result: dict[str, JsonValue], key: str, value: JsonValue) -> None:
    if value is not None:
        result[key] = value


def _put_if_set(result: dict[str, JsonValue], key: str, value: JsonValue) -> None:
    if value is not UNSET:
        result[key] = value


__all__ = [
    "ThreadRealtimeAppendAudioParams",
    "ThreadRealtimeAppendAudioResponse",
    "ThreadRealtimeAppendTextParams",
    "ThreadRealtimeAppendTextResponse",
    "ThreadRealtimeAudioChunk",
    "ThreadRealtimeClosedNotification",
    "ThreadRealtimeErrorNotification",
    "ThreadRealtimeItemAddedNotification",
    "ThreadRealtimeListVoicesParams",
    "ThreadRealtimeListVoicesResponse",
    "ThreadRealtimeOutputAudioDeltaNotification",
    "ThreadRealtimeSdpNotification",
    "ThreadRealtimeStartParams",
    "ThreadRealtimeStartResponse",
    "ThreadRealtimeStartTransport",
    "ThreadRealtimeStartedNotification",
    "ThreadRealtimeStopParams",
    "ThreadRealtimeStopResponse",
    "ThreadRealtimeTranscriptDeltaNotification",
    "ThreadRealtimeTranscriptDoneNotification",
    "UNSET",
]
