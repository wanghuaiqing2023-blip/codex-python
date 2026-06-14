from pycodex.features import Feature, Features, unstable_features_warning_event


def _features_with_child_agents_md() -> Features:
    return Features.with_defaults().enable(Feature.CHILD_AGENTS_MD)


def test_emits_warning_when_unstable_features_enabled_via_config() -> None:
    # Rust: core/tests/suite/unstable_features_warning.rs::emits_warning_when_unstable_features_enabled_via_config.
    event = unstable_features_warning_event(
        {"child_agents_md": True},
        suppress_unstable_features_warning=False,
        features=_features_with_child_agents_md(),
        config_path="/tmp/codex-home/config.toml",
    )

    assert event is not None
    assert event.msg.type == "warning"
    message = event.msg.payload.message
    assert "child_agents_md" in message
    assert "Under-development features enabled" in message
    assert "suppress_unstable_features_warning = true" in message


def test_suppresses_warning_when_configured() -> None:
    # Rust: core/tests/suite/unstable_features_warning.rs::suppresses_warning_when_configured.
    event = unstable_features_warning_event(
        {"child_agents_md": True},
        suppress_unstable_features_warning=True,
        features=_features_with_child_agents_md(),
        config_path="/tmp/codex-home/config.toml",
    )

    assert event is None
