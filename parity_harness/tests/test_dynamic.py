from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from parity_harness.dynamic import (
    SemanticEvent,
    Trace,
    TraceComparator,
    capture_jsonl_command,
    load_trace,
)
from parity_harness.model import Verdict
from parity_harness.paths import ArtifactWorkspace
from parity_harness.workflow import TRACE_ROOT, example_contract, run_dynamic


class DynamicTests(unittest.TestCase):
    def test_nonsemantic_ids_timestamps_and_absolute_roots_are_normalized(self) -> None:
        result = run_dynamic(example_contract(), "matching")
        self.assertEqual(result.verdict, Verdict.VERIFIED)

    def test_missing_duplicate_and_out_of_order_events_fail(self) -> None:
        for scenario, expected_code in (
            ("missing", "DYN001"),
            ("duplicate", "DYN001"),
            ("out-of-order", "DYN001"),
        ):
            with self.subTest(scenario=scenario):
                result = run_dynamic(example_contract(), scenario)
                self.assertEqual(result.verdict, Verdict.FAILED)
                self.assertIn(expected_code, {item.code for item in result.findings})

    def test_ordered_subsequence_detects_missing_and_duplicate_events(self) -> None:
        reference = load_trace(TRACE_ROOT / "rust_reference.json")
        missing = load_trace(TRACE_ROOT / "python_missing.json")
        duplicate = load_trace(TRACE_ROOT / "python_duplicate.json")
        comparator = TraceComparator()
        self.assertIn("DYN002", {item.code for item in comparator.compare(reference, missing, strategy="ordered-subsequence").findings})
        self.assertIn("DYN003", {item.code for item in comparator.compare(reference, duplicate, strategy="ordered-subsequence").findings})

    def test_state_and_outcome_link_strategies(self) -> None:
        events = (
            SemanticEvent("state", "working", state="working"),
            SemanticEvent("outcome.link", "done", outcome_ref="file:x"),
            SemanticEvent("state", "idle", state="idle"),
        )
        reference = Trace("rust", "contract", events)
        wrong_state = Trace("python", "contract", (events[0], events[1], SemanticEvent("state", "busy", state="busy")))
        wrong_link = Trace("python", "contract", (events[0], SemanticEvent("outcome.link", "done", outcome_ref="file:y"), events[2]))
        self.assertIn("DYN004", {item.code for item in TraceComparator().compare(reference, wrong_state, strategy="state-invariant").findings})
        self.assertIn("DYN005", {item.code for item in TraceComparator().compare(reference, wrong_link, strategy="outcome-linked").findings})

    def test_unavailable_rust_baseline_is_inconclusive(self) -> None:
        result = run_dynamic(example_contract(), "unavailable")
        self.assertEqual(result.verdict, Verdict.INCONCLUSIVE)
        self.assertIn("DYN000", {item.code for item in result.findings})

    def test_command_adapter_records_jsonl_or_reports_unavailable(self) -> None:
        event = {"category": "termination", "name": "completed"}
        command = (sys.executable, "-c", f"import json; print(json.dumps({event!r}))")
        with ArtifactWorkspace("capture-") as workspace:
            trace = capture_jsonl_command(command, source="rust", contract_id="capture", cwd=workspace)
            self.assertTrue(trace.executable_baseline)
            self.assertEqual(trace.events[0].name, "completed")
            unavailable = capture_jsonl_command((), source="rust", contract_id="capture", cwd=workspace)
            self.assertFalse(unavailable.executable_baseline)


if __name__ == "__main__":
    unittest.main()

