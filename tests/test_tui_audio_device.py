import pytest

from pycodex.tui.audio_device import (
    AudioDevice,
    AudioHost,
    RealtimeAudioDeviceKind,
    SupportedStreamConfig,
    SupportedStreamConfigRange,
    configured_name,
    devices,
    list_realtime_audio_device_names,
    missing_device_error,
    preferred_input_config,
    preferred_input_sample_rate,
    select_configured_input_device_and_config,
    select_configured_output_device_and_config,
    set_audio_host_factory,
)


def test_list_realtime_audio_device_names_deduplicates_and_skips_name_errors():
    # Rust: codex-tui, audio_device.rs, list_realtime_audio_device_names.
    host = AudioHost(
        input=[
            AudioDevice("Mic A"),
            AudioDevice("Mic A"),
            AudioDevice("broken", name_error="no name"),
            AudioDevice("Mic B"),
        ]
    )

    assert list_realtime_audio_device_names(RealtimeAudioDeviceKind.MICROPHONE, host=host) == ["Mic A", "Mic B"]


def test_list_realtime_audio_device_names_uses_output_devices_for_speakers():
    host = AudioHost(
        output=[
            AudioDevice("Speaker A"),
            AudioDevice("Speaker A"),
            AudioDevice("broken", name_error="no name"),
            AudioDevice("Speaker B"),
        ],
    )

    assert list_realtime_audio_device_names(RealtimeAudioDeviceKind.SPEAKER, host=host) == [
        "Speaker A",
        "Speaker B",
    ]


def test_preferred_input_sample_rate_clamps_to_supported_range():
    assert preferred_input_sample_rate(SupportedStreamConfigRange(16_000, 48_000, 1, "i16")) == 24_000
    assert preferred_input_sample_rate(SupportedStreamConfigRange(44_100, 48_000, 1, "i16")) == 44_100
    assert preferred_input_sample_rate(SupportedStreamConfigRange(8_000, 16_000, 1, "i16")) == 16_000


def test_preferred_input_config_ranks_rate_then_channels_then_format():
    # Rust ranks by `(sample_rate_penalty, channel_penalty, sample_format_rank)`.
    device = AudioDevice(
        "Mic",
        input_configs=[
            SupportedStreamConfigRange(24_000, 24_000, 2, "i16"),
            SupportedStreamConfigRange(22_000, 22_000, 1, "i16"),
            SupportedStreamConfigRange(24_000, 24_000, 1, "f32"),
            SupportedStreamConfigRange(24_000, 24_000, 1, "i16"),
        ],
    )

    assert preferred_input_config(device) == SupportedStreamConfig(24_000, 1, "i16")


def test_preferred_input_config_falls_back_to_default_when_no_supported_formats():
    fallback = SupportedStreamConfig(48_000, 2, "unknown")
    device = AudioDevice(
        "Mic",
        input_configs=[SupportedStreamConfigRange(24_000, 24_000, 1, "unsupported")],
        default_input=fallback,
    )

    assert preferred_input_config(device) == fallback


def test_preferred_input_config_reports_input_config_enumeration_error():
    device = AudioDevice("Mic", input_configs_error="boom")

    with pytest.raises(RuntimeError) as excinfo:
        preferred_input_config(device)

    assert str(excinfo.value) == "failed to enumerate input audio configs: boom"


def test_select_configured_device_prefers_matching_name_then_default():
    configured = AudioDevice("Configured", input_configs=[SupportedStreamConfigRange(24_000, 24_000, 1, "i16")])
    default = AudioDevice("Default", input_configs=[SupportedStreamConfigRange(48_000, 48_000, 1, "i16")])
    host = AudioHost(input=[configured, default], default_input=default)

    selected, config = select_configured_input_device_and_config(
        {"realtime_audio": {"microphone": "Configured"}},
        host=host,
    )

    assert selected is configured
    assert config == SupportedStreamConfig(24_000, 1, "i16")


def test_select_configured_device_falls_back_to_default_when_named_device_missing():
    default = AudioDevice("Default", output_configs=[], default_output=SupportedStreamConfig(48_000, 2, "f32"))
    host = AudioHost(output=[default], default_output=default)

    selected, config = select_configured_output_device_and_config(
        {"realtime_audio": {"speaker": "Missing"}},
        host=host,
    )

    assert selected is default
    assert config == SupportedStreamConfig(48_000, 2, "f32")


def test_select_configured_device_reports_missing_default_with_configured_name():
    host = AudioHost(input=[])

    with pytest.raises(RuntimeError) as excinfo:
        select_configured_input_device_and_config(
            {"realtime_audio": {"microphone": "Missing"}},
            host=host,
        )

    assert str(excinfo.value) == (
        "configured microphone `Missing` was unavailable and no default input audio device was found"
    )


def test_select_configured_device_reports_missing_default_without_configured_name():
    host = AudioHost(output=[])

    with pytest.raises(RuntimeError) as excinfo:
        select_configured_output_device_and_config({"realtime_audio": {}}, host=host)

    assert str(excinfo.value) == "no output audio device available"


def test_devices_wraps_host_enumeration_errors_and_configured_lookup_is_best_effort():
    host = AudioHost(input_devices_error="host offline")

    with pytest.raises(RuntimeError) as excinfo:
        devices(host, RealtimeAudioDeviceKind.MICROPHONE)

    assert str(excinfo.value) == "failed to enumerate input audio devices: host offline"

    with pytest.raises(RuntimeError) as missing:
        select_configured_input_device_and_config(
            {"realtime_audio": {"microphone": "Configured"}},
            host=host,
        )

    assert str(missing.value) == (
        "configured microphone `Configured` was unavailable and no default input audio device was found"
    )


def test_select_configured_output_device_reports_default_config_error():
    default = AudioDevice("Default")
    host = AudioHost(output=[default], default_output=default)

    with pytest.raises(RuntimeError) as excinfo:
        select_configured_output_device_and_config({"realtime_audio": {}}, host=host)

    assert str(excinfo.value) == "failed to get default output config"


def test_configured_name_reads_realtime_audio_fields():
    config = {"realtime_audio": {"microphone": "Mic", "speaker": "Speaker"}}

    assert configured_name(RealtimeAudioDeviceKind.MICROPHONE, config) == "Mic"
    assert configured_name(RealtimeAudioDeviceKind.SPEAKER, config) == "Speaker"


def test_missing_device_error_messages_match_rust_text():
    assert missing_device_error(RealtimeAudioDeviceKind.MICROPHONE, "Mic") == (
        "configured microphone `Mic` was unavailable and no default input audio device was found"
    )
    assert missing_device_error(RealtimeAudioDeviceKind.SPEAKER, "Speaker") == (
        "configured speaker `Speaker` was unavailable and no default output audio device was found"
    )
    assert missing_device_error(RealtimeAudioDeviceKind.MICROPHONE, None) == "no input audio device available"
    assert missing_device_error(RealtimeAudioDeviceKind.SPEAKER, None) == "no output audio device available"


def test_real_audio_enumeration_requires_injected_host():
    with pytest.raises(NotImplementedError):
        list_realtime_audio_device_names(RealtimeAudioDeviceKind.MICROPHONE)


def test_runtime_host_factory_models_cpal_default_host_boundary():
    host = AudioHost(input=[AudioDevice("Factory Mic")])
    set_audio_host_factory(lambda: host)
    try:
        assert list_realtime_audio_device_names(RealtimeAudioDeviceKind.MICROPHONE) == ["Factory Mic"]
    finally:
        set_audio_host_factory(None)
