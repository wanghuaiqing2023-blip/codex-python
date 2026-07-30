"""Core conversation test builder derived from ``test_codex.rs``."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .test_codex_exec import TestCodexExecBuilder, test_codex_exec

__test__ = False


@dataclass
class TestCodexBuilder:
    cwd: Path | None = None
    home: Path | None = None
    model: str | None = None
    config_mutators: list[Callable[[dict[str, Any]], None]] = field(default_factory=list)

    def with_config(self, mutator: Callable[[dict[str, Any]], None]) -> "TestCodexBuilder":
        self.config_mutators.append(mutator)
        return self

    def with_model(self, model: str) -> "TestCodexBuilder":
        self.model = model
        return self

    def with_home(self, home: str | Path) -> "TestCodexBuilder":
        self.home = Path(home)
        return self

    async def build(self, _server: Any = None) -> "TestCodex":
        cwd = (self.cwd or Path(tempfile.mkdtemp(prefix="pycodex-core-test-cwd-"))).resolve()
        home = (self.home or Path(tempfile.mkdtemp(prefix="pycodex-core-test-home-"))).resolve()
        cwd.mkdir(parents=True, exist_ok=True)
        home.mkdir(parents=True, exist_ok=True)
        config: dict[str, Any] = {}
        for mutator in self.config_mutators:
            mutator(config)
        return TestCodex(test_codex_exec(cwd=cwd, home=home), config, self.model)


@dataclass
class TestCodex:
    exec_builder: TestCodexExecBuilder
    config: dict[str, Any]
    model: str | None = None

    def cwd_path(self) -> Path:
        return self.exec_builder.cwd_path()

    def codex_home_path(self) -> Path:
        return self.exec_builder.home_path()

    def workspace_path(self, relative: str | Path) -> Path:
        return self.cwd_path() / relative

    async def write_file(self, relative: str | Path, content: str) -> Path:
        target = self.workspace_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")
        return target

    async def read_file_text(self, relative: str | Path) -> str:
        return await asyncio.to_thread(self.workspace_path(relative).read_text, encoding="utf-8")

    async def path_exists(self, relative: str | Path) -> bool:
        return await asyncio.to_thread(self.workspace_path(relative).exists)

    def run(self, *args: str, timeout: float = 60.0):
        environment = {"CODEX_MODEL": self.model} if self.model else None
        return self.exec_builder.run(*args, env=environment, timeout=timeout)


@dataclass
class TestCodexHarness:
    test: TestCodex

    @classmethod
    async def new(cls) -> "TestCodexHarness":
        return cls(await test_codex().build())

    @classmethod
    async def with_builder(cls, builder: TestCodexBuilder) -> "TestCodexHarness":
        return cls(await builder.build())

    def cwd(self) -> Path:
        return self.test.cwd_path()

    def path(self, relative: str | Path) -> Path:
        return self.test.workspace_path(relative)


def test_codex() -> TestCodexBuilder:
    return TestCodexBuilder()


test_codex.__test__ = False
TestCodex.__test__ = False
TestCodexBuilder.__test__ = False
TestCodexHarness.__test__ = False


__all__ = ["TestCodex", "TestCodexBuilder", "TestCodexHarness", "test_codex"]
