from __future__ import annotations

import os

import pytest


def test_validate_remote_bundle_uses_detail_name_for_local_plugin_id() -> None:
    from pycodex.core_plugins.remote_bundle import validate_remote_plugin_bundle

    bundle = validate_remote_plugin_bundle(
        "plugins~Plugin_00000000000000000000000000000000",
        "openai-curated-remote",
        "linear",
        "1.2.3",
        "https://example.com/linear.tar.gz",
        None,
    )

    assert bundle.plugin_id.plugin_name == "linear"
    assert bundle.plugin_id.marketplace_name == "openai-curated-remote"
    assert bundle.plugin_version == "1.2.3"
    assert bundle.bundle_download_url == "https://example.com/linear.tar.gz"


@pytest.mark.parametrize(
    ("version", "url", "message"),
    [
        (None, "https://example.com/plugin.tar.gz", "release version"),
        ("../bad", "https://example.com/plugin.tar.gz", "invalid release version"),
        ("1.0.0", None, "download URL"),
        ("1.0.0", "file:///tmp/plugin.tar.gz", "unsupported download URL scheme"),
    ],
)
def test_validate_remote_bundle_rejects_invalid_metadata(
    version: str | None,
    url: str | None,
    message: str,
) -> None:
    from pycodex.core_plugins.remote_bundle import (
        RemotePluginBundleInstallError,
        validate_remote_plugin_bundle,
    )

    with pytest.raises(RemotePluginBundleInstallError, match=message):
        validate_remote_plugin_bundle(
            "remote-1",
            "openai-curated-remote",
            "linear",
            version,
            url,
            None,
        )


def test_http_bundle_is_only_allowed_for_loopback_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pycodex.core_plugins.remote_bundle import (
        RemotePluginBundleInstallError,
        validate_remote_plugin_bundle,
    )

    env = "CODEX_TEST_ALLOW_HTTP_REMOTE_PLUGIN_BUNDLE_DOWNLOADS"
    monkeypatch.delenv(env, raising=False)
    with pytest.raises(RemotePluginBundleInstallError):
        validate_remote_plugin_bundle(
            "remote-1",
            "openai-curated-remote",
            "linear",
            "1",
            "http://127.0.0.1/plugin.tar.gz",
            None,
        )

    monkeypatch.setenv(env, "1")
    bundle = validate_remote_plugin_bundle(
        "remote-1",
        "openai-curated-remote",
        "linear",
        "1",
        "http://localhost/plugin.tar.gz",
        None,
    )
    assert bundle.bundle_download_url.startswith("http://localhost/")

    assert os.environ[env] == "1"
