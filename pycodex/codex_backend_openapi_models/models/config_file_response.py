"""Port of Rust ``codex-backend-openapi-models::models::config_file_response``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/config_file_response.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ConfigFileResponse:
    contents: str | None = None
    sha256: str | None = None
    updated_at: str | None = None
    updated_by_user_id: str | None = None

    @classmethod
    def new(
        cls,
        contents: str | None,
        sha256: str | None,
        updated_at: str | None,
        updated_by_user_id: str | None,
    ) -> "ConfigFileResponse":
        return cls(
            contents=contents,
            sha256=sha256,
            updated_at=updated_at,
            updated_by_user_id=updated_by_user_id,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConfigFileResponse":
        return cls(
            contents=_optional_str(value.get("contents")),
            sha256=_optional_str(value.get("sha256")),
            updated_at=_optional_str(value.get("updated_at")),
            updated_by_user_id=_optional_str(value.get("updated_by_user_id")),
        )

    def to_json_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.contents is not None:
            result["contents"] = self.contents
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        if self.updated_at is not None:
            result["updated_at"] = self.updated_at
        if self.updated_by_user_id is not None:
            result["updated_by_user_id"] = self.updated_by_user_id
        return result


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError("expected optional string")


__all__ = ["ConfigFileResponse"]
