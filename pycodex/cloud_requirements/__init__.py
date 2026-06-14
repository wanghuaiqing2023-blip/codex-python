"""Python API boundary for Rust crate ``codex-cloud-requirements``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CloudRequirementsNotImplementedError(NotImplementedError):
    """Raised when cloud requirements loading is not ported yet."""


@dataclass(frozen=True)
class CloudRequirementsLoader:
    """Callable cloud requirements loader boundary used by config/TUI paths."""

    source: str = "cloud-requirements"
    payload: Any = None

    async def load(self) -> Any:
        raise CloudRequirementsNotImplementedError("CloudRequirementsLoader.load is not ported yet")


def cloud_requirements_loader(*_args: Any, **_kwargs: Any) -> CloudRequirementsLoader:
    """Python boundary for Rust ``cloud_requirements_loader``."""

    return CloudRequirementsLoader()


async def cloud_requirements_loader_for_storage(*_args: Any, **_kwargs: Any) -> CloudRequirementsLoader:
    """Python boundary for Rust ``cloud_requirements_loader_for_storage``."""

    return CloudRequirementsLoader(source="storage")


__all__ = [
    "CloudRequirementsLoader",
    "CloudRequirementsNotImplementedError",
    "cloud_requirements_loader",
    "cloud_requirements_loader_for_storage",
]
