"""Semantic event traces for contract-owned dynamic behavior."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any, Iterable

from parity_harness.model import Evidence, Finding, LayerResult, Verdict


NON_SEMANTIC_KEYS = frozenset(
    {
        "timestamp",
        "elapsed_ms",
        "session_id",
        "thread_id",
        "turn_id",
        "request_id",
        "uuid",
    }
)
EVENT_CATEGORIES = frozenset(
    {
        "input",
        "context",
        "tool.available",
        "tool.call",
        "tool.result",
        "protocol",
        "state",
        "tui",
        "retry",
        "cancel",
        "failure",
        "termination",
        "outcome.link",
    }
)


def _normalize_string(value: str, roots: tuple[Path, ...]) -> str:
    normalized = value.replace("\\", "/")
    for root in roots:
        root_value = root.resolve().as_posix()
        if normalized.lower().startswith(root_value.lower()):
            suffix = normalized[len(root_value) :].lstrip("/")
            return f"<ROOT>/{suffix}" if suffix else "<ROOT>"
    normalized = re.sub(
        r"(?i)\b[A-Z]:/(?:[^\s\"']+/)*([^/\s\"']+)",
        r"<ABS>/\1",
        normalized,
    )
    return normalized


def normalize_value(value: Any, roots: tuple[Path, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_value(item, roots)
            for key, item in sorted(value.items())
            if key not in NON_SEMANTIC_KEYS
        }
    if isinstance(value, list):
        return [normalize_value(item, roots) for item in value]
    if isinstance(value, str):
        return _normalize_string(value, roots)
    return value


@dataclass(frozen=True)
class SemanticEvent:
    category: str
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    state: str = ""
    tool: str = ""
    outcome_ref: str = ""

    def normalized(self, roots: tuple[Path, ...] = ()) -> SemanticEvent:
        return SemanticEvent(
            category=self.category,
            name=self.name,
            payload=normalize_value(self.payload, roots),
            state=self.state,
            tool=self.tool,
            outcome_ref=self.outcome_ref,
        )

    def key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SemanticEvent:
        return cls(
            category=str(value["category"]),
            name=str(value["name"]),
            payload=dict(value.get("payload", {})),
            state=str(value.get("state", "")),
            tool=str(value.get("tool", "")),
            outcome_ref=str(value.get("outcome_ref", "")),
        )


@dataclass(frozen=True)
class Trace:
    source: str
    contract_id: str
    events: tuple[SemanticEvent, ...]
    executable_baseline: bool = True
    baseline_detail: str = ""

    def normalized(self, roots: tuple[Path, ...] = ()) -> Trace:
        return Trace(
            source=self.source,
            contract_id=self.contract_id,
            events=tuple(event.normalized(roots) for event in self.events),
            executable_baseline=self.executable_baseline,
            baseline_detail=self.baseline_detail,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "contract_id": self.contract_id,
            "executable_baseline": self.executable_baseline,
            "baseline_detail": self.baseline_detail,
            "events": [asdict(event) for event in self.events],
        }


class TraceRecorder:
    """Records every supported event family through one semantic interface."""

    def __init__(self, source: str, contract_id: str) -> None:
        self.source = source
        self.contract_id = contract_id
        self._events: list[SemanticEvent] = []

    def record(
        self,
        category: str,
        name: str,
        *,
        payload: dict[str, Any] | None = None,
        state: str = "",
        tool: str = "",
        outcome_ref: str = "",
    ) -> None:
        if category not in EVENT_CATEGORIES:
            raise ValueError(f"unknown semantic event category: {category}")
        self._events.append(
            SemanticEvent(category, name, payload or {}, state, tool, outcome_ref)
        )

    def finish(self) -> Trace:
        return Trace(self.source, self.contract_id, tuple(self._events))

    def write(self, path: Path) -> Trace:
        trace = self.finish()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
        return trace


def load_trace(path: Path) -> Trace:
    value = json.loads(path.read_text(encoding="utf-8"))
    return Trace(
        source=str(value["source"]),
        contract_id=str(value["contract_id"]),
        events=tuple(SemanticEvent.from_dict(item) for item in value.get("events", ())),
        executable_baseline=bool(value.get("executable_baseline", True)),
        baseline_detail=str(value.get("baseline_detail", "")),
    )


def capture_jsonl_command(
    command: Iterable[str],
    *,
    source: str,
    contract_id: str,
    cwd: Path,
) -> Trace:
    """Capture a real adapter command that emits one semantic event per JSON line."""
    command = tuple(command)
    if not command:
        return Trace(source, contract_id, (), False, "no executable baseline command supplied")
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Trace(source, contract_id, (), False, f"baseline command unavailable: {exc}")
    if completed.returncode:
        rendered = shlex.join(command)
        return Trace(
            source,
            contract_id,
            (),
            False,
            f"baseline command failed ({completed.returncode}): {rendered}: {completed.stderr.strip()}",
        )
    try:
        events = tuple(
            SemanticEvent.from_dict(json.loads(line))
            for line in completed.stdout.splitlines()
            if line.strip()
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return Trace(source, contract_id, (), False, f"invalid JSONL trace: {exc}")
    return Trace(source, contract_id, events)


class TraceComparator:
    CHECKER_ID = "dynamic.semantic-trace"
    STRATEGIES = frozenset({"exact", "ordered-subsequence", "state-invariant", "outcome-linked"})

    def compare(
        self,
        reference: Trace,
        candidate: Trace,
        *,
        strategy: str = "exact",
        roots: tuple[Path, ...] = (),
    ) -> LayerResult:
        if strategy not in self.STRATEGIES:
            raise ValueError(f"unknown trace strategy: {strategy}")
        if reference.contract_id != candidate.contract_id:
            raise ValueError("trace contract IDs do not match")
        if not reference.executable_baseline:
            finding = Finding(
                "DYN000",
                reference.baseline_detail or "Rust baseline is not executable",
                severity="warning",
                coordinate=reference.contract_id,
                evidence_type="baseline",
            )
            return LayerResult(
                "dynamic",
                reference.contract_id,
                Verdict.INCONCLUSIVE,
                findings=(finding,),
            )
        expected = reference.normalized(roots).events
        actual = candidate.normalized(roots).events
        findings: list[Finding] = []

        if strategy == "exact":
            self._exact(expected, actual, findings)
        elif strategy == "ordered-subsequence":
            self._subsequence(expected, actual, findings)
            self._duplicates(expected, actual, findings)
        elif strategy == "state-invariant":
            self._states(expected, actual, findings)
        else:
            self._subsequence(expected, actual, findings)
            self._outcome_links(expected, actual, findings)

        evidence = Evidence(
            evidence_id=f"{reference.contract_id}.dynamic",
            evidence_type="semantic-trace-comparison",
            coordinate=reference.contract_id,
            source=self.CHECKER_ID,
            status="verified" if not findings else "implemented",
            detail=f"Compared Rust and Python semantic traces using {strategy}",
            provenance=("rust", "python", "cross"),
            metadata={
                "strategy": strategy,
                "reference_events": len(expected),
                "candidate_events": len(actual),
            },
        )
        return LayerResult(
            layer="dynamic",
            contract_id=reference.contract_id,
            verdict=Verdict.FAILED if findings else Verdict.VERIFIED,
            evidence=(evidence,),
            findings=tuple(findings),
        )

    @staticmethod
    def _exact(expected: tuple[SemanticEvent, ...], actual: tuple[SemanticEvent, ...], findings: list[Finding]) -> None:
        limit = max(len(expected), len(actual))
        for index in range(limit):
            left = expected[index] if index < len(expected) else None
            right = actual[index] if index < len(actual) else None
            if left != right:
                findings.append(
                    Finding(
                        "DYN001",
                        f"event mismatch at index {index}: expected={left!r}, actual={right!r}",
                        coordinate=str(index),
                        evidence_type="event-order",
                    )
                )

    @staticmethod
    def _subsequence(expected: tuple[SemanticEvent, ...], actual: tuple[SemanticEvent, ...], findings: list[Finding]) -> None:
        cursor = 0
        for event in expected:
            while cursor < len(actual) and actual[cursor] != event:
                cursor += 1
            if cursor == len(actual):
                findings.append(
                    Finding(
                        "DYN002",
                        f"required ordered event is missing: {event.category}:{event.name}",
                        coordinate=str(cursor),
                        evidence_type="event-presence",
                    )
                )
                return
            cursor += 1

    @staticmethod
    def _duplicates(expected: tuple[SemanticEvent, ...], actual: tuple[SemanticEvent, ...], findings: list[Finding]) -> None:
        expected_counts = Counter(event.key() for event in expected)
        actual_counts = Counter(event.key() for event in actual)
        for key, count in actual_counts.items():
            if count > expected_counts.get(key, 0):
                findings.append(
                    Finding(
                        "DYN003",
                        f"unexpected duplicate semantic event ({count} vs {expected_counts.get(key, 0)})",
                        coordinate=key,
                        evidence_type="event-duplication",
                    )
                )

    @staticmethod
    def _states(expected: tuple[SemanticEvent, ...], actual: tuple[SemanticEvent, ...], findings: list[Finding]) -> None:
        expected_states = tuple(event.state for event in expected if event.category == "state")
        actual_states = tuple(event.state for event in actual if event.category == "state")
        if expected_states != actual_states:
            findings.append(
                Finding(
                    "DYN004",
                    f"state sequence differs: expected={expected_states}, actual={actual_states}",
                    evidence_type="state-invariant",
                )
            )

    @staticmethod
    def _outcome_links(expected: tuple[SemanticEvent, ...], actual: tuple[SemanticEvent, ...], findings: list[Finding]) -> None:
        expected_links = {event.outcome_ref for event in expected if event.outcome_ref}
        actual_links = {event.outcome_ref for event in actual if event.outcome_ref}
        if expected_links != actual_links:
            findings.append(
                Finding(
                    "DYN005",
                    f"outcome links differ: expected={sorted(expected_links)}, actual={sorted(actual_links)}",
                    evidence_type="outcome-link",
                )
            )

