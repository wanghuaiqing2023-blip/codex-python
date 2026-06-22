import asyncio
from dataclasses import dataclass

import pytest

from pycodex.app_server.mcp_refresh import (
    McpRefreshError,
    build_refresh_config,
    queue_best_effort_refresh,
    queue_refresh,
    queue_strict_refresh,
)


@dataclass
class Config:
    cwd: str
    mcp_oauth_credentials_store_mode: str = "chatgpt"


class Thread:
    def __init__(self, thread_id: str, config: Config, *, submit_error: Exception | None = None) -> None:
        self.thread_id = thread_id
        self._config = config
        self.submit_error = submit_error
        self.submissions = []

    async def config(self) -> Config:
        return self._config

    async def submit(self, op):
        if self.submit_error is not None:
            raise self.submit_error
        self.submissions.append(op)
        return None


class McpManager:
    async def configured_servers(self, config: Config):
        return {"server": {"cwd": config.cwd}}


class ThreadManager:
    def __init__(self, threads: dict[str, Thread], *, load_errors: dict[str, Exception] | None = None) -> None:
        self.threads = threads
        self.load_errors = load_errors or {}
        self.mcp = McpManager()

    async def list_thread_ids(self):
        return list(self.threads)

    async def get_thread(self, thread_id: str):
        if thread_id in self.load_errors:
            raise self.load_errors[thread_id]
        return self.threads[thread_id]

    def mcp_manager(self):
        return self.mcp


class ConfigManager:
    def __init__(self, *, bad_cwd: str | None = None, latest_error: Exception | None = None) -> None:
        self.bad_cwd = bad_cwd
        self.latest_error = latest_error
        self.load_latest_calls = []
        self.good_loads = 0
        self.bad_loads = 0

    async def load_latest_config(self, fallback_cwd):
        self.load_latest_calls.append(fallback_cwd)
        if self.latest_error is not None:
            raise self.latest_error

    async def load_latest_config_for_thread(self, thread_config: Config):
        if thread_config.cwd == self.bad_cwd:
            self.bad_loads += 1
            raise RuntimeError("failed to load refresh config")
        self.good_loads += 1
        return thread_config


def test_strict_refresh_reports_thread_planning_failures_and_queues_nothing() -> None:
    # Rust: strict_refresh_reports_thread_planning_failures.
    good = Thread("good", Config("good"))
    bad = Thread("bad", Config("bad"))
    thread_manager = ThreadManager({"good": good, "bad": bad})
    config_manager = ConfigManager(bad_cwd="bad")

    with pytest.raises(RuntimeError, match="failed to load refresh config"):
        asyncio.run(queue_strict_refresh(thread_manager, config_manager))

    assert config_manager.load_latest_calls == [None]
    assert config_manager.good_loads == 1
    assert config_manager.bad_loads == 1
    assert good.submissions == []
    assert bad.submissions == []


def test_best_effort_refresh_attempts_every_loaded_thread() -> None:
    # Rust: best_effort_refresh_attempts_every_loaded_thread.
    good = Thread("good", Config("good"))
    bad = Thread("bad", Config("bad"))
    thread_manager = ThreadManager({"good": good, "bad": bad})
    config_manager = ConfigManager(bad_cwd="bad")

    asyncio.run(queue_best_effort_refresh(thread_manager, config_manager))

    assert config_manager.good_loads == 1
    assert config_manager.bad_loads == 1
    assert [op.type for op in good.submissions] == ["refresh_mcp_servers"]
    assert bad.submissions == []


def test_strict_refresh_wraps_thread_load_failures_like_rust() -> None:
    # Rust: get_thread errors are mapped to "failed to load thread {thread_id}: {err}".
    thread_manager = ThreadManager({"missing": Thread("missing", Config("missing"))}, load_errors={"missing": RuntimeError("gone")})
    config_manager = ConfigManager()

    with pytest.raises(McpRefreshError, match="failed to load thread missing: gone"):
        asyncio.run(queue_strict_refresh(thread_manager, config_manager))


def test_best_effort_refresh_skips_load_and_submit_failures() -> None:
    # Rust: best-effort warns and continues on get_thread/build/queue failures.
    good = Thread("good", Config("good"))
    submit_bad = Thread("submit_bad", Config("submit_bad"), submit_error=RuntimeError("closed"))
    skipped = Thread("skipped", Config("skipped"))
    thread_manager = ThreadManager(
        {"good": good, "submit_bad": submit_bad, "skipped": skipped},
        load_errors={"skipped": RuntimeError("gone")},
    )
    config_manager = ConfigManager()

    asyncio.run(queue_best_effort_refresh(thread_manager, config_manager))

    assert [op.type for op in good.submissions] == ["refresh_mcp_servers"]
    assert submit_bad.submissions == []
    assert skipped.submissions == []
    assert config_manager.good_loads == 2


def test_build_refresh_config_serializes_servers_and_oauth_mode() -> None:
    # Rust: build_refresh_config serializes configured servers and mcp_oauth_credentials_store_mode.
    thread_manager = ThreadManager({})
    config_manager = ConfigManager()

    config = asyncio.run(build_refresh_config(thread_manager, config_manager, Config("repo", "none")))

    assert config.to_mapping() == {
        "mcp_servers": {"server": {"cwd": "repo"}},
        "mcp_oauth_credentials_store_mode": "none",
    }


def test_queue_refresh_wraps_submit_errors_with_thread_id() -> None:
    # Rust: queue_refresh maps submit failure to thread-id-qualified io error.
    thread = Thread("t1", Config("repo"), submit_error=RuntimeError("mailbox closed"))

    with pytest.raises(McpRefreshError, match="failed to queue MCP refresh for thread t1: mailbox closed"):
        asyncio.run(queue_refresh("t1", thread, build_config()))


def build_config():
    from pycodex.protocol import McpServerRefreshConfig

    return McpServerRefreshConfig(mcp_servers={}, mcp_oauth_credentials_store_mode="none")
