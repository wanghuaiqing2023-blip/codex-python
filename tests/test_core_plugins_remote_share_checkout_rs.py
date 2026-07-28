from __future__ import annotations

import json
from pathlib import Path

import pytest

from pycodex.app_server_protocol import PluginAuthPolicy, PluginInstallPolicy


def test_personal_marketplace_relative_path_must_stay_inside_home(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.remote.share.checkout import (
        InvalidCheckoutPathError,
        personal_marketplace_relative_plugin_path,
    )

    plugin = tmp_path / "plugins" / "demo"
    assert personal_marketplace_relative_plugin_path(tmp_path, plugin) == "./plugins/demo"

    with pytest.raises(InvalidCheckoutPathError, match="inside the home directory"):
        personal_marketplace_relative_plugin_path(tmp_path, tmp_path.parent / "demo")


def test_update_personal_marketplace_creates_and_updates_same_source(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.remote.share.checkout import update_personal_marketplace

    plugin = tmp_path / "plugins" / "demo"
    plugin.mkdir(parents=True)
    result = update_personal_marketplace(
        tmp_path,
        "demo",
        plugin,
        PluginInstallPolicy.AVAILABLE,
        PluginAuthPolicy.ON_USE,
        "productivity",
    )
    assert result.name == "codex-curated"

    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["plugins"] == [
        {
            "name": "demo",
            "source": {"source": "local", "path": "./plugins/demo"},
            "policy": {
                "installation": "AVAILABLE",
                "authentication": "ON_USE",
            },
            "category": "productivity",
        }
    ]

    update_personal_marketplace(
        tmp_path,
        "demo",
        plugin,
        PluginInstallPolicy.INSTALLED_BY_DEFAULT,
        PluginAuthPolicy.ON_INSTALL,
        None,
    )
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert len(payload["plugins"]) == 1
    assert payload["plugins"][0]["policy"]["installation"] == "INSTALLED_BY_DEFAULT"


def test_update_personal_marketplace_rejects_existing_different_source(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.remote.share.checkout import (
        InvalidCheckoutPathError,
        update_personal_marketplace,
    )

    marketplace = tmp_path / ".agents" / "plugins" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps(
            {
                "name": "codex-curated",
                "plugins": [
                    {
                        "name": "demo",
                        "source": {"source": "local", "path": "./plugins/old"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plugin = tmp_path / "plugins" / "demo"
    plugin.mkdir(parents=True)

    with pytest.raises(InvalidCheckoutPathError, match="different source path"):
        update_personal_marketplace(
            tmp_path,
            "demo",
            plugin,
            PluginInstallPolicy.AVAILABLE,
            PluginAuthPolicy.ON_USE,
            None,
        )
