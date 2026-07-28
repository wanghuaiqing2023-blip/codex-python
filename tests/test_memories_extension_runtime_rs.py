from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pycodex.ext.memories.extension import MemoriesExtensionConfig
from pycodex.extension_api import ExtensionData, ExtensionRegistryBuilder, ThreadStartInput
from pycodex.features import Feature


class _Features:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def enabled(self, feature: Feature) -> bool:
        return self._enabled and feature is Feature.MEMORY_TOOL


def _config(codex_home: Path, *, feature: bool = True, dedicated: bool = True):
    return SimpleNamespace(
        codex_home=codex_home,
        features=_Features(feature),
        memories=SimpleNamespace(use_memories=True, dedicated_tools=dedicated),
    )


def test_extension_config_requires_feature_and_memory_setting(tmp_path: Path) -> None:
    assert MemoriesExtensionConfig.from_config(_config(tmp_path)).enabled
    assert not MemoriesExtensionConfig.from_config(
        _config(tmp_path, feature=False)
    ).enabled


def test_installed_extension_contributes_prompt_and_real_tools(tmp_path: Path) -> None:
    from pycodex.ext.memories import install

    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "memory_summary.md").write_text("use this context", encoding="utf-8")
    builder = ExtensionRegistryBuilder.new()
    extension = install(builder)
    registry = builder.build()
    session_store = ExtensionData("session")
    thread_store = ExtensionData("thread")
    asyncio.run(
        extension.on_thread_start(
            ThreadStartInput(
                config=_config(tmp_path),
                session_source="test",
                persistent_thread_state_available=False,
                session_store=session_store,
                thread_store=thread_store,
            )
        )
    )

    fragments = asyncio.run(extension.contribute(session_store, thread_store))
    tools = extension.tools(session_store, thread_store)

    assert len(fragments) == 1
    assert "use this context" in fragments[0].text
    assert len(tools) == 4
    assert registry.context_contributors() == (extension,)
    assert registry.tool_contributors() == (extension,)
