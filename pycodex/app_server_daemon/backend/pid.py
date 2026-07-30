from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import time


STOP_POLL_INTERVAL = 0.05
STOP_GRACE_PERIOD = 60.0
STOP_TIMEOUT = 70.0
START_TIMEOUT = 10.0
STDERR_LOG_TAIL_BYTES = 4096


@dataclass(frozen=True)
class PidRecord:
    pid: int
    process_start_time: str

    @classmethod
    def from_mapping(cls, value: object, path: Path) -> "PidRecord":
        if not isinstance(value, dict):
            raise RuntimeError(f"invalid pid file contents in {path}")
        pid = value.get("pid")
        start = value.get("processStartTime")
        if not isinstance(pid, int) or not isinstance(start, str) or not start:
            raise RuntimeError(f"invalid pid file contents in {path}")
        return cls(pid=pid, process_start_time=start)

    def to_mapping(self) -> dict[str, object]:
        return {"pid": self.pid, "processStartTime": self.process_start_time}


@dataclass(frozen=True)
class PidLogTail:
    path: Path
    contents: str

    def append_to_context(self, context: str) -> str:
        lines = "".join(f"\n  {line}" for line in self.contents.splitlines())
        return f"{context}\n\nManaged app-server stderr ({self.path}):{lines}"


class PidBackend:
    def __init__(
        self,
        codex_bin: Path,
        pid_file: Path,
        *,
        remote_control_enabled: bool | None,
        update_loop: bool,
    ) -> None:
        self.codex_bin = Path(codex_bin)
        self.pid_file = Path(pid_file)
        self.lock_file = self.pid_file.with_suffix(".pid.lock")
        self.remote_control_enabled = remote_control_enabled
        self.update_loop = update_loop

    @classmethod
    def new(
        cls,
        codex_bin: Path,
        pid_file: Path,
        remote_control_enabled: bool,
    ) -> "PidBackend":
        return cls(
            codex_bin,
            pid_file,
            remote_control_enabled=remote_control_enabled,
            update_loop=False,
        )

    @classmethod
    def new_update_loop(cls, codex_bin: Path, pid_file: Path) -> "PidBackend":
        return cls(
            codex_bin,
            pid_file,
            remote_control_enabled=None,
            update_loop=True,
        )

    def command_args(self) -> tuple[str, ...]:
        if self.update_loop:
            return ("app-server", "daemon", "pid-update-loop")
        if self.remote_control_enabled:
            return ("app-server", "--remote-control", "--listen", "unix://")
        return ("app-server", "--listen", "unix://")

    async def is_starting_or_running(self) -> bool:
        record = await self._read_pid_record()
        if record is not None and await _process_matches_record(record):
            return True
        if record is not None:
            await self._remove_record_if_equal(record)
        return await asyncio.to_thread(_reservation_lock_is_active, self.lock_file)

    async def start(self) -> int | None:
        if os.name == "nt":
            raise RuntimeError(
                "pid-managed app-server startup is unsupported on this platform"
            )
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        lock = await asyncio.to_thread(_acquire_lock, self.lock_file, START_TIMEOUT)
        try:
            record = await self._read_pid_record()
            if record is not None and await _process_matches_record(record):
                return None
            if record is not None:
                await self._remove_record_if_equal(record)
            self.pid_file.write_text("", encoding="utf-8")
            stderr_path = _stderr_log_file_for_pid_file(self.pid_file)
            stderr_file = stderr_path.open("wb")
            try:
                process = subprocess.Popen(
                    [str(self.codex_bin), *self.command_args()],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_file,
                    start_new_session=True,
                )
            except OSError as exc:
                self.pid_file.unlink(missing_ok=True)
                raise RuntimeError(
                    "failed to spawn detached app-server process using "
                    f"{self.codex_bin}: {exc}"
                ) from exc
            finally:
                stderr_file.close()
            try:
                start_time = await _read_process_start_time(process.pid)
                record = PidRecord(process.pid, start_time)
                temp = self.pid_file.with_suffix(".pid.tmp")
                temp.write_text(
                    json.dumps(record.to_mapping(), separators=(",", ":")),
                    encoding="utf-8",
                )
                temp.replace(self.pid_file)
            except BaseException:
                _signal_process(process.pid, signal.SIGTERM)
                self.pid_file.unlink(missing_ok=True)
                raise
            return process.pid
        finally:
            await asyncio.to_thread(_release_lock, lock)

    async def stop(self) -> None:
        if os.name == "nt":
            raise RuntimeError(
                "pid-managed app-server shutdown is unsupported on this platform"
            )
        record = await self._wait_for_pid_start()
        if record is None:
            return
        if not await _process_matches_record(record):
            await self._remove_record_if_equal(record)
            return
        _signal_process(record.pid, signal.SIGTERM)
        started = time.monotonic()
        deadline = started + STOP_TIMEOUT
        forced = False
        while time.monotonic() < deadline:
            if not await _process_matches_record(record):
                await self._remove_record_if_equal(record)
                return
            if not forced and time.monotonic() - started >= STOP_GRACE_PERIOD:
                target = -record.pid if self.update_loop else record.pid
                _signal_process(target, signal.SIGKILL)
                forced = True
            await asyncio.sleep(STOP_POLL_INTERVAL)
        raise RuntimeError(
            f"timed out waiting for pid-managed app server {record.pid} to stop"
        )

    async def _wait_for_pid_start(self) -> PidRecord | None:
        deadline = time.monotonic() + START_TIMEOUT
        while True:
            record = await self._read_pid_record()
            if record is not None:
                return record
            if not self.pid_file.exists():
                return None
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "timed out waiting for pid reservation in "
                    f"{self.pid_file} to finish initializing"
                )
            await asyncio.sleep(STOP_POLL_INTERVAL)

    async def _read_pid_record(self) -> PidRecord | None:
        try:
            contents = await asyncio.to_thread(
                self.pid_file.read_text,
                encoding="utf-8",
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RuntimeError(f"failed to read pid file {self.pid_file}: {exc}") from exc
        if not contents.strip():
            return None
        try:
            return PidRecord.from_mapping(json.loads(contents), self.pid_file)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"invalid pid file contents in {self.pid_file}: {exc}"
            ) from exc

    async def _remove_record_if_equal(self, expected: PidRecord) -> None:
        current = await self._read_pid_record()
        if current == expected:
            await asyncio.to_thread(self.pid_file.unlink, missing_ok=True)


