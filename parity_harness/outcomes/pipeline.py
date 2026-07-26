"""Scenario -> driver -> completion -> collector -> normalizer -> grader -> cleanup."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
from pathlib import Path
import subprocess
from threading import Event, Thread
import time
from typing import Any, Callable, Protocol

from parity_harness.model import Evidence, Finding, LayerResult, Verdict
from parity_harness.paths import ArtifactWorkspace


@dataclass(frozen=True)
class ProcessOutcome:
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    alive_after_completion: bool = False


@dataclass(frozen=True)
class TuiOutcome:
    frame: tuple[str, ...] = ()
    active_view: str = ""
    cursor: tuple[int, int] | None = None
    status_line: str = ""


@dataclass(frozen=True)
class OutcomeSnapshot:
    claims: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str | None] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    processes: tuple[ProcessOutcome, ...] = ()
    pending_resources: tuple[str, ...] = ()
    tui: TuiOutcome = field(default_factory=TuiOutcome)
    states: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FileExpectation:
    path: str
    exists: bool = True
    content: str | None = None


@dataclass(frozen=True)
class OutcomeExpectation:
    files: tuple[FileExpectation, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)
    process_returncodes: tuple[int, ...] = ()
    process_stdout_contains: tuple[str, ...] = ()
    no_pending_resources: bool = True
    tui: dict[str, Any] = field(default_factory=dict)
    states: dict[str, Any] = field(default_factory=dict)


class Driver(Protocol):
    def start(self, workspace: Path, resources: ResourceRegistry) -> Any: ...


class CompletionCondition(Protocol):
    def wait(self, context: Any, timeout: float) -> bool: ...


class Collector(Protocol):
    def collect(self, workspace: Path, context: Any, resources: ResourceRegistry) -> OutcomeSnapshot: ...


class Normalizer(Protocol):
    def normalize(self, snapshot: OutcomeSnapshot, workspace: Path) -> OutcomeSnapshot: ...


class Grader(Protocol):
    def grade(self, contract_id: str, snapshot: OutcomeSnapshot, expectation: OutcomeExpectation) -> LayerResult: ...


class CallableDriver:
    def __init__(self, callback: Callable[[Path, ResourceRegistry], Any]) -> None:
        self.callback = callback

    def start(self, workspace: Path, resources: ResourceRegistry) -> Any:
        return self.callback(workspace, resources)


class CallableCollector:
    def __init__(self, callback: Callable[[Path, Any, ResourceRegistry], OutcomeSnapshot]) -> None:
        self.callback = callback

    def collect(self, workspace: Path, context: Any, resources: ResourceRegistry) -> OutcomeSnapshot:
        return self.callback(workspace, context, resources)


class EventCompletion:
    """Waits on an explicit event rather than a fixed-duration sleep."""

    def __init__(self, event_getter: Callable[[Any], Event]) -> None:
        self.event_getter = event_getter

    def wait(self, context: Any, timeout: float) -> bool:
        return self.event_getter(context).wait(timeout)


class PredicateCompletion:
    """Polls a state predicate until success or deadline."""

    def __init__(self, predicate: Callable[[Any], bool], interval: float = 0.01) -> None:
        self.predicate = predicate
        self.interval = interval

    def wait(self, context: Any, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.predicate(context):
                return True
            time.sleep(self.interval)
        return self.predicate(context)


class DefaultNormalizer:
    def normalize(self, snapshot: OutcomeSnapshot, workspace: Path) -> OutcomeSnapshot:
        root = workspace.resolve().as_posix()

        def clean(value: str) -> str:
            return value.replace("\\", "/").replace(root, "<WORKSPACE>")

        return replace(
            snapshot,
            files={clean(path): value for path, value in snapshot.files.items()},
            processes=tuple(
                replace(item, stdout=clean(item.stdout), stderr=clean(item.stderr))
                for item in snapshot.processes
            ),
            tui=replace(snapshot.tui, frame=tuple(clean(line) for line in snapshot.tui.frame)),
        )


class ResourceRegistry:
    """Tracks subprocesses, threads, and callbacks for deterministic cleanup."""

    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[str]] = []
        self.threads: list[Thread] = []
        self.callbacks: list[Callable[[], None]] = []
        self.cleanup_failures: list[str] = []

    def register_process(self, process: subprocess.Popen[str]) -> subprocess.Popen[str]:
        self.processes.append(process)
        return process

    def register_thread(self, thread: Thread) -> Thread:
        self.threads.append(thread)
        return thread

    def register_cleanup(self, callback: Callable[[], None]) -> None:
        self.callbacks.append(callback)

    def pending(self) -> tuple[str, ...]:
        values = [f"process:{item.pid}" for item in self.processes if item.poll() is None]
        values.extend(f"thread:{item.name}" for item in self.threads if item.is_alive())
        return tuple(values)

    def cleanup(self) -> None:
        for callback in reversed(self.callbacks):
            try:
                callback()
            except Exception as exc:  # cleanup must continue after one failure
                self.cleanup_failures.append(f"callback: {exc}")
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=2)
            if thread.is_alive():
                self.cleanup_failures.append(f"thread still alive: {thread.name}")


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    contract_id: str
    driver: Driver
    completion: CompletionCondition
    collector: Collector
    expectation: OutcomeExpectation
    normalizer: Normalizer = field(default_factory=DefaultNormalizer)
    grader: Grader = field(default_factory=lambda: OutcomeGrader())
    timeout: float = 5.0


class OutcomeGrader:
    CHECKER_ID = "outcome.environment-state"

    def grade(
        self,
        contract_id: str,
        snapshot: OutcomeSnapshot,
        expectation: OutcomeExpectation,
    ) -> LayerResult:
        findings: list[Finding] = []
        for expected in expectation.files:
            value = snapshot.files.get(expected.path)
            exists = expected.path in snapshot.files and value is not None
            if exists != expected.exists:
                findings.append(
                    Finding(
                        "OUT001",
                        f"file existence differs: expected={expected.exists}, actual={exists}",
                        coordinate=expected.path,
                        evidence_type="filesystem-outcome",
                    )
                )
            if expected.content is not None and value != expected.content:
                findings.append(
                    Finding(
                        "OUT002",
                        "file content differs from expected environment state",
                        coordinate=expected.path,
                        evidence_type="filesystem-outcome",
                    )
                )
        for key, value in expectation.config.items():
            if snapshot.config.get(key) != value:
                findings.append(
                    Finding("OUT003", f"persisted config differs for {key}", coordinate=key, evidence_type="config-outcome")
                )
        if expectation.process_returncodes:
            actual_codes = tuple(item.returncode for item in snapshot.processes)
            if actual_codes != expectation.process_returncodes:
                findings.append(
                    Finding("OUT004", f"process return codes differ: {actual_codes}", evidence_type="process-outcome")
                )
        combined_stdout = "\n".join(item.stdout for item in snapshot.processes)
        for fragment in expectation.process_stdout_contains:
            if fragment not in combined_stdout:
                findings.append(
                    Finding("OUT005", f"process output is missing {fragment!r}", evidence_type="process-outcome")
                )
        if expectation.no_pending_resources and snapshot.pending_resources:
            findings.append(
                Finding(
                    "OUT006",
                    f"resources remain pending: {', '.join(snapshot.pending_resources)}",
                    evidence_type="resource-outcome",
                )
            )
        for key, value in expectation.states.items():
            if snapshot.states.get(key) != value:
                findings.append(
                    Finding("OUT007", f"final state differs for {key}", coordinate=key, evidence_type="state-outcome")
                )
        tui_value = asdict(snapshot.tui)
        for key, value in expectation.tui.items():
            if tui_value.get(key) != value:
                findings.append(
                    Finding("OUT008", f"TUI outcome differs for {key}", coordinate=key, evidence_type="tui-outcome")
                )

        evidence = Evidence(
            evidence_id=f"{contract_id}.outcome",
            evidence_type="environment-outcome",
            coordinate=contract_id,
            source=self.CHECKER_ID,
            status="verified" if not findings else "implemented",
            detail="Graded final environment state independently of agent claims",
            provenance=("environment",),
            metadata={"claims": snapshot.claims, "snapshot": snapshot.to_dict()},
        )
        return LayerResult(
            "outcome",
            contract_id,
            Verdict.FAILED if findings else Verdict.VERIFIED,
            evidence=(evidence,),
            findings=tuple(findings),
        )


class OutcomeRunner:
    def run(self, scenario: Scenario) -> LayerResult:
        resources = ResourceRegistry()
        context: Any = None
        snapshot: OutcomeSnapshot | None = None
        with ArtifactWorkspace(prefix=f"{scenario.scenario_id}-") as workspace:
            try:
                context = scenario.driver.start(workspace, resources)
                completed = scenario.completion.wait(context, scenario.timeout)
                if not completed:
                    return LayerResult(
                        "outcome",
                        scenario.contract_id,
                        Verdict.FAILED,
                        findings=(
                            Finding(
                                "OUT000",
                                "scenario did not reach its explicit completion condition",
                                coordinate=scenario.scenario_id,
                                evidence_type="completion-condition",
                            ),
                        ),
                    )
                snapshot = scenario.collector.collect(workspace, context, resources)
                snapshot = scenario.normalizer.normalize(snapshot, workspace)
                return scenario.grader.grade(scenario.contract_id, snapshot, scenario.expectation)
            except Exception as exc:
                return LayerResult(
                    "outcome",
                    scenario.contract_id,
                    Verdict.FAILED,
                    findings=(
                        Finding(
                            "OUT999",
                            f"scenario execution failed: {exc}",
                            coordinate=scenario.scenario_id,
                            evidence_type="harness-execution",
                        ),
                    ),
                )
            finally:
                resources.cleanup()


def write_snapshot(snapshot: OutcomeSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), indent=2) + "\n", encoding="utf-8")

