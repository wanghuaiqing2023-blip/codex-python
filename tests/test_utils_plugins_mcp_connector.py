from __future__ import annotations

from pycodex.utils.plugins.mcp_connector import (
    DISALLOWED_CONNECTOR_IDS,
    FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS,
    is_connector_id_allowed,
    sanitize_name,
)


def test_default_originator_rejects_general_disallowed_connector_ids() -> None:
    # Source: codex/codex-rs/utils/plugins/src/mcp_connector.rs
    # Contract: non-first-party-chat originators use DISALLOWED_CONNECTOR_IDS.
    disallowed = next(iter(DISALLOWED_CONNECTOR_IDS))

    assert not is_connector_id_allowed(disallowed)
    assert is_connector_id_allowed("connector_allowed")


def test_first_party_chat_originator_uses_chat_specific_disallowed_ids() -> None:
    # Source: codex/codex-rs/utils/plugins/src/mcp_connector.rs
    # Contract: first-party chat originators use FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS.
    chat_disallowed = next(iter(FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS))
    general_disallowed = next(iter(DISALLOWED_CONNECTOR_IDS))

    assert not is_connector_id_allowed(chat_disallowed, first_party_chat_originator=True)
    assert is_connector_id_allowed(general_disallowed, first_party_chat_originator=True)


def test_sanitize_name_lowercases_ascii_alnum_and_replaces_separators() -> None:
    # Source: codex/codex-rs/utils/plugins/src/mcp_connector.rs
    # Contract: sanitize_slug lowercases ASCII alnum, maps other chars to `-`, trims,
    # then sanitize_name converts hyphens to underscores.
    assert sanitize_name("GitHub Connector") == "github_connector"
    assert sanitize_name("  My.Plugin/V2  ") == "my_plugin_v2"


def test_sanitize_name_defaults_empty_slug_to_app() -> None:
    # Source: codex/codex-rs/utils/plugins/src/mcp_connector.rs
    # Contract: empty sanitized slug becomes `app`.
    assert sanitize_name(" ! ") == "app"
