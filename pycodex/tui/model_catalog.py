"""Model catalog snapshot for the TUI port.

Rust counterpart: ``codex-rs/tui/src/model_catalog.rs``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Tuple


@dataclass(frozen=True)
class ModelCatalog:
    """Semantic mirror of Rust ``ModelCatalog``.

    Rust stores a ``Vec<ModelPreset>`` and ``try_list_models`` returns a cloned
    vector in an ``Infallible`` result. Python stores an immutable snapshot and
    returns a deep-copied list so callers cannot mutate the catalog internals.
    """

    models: Tuple[Any, ...]

    @classmethod
    def new(cls, models: Iterable[Any]) -> "ModelCatalog":
        return cls(tuple(deepcopy(list(models))))

    def try_list_models(self) -> list[Any]:
        return deepcopy(list(self.models))


__all__ = ["ModelCatalog"]
