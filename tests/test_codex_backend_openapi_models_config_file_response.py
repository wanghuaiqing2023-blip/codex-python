from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import ConfigFileResponse


def test_new_matches_rust_constructor() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/config_file_response.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/config_file_response.rs
    # Contract: ConfigFileResponse::new assigns all four optional string fields.
    response = ConfigFileResponse.new("contents", "sha", "2026-01-01T00:00:00Z", "user")

    assert response.contents == "contents"
    assert response.sha256 == "sha"
    assert response.updated_at == "2026-01-01T00:00:00Z"
    assert response.updated_by_user_id == "user"


def test_default_and_serialization_omit_none_fields() -> None:
    # Rust contract: derived Default sets all options to None and serde skips None fields.
    assert ConfigFileResponse().to_json_dict() == {}
    assert ConfigFileResponse(contents="contents").to_json_dict() == {"contents": "contents"}


def test_from_mapping_uses_rust_serde_field_names() -> None:
    # Rust contract: serde names are contents, sha256, updated_at, and updated_by_user_id.
    response = ConfigFileResponse.from_mapping(
        {
            "contents": "contents",
            "sha256": "sha",
            "updated_at": "date",
            "updated_by_user_id": "user",
        }
    )

    assert response.to_json_dict() == {
        "contents": "contents",
        "sha256": "sha",
        "updated_at": "date",
        "updated_by_user_id": "user",
    }


def test_from_mapping_rejects_non_string_optional_fields() -> None:
    # Rust serde contract: present optional fields must deserialize as strings or null.
    with pytest.raises(TypeError, match="expected optional string"):
        ConfigFileResponse.from_mapping({"sha256": 123})
