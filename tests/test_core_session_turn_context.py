from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pycodex.core.session.turn_context as turn_context_module
from pycodex.core.session.turn_context import local_iana_timezone, local_time_context


class _FixedZone:
    def __init__(self, key: str | None = None, zone: str | None = None) -> None:
        self.key = key
        self.zone = zone


def test_local_time_context_uses_iana_timezone_from_active_zoneinfo(monkeypatch) -> None:
    # Rust module contract: codex-core::session::turn_context resolves the
    # local date plus a stable IANA zone string for prompt environment context.
    fixed_now = datetime(2026, 7, 16, 9, 30, 0)
    fixed_tz = _FixedZone(key="Asia/Shanghai")

    class _FakeDateTime:
        @staticmethod
        def now(tz=None):
            if tz is not None:
                return fixed_now
            return SimpleNamespace(
                astimezone=lambda: SimpleNamespace(
                    strftime=fixed_now.strftime,
                    tzinfo=fixed_tz,
                )
            )

    monkeypatch.setattr(turn_context_module, "datetime", _FakeDateTime)
    monkeypatch.setattr(turn_context_module.os, "environ", {}, raising=False)

    assert local_iana_timezone() == "Asia/Shanghai"
    assert local_time_context() == ("2026-07-16", "Asia/Shanghai")


def test_local_time_context_falls_back_to_utc_when_timezone_is_unknown(monkeypatch) -> None:
    # Rust module contract: unresolved local zones fall back to Etc/UTC rather
    # than surfacing a localized display name.
    fixed_now = datetime(2026, 7, 16, 1, 2, 3)

    class _FakeDateTime:
        @staticmethod
        def now(tz=None):
            if tz is not None:
                return fixed_now
            return SimpleNamespace(
                astimezone=lambda: SimpleNamespace(
                    strftime=fixed_now.strftime,
                    tzinfo=_FixedZone(key=None, zone=None),
                )
            )

    monkeypatch.setattr(turn_context_module, "datetime", _FakeDateTime)
    monkeypatch.setattr(turn_context_module.os, "environ", {}, raising=False)
    monkeypatch.setattr(turn_context_module, "_windows_timezone_key_name", lambda: None)

    assert local_iana_timezone() is None
    assert local_time_context() == ("2026-07-16", "Etc/UTC")
