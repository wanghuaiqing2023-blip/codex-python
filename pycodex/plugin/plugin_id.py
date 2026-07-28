"""Stable plugin identifier parsing owned by ``codex-plugin::plugin_id``."""

from __future__ import annotations

from dataclasses import dataclass


class PluginIdError(ValueError):
    pass


def validate_plugin_segment(segment: str, kind: str) -> None:
    if not segment:
        raise PluginIdError(f"invalid {kind}: must not be empty")
    if not all(character.isascii() and (character.isalnum() or character in "_-") for character in segment):
        raise PluginIdError(
            f"invalid {kind}: only ASCII letters, digits, `_`, and `-` are allowed"
        )


@dataclass(frozen=True)
class PluginId:
    plugin_name: str
    marketplace_name: str

    def __post_init__(self) -> None:
        validate_plugin_segment(self.plugin_name, "plugin name")
        validate_plugin_segment(self.marketplace_name, "marketplace name")

    @classmethod
    def parse(cls, plugin_key: str) -> "PluginId":
        plugin_name, separator, marketplace_name = plugin_key.rpartition("@")
        if not separator or not plugin_name or not marketplace_name:
            raise PluginIdError(
                f"invalid plugin key `{plugin_key}`; expected <plugin>@<marketplace>"
            )
        try:
            return cls(plugin_name, marketplace_name)
        except PluginIdError as exc:
            raise PluginIdError(f"{exc} in `{plugin_key}`") from exc

    def as_key(self) -> str:
        return f"{self.plugin_name}@{self.marketplace_name}"

    def __str__(self) -> str:
        return self.as_key()


__all__ = [
    "PluginId",
    "PluginIdError",
    "validate_plugin_segment",
]
