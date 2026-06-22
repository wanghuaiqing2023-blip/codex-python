from __future__ import annotations

import pycodex.codex_backend_openapi_models as backend_models


def test_crate_root_reexports_models_namespace_only() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/lib.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/lib.rs
    # Contract: crate root publicly exposes the generated models namespace.
    assert backend_models.__all__ == ["models"]
    assert backend_models.models is not None
