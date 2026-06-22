"""Python namespace for the ``codex-lmstudio`` Rust crate.

Ported from ``codex-lmstudio/src/lib.rs`` and ``src/client.rs``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .client import LMSTUDIO_CONNECTION_ERROR, LMStudioClient

DEFAULT_OSS_MODEL = "openai/gpt-oss-20b"


async def ensure_oss_ready(
    config: Any,
    *,
    client_factory: Callable[[Any], Awaitable[LMStudioClient]] | None = None,
    task_spawner: Callable[[Awaitable[Any]], Any] | None = None,
) -> None:
    """Prepare the local LM Studio OSS environment.

    Mirrors Rust ``ensure_oss_ready``:

    - choose ``config.model`` or ``DEFAULT_OSS_MODEL``;
    - construct and check ``LMStudioClient`` through ``try_from_provider``;
    - fetch local models and download the selected model when missing;
    - ignore model-listing failures;
    - load the selected model in the background and ignore load failures there.
    """

    model = _config_model(config) or DEFAULT_OSS_MODEL
    factory = client_factory or LMStudioClient.try_from_provider
    client = await factory(config)

    try:
        models = await client.fetch_models()
    except Exception as exc:  # noqa: BLE001 - Rust logs and continues.
        logging.getLogger(__name__).warning("Failed to query local models from LM Studio: %s.", exc)
    else:
        if model not in models:
            await client.download_model(model)

    spawner = task_spawner or asyncio.create_task
    spawner(_load_model_ignoring_errors(client, model))


async def _load_model_ignoring_errors(client: LMStudioClient, model: str) -> None:
    try:
        await client.load_model(model)
    except Exception as exc:  # noqa: BLE001 - Rust logs and continues in spawned task.
        logging.getLogger(__name__).warning("Failed to load model %s: %s", model, exc)


def _config_model(config: Any) -> str | None:
    if isinstance(config, dict):
        value = config.get("model")
    else:
        value = getattr(config, "model", None)
    return value if isinstance(value, str) and value else None


__all__ = ["DEFAULT_OSS_MODEL", "LMSTUDIO_CONNECTION_ERROR", "LMStudioClient", "ensure_oss_ready"]
