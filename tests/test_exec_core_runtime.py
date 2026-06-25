import unittest
import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, patch

from pycodex.exec import core_runtime
from pycodex.exec import local_runtime
from pycodex.exec.event_processor import JsonEventProcessor


class ExecCoreRuntimeTests(unittest.TestCase):
    def test_core_runtime_facade_exports_core_helpers(self) -> None:
        self.assertIs(
            core_runtime.align_core_exec_resume_model_client,
            local_runtime.align_local_http_exec_resume_model_client,
        )
        self.assertIsNot(
            core_runtime.build_default_core_exec_runtime,
            local_runtime.build_default_local_http_exec_runtime,
        )
        self.assertIs(core_runtime.core_exec_enabled, local_runtime.core_exec_enabled)
        self.assertIs(core_runtime.core_exec_config_summary, local_runtime.core_exec_config_summary)
        self.assertIs(
            core_runtime.core_exec_initial_messages_from_rollout,
            local_runtime.core_exec_initial_messages_from_rollout,
        )
        self.assertIs(
            core_runtime.core_review_rollout_input_items,
            local_runtime.core_review_rollout_input_items,
        )
        self.assertIs(core_runtime.persist_core_exec_rollout, local_runtime.persist_core_exec_rollout)
        self.assertIs(
            core_runtime.persist_core_exec_resume_rollout,
            local_runtime.persist_core_exec_resume_rollout,
        )
        self.assertIs(
            core_runtime.run_exec_user_turn_core_sampling,
            local_runtime.run_exec_user_turn_core_sampling,
        )
        self.assertIs(
            core_runtime.run_exec_user_turn_core_http_sampling,
            local_runtime.run_exec_user_turn_core_http_sampling,
        )
        self.assertIs(
            core_runtime.run_exec_resume_user_turn_core_http_sampling,
            local_runtime.run_exec_resume_user_turn_core_http_sampling,
        )
        self.assertIs(
            core_runtime.run_exec_review_core_http_sampling,
            local_runtime.run_exec_review_core_http_sampling,
        )

    def test_core_runtime_all_is_core_facing(self) -> None:
        self.assertEqual(
            sorted(core_runtime.__all__),
            [
                "CoreExecResumeTarget",
                "align_core_exec_resume_model_client",
                "build_default_core_exec_runtime",
                "core_exec_config_summary",
                "core_exec_enabled",
                "core_exec_initial_messages_from_rollout",
                "core_exec_rollout_input_items",
                "core_review_rollout_input_items",
                "emit_core_exec_config_summary",
                "emit_core_exec_result",
                "persist_core_exec_result",
                "persist_core_exec_resume_rollout",
                "persist_core_exec_rollout",
                "resolve_core_exec_resume_target",
                "run_core_exec_command",
                "run_exec_resume_user_turn_core_http_sampling",
                "run_exec_review_core_http_sampling",
                "run_exec_user_turn_core_http_sampling",
                "run_exec_user_turn_core_sampling",
            ],
        )

    def test_build_default_core_exec_runtime_rewrites_auth_error(self) -> None:
        config = SimpleNamespace(model_provider_id=None, model=None)

        with self.assertRaisesRegex(ValueError, "required for core exec runtime"):
            core_runtime.build_default_core_exec_runtime(config, env={})

    def test_build_default_core_exec_runtime_delegates_success(self) -> None:
        expected = (object(), object(), object(), "auth")

        with patch(
            "pycodex.exec.core_runtime._build_default_local_http_exec_runtime",
            return_value=expected,
        ) as build_runtime:
            returned = core_runtime.build_default_core_exec_runtime(
                "config",
                auth="auth",
                env={"OPENAI_API_KEY": "sk-env"},
                config_toml={"model": "gpt-test"},
            )

        self.assertEqual(returned, expected)
        build_runtime.assert_called_once_with(
            "config",
            auth="auth",
            env={"OPENAI_API_KEY": "sk-env"},
            config_toml={"model": "gpt-test"},
        )

    def test_resolve_core_exec_resume_target_aligns_named_session(self) -> None:
        seen = {}

        def fake_align(codex_home, config, model_client, **kwargs):
            seen["codex_home"] = codex_home
            seen["config"] = config
            seen["model_client"] = model_client
            seen.update(kwargs)
            return Path("rollout.jsonl")

        config = object()
        model_client = object()
        resume = SimpleNamespace(session_id="named session", last=True, all=False)
        with patch("pycodex.exec.core_runtime.align_core_exec_resume_model_client", side_effect=fake_align):
            target = core_runtime.resolve_core_exec_resume_target("home", config, model_client, resume)

        self.assertIsNone(target.thread_id)
        self.assertEqual(target.session_name, "named session")
        self.assertEqual(target.rollout_path, Path("rollout.jsonl"))
        self.assertEqual(seen["codex_home"], "home")
        self.assertIs(seen["config"], config)
        self.assertIs(seen["model_client"], model_client)
        self.assertIsNone(seen["thread_id"])
        self.assertEqual(seen["session_name"], "named session")
        self.assertTrue(seen["resume_last"])
        self.assertFalse(seen["include_all"])

    def test_resolve_core_exec_resume_target_aligns_direct_thread_id(self) -> None:
        seen = {}
        thread_id = "12345678-1234-5678-1234-567812345678"

        def fake_align(_codex_home, _config, _model_client, **kwargs):
            seen.update(kwargs)
            return "direct-rollout.jsonl"

        resume = SimpleNamespace(session_id=thread_id, last=False, all=True)
        with patch("pycodex.exec.core_runtime.align_core_exec_resume_model_client", side_effect=fake_align):
            target = core_runtime.resolve_core_exec_resume_target("home", object(), object(), resume)

        self.assertEqual(target.thread_id, thread_id)
        self.assertIsNone(target.session_name)
        self.assertEqual(target.rollout_path, Path("direct-rollout.jsonl"))
        self.assertEqual(seen["thread_id"], thread_id)
        self.assertIsNone(seen["session_name"])
        self.assertFalse(seen["resume_last"])
        self.assertTrue(seen["include_all"])

    def test_resolve_core_exec_resume_target_rejects_missing_args_and_returns_none_without_rollout(self) -> None:
        with self.assertRaisesRegex(ValueError, "resume command is missing resume arguments"):
            core_runtime.resolve_core_exec_resume_target("home", object(), object(), None)

        resume = SimpleNamespace(session_id=None, last=True, all=False)
        with patch("pycodex.exec.core_runtime.align_core_exec_resume_model_client", return_value=None):
            self.assertIsNone(core_runtime.resolve_core_exec_resume_target("home", object(), object(), resume))

    def test_core_exec_rollout_input_items_uses_review_input_for_review(self) -> None:
        result = object()
        with patch("pycodex.exec.core_runtime.core_review_rollout_input_items", return_value=("review",)) as review_items:
            self.assertEqual(core_runtime.core_exec_rollout_input_items("review", object(), result), ("review",))

        review_items.assert_called_once_with(result)

    def test_core_exec_rollout_input_items_uses_initial_user_turn_for_fresh_exec(self) -> None:
        plan = SimpleNamespace(initial_operation=SimpleNamespace(kind="user_turn", items=("user",)))

        self.assertEqual(core_runtime.core_exec_rollout_input_items("exec", plan, object()), ("user",))

    def test_core_exec_rollout_input_items_skips_resume_and_non_user_turns(self) -> None:
        user_plan = SimpleNamespace(initial_operation=SimpleNamespace(kind="user_turn", items=("user",)))
        review_plan = SimpleNamespace(initial_operation=SimpleNamespace(kind="review", items=("ignored",)))

        self.assertEqual(core_runtime.core_exec_rollout_input_items("resume", user_plan, object()), ())
        self.assertEqual(core_runtime.core_exec_rollout_input_items("exec", review_plan, object()), ())

    def test_persist_core_exec_result_persists_fresh_exec(self) -> None:
        plan = SimpleNamespace(initial_operation=SimpleNamespace(kind="user_turn", items=("user",)))
        result = object()
        config = object()
        model_client = object()

        with patch("pycodex.exec.core_runtime.persist_core_exec_rollout") as persist_rollout:
            persisted = core_runtime.persist_core_exec_result(
                "exec",
                "home",
                config,
                result,
                model_client,
                plan,
                cli_version="1.2.3",
            )

        self.assertTrue(persisted)
        persist_rollout.assert_called_once_with(
            "home",
            config,
            result,
            model_client,
            input_items=("user",),
            cli_version="1.2.3",
        )

    def test_persist_core_exec_result_skips_resume(self) -> None:
        with patch("pycodex.exec.core_runtime.persist_core_exec_rollout") as persist_rollout:
            persisted = core_runtime.persist_core_exec_result(
                "resume",
                "home",
                object(),
                object(),
                object(),
                object(),
                cli_version="1.2.3",
            )

        self.assertFalse(persisted)
        persist_rollout.assert_not_called()

    def test_emit_core_exec_result_emits_result_and_completion_message(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        processor = object()
        result = object()
        config = object()

        with patch("pycodex.exec.core_runtime.emit_local_http_exec_result") as emit_result:
            core_runtime.emit_core_exec_result(
                "exec",
                processor,
                result,
                config,
                stdout=stdout,
                stderr=stderr,
            )

        emit_result.assert_called_once_with(
            processor,
            result,
            config=config,
            stdout=stdout,
            stderr=stderr,
        )
        self.assertIn("completed core non-interactive exec execution", stderr.getvalue())

    def test_emit_core_exec_config_summary_builds_and_prints_human_summary(self) -> None:
        class Processor:
            def __init__(self) -> None:
                self.calls = []

            def print_config_summary(self, *args, **kwargs) -> None:
                self.calls.append((args, kwargs))

        stdout = io.StringIO()
        stderr = io.StringIO()
        processor = Processor()
        config = SimpleNamespace(model_provider_id=None)
        plan = SimpleNamespace(prompt_summary="hello")
        model_client = SimpleNamespace(state=SimpleNamespace(session_id="session", thread_id="thread"))
        model_info = SimpleNamespace(slug="gpt-test")

        with patch(
            "pycodex.exec.core_runtime.core_exec_initial_messages_from_rollout",
            return_value=("initial",),
        ) as initial_messages:
            with patch(
                "pycodex.exec.core_runtime.core_exec_config_summary",
                return_value=("summary-config", "summary-session"),
            ) as config_summary:
                returned = core_runtime.emit_core_exec_config_summary(
                    processor,
                    config,
                    plan,
                    model_client,
                    model_info,
                    rollout_path=Path("rollout.jsonl"),
                    stdout=stdout,
                    stderr=stderr,
                    version="1.2.3",
                )

        self.assertEqual(returned, ("summary-config", "summary-session"))
        initial_messages.assert_called_once_with(Path("rollout.jsonl"))
        config_summary.assert_called_once_with(
            config,
            model="gpt-test",
            provider_id="openai",
            session_id="session",
            thread_id="thread",
            initial_messages=("initial",),
            rollout_path=Path("rollout.jsonl"),
        )
        self.assertEqual(processor.calls[0][0], ("summary-config", "hello", "summary-session"))
        self.assertIs(processor.calls[0][1]["stderr"], stderr)
        self.assertEqual(processor.calls[0][1]["version"], "1.2.3")

    def test_emit_core_exec_config_summary_uses_json_output_kwarg(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        processor = JsonEventProcessor()
        config = SimpleNamespace(model_provider_id="custom")
        plan = SimpleNamespace(prompt_summary="hello")
        model_client = SimpleNamespace(state=SimpleNamespace(session_id="session", thread_id="thread"))
        model_info = SimpleNamespace(slug="gpt-test")

        with patch(
            "pycodex.exec.core_runtime.core_exec_config_summary",
            return_value=("summary-config", "summary-session"),
        ):
            with patch.object(JsonEventProcessor, "print_config_summary") as print_summary:
                core_runtime.emit_core_exec_config_summary(
                    processor,
                    config,
                    plan,
                    model_client,
                    model_info,
                    stdout=stdout,
                    stderr=stderr,
                    version="1.2.3",
        )

        print_summary.assert_called_once()
        self.assertEqual(print_summary.call_args.args, ("summary-config", "hello", "summary-session"))
        self.assertIs(print_summary.call_args.kwargs["output"], stdout)

    def test_run_core_exec_command_runs_fresh_exec_and_persists(self) -> None:
        result = object()
        config = object()
        plan = object()
        model_client = object()
        provider = object()
        model_info = object()

        async def fake_run(*args, **kwargs):
            return result

        with patch("pycodex.exec.core_runtime.run_exec_user_turn_core_http_sampling", side_effect=fake_run) as run_fresh:
            with patch("pycodex.exec.core_runtime.persist_core_exec_result", return_value=True) as persist_result:
                returned = asyncio.run(
                    core_runtime.run_core_exec_command(
                        None,
                        "home",
                        config,
                        plan,
                        model_client,
                        provider,
                        model_info,
                        auth="auth",
                        max_tool_followups=2,
                        cli_version="1.2.3",
                    )
                )

        self.assertIs(returned, result)
        run_fresh.assert_called_once_with(
            config,
            plan,
            model_client,
            provider,
            model_info,
            auth="auth",
            endpoint=None,
            timeout=None,
            opener=None,
            built_tools=None,
            max_tool_followups=2,
            auth_manager=ANY,
        )
        self.assertTrue(hasattr(run_fresh.call_args.kwargs["auth_manager"], "unauthorized_recovery"))
        persist_result.assert_called_once_with(
            "exec",
            "home",
            config,
            result,
            model_client,
            plan,
            cli_version="1.2.3",
        )

    def test_run_core_exec_command_runs_review_and_persists(self) -> None:
        result = object()
        config = object()
        plan = object()
        model_client = object()
        provider = object()
        model_info = object()

        async def fake_run(*args, **kwargs):
            return result

        with patch("pycodex.exec.core_runtime.run_exec_review_core_http_sampling", side_effect=fake_run) as run_review:
            with patch("pycodex.exec.core_runtime.persist_core_exec_result", return_value=True) as persist_result:
                returned = asyncio.run(
                    core_runtime.run_core_exec_command(
                        "review",
                        Path("home"),
                        config,
                        plan,
                        model_client,
                        provider,
                        model_info,
                        auth="auth",
                        max_tool_followups=3,
                        cli_version="1.2.3",
                    )
                )

        self.assertIs(returned, result)
        run_review.assert_called_once_with(
            config,
            plan,
            model_client,
            provider,
            model_info,
            auth="auth",
            endpoint=None,
            timeout=None,
            opener=None,
            built_tools=None,
            max_tool_followups=3,
            auth_manager=ANY,
        )
        self.assertTrue(hasattr(run_review.call_args.kwargs["auth_manager"], "unauthorized_recovery"))
        persist_result.assert_called_once_with(
            "review",
            Path("home"),
            config,
            result,
            model_client,
            plan,
            cli_version="1.2.3",
        )

    def test_run_core_exec_command_runs_resume_without_persisting(self) -> None:
        result = object()
        resume_args = SimpleNamespace(last=True, all=False)
        target = core_runtime.CoreExecResumeTarget(
            thread_id=None,
            session_name="named",
            rollout_path=Path("rollout.jsonl"),
        )

        async def fake_run(*args, **kwargs):
            return result

        with patch("pycodex.exec.core_runtime.run_exec_resume_user_turn_core_http_sampling", side_effect=fake_run) as run_resume:
            with patch("pycodex.exec.core_runtime.persist_core_exec_result") as persist_result:
                returned = asyncio.run(
                    core_runtime.run_core_exec_command(
                        "resume",
                        "home",
                        object(),
                        object(),
                        object(),
                        object(),
                        object(),
                        resume_args=resume_args,
                        resume_target=target,
                        auth="auth",
                        max_tool_followups=4,
                        cli_version="1.2.3",
                    )
                )

        self.assertIs(returned, result)
        self.assertEqual(run_resume.call_args.args[0], Path("home"))
        self.assertIsNone(run_resume.call_args.kwargs["thread_id"])
        self.assertEqual(run_resume.call_args.kwargs["session_name"], "named")
        self.assertTrue(run_resume.call_args.kwargs["resume_last"])
        self.assertFalse(run_resume.call_args.kwargs["include_all"])
        self.assertEqual(run_resume.call_args.kwargs["resolved_rollout_path"], Path("rollout.jsonl"))
        self.assertEqual(run_resume.call_args.kwargs["auth"], "auth")
        self.assertEqual(run_resume.call_args.kwargs["max_tool_followups"], 4)
        persist_result.assert_not_called()

    def test_run_core_exec_command_resume_without_target_starts_new_turn_and_persists(self) -> None:
        result = object()
        resume_args = SimpleNamespace(last=True, all=False)

        async def fake_run(*args, **kwargs):
            return result

        with patch("pycodex.exec.core_runtime.resolve_core_exec_resume_target", return_value=None) as resolve_target:
            with patch("pycodex.exec.core_runtime.run_exec_user_turn_core_http_sampling", side_effect=fake_run) as run_fresh:
                with patch("pycodex.exec.core_runtime.persist_core_exec_result", return_value=True) as persist_result:
                    returned = asyncio.run(
                        core_runtime.run_core_exec_command(
                            "resume",
                            "home",
                            "config",
                            "plan",
                            "model-client",
                            "provider",
                            "model-info",
                            resume_args=resume_args,
                            auth="auth",
                            max_tool_followups=5,
                            cli_version="1.2.3",
                        )
                    )

        self.assertIs(returned, result)
        resolve_target.assert_called_once_with("home", "config", "model-client", resume_args)
        run_fresh.assert_called_once_with(
            "config",
            "plan",
            "model-client",
            "provider",
            "model-info",
            auth="auth",
            endpoint=None,
            timeout=None,
            opener=None,
            built_tools=None,
            max_tool_followups=5,
            auth_manager=ANY,
        )
        self.assertTrue(hasattr(run_fresh.call_args.kwargs["auth_manager"], "unauthorized_recovery"))
        persist_result.assert_called_once_with(
            "exec",
            "home",
            "config",
            result,
            "model-client",
            "plan",
            cli_version="1.2.3",
        )

    def test_run_core_exec_command_resume_pre_resolved_miss_does_not_lookup_again(self) -> None:
        result = object()
        resume_args = SimpleNamespace(last=True, all=False)

        async def fake_run(*args, **kwargs):
            return result

        with patch(
            "pycodex.exec.core_runtime.resolve_core_exec_resume_target",
            side_effect=AssertionError("resume target was already resolved"),
        ):
            with patch("pycodex.exec.core_runtime.run_exec_user_turn_core_http_sampling", side_effect=fake_run) as run_fresh:
                with patch("pycodex.exec.core_runtime.persist_core_exec_result", return_value=True):
                    returned = asyncio.run(
                        core_runtime.run_core_exec_command(
                            "resume",
                            "home",
                            "config",
                            "plan",
                            "model-client",
                            "provider",
                            "model-info",
                            resume_args=resume_args,
                            resume_target=None,
                            resume_target_resolved=True,
                            auth="auth",
                            cli_version="1.2.3",
                        )
                    )

        self.assertIs(returned, result)
        run_fresh.assert_called_once()
