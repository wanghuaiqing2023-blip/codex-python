from pycodex.tui.config_update import SERVICE_TIER_DEFAULT_REQUEST_VALUE
from pycodex.tui.service_tier_resolution import (
    FAST_MODE_FEATURE,
    Config,
    FeatureSet,
    ModelPreset,
    Notices,
    ServiceTierPreset,
    configured_service_tier,
    effective_service_tier,
    model_supports_service_tier,
    service_tier_update_for_core,
)


def fast_config(service_tier=None, opt_out=None):
    return Config(
        service_tier=service_tier,
        features=FeatureSet(frozenset({FAST_MODE_FEATURE})),
        notices=Notices(fast_default_opt_out=opt_out),
    )


def preset(model="gpt-5", tiers=("fast", "flex"), default="fast"):
    return ModelPreset(
        model=model,
        service_tiers=tuple(ServiceTierPreset(tier) for tier in tiers),
        default_service_tier=default,
    )


def test_configured_service_tier_prefers_explicit_config_then_opt_out_default():
    # Rust: codex-tui, service_tier_resolution.rs, configured_service_tier.
    assert configured_service_tier(fast_config(service_tier="flex", opt_out=True)) == "flex"
    assert configured_service_tier(fast_config(opt_out=True)) == SERVICE_TIER_DEFAULT_REQUEST_VALUE
    assert configured_service_tier(fast_config(opt_out=False)) is None
    assert configured_service_tier(fast_config()) is None


def test_configured_service_tier_opt_out_requires_exact_true():
    # Rust uses `fast_default_opt_out == Some(true)`, so falsey/truthy
    # non-bool values do not trigger the default sentinel.
    assert configured_service_tier(fast_config(opt_out=1)) is None
    assert configured_service_tier(fast_config(opt_out="true")) is None


def test_effective_service_tier_is_none_when_fast_mode_disabled():
    # Rust: codex-tui, service_tier_resolution.rs, early FastMode guard.
    config = Config(features=FeatureSet())

    assert effective_service_tier(config, "gpt-5", [preset()]) is None
    assert service_tier_update_for_core(config, "gpt-5", [preset()]) is None


def test_effective_service_tier_returns_configured_when_model_unknown():
    assert effective_service_tier(fast_config(service_tier="flex"), "unknown", [preset()]) == "flex"
    assert service_tier_update_for_core(fast_config(service_tier="flex"), "unknown", [preset()]) == "flex"


def test_effective_service_tier_keeps_default_sentinel_even_if_not_in_model_tiers():
    config = fast_config(service_tier=SERVICE_TIER_DEFAULT_REQUEST_VALUE)

    assert effective_service_tier(config, "gpt-5", [preset(tiers=("fast",), default="fast")]) == "default"


def test_effective_service_tier_drops_unsupported_configured_tier():
    config = fast_config(service_tier="flex")
    model = preset(tiers=("fast",), default="fast")

    assert effective_service_tier(config, "gpt-5", [model]) is None
    assert service_tier_update_for_core(config, "gpt-5", [model]) == SERVICE_TIER_DEFAULT_REQUEST_VALUE


def test_effective_service_tier_uses_supported_model_default_when_unconfigured():
    assert effective_service_tier(fast_config(), "gpt-5", [preset(default="flex")]) == "flex"
    assert service_tier_update_for_core(fast_config(), "gpt-5", [preset(default="flex")]) == "flex"


def test_effective_service_tier_uses_first_matching_model_preset():
    # Rust uses `models.iter().find`, so duplicate model ids resolve to the
    # first preset and do not inspect later presets.
    first = preset(model="gpt-5", tiers=("fast",), default="fast")
    second = preset(model="gpt-5", tiers=("flex",), default="flex")

    assert effective_service_tier(fast_config(), "gpt-5", [first, second]) == "fast"
    assert effective_service_tier(fast_config(service_tier="flex"), "gpt-5", [first, second]) is None


def test_effective_service_tier_ignores_unsupported_model_default():
    model = preset(tiers=("fast",), default="flex")

    assert effective_service_tier(fast_config(), "gpt-5", [model]) is None
    assert service_tier_update_for_core(fast_config(), "gpt-5", [model]) == SERVICE_TIER_DEFAULT_REQUEST_VALUE


def test_service_tier_update_for_core_sends_no_update_for_unknown_model_without_effective_tier():
    assert service_tier_update_for_core(fast_config(), "unknown", [preset()]) is None


def test_model_supports_service_tier_accepts_semantic_model_shapes():
    assert model_supports_service_tier(preset(tiers=("fast", "flex")), "flex") is True
    assert model_supports_service_tier({"service_tiers": [{"id": "fast"}]}, "flex") is False
