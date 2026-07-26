"""Data-driven self-test scenarios; these do not implement product behavior."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from threading import Event
from typing import Any

from parity_harness.outcomes.pipeline import (
    CallableCollector,
    CallableDriver,
    EventCompletion,
    FileExpectation,
    OutcomeExpectation,
    OutcomeSnapshot,
    ProcessOutcome,
    ResourceRegistry,
    Scenario,
)


@dataclass
class _ScenarioContext:
    completed: Event
    claim: str
    relative_path: str
    states: dict[str, Any]
    config: dict[str, Any] | None = None
    processes: tuple[ProcessOutcome, ...] = ()


def load_file_scenario(path: Path, *, contract_id: str) -> Scenario:
    value = json.loads(path.read_text(encoding="utf-8"))

    def drive(workspace: Path, _: ResourceRegistry) -> _ScenarioContext:
        context = _ScenarioContext(Event(), str(value["claim"]), str(value["path"]), dict(value["states"]))
        if value["action"] == "write-file":
            target = workspace / context.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(value["content"]), encoding="utf-8")
        elif value["action"] != "claim-only":
            if value["action"] != "persist-config-restart":
                raise ValueError(f"unknown fixture action: {value['action']}")
            target = workspace / context.relative_path
            target.write_text(
                json.dumps({str(value["key"]): value["value"]}), encoding="utf-8"
            )
            command = (
                sys.executable,
                "-c",
                "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))[sys.argv[2]])",
                str(target),
                str(value["key"]),
            )
            completed = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )
            context.config = {str(value["key"]): completed.stdout.strip()}
            context.processes = (
                ProcessOutcome(command, completed.returncode, completed.stdout, completed.stderr),
            )
        context.completed.set()
        return context

    def collect(workspace: Path, context: _ScenarioContext, resources: ResourceRegistry) -> OutcomeSnapshot:
        target = workspace / context.relative_path
        return OutcomeSnapshot(
            claims={"final_response": context.claim},
            files={context.relative_path: target.read_text(encoding="utf-8") if target.is_file() else None},
            config=context.config or {},
            processes=context.processes,
            pending_resources=resources.pending(),
            states=context.states,
        )

    if value["action"] == "persist-config-restart":
        expectation = OutcomeExpectation(
            files=(FileExpectation(str(value["path"]), True),),
            config={str(value["key"]): value["value"]},
            process_returncodes=(0,),
            process_stdout_contains=(str(value["value"]),),
            states=dict(value["states"]),
        )
    else:
        expectation = OutcomeExpectation(
            files=(FileExpectation(str(value["path"]), True, str(value["content"])),),
            states=dict(value["states"]),
        )
    return Scenario(
        scenario_id=str(value["scenario_id"]),
        contract_id=contract_id,
        driver=CallableDriver(drive),
        completion=EventCompletion(lambda context: context.completed),
        collector=CallableCollector(collect),
        expectation=expectation,
    )
