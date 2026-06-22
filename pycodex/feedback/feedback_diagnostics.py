"""Connectivity diagnostics ported from ``codex-feedback/src/feedback_diagnostics.rs``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME = "codex-connectivity-diagnostics.txt"
PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)
PROXY_DIAGNOSTIC_HEADLINE = "Proxy environment variables are set and may affect connectivity."


@dataclass(frozen=True)
class FeedbackDiagnostic:
    headline: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeedbackDiagnostics:
    diagnostics: list[FeedbackDiagnostic] = field(default_factory=list)

    @classmethod
    def new(cls, diagnostics: Iterable[FeedbackDiagnostic]) -> "FeedbackDiagnostics":
        return cls(list(diagnostics))

    @classmethod
    def collect_from_env(cls, env: Mapping[str, str] | None = None) -> "FeedbackDiagnostics":
        return cls.collect_from_pairs((os.environ if env is None else env).items())

    @classmethod
    def collect_from_pairs(cls, pairs: Iterable[tuple[Any, Any]]) -> "FeedbackDiagnostics":
        env = {str(key): str(value) for key, value in pairs}
        proxy_details = [f"{key} = {env[key]}" for key in PROXY_ENV_VARS if key in env]
        if not proxy_details:
            return cls()
        return cls([FeedbackDiagnostic(headline=PROXY_DIAGNOSTIC_HEADLINE, details=proxy_details)])

    def is_empty(self) -> bool:
        return not self.diagnostics

    def attachment_text(self) -> str | None:
        if not self.diagnostics:
            return None
        lines = ["Connectivity diagnostics", ""]
        for diagnostic in self.diagnostics:
            lines.append(f"- {diagnostic.headline}")
            lines.extend(f"  - {detail}" for detail in diagnostic.details)
        return "\n".join(lines)

    def to_json_text(self) -> str:
        return json.dumps(
            [
                {
                    "headline": diagnostic.headline,
                    "details": list(diagnostic.details),
                }
                for diagnostic in self.diagnostics
            ],
            ensure_ascii=False,
        )


__all__ = [
    "FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME",
    "PROXY_DIAGNOSTIC_HEADLINE",
    "PROXY_ENV_VARS",
    "FeedbackDiagnostic",
    "FeedbackDiagnostics",
]
