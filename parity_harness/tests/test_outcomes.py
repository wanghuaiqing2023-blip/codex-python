from __future__ import annotations

import subprocess
import sys
from threading import Event, Thread
import unittest

from parity_harness.model import Verdict
from parity_harness.outcomes import OutcomeGrader
from parity_harness.outcomes.pipeline import (
    OutcomeExpectation,
    OutcomeSnapshot,
    ProcessOutcome,
    ResourceRegistry,
    TuiOutcome,
)
from parity_harness.paths import ARTIFACT_ROOT, ArtifactWorkspace
from parity_harness.workflow import example_contract, run_outcome


class OutcomeTests(unittest.TestCase):
    def test_real_file_result_passes(self) -> None:
        result = run_outcome(example_contract(), "success")
        self.assertEqual(result.verdict, Verdict.VERIFIED)

    def test_success_claim_without_environment_result_fails(self) -> None:
        result = run_outcome(example_contract(), "false-claim")
        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertIn("OUT001", {item.code for item in result.findings})
        self.assertEqual(result.evidence[0].metadata["claims"]["final_response"], "completed")

    def test_persisted_config_is_read_by_a_fresh_process(self) -> None:
        result = run_outcome(example_contract(), "config-restart")
        self.assertEqual(result.verdict, Verdict.VERIFIED)
        snapshot = result.evidence[0].metadata["snapshot"]
        self.assertEqual(snapshot["config"]["model"], "gpt-test")
        self.assertEqual(snapshot["processes"][0]["returncode"], 0)

    def test_process_config_tui_and_runtime_state_are_gradable(self) -> None:
        snapshot = OutcomeSnapshot(
            config={"model": "gpt-test"},
            processes=(ProcessOutcome(("demo",), 0, "ready", ""),),
            tui=TuiOutcome(("Working" ,), "composer", (0, 2), "idle"),
            states={"working": False, "turn": "completed"},
        )
        expectation = OutcomeExpectation(
            config={"model": "gpt-test"},
            process_returncodes=(0,),
            process_stdout_contains=("ready",),
            tui={"active_view": "composer", "status_line": "idle"},
            states={"working": False, "turn": "completed"},
        )
        result = OutcomeGrader().grade("outcome-types", snapshot, expectation)
        self.assertEqual(result.verdict, Verdict.VERIFIED)

    def test_process_and_async_resources_are_cleaned(self) -> None:
        registry = ResourceRegistry()
        process = registry.register_process(
            subprocess.Popen(
                (sys.executable, "-c", "import time; time.sleep(30)"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        stop = Event()
        thread = registry.register_thread(Thread(target=stop.wait, name="fixture-worker"))
        registry.register_cleanup(stop.set)
        thread.start()
        self.assertTrue(registry.pending())
        registry.cleanup()
        self.assertIsNotNone(process.poll())
        self.assertFalse(thread.is_alive())
        self.assertFalse(registry.cleanup_failures)

    def test_temporary_workspaces_stay_under_artifacts_and_are_removed(self) -> None:
        with ArtifactWorkspace("placement-") as workspace:
            path = workspace
            self.assertIn(ARTIFACT_ROOT.resolve(), workspace.resolve().parents)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
