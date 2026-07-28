"""Timer argument handling ported from ``runtime/timers.rs``."""
from __future__ import annotations
import math
import threading
from typing import Any
JsonValue = Any
_U64_MAX = (1 << 64) - 1


class RuntimeTimerScheduler:
    def __init__(self) -> None:
        self._next_id = 1
        self._timers: dict[int, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule_timeout(self, callback: Any, delay_ms: JsonValue | None = None) -> int:
        delay = normalize_timeout_delay_ms(delay_ms)
        with self._lock:
            timeout_id = self._next_id
            self._next_id += 1
            timer = threading.Timer(
                delay / 1000.0,
                self.invoke_timeout_callback,
                args=(timeout_id, callback),
            )
            timer.daemon = True
            self._timers[timeout_id] = timer
        timer.start()
        return timeout_id

    def clear_timeout(self, value: JsonValue | None = None) -> bool:
        timeout_id = clear_timeout_id_from_value(value)
        if timeout_id is None:
            return False
        with self._lock:
            timer = self._timers.pop(timeout_id, None)
        if timer is None:
            return False
        timer.cancel()
        return True

    def invoke_timeout_callback(self, timeout_id: int, callback: Any) -> bool:
        with self._lock:
            timer = self._timers.pop(timeout_id, None)
        if timer is None:
            return False
        callback()
        return True

    def close(self) -> None:
        with self._lock:
            timers = tuple(self._timers.values())
            self._timers.clear()
        for timer in timers:
            timer.cancel()

def normalize_timeout_delay_ms(value: JsonValue | None = None) -> int:
    number = _js_number_value(value)
    if number is None or not math.isfinite(number) or number <= 0.0:
        return 0
    return min(math.trunc(number), _U64_MAX)


def clear_timeout_id_from_value(value: JsonValue | None = None) -> int | None:
    if value is None:
        return None
    number = _js_number_value(value)
    if number is None:
        raise ValueError("clearTimeout expects a numeric timeout id")
    if not math.isfinite(number) or number <= 0.0:
        return None
    return min(math.trunc(number), _U64_MAX)


def schedule_timeout(
    scheduler: RuntimeTimerScheduler,
    callback: Any,
    delay_ms: JsonValue | None = None,
) -> int:
    return scheduler.schedule_timeout(callback, delay_ms)


def clear_timeout(
    scheduler: RuntimeTimerScheduler,
    timeout_id: JsonValue | None = None,
) -> bool:
    return scheduler.clear_timeout(timeout_id)


def invoke_timeout_callback(
    scheduler: RuntimeTimerScheduler,
    timeout_id: int,
    callback: Any,
) -> bool:
    return scheduler.invoke_timeout_callback(timeout_id, callback)


__all__ = [
    "RuntimeTimerScheduler",
    "clear_timeout",
    "clear_timeout_id_from_value",
    "invoke_timeout_callback",
    "normalize_timeout_delay_ms",
    "schedule_timeout",
]


def _js_number_value(value: JsonValue | None) -> float | None:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return 0.0
        try:
            return float(text)
        except ValueError:
            return math.nan
    return None
