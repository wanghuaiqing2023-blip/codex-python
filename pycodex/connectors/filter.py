"""Connector filtering aligned with ``codex-rs/connectors/src/filter.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.app_server_protocol.apps import AppInfo

from .metadata import coerce_app_info

JsonValue = Any

DISALLOWED_CONNECTOR_IDS = frozenset(
    (
        "asdk_app_6938a94a61d881918ef32cb999ff937c",
        "connector_2b0a9009c9c64bf9933a3dae3f2b1254",
        "connector_3f8d1a79f27c4c7ba1a897ab13bf37dc",
        "connector_68de829bf7648191acd70a907364c67c",
        "connector_68e004f14af881919eb50893d3d9f523",
        "connector_69272cb413a081919685ec3c88d1744e",
    )
)
FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS = frozenset(
    ("connector_0f9c9d4592e54d0a9a12b3f44a1e2010",)
)


def filter_tool_suggest_discoverable_connectors(
    directory_connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    accessible_connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    discoverable_connector_ids: Iterable[str],
    originator_value: str,
) -> list[AppInfo]:
    accessible_connector_ids = {
        connector.id
        for connector in (coerce_app_info(connector) for connector in accessible_connectors)
        if connector.is_accessible
    }
    discoverable_ids = {str(connector_id) for connector_id in discoverable_connector_ids}
    connectors = [
        connector
        for connector in filter_disallowed_connectors(directory_connectors, originator_value)
        if connector.id not in accessible_connector_ids and connector.id in discoverable_ids
    ]
    connectors.sort(key=lambda connector: (connector.name, connector.id))
    return connectors


def filter_disallowed_connectors(
    connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    originator_value: str,
) -> list[AppInfo]:
    first_party_chat_originator = is_first_party_chat_originator(originator_value)
    return [
        connector
        for connector in (coerce_app_info(connector) for connector in connectors)
        if is_connector_id_allowed(connector.id, first_party_chat_originator)
    ]


def is_first_party_chat_originator(originator_value: str) -> bool:
    return originator_value in {"codex_atlas", "codex_chatgpt_desktop"}


def is_connector_id_allowed(connector_id: str, first_party_chat_originator: bool) -> bool:
    disallowed_connector_ids = (
        FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS
        if first_party_chat_originator
        else DISALLOWED_CONNECTOR_IDS
    )
    return connector_id not in disallowed_connector_ids


__all__ = [
    "DISALLOWED_CONNECTOR_IDS",
    "FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS",
    "filter_disallowed_connectors",
    "filter_tool_suggest_discoverable_connectors",
    "is_connector_id_allowed",
    "is_first_party_chat_originator",
]
