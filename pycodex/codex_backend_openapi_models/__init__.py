"""Python surface for Rust ``codex-backend-openapi-models``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/lib.rs``

The crate root intentionally re-exports the generated ``models`` namespace and
contains no hand-written model types. See ``TEST_ALIGNMENT.md`` for
module-level status.
"""

from __future__ import annotations

from . import models

__all__ = ["models"]
