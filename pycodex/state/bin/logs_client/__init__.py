"""CLI port of ``codex-state/src/bin/logs_client.rs``."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import os
from pathlib import Path
from typing import Any, Sequence

from pycodex.state.model import LogQuery, LogRow
from pycodex.state.runtime import StateRuntime, logs_db_path

from . import formatter, matcher


class LogLevelThreshold(str, Enum):
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"

    def levels_upper(self) -> tuple[str, ...]:
        levels = ("TRACE", "DEBUG", "INFO", "WARN", "ERROR")
        return levels[levels.index(self.value.upper()) :]


@dataclass(frozen=True)
class LogFilter:
    levels_upper: tuple[str, ...] = ()
    from_ts: int | None = None
    to_ts: int | None = None
    module_like: tuple[str, ...] = ()
    file_like: tuple[str, ...] = ()
    thread_ids: tuple[str, ...] = ()
    search: str | None = None
    include_threadless: bool = False


def _level(value: str) -> LogLevelThreshold:
    try:
        return LogLevelThreshold(value.lower())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid log level: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-state-logs",
        description="Tail Codex logs from the dedicated logs SQLite DB with simple filters",
    )
    parser.add_argument("--codex-home", type=Path, default=os.environ.get("CODEX_HOME"))
    parser.add_argument("--db", type=Path)
    parser.add_argument("--level", type=_level)
    parser.add_argument("--from", dest="from_value")
    parser.add_argument("--to", dest="to_value")
    parser.add_argument("--module", action="append", default=[])
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--thread-id", action="append", default=[])
    parser.add_argument("--search")
    parser.add_argument("--threadless", action="store_true")
    parser.add_argument("--backfill", type=int, default=200)
    parser.add_argument("--poll-ms", type=int, default=500)
    parser.add_argument("--compact", action="store_true")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def resolve_db_path(args: argparse.Namespace) -> Path:
    if args.db is not None:
        return Path(args.db)
    return logs_db_path(args.codex_home or default_codex_home())


def default_codex_home() -> Path:
    return Path.home() / ".codex"


def parse_timestamp(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(parsed.timestamp())


def build_filter(args: argparse.Namespace) -> LogFilter:
    return LogFilter(
        levels_upper=() if args.level is None else args.level.levels_upper(),
        from_ts=None if args.from_value is None else parse_timestamp(args.from_value),
        to_ts=None if args.to_value is None else parse_timestamp(args.to_value),
        module_like=tuple(value for value in args.module if value),
        file_like=tuple(value for value in args.file if value),
        thread_ids=tuple(value for value in args.thread_id if value),
        search=args.search,
        include_threadless=args.threadless,
    )


def to_log_query(
    filter_: LogFilter,
    limit: int | None,
    after_id: int | None,
    descending: bool,
) -> LogQuery:
    return LogQuery(
        levels_upper=filter_.levels_upper,
        from_ts=filter_.from_ts,
        to_ts=filter_.to_ts,
        module_like=filter_.module_like,
        file_like=filter_.file_like,
        thread_ids=filter_.thread_ids,
        search=filter_.search,
        include_threadless=filter_.include_threadless,
        after_id=after_id,
        limit=limit,
        descending=descending,
    )


async def fetch_backfill(runtime: StateRuntime, filter_: LogFilter, backfill: int) -> list[LogRow]:
    return await runtime.query_logs(to_log_query(filter_, backfill, None, True))


async def fetch_new_rows(runtime: StateRuntime, filter_: LogFilter, last_id: int) -> list[LogRow]:
    return await runtime.query_logs(to_log_query(filter_, None, last_id, False))


async def fetch_max_id(runtime: StateRuntime, filter_: LogFilter) -> int:
    return await runtime.max_log_id(to_log_query(filter_, None, None, False))


async def print_backfill(
    runtime: StateRuntime,
    filter_: LogFilter,
    backfill: int,
    compact: bool,
) -> int:
    if backfill == 0:
        return 0
    rows = await fetch_backfill(runtime, filter_, backfill)
    rows.reverse()
    last_id = 0
    for row in rows:
        last_id = max(last_id, row.id)
        print(format_row(row, compact))
    return last_id


def heuristic_formatting(message: str) -> str:
    return formatter.apply_patch(message) if matcher.apply_patch(message) else formatter.bold(message)


def format_row(row: LogRow, compact: bool) -> str:
    timestamp = formatter.dim(formatter.ts(row.ts, row.ts_nanos, compact))
    level = formatter.level(row.level)
    message = heuristic_formatting(row.message or "")
    if compact:
        return f"{timestamp} {level} {message}"
    thread_id = formatter.blue_dim(row.thread_id or "-")
    target = formatter.dim(row.target)
    return f"{timestamp} {level} [{thread_id}] {target} - {message}"


async def run(args: argparse.Namespace) -> None:
    db_path = resolve_db_path(args)
    filter_ = build_filter(args)
    runtime = await StateRuntime.init(db_path.parent, "logs-client")
    try:
        last_id = await print_backfill(runtime, filter_, args.backfill, args.compact)
        if last_id == 0:
            last_id = await fetch_max_id(runtime, filter_)
        while True:
            for row in await fetch_new_rows(runtime, filter_, last_id):
                last_id = max(last_id, row.id)
                print(format_row(row, args.compact))
            await asyncio.sleep(args.poll_ms / 1000)
    finally:
        await runtime.close()


def main(argv: Sequence[str] | None = None) -> int:
    asyncio.run(run(parse_args(argv)))
    return 0


__all__ = [
    "LogFilter",
    "LogLevelThreshold",
    "build_filter",
    "build_parser",
    "default_codex_home",
    "fetch_backfill",
    "fetch_max_id",
    "fetch_new_rows",
    "format_row",
    "heuristic_formatting",
    "main",
    "parse_args",
    "parse_timestamp",
    "print_backfill",
    "resolve_db_path",
    "run",
    "to_log_query",
]
