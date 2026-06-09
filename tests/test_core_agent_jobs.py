import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from pycodex.core.tools.handlers.agent_jobs import (
    AgentJobItem,
    AgentJobItemCreateParams,
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
from pycodex.core.tools.context import ToolCallSource, ToolInvocation
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ToolName
from pycodex.core.environment_selection import ResolvedTurnEnvironments, TurnEnvironment


class FakeAgentControl:
    def __init__(self, store: InMemoryAgentJobStore | None = None, *, auto_report: bool = True) -> None:
        self.store = store
        self.auto_report = auto_report
        self.next_thread_id = 1
        self.shutdowns: list[str] = []

    def spawn_agent_with_metadata(self, spawn_config: object, items: tuple[object, ...], session_source: object, options: object) -> dict[str, str]:
        thread_id = f"thread-{self.next_thread_id}"
        self.next_thread_id += 1
        return {"thread_id": thread_id}

    def subscribe_status(self, thread_id: object) -> None:
        return None

    def get_status(self, thread_id: object) -> str:
        if self.auto_report and self.store is not None:
            thread_id_text = str(thread_id)
            for item in list(self.store.items.values()):
                if item.assigned_thread_id == thread_id_text and item.status == "running" and item.result_json is None:
                    self.store.report_agent_job_item_result(
                        item.job_id,
                        item.item_id,
                        thread_id_text,
                        {"ok": True},
                    )
                    break
        return {"type": "completed"}

    def shutdown_live_agent(self, thread_id: object) -> None:
        self.shutdowns.append(str(thread_id))


def agent_job_session(store: InMemoryAgentJobStore, agent_control: FakeAgentControl | None = None) -> object:
    return type(
        "Session",
        (),
        {
            "state_db": store,
            "agent_control": agent_control or FakeAgentControl(store),
        },
    )()


class CoreAgentJobsTests(unittest.TestCase):
    def test_specs_match_upstream_required_fields(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/agent_jobs_spec.rs
        # Rust tests: agent_jobs_spec_tests.rs::spawn_agents_on_csv_tool_requires_csv_and_instruction
        # and report_agent_job_result_tool_requires_result_payload
        spawn = create_spawn_agents_on_csv_tool()
        self.assertEqual(spawn["name"], "spawn_agents_on_csv")
        self.assertEqual(
            spawn["description"],
            "Process a CSV by spawning one worker sub-agent per row. The instruction string is a template where `{column}` placeholders are replaced with row values. Each worker must call `report_agent_job_result` with a JSON object (matching `output_schema` when provided); missing reports are treated as failures. This call blocks until all rows finish and automatically exports results to `output_csv_path` (or a default path).",
        )
        self.assertFalse(spawn["strict"])
        self.assertIsNone(spawn.get("defer_loading"))
        self.assertIsNone(spawn.get("output_schema"))
        self.assertEqual(spawn["parameters"]["required"], ["csv_path", "instruction"])
        self.assertFalse(spawn["parameters"]["additionalProperties"])
        self.assertEqual(
            spawn["parameters"]["properties"],
            {
                "csv_path": {
                    "type": "string",
                    "description": "Path to the CSV file containing input rows.",
                },
                "instruction": {
                    "type": "string",
                    "description": "Instruction template to apply to each CSV row. Use {column_name} placeholders to inject values from the row.",
                },
                "id_column": {
                    "type": "string",
                    "description": "Optional column name to use as stable item id.",
                },
                "output_csv_path": {
                    "type": "string",
                    "description": "Optional output CSV path for exported results.",
                },
                "max_concurrency": {
                    "type": "number",
                    "description": "Maximum concurrent workers for this job. Defaults to 16 and is capped by config.",
                },
                "max_workers": {
                    "type": "number",
                    "description": "Alias for max_concurrency. Set to 1 to run sequentially.",
                },
                "max_runtime_seconds": {
                    "type": "number",
                    "description": "Maximum runtime per worker before it is failed. Defaults to 1800 seconds.",
                },
                "output_schema": {"type": "object", "properties": {}},
            },
        )

        report = create_report_agent_job_result_tool()
        self.assertEqual(report["name"], "report_agent_job_result")
        self.assertEqual(
            report["description"],
            "Worker-only tool to report a result for an agent job item. Main agents should not call this.",
        )
        self.assertFalse(report["strict"])
        self.assertIsNone(report.get("defer_loading"))
        self.assertIsNone(report.get("output_schema"))
        self.assertEqual(report["parameters"]["required"], ["job_id", "item_id", "result"])
        self.assertFalse(report["parameters"]["additionalProperties"])
        self.assertEqual(
            report["parameters"]["properties"],
            {
                "job_id": {
                    "type": "string",
                    "description": "Identifier of the job.",
                },
                "item_id": {
                    "type": "string",
                    "description": "Identifier of the job item.",
                },
                "result": {"type": "object", "properties": {}},
                "stop": {
                    "type": "boolean",
                    "description": "Optional. When true, cancels the remaining job items after this result is recorded.",
                },
            },
        )

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
            "Review {path} in {area}. Also see {file path}. Use {{literal}}.",
            {"path": "src/lib.rs", "area": "test", "file path": "docs/readme.md"},
        )
        self.assertEqual(
            rendered,
            "Review src/lib.rs in test. Also see docs/readme.md. Use {literal}.",
        )

    def test_render_instruction_template_leaves_unknown_placeholders(self) -> None:
        # Rust test: render_instruction_template_leaves_unknown_placeholders.
        rendered = render_instruction_template("Check {path} then {missing}", {"path": "src/lib.rs"})

        self.assertEqual(rendered, "Check src/lib.rs then {missing}")

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
        job_id = "job"
        item_id = "item"
        store.create_agent_job(
            job_id=job_id,
            name="test",
            instruction="do",
            auto_export=True,
            max_runtime_seconds=None,
            output_schema_json=None,
            input_headers=["id"],
            input_csv_path="in.csv",
            output_csv_path="out.csv",
        )
        store.create_agent_job_items(
            job_id,
            (AgentJobItemCreateParams(item_id=item_id, row_index=0, source_id=None, row_json={"id": "1"}),),
        )
        store.mark_agent_job_running(job_id)
        store.mark_agent_job_item_running_with_thread(job_id, item_id, "thread")
        output = ReportAgentJobResultHandler(store, reporting_thread_id="thread").handle(
            ToolPayload.function(
                json.dumps(
                    {
                        "job_id": job_id,
                        "item_id": item_id,
                        "result": {"ok": True},
                        "stop": True,
                    }
                )
            )
        )
        self.assertEqual(json.loads(output.into_text()), {"accepted": True})
        self.assertEqual(store.reported_results[(job_id, item_id)], {"ok": True})
        self.assertEqual(store.cancelled_jobs["job"], "cancelled by worker request")

    def test_report_agent_job_result_returns_false_for_missing_item(self) -> None:
        store = InMemoryAgentJobStore()
        output = ReportAgentJobResultHandler(store, reporting_thread_id="thread").handle(
            ToolPayload.function(
                json.dumps(
                    {
                        "job_id": "missing_job",
                        "item_id": "missing_item",
                        "result": {"ok": True},
                    }
                )
            )
        )
        self.assertEqual(output.into_text(), '{"accepted":false}')
        self.assertEqual(len(store.reported_results), 0)

    def test_report_agent_job_result_requires_running_thread_id_match(self) -> None:
        store = InMemoryAgentJobStore()
        job_id = "job-1"
        item_id = "item-1"
        store.create_agent_job(
            job_id=job_id,
            name="test",
            instruction="do",
            auto_export=True,
            max_runtime_seconds=None,
            output_schema_json=None,
            input_headers=["id"],
            input_csv_path="in.csv",
            output_csv_path="out.csv",
        )
        store.create_agent_job_items(job_id, (AgentJobItemCreateParams(item_id=item_id, row_index=0, source_id=None, row_json={"id": "1"}),))
        store.mark_agent_job_running(job_id)
        store.mark_agent_job_item_running_with_thread(job_id, item_id, "thread-a")
        # Missing/wrong reporting thread should be rejected.
        output = ReportAgentJobResultHandler(store, reporting_thread_id="thread-b").handle(
            ToolPayload.function(
                json.dumps(
                    {"job_id": job_id, "item_id": item_id, "result": {"ok": True}}
                )
            )
        )
        self.assertEqual(output.into_text(), '{"accepted":false}')
        item = store.get_agent_job_item(job_id, item_id)
        self.assertEqual(item.status, "running")
        self.assertNotIn((job_id, item_id), store.reported_results)
    def test_report_agent_job_result_handler_surface_matches_rust_runtime(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/agent_jobs/report_agent_job_result.rs
        # Contract: plain tool name, report tool spec, function-payload runtime matching,
        # and compact JSON FunctionToolOutput on accepted reports.
        store = InMemoryAgentJobStore()
        job_id = "job"
        item_id = "item"
        store.create_agent_job(
            job_id=job_id,
            name="test",
            instruction="do",
            auto_export=True,
            max_runtime_seconds=None,
            output_schema_json=None,
            input_headers=["id"],
            input_csv_path="in.csv",
            output_csv_path="out.csv",
        )
        store.create_agent_job_items(
            job_id,
            (AgentJobItemCreateParams(item_id=item_id, row_index=0, source_id=None, row_json={"id": "1"}),),
        )
        store.mark_agent_job_running(job_id)
        store.mark_agent_job_item_running_with_thread(job_id, item_id, "thread-1")
        handler = ReportAgentJobResultHandler(store, reporting_thread_id="thread-1")
        payload = ToolPayload.function(json.dumps({"job_id": "job", "item_id": "item", "result": {"ok": True}}))

        self.assertEqual(handler.tool_name(), ToolName.plain("report_agent_job_result"))
        self.assertEqual(handler.spec()["name"], "report_agent_job_result")
        self.assertTrue(handler.matches_kind(payload))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))

        output = handler.handle(payload)

        self.assertEqual(output.into_text(), '{"accepted":true}')
        self.assertEqual(store.reported_results[("job", "item")], {"ok": True})
        self.assertNotIn("job", store.cancelled_jobs)

    def test_report_agent_job_result_infers_thread_id_from_invocation_session(self) -> None:
        store = InMemoryAgentJobStore()
        job_id = "job-1"
        item_id = "item-1"
        store.create_agent_job(
            job_id=job_id,
            name="test",
            instruction="do",
            auto_export=True,
            max_runtime_seconds=None,
            output_schema_json=None,
            input_headers=["id"],
            input_csv_path="in.csv",
            output_csv_path="out.csv",
        )
        store.create_agent_job_items(
            job_id,
            (AgentJobItemCreateParams(item_id=item_id, row_index=0, source_id=None, row_json={"id": "1"}),),
        )
        store.mark_agent_job_running(job_id)
        store.mark_agent_job_item_running_with_thread(job_id, item_id, "thread-session")
        invocation = type("Invocation", (), {
            "session": type("Session", (), {"conversation_id": "thread-session"})(),
            "payload": ToolPayload.function(
                json.dumps(
                    {"job_id": job_id, "item_id": item_id, "result": {"ok": True}}
                )
            ),
        })()

        output = ReportAgentJobResultHandler(store).handle(invocation)

        self.assertEqual(output.into_text(), '{"accepted":true}')
        self.assertEqual(store.reported_results[(job_id, item_id)], {"ok": True})

    def test_report_agent_job_result_requires_reporting_thread_id(self) -> None:
        invocation = type("Invocation", (), {
            "session": object(),
            "payload": ToolPayload.function(
                json.dumps({"job_id": "job", "item_id": "item", "result": {"ok": True}})
            ),
        })()
        with self.assertRaisesRegex(
            FunctionCallError,
            "requires a reporting_thread_id",
        ):
            ReportAgentJobResultHandler().handle(invocation)

    def test_report_agent_job_result_accepted_false_and_store_failure(self) -> None:
        # Rust source: report_agent_job_result.rs::handle records the result first,
        # cancels only when accepted && stop, and reports db errors to the model.
        class RejectingStore:
            def __init__(self) -> None:
                self.cancelled: list[tuple[str, str]] = []

            def report_agent_job_item_result(
                self,
                job_id: str,
                item_id: str,
                reporting_thread_id: str,
                result: object,
            ) -> bool:
                self.reported = (job_id, item_id, reporting_thread_id, result)
                return False

            def mark_agent_job_cancelled(self, job_id: str, message: str) -> None:
                self.cancelled.append((job_id, message))

        rejecting = RejectingStore()
        output = ReportAgentJobResultHandler(rejecting, reporting_thread_id="thread").handle(
            ToolPayload.function(
                json.dumps(
                    {
                        "job_id": "job",
                        "item_id": "item",
                        "result": {"ok": False},
                        "stop": True,
                    }
                )
            )
        )

        self.assertEqual(output.into_text(), '{"accepted":false}')
        self.assertEqual(rejecting.reported, ("job", "item", "thread", {"ok": False}))
        self.assertEqual(rejecting.cancelled, [])

        class FailingStore:
            def report_agent_job_item_result(self, *_args: object) -> bool:
                raise RuntimeError("db down")

            def mark_agent_job_cancelled(self, _job_id: str, _message: str) -> None:
                raise AssertionError("cancel should not be attempted after report failure")

        with self.assertRaisesRegex(
            FunctionCallError,
            "failed to record agent job result for job / item: db down",
        ):
            ReportAgentJobResultHandler(
                FailingStore(),
                reporting_thread_id="thread",
            ).handle(
                ToolPayload.function(json.dumps({"job_id": "job", "item_id": "item", "result": {"ok": True}}))
            )

    def test_report_agent_job_result_rejects_non_object_result_and_payload(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "result must be a JSON object"):
            ReportAgentJobResultHandler(reporting_thread_id="thread").handle(
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

    def test_spawn_handler_runs_and_exports_placeholder_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_csv = root / "input.csv"
            input_csv.write_text("id,name\nA,one\nB,two\n", encoding="utf-8")

            class _Environment:
                def is_remote(self) -> bool:
                    return False

            turn = type(
                "Turn",
                (),
                {
                    "config": type("Config", (), {"agent_max_threads": 4, "agent_job_max_runtime_seconds": None})(),
                    "environments": ResolvedTurnEnvironments(
                        (TurnEnvironment(environment_id="local", environment=_Environment(), cwd=root),)
                    ),
                },
            )()

            store = InMemoryAgentJobStore()
            invocation = ToolInvocation(
                session=agent_job_session(store),
                turn=turn,
                cancellation_token=None,
                tracker=None,
                call_id="call-1",
                tool_name="spawn_agents_on_csv",
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(
                    json.dumps(
                        {
                            "csv_path": "input.csv",
                            "instruction": "Process {name}",
                            "max_concurrency": 2,
                        }
                    )
                ),
            )

            output = SpawnAgentsOnCsvHandler().handle(invocation)

            data = json.loads(output.into_text())
            self.assertEqual(data["status"], "completed")
            self.assertEqual(data["total_items"], 2)
            self.assertEqual(data["completed_items"], 2)
            self.assertEqual(data["failed_items"], 0)
            output_path = Path(data["output_csv_path"])
            self.assertTrue(output_path.exists())
            content = output_path.read_text()
            self.assertIn("item_id", content)
            self.assertIn("row_index", content)


    def test_spawn_handler_marks_cancelled_status_when_store_reports_cancelled(self) -> None:
        class CancelingStore(InMemoryAgentJobStore):
            def __init__(self) -> None:
                super().__init__()
                self._cancelled = False

            def mark_agent_job_running(self, job_id: str) -> None:
                super().mark_agent_job_running(job_id)
                self._cancelled = True

            def is_agent_job_cancelled(self, job_id: str) -> bool:
                return self._cancelled

            def mark_agent_job_cancelled(self, job_id: str, message: str) -> None:
                self._cancelled = True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_csv = root / "input.csv"
            input_csv.write_text("id,name\nA,one\nB,two\n", encoding="utf-8")

            class _Environment:
                def is_remote(self) -> bool:
                    return False

            turn = type(
                "Turn",
                (),
                {
                    "config": type("Config", (), {"agent_max_threads": 4, "agent_job_max_runtime_seconds": None})(),
                    "environments": ResolvedTurnEnvironments(
                        (TurnEnvironment(environment_id="local", environment=_Environment(), cwd=root),)
                    ),
                },
            )()

            store = CancelingStore()
            invocation = ToolInvocation(
                session=agent_job_session(store),
                turn=turn,
                cancellation_token=None,
                tracker=None,
                call_id="call-cancel-1",
                tool_name="spawn_agents_on_csv",
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(
                    json.dumps(
                        {
                            "csv_path": "input.csv",
                            "instruction": "Process {name}",
                            "max_concurrency": 2,
                        }
                    )
                ),
            )

            output = SpawnAgentsOnCsvHandler(state_db=store).handle(invocation)
            data = json.loads(output.into_text())
            self.assertEqual(data["status"], "cancelled")
            self.assertEqual(data["completed_items"], 0)
            self.assertEqual(data["failed_items"], 0)

    def test_spawn_handler_returns_failed_status_when_export_fails(self) -> None:
        class FailingExportHandler(SpawnAgentsOnCsvHandler):
            def _export_job_csv_snapshot(self, store: Any, job_id: str) -> None:
                raise RuntimeError("export failed")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_csv = root / "input.csv"
            input_csv.write_text("id,name\nA,one\n", encoding="utf-8")

            class _Environment:
                def is_remote(self) -> bool:
                    return False

            turn = type(
                "Turn",
                (),
                {
                    "config": type("Config", (), {"agent_max_threads": 4, "agent_job_max_runtime_seconds": None})(),
                    "environments": ResolvedTurnEnvironments(
                        (TurnEnvironment(environment_id="local", environment=_Environment(), cwd=root),)
                    ),
                },
            )()

            store = InMemoryAgentJobStore()
            invocation = ToolInvocation(
                session=agent_job_session(store),
                turn=turn,
                cancellation_token=None,
                tracker=None,
                call_id="call-export-fail",
                tool_name="spawn_agents_on_csv",
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(
                    json.dumps(
                        {
                            "csv_path": "input.csv",
                            "instruction": "Process {name}",
                            "max_concurrency": 1,
                        }
                    )
                ),
            )

            output = FailingExportHandler().handle(invocation)
            data = json.loads(output.into_text())
            self.assertEqual(data["status"], "failed")
            self.assertEqual(data["failed_items"], 0)
            self.assertIsInstance(data["job_error"], str)
            self.assertIn("auto-export failed", data["job_error"])


    def test_spawn_handler_marks_failed_items_when_workers_cannot_claim_item(self) -> None:
        class RefusingStore(InMemoryAgentJobStore):
            def mark_agent_job_item_running_with_thread(
                self, job_id: str, item_id: str, thread_id: str
            ) -> bool:
                self.mark_agent_job_item_failed(job_id, item_id, "failed to claim worker item")
                return False

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_csv = root / "input.csv"
            input_csv.write_text("id,name\nA,one\nB,two\n", encoding="utf-8")

            class _Environment:
                def is_remote(self) -> bool:
                    return False

            turn = type(
                "Turn",
                (),
                {
                    "config": type("Config", (), {"agent_max_threads": 4, "agent_job_max_runtime_seconds": None})(),
                    "environments": ResolvedTurnEnvironments(
                        (TurnEnvironment(environment_id="local", environment=_Environment(), cwd=root),)
                    ),
                },
            )()

            store = RefusingStore()
            invocation = ToolInvocation(
                session=agent_job_session(store),
                turn=turn,
                cancellation_token=None,
                tracker=None,
                call_id="call-fail-1",
                tool_name="spawn_agents_on_csv",
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(
                    json.dumps(
                        {
                            "csv_path": "input.csv",
                            "instruction": "Process {name}",
                            "max_concurrency": 2,
                        }
                    )
                ),
            )

            output = SpawnAgentsOnCsvHandler(state_db=store).handle(invocation)
            data = json.loads(output.into_text())
            self.assertEqual(data["status"], "completed")
            self.assertEqual(data["total_items"], 2)
            self.assertEqual(data["completed_items"], 0)
            self.assertEqual(data["failed_items"], 2)
            failed_items = {item["item_id"] for item in data["failed_item_errors"]}
            self.assertEqual(failed_items, {"row-1", "row-2"})


    def test_spawn_handler_rejects_unsupported_payload(self) -> None:
        with self.assertRaisesRegex(
            FunctionCallError,
            "agent jobs handler received unsupported payload",
        ):
            SpawnAgentsOnCsvHandler().handle(ToolPayload.custom("raw"))

    def test_spawn_handler_rejects_when_depth_limit_reached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_csv = root / "input.csv"
            input_csv.write_text("id,name\nA,one\n", encoding="utf-8")

            class _Environment:
                def is_remote(self) -> bool:
                    return False

            turn = type(
                "Turn",
                (),
                {
                    "config": type(
                        "Config",
                        (),
                        {
                            "agent_max_threads": 4,
                            "agent_max_depth": 0,
                            "agent_job_max_runtime_seconds": None,
                        },
                    )(),
                    "environments": ResolvedTurnEnvironments(
                        (TurnEnvironment(environment_id="local", environment=_Environment(), cwd=root),)
                    ),
                },
            )()

            store = InMemoryAgentJobStore()
            invocation = ToolInvocation(
                session=agent_job_session(store),
                turn=turn,
                cancellation_token=None,
                tracker=None,
                call_id="call-depth-limit",
                tool_name="spawn_agents_on_csv",
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(json.dumps({"csv_path": "input.csv", "instruction": "Process {name}"})),
            )

            with self.assertRaisesRegex(
                FunctionCallError,
                "agent depth limit reached; this session cannot spawn more subagents",
            ):
                SpawnAgentsOnCsvHandler().handle(invocation)


if __name__ == "__main__":
    unittest.main()