async def read_stderr_log_tail(pid_file: Path) -> PidLogTail | None:
    path = _stderr_log_file_for_pid_file(pid_file)
    contents = await asyncio.to_thread(_read_log_tail, path, STDERR_LOG_TAIL_BYTES)
    if contents is None:
        return None
    return PidLogTail(path=path, contents=contents)


def _stderr_log_file_for_pid_file(pid_file: Path) -> Path:
    return pid_file.with_suffix(".stderr.log")


def _read_log_tail(path: Path, byte_limit: int) -> str | None:
    try:
        with path.open("rb") as file:
            file.seek(0, os.SEEK_END)
            length = file.tell()
            if length == 0:
                return None
            start = max(0, length - byte_limit)
            file.seek(start)
            contents = file.read()
    except FileNotFoundError:
        return None
    if start > 0 and b"\n" in contents:
        contents = contents.split(b"\n", 1)[1]
    text = contents.decode("utf-8", errors="replace").rstrip()
    return text or None


async def _read_process_start_time(pid: int) -> str:
    process = await asyncio.create_subprocess_exec(
        "ps",
        "-p",
        str(pid),
        "-o",
        "lstart=",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate()
    value = stdout.decode("utf-8").strip()
    if process.returncode != 0 or not value:
        raise RuntimeError(
            f"failed to read start time for pid-managed app server {pid}"
        )
    return value


async def _process_matches_record(record: PidRecord) -> bool:
    if os.name == "nt" or not _process_exists(record.pid):
        return False
    try:
        return await _read_process_start_time(record.pid) == record.process_start_time
    except RuntimeError:
        return False if not _process_exists(record.pid) else False


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_process(pid: int, value: signal.Signals) -> None:
    try:
        os.kill(pid, value)
    except ProcessLookupError:
        return


def _acquire_lock(path: Path, timeout: float) -> object:
    if os.name == "nt":
        raise RuntimeError(
            "pid-managed app-server startup is unsupported on this platform"
        )
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    file = path.open("a+b")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return file
        except BlockingIOError:
            if time.monotonic() >= deadline:
                file.close()
                raise RuntimeError(f"timed out waiting for pid lock {path}")
            time.sleep(STOP_POLL_INTERVAL)


def _release_lock(file: object) -> None:
    import fcntl

    typed = file
    fcntl.flock(typed.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
    typed.close()  # type: ignore[attr-defined]


def _reservation_lock_is_active(path: Path) -> bool:
    if os.name == "nt":
        return False
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as file:
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    return False


__all__ = [
    "PidBackend",
    "PidLogTail",
    "PidRecord",
    "read_stderr_log_tail",
]
