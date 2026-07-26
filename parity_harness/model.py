"""Shared evidence types crossing harness layer boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from typing import Any


class MappingStatus(StrEnum):
    CANDIDATE = "candidate"
    MAPPED = "mapped"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    INCONCLUSIVE = "inconclusive"


class Verdict(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    severity: str = "error"
    coordinate: str = ""
    evidence_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Finding:
        return cls(**value)


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    evidence_type: str
    coordinate: str
    source: str
    status: str
    detail: str
    provenance: tuple[str, ...] = ()
    artifact: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Evidence:
        data = dict(value)
        data["provenance"] = tuple(data.get("provenance", ()))
        return cls(**data)


@dataclass(frozen=True)
class LayerResult:
    layer: str
    contract_id: str
    verdict: Verdict
    evidence: tuple[Evidence, ...] = ()
    findings: tuple[Finding, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict.value
        return data

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> LayerResult:
        return cls(
            layer=str(value["layer"]),
            contract_id=str(value["contract_id"]),
            verdict=Verdict(value["verdict"]),
            evidence=tuple(Evidence.from_dict(item) for item in value.get("evidence", ())),
            findings=tuple(Finding.from_dict(item) for item in value.get("findings", ())),
            metadata=dict(value.get("metadata", {})),
        )

    @classmethod
    def read_json(cls, path: Path) -> LayerResult:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def result_verdict(findings: list[Finding], *, conclusive: bool = True) -> Verdict:
    if any(item.severity == "error" for item in findings):
        return Verdict.FAILED
    if not conclusive:
        return Verdict.INCONCLUSIVE
    return Verdict.VERIFIED
