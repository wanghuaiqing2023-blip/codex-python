"""Textual TUI scenario runner for fake-runtime automation."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from pycodex.tui.app.runtime import TuiAppRuntime
from pycodex.tui.chatwidget.protocol import ServerNotification
from pycodex.tui.textual_compat import Static
from pycodex.tui.textual_runtime import CodexComposerTextArea, PyCodexTextualApp, configure_app_runtime_thread_identity

from .runtime import ManualActiveThreadRuntime


@dataclass
class TextualScenario:
    runtime: ManualActiveThreadRuntime
    app: PyCodexTextualApp
    pilot: object

    async def submit(self, prompt: str) -> None:
        composer = self.app.query_one("#composer", CodexComposerTextArea)
        composer.text = prompt
        composer.move_cursor((len(prompt.splitlines()) - 1, len(prompt.splitlines()[-1]) if prompt else 0))
        await self.pilot.press("enter")
        await self.pilot.pause(0.02)

    async def wait_for_submit_count(self, count: int, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.runtime.submitted_ops) >= count:
                return
            await self.pilot.pause(0.02)
        raise AssertionError(f"TUI submitted {len(self.runtime.submitted_ops)} ops, expected at least {count}")

    async def wait_for_idle(self, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.app._busy:
                return
            await self.pilot.pause(0.02)
        raise AssertionError("Textual TUI did not become idle")

    async def wait_for_text(self, needle: str, *, timeout: float = 1.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = self.text()
            if needle in text:
                return text
            await self.pilot.pause(0.02)
        raise AssertionError(f"Textual TUI did not render {needle!r}; text was:\n{self.text()}")

    def send(self, notification: ServerNotification) -> None:
        self.runtime.send(notification)

    def text(self) -> str:
        parts = [f"{block.label}\n{block.text}" for block in self.app._blocks]
        status = self.app.query_one("#status-line", Static).renderable
        return "\n\n".join([*parts, str(status)])

    def blocks(self) -> list[tuple[str, str]]:
        return [(block.label, block.text) for block in self.app._blocks]

    def status(self) -> str:
        return str(self.app.query_one("#status-line", Static).renderable)


@asynccontextmanager
async def start_textual_scenario(
    *,
    runtime: ManualActiveThreadRuntime | None = None,
    size: tuple[int, int] = (100, 32),
) -> AsyncIterator[TextualScenario]:
    active_runtime = runtime or ManualActiveThreadRuntime()
    app_runtime = TuiAppRuntime(active_runtime)
    configure_app_runtime_thread_identity(app_runtime, active_runtime)
    app = PyCodexTextualApp(app_runtime)
    async with app.run_test(size=size) as pilot:
        yield TextualScenario(runtime=active_runtime, app=app, pilot=pilot)
