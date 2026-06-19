"""LM Studio client helpers ported from ``codex-lmstudio/src/client.rs``."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pycodex.model_provider_info import LMSTUDIO_OSS_PROVIDER_ID

LMSTUDIO_CONNECTION_ERROR = (
    "LM Studio is not responding. Install from https://lmstudio.ai/download "
    "and run 'lms server start'."
)


@dataclass(frozen=True)
class LMStudioClient:
    base_url: str
    timeout: float = 5.0

    @classmethod
    async def try_from_provider(cls, config: Any) -> "LMStudioClient":
        providers = _field(config, "model_providers", {})
        if not isinstance(providers, Mapping) or LMSTUDIO_OSS_PROVIDER_ID not in providers:
            raise FileNotFoundError(f"Built-in provider {LMSTUDIO_OSS_PROVIDER_ID} not found")
        provider = providers[LMSTUDIO_OSS_PROVIDER_ID]
        base_url = _field(provider, "base_url")
        if base_url is None:
            raise ValueError("oss provider must have a base_url")
        client = cls(str(base_url))
        await client.check_server()
        return client

    @classmethod
    def from_host_root(cls, host_root: str) -> "LMStudioClient":
        return cls(str(host_root))

    async def check_server(self) -> None:
        url = f"{self.base_url.rstrip('/')}/models"

        def request() -> None:
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as response:
                    status = response.status
                    if 200 <= status < 300:
                        return
                    raise OSError(f"Server returned error: {status} {LMSTUDIO_CONNECTION_ERROR}")
            except urllib.error.HTTPError as exc:
                raise OSError(f"Server returned error: {exc.code} {LMSTUDIO_CONNECTION_ERROR}") from exc
            except OSError as exc:
                message = str(exc)
                if message.startswith("Server returned error:"):
                    raise
                raise OSError(LMSTUDIO_CONNECTION_ERROR) from exc

        await asyncio.to_thread(request)

    async def load_model(self, model: str) -> None:
        url = f"{self.base_url.rstrip('/')}/responses"
        body = json.dumps({"model": model, "input": "", "max_output_tokens": 1}).encode("utf-8")

        def request() -> None:
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    status = response.status
                    if 200 <= status < 300:
                        return
                    raise OSError(f"Failed to load model: {status}")
            except urllib.error.HTTPError as exc:
                raise OSError(f"Failed to load model: {exc.code}") from exc
            except OSError as exc:
                if str(exc).startswith("Failed to load model:"):
                    raise
                raise OSError(f"Request failed: {exc}") from exc

        await asyncio.to_thread(request)

    async def fetch_models(self) -> list[str]:
        url = f"{self.base_url.rstrip('/')}/models"

        def request() -> list[str]:
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as response:
                    status = response.status
                    if not 200 <= status < 300:
                        raise OSError(f"Failed to fetch models: {status}")
                    try:
                        payload = json.loads(response.read().decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ValueError(f"JSON parse error: {exc}") from exc
            except urllib.error.HTTPError as exc:
                raise OSError(f"Failed to fetch models: {exc.code}") from exc
            except OSError as exc:
                if str(exc).startswith("Failed to fetch models:"):
                    raise
                raise OSError(f"Request failed: {exc}") from exc

            data = payload.get("data") if isinstance(payload, Mapping) else None
            if not isinstance(data, list):
                raise ValueError("No 'data' array in response")
            return [str(model["id"]) for model in data if isinstance(model, Mapping) and isinstance(model.get("id"), str)]

        return await asyncio.to_thread(request)

    @staticmethod
    def find_lms() -> str:
        return LMStudioClient.find_lms_with_home_dir(None)

    @staticmethod
    def find_lms_with_home_dir(home_dir: str | None) -> str:
        if shutil.which("lms") is not None:
            return "lms"
        home = home_dir
        if home is None:
            home = os.environ.get("USERPROFILE" if sys.platform.startswith("win") else "HOME", "")
        fallback = Path(home) / ".lmstudio" / "bin" / ("lms.exe" if sys.platform.startswith("win") else "lms")
        if fallback.exists():
            return str(fallback)
        raise FileNotFoundError("LM Studio not found. Please install LM Studio from https://lmstudio.ai/")

    async def download_model(self, model: str) -> None:
        lms = self.find_lms()

        def run() -> None:
            try:
                result = subprocess.run(
                    [lms, "get", "--yes", model],
                    stdout=None,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except OSError as exc:
                raise OSError(f"Failed to execute '{lms} get --yes {model}': {exc}") from exc
            if result.returncode != 0:
                raise OSError(f"Model download failed with exit code: {result.returncode}")

        await asyncio.to_thread(run)


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


__all__ = ["LMSTUDIO_CONNECTION_ERROR", "LMStudioClient"]
