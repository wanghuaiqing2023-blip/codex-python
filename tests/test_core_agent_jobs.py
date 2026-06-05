import json
import tempfile
import unittest
from pathlib import Path

from pycodex.core.tools.handlers.agent_jobs import (
    AgentJobItem,
    InMemoryAgentJobStore,
    ReportAgentJobResultHandler,
    SpawnAgentsOnCsvHandler,
    build_agent_job_items,
    build_worker_prompt,
    create_report_agent_job_result_tool,
    create_spawn_agents_on_csv_tool,
    csv_escape,
    default_output_csv_path,
    ensure_unique_headers,
    normalize_concurrency,
    normalize_max_runtime_seconds,
    parse_csv,
    render_instruction_template,
    render_job_csv,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.router import FunctionCallError


class CoreAgentJobsTests(unittest.TestCase):
    def test_specs_match_upstream_required_fields(self) -> None:
        spawn = create_spawn_agents_on_csv_tool()
        self.assertEqual(spawn["name"], "spawn_agents_on_csv")
        self.assertEqual(spawn["parameters"]["required"], ["csv_path", "instruction"])
        report = create_report_agent_job_result_tool()
        self.assertEqual(report["name"], "report_agent_job_result")
        self.assertEqual(report["parameters"]["required"], ["job_id", "item_id", "result"])

    def test_parse_csv_supports_quotes_commas_and_bom(self) -> None:
        headers, rows = parse_csv("\ufeffid,name\n1,\"alpha, beta\"\n2,gamma\n\n")
        self.assertEqual(headers, ["id", "name"])
        self.assertEqual(rows, [["1", "alpha, beta"], ["2", "gamma"]])

    def test_csv_escape_quotes_when_needed(self) -> None:
        self.assertEqual(csv_escape("simple"), "simple")
        self.assertEqual(csv_escape("a,b"), '"a,b"')
        self.assertEqual(csv_escape('a"b'), '"a""b"')

    def test_render_instruction_template_expands_placeholders_and_escapes_braces(self) -> None:
        rendered = render_instruction_template(
            "Review {path} in {area}. Use {{literal}}.",
            {"path": "src/lib.rs", "area": "test"},
        )
        self.assertEqual(rendered, "Review src/lib.rs in test. Use {literal}.")

    def test_build_worker_prompt_matches_agent_job_contract(self) -> None:
        prompt = build_worker_prompt(
            job_id="job-1",
            item_id="item-1",
            instruction="Review {path} with severity {severity}.",
            row_json={"path": "src/lib.rs", "severity": 2},
            output_schema={"type": "object", "required": ["summary"]},
        )

        self.assertIn("You are processing one item for a generic agent job.", prompt)
        self.assertIn("Job ID: job-1", prompt)
        self.assertIn("Item ID: item-1", prompt)
        self.assertIn("Review src/lib.rs with severity 2.", prompt)
        self.assertIn('"path": "src/lib.rs"', prompt)
        self.assertIn('"required": [', prompt)
        self.assertIn("You MUST call the `report_agent_job_result` tool exactly once", prompt)
        self.assertIn('1. `job_id` = "job-1"', prompt)
        self.assertIn('2. `item_id` = "item-1"', prompt)
        self.assertIn("After the tool call succeeds, stop.", prompt)

    def test_build_agent_job_items_uses_id_column_and_suffixes_duplicates(self) -> None:
        items = build_agent_job_items(
            ["id", "name"],
            [["A", "one"], ["A", "two"], ["", "three"]],
            "id",
        )
        self.assertEqual([item.item_id for item in items], ["A", "A-2", "row-3"])
        self.assertEqual(items[0].row_index, 0)
        self.assertEqual(items[0].row_json, {"id": "A", "name": "one"})

    def test_build_agent_job_items_rejects_missing_id_column_and_short_rows(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "id_column missing"):
            build_agent_job_items(["id"], [["1"]], "missing")
        with self.assertRaisesRegex(FunctionCallError, "csv row 2 has 1 fields"):
            build_agent_job_items(["id", "name"], [["1"]], None)

    def test_unique_headers_and_runtime_bounds(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "csv header path is duplicated"):
            ensure_unique_headers(["path", "path"])
        self.assertEqual(normalize_concurrency(None, None), 16)
        self.assertEqual(normalize_concurrency(100, None), 64)
        self.assertEqual(normalize_concurrency(32, 4), 4)
        with self.assertRaisesRegex(FunctionCallError, "max_runtime_seconds must be >= 1"):
            normalize_max_runtime_seconds(0)

    def test_default_output_path_uses_stem_and_job_suffix(self) -> None:
        path = default_output_csv_path(Path("input/tasks.csv"), "1234567890")
        self.assertEqual(path, Path("input/tasks.agent-job-12345678.csv"))

    def test_render_job_csv_matches_status_and_result_columns(self) -> None:
        content = render_job_csv(
            ["id", "name"],
            [
                AgentJobItem(
                    job_id="job",
                    item_id="item",
                    row_index=0,
                    row_json={"id": "1", "name": "a,b"},
                    status="completed",
                    result_json={"ok": True},
                )
            ],
        )
        self.assertIn("job_id,item_id,row_index,source_id,status", content)
        self.assertIn('"a,b"', content)
        self.assertIn('"{""ok"":true}"', content)

    def test_report_agent_job_result_records_and_cancels_on_stop(self) -> None:
        store = InMemoryAgentJobStore()
        output = ReportAgentJobResultHandler(store, reporting_thread_id="thread").handle(
            ToolPayload.function(
                json.dumps(
                    {
                        "job_id": "job",
                        "item_id": "item",
                        "result": {"ok": True},
                        "stop": True,
                    }
                )
            )
        )
        self.assertEqual(json.loads(output.into_text()), {"accepted": True})
        self.assertEqual(store.reported_results[("job", "item")], {"ok": True})
        self.assertEqual(store.cancelled_jobs["job"], "cancelled by worker request")

    def test_report_agent_job_result_rejects_non_object_result_and_payload(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "result must be a JSON object"):
            ReportAgentJobResultHandler().handle(
                ToolPayload.function(json.dumps({"job_id": "j", "item_id": "i", "result": []}))
            )
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            ReportAgentJobResultHandler().handle(ToolPayload.custom("raw"))

    def test_spawn_prepare_only_reads_csv_and_builds_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.csv").write_text("id,name\nA,one\n", encoding="utf-8")
            job_id, output_path, items = SpawnAgentsOnCsvHandler().handle_prepare_only(
                json.dumps({"csv_path": "input.csv", "instruction": "Process {name}", "id_column": "id"}),
                root,
            )
        self.assertEqual(len(job_id), 36)
        self.assertTrue(output_path.endswith(f".agent-job-{job_id[:8]}.csv"))
        self.assertEqual(items[0].item_id, "A")


if __name__ == "__main__":
    unittest.main()
