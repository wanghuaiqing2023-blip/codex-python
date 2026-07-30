from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping

from pycodex import __version__


def write_models_cache(codex_home: Path) -> None:
    write_models_cache_with_models(codex_home, [])


def write_models_cache_with_models(
    codex_home: Path,
    models: Iterable[Mapping[str, object]],
) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "etag": None,
        "client_version": __version__,
        "models": list(models),
    }
    (codex_home / "models_cache.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
