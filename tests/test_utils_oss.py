from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pycodex.utils.oss import (
    LMSTUDIO_DEFAULT_OSS_MODEL,
    LMSTUDIO_OSS_PROVIDER_ID,
    OLLAMA_DEFAULT_OSS_MODEL,
    OLLAMA_OSS_PROVIDER_ID,
    ensure_oss_provider_ready,
    get_default_model_for_oss_provider,
)


@dataclass
class Config:
    model_provider: Any = "model-provider"


class Backend:
    def __init__(self, *, fail_ready: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail_ready = fail_ready

    async def ensure_responses_supported(self, model_provider: Any) -> None:
        self.calls.append(("ensure_responses_supported", model_provider))

    async def ensure_oss_ready(self, config: Config) -> None:
        self.calls.append(("ensure_oss_ready", config))
        if self.fail_ready:
            raise RuntimeError("backend unavailable")


def test_get_default_model_for_provider_lmstudio() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Rust test: tests::test_get_default_model_for_provider_lmstudio
    assert get_default_model_for_oss_provider(LMSTUDIO_OSS_PROVIDER_ID) == LMSTUDIO_DEFAULT_OSS_MODEL


def test_get_default_model_for_provider_ollama() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Rust test: tests::test_get_default_model_for_provider_ollama
    assert get_default_model_for_oss_provider(OLLAMA_OSS_PROVIDER_ID) == OLLAMA_DEFAULT_OSS_MODEL


def test_get_default_model_for_provider_unknown() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Rust test: tests::test_get_default_model_for_provider_unknown
    assert get_default_model_for_oss_provider("unknown-provider") is None


@pytest.mark.asyncio
async def test_unknown_provider_skips_setup() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Contract: unknown provider branch returns Ok(()) without backend setup.
    await ensure_oss_provider_ready("unknown-provider", Config(), backends={})


@pytest.mark.asyncio
async def test_lmstudio_delegates_to_ensure_ready() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Contract: LM Studio delegates directly to codex_lmstudio::ensure_oss_ready.
    config = Config()
    backend = Backend()

    await ensure_oss_provider_ready(LMSTUDIO_OSS_PROVIDER_ID, config, {LMSTUDIO_OSS_PROVIDER_ID: backend})

    assert backend.calls == [("ensure_oss_ready", config)]


@pytest.mark.asyncio
async def test_ollama_checks_responses_support_before_ensure_ready() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Contract: Ollama checks responses support before ensure_oss_ready.
    config = Config(model_provider={"id": "ollama"})
    backend = Backend()

    await ensure_oss_provider_ready(OLLAMA_OSS_PROVIDER_ID, config, {OLLAMA_OSS_PROVIDER_ID: backend})

    assert backend.calls == [
        ("ensure_responses_supported", config.model_provider),
        ("ensure_oss_ready", config),
    ]


@pytest.mark.asyncio
async def test_known_provider_requires_readiness_backend() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Python adaptation: actual local provider setup is injected by backend facades.
    with pytest.raises(NotImplementedError, match="OSS readiness backend required"):
        await ensure_oss_provider_ready(LMSTUDIO_OSS_PROVIDER_ID, Config(), backends={})


@pytest.mark.asyncio
async def test_ensure_ready_error_is_wrapped_like_rust_io_error() -> None:
    # Source: codex/codex-rs/utils/oss/src/lib.rs
    # Contract: ensure_oss_ready failures are reported as "OSS setup failed: ...".
    backend = Backend(fail_ready=True)

    with pytest.raises(OSError, match="OSS setup failed: backend unavailable"):
        await ensure_oss_provider_ready(LMSTUDIO_OSS_PROVIDER_ID, Config(), {LMSTUDIO_OSS_PROVIDER_ID: backend})
