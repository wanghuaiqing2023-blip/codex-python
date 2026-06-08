"""MCP connector helpers ported from ``codex-rs/utils/plugins``."""

from __future__ import annotations

DISALLOWED_CONNECTOR_IDS = frozenset(
    {
        "asdk_app_6938a94a61d881918ef32cb999ff937c",
        "connector_2b0a9009c9c64bf9933a3dae3f2b1254",
        "connector_3f8d1a79f27c4c7ba1a897ab13bf37dc",
        "connector_68de829bf7648191acd70a907364c67c",
        "connector_68e004f14af881919eb50893d3d9f523",
        "connector_69272cb413a081919685ec3c88d1744e",
    }
)
FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS = frozenset(
    {"connector_0f9c9d4592e54d0a9a12b3f44a1e2010"}
)


def is_connector_id_allowed(connector_id: str, *, first_party_chat_originator: bool = False) -> bool:
    if not isinstance(connector_id, str):
        raise TypeError("connector_id must be a string")
    disallowed = (
        FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS
        if first_party_chat_originator
        else DISALLOWED_CONNECTOR_IDS
    )
    return connector_id not in disallowed


def sanitize_name(name: str) -> str:
    return _sanitize_slug(name).replace("-", "_")


def _sanitize_slug(name: str) -> str:
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    normalized = "".join(
        character.lower() if character.isascii() and character.isalnum() else "-"
        for character in name
    ).strip("-")
    return normalized or "app"


__all__ = [
    "DISALLOWED_CONNECTOR_IDS",
    "FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS",
    "is_connector_id_allowed",
    "sanitize_name",
]
