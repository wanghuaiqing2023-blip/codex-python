import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from pycodex.apply_patch import (
    APPLY_PATCH_FREEFORM_DESCRIPTION,
    APPLY_PATCH_LARK_GRAMMAR,
    APPLY_PATCH_TOOL_NAME,
    ApplyPatchAction,
    ApplyPatchArgs,
    ApplyPatchArgumentDiffConsumer,
    ApplyPatchError,
    ApplyPatchFileChange,
    ApplyPatchFileUpdate,
    ApplyPatchHandler,
    ApplyPatchParseError,
    Hunk,
    MaybeApplyPatch,
    StreamingPatchParser,
    UpdateFileChunk,
    convert_apply_patch_hunks_to_protocol,
    convert_apply_patch_to_protocol,
    create_apply_patch_freeform_tool,
    derive_new_contents_from_chunks,
    maybe_parse_apply_patch,
    maybe_parse_apply_patch_verified,
    parse_patch,
    require_apply_patch_environment_id,
    resolve_apply_patch_invocation,
    unified_diff_from_chunks,
    verify_apply_patch_args,
)
from pycodex.core import (
    ApplyPatchToolOutput,
    FunctionCallError,
    ToolPayload,
    ToolInvocation,
)
from pycodex.features import Feature
from pycodex.core.tools.hook_names import HookToolName
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    GranularApprovalConfig,
    PermissionProfile,
    ToolName,
)
from pycodex.protocol import FileChange


class CoreApplyPatchTests(unittest.TestCase):
    def assert_apply_patch_body(
        self,
        result: MaybeApplyPatch,
        expected_workdir: str | None = None,
    ) -> ApplyPatchArgs:
        self.assertEqual(result.type, "body")
        self.assertIsNotNone(result.body)
        body = result.body
        self.assertEqual(body.workdir, expected_workdir)
        return body

    def update_chunks_from_patch(self, patch: str) -> tuple[UpdateFileChunk, ...]:
        parsed = parse_patch(patch)
        self.assertEqual(len(parsed.hunks), 1)
        hunk = parsed.hunks[0]
        self.assertEqual(hunk.type, "update")
        return hunk.chunks

    def make_workspace_dir(self) -> Path:
        path = Path.cwd() / f".pycodex-test-{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def test_convert_apply_patch_maps_add_variant(self) -> None:
        path = Path("a.txt")
        action = ApplyPatchAction.new_add_for_test(path, "hello")

        self.assertEqual(
            convert_apply_patch_to_protocol(action),
            {path: FileChange.add("hello")},
        )

    def test_convert_apply_patch_maps_delete_and_update_variants(self) -> None:
        action = ApplyPatchAction(
            {
                Path("old.txt"): ApplyPatchFileChange.delete("old contents"),
                Path("edit.txt"): ApplyPatchFileChange.update(
                    "@@ -1 +1 @@\n-old\n+new\n",
                    new_content="new\n",
                ),
                Path("move.txt"): ApplyPatchFileChange.update(
                    "@@ -1 +1 @@\n-before\n+after\n",
                    move_path=Path("moved.txt"),
                    new_content="after\n",
                ),
            }
        )

        self.assertEqual(
            convert_apply_patch_to_protocol(action),
            {
                Path("old.txt"): FileChange.delete("old contents"),
                Path("edit.txt"): FileChange.update("@@ -1 +1 @@\n-old\n+new\n"),
                Path("move.txt"): FileChange.update(
                    "@@ -1 +1 @@\n-before\n+after\n",
                    move_path=Path("moved.txt"),
                ),
            },
        )

    def test_convert_apply_patch_accepts_mapping_shape(self) -> None:
        self.assertEqual(
            convert_apply_patch_to_protocol(
                {
                    "cwd": "/repo",
                    "changes": {
                        "new.txt": {"type": "add", "content": "new"},
                        "gone.txt": {"type": "delete", "content": "gone"},
                        "renamed.txt": {
                            "type": "update",
                            "unified_diff": "@@ -1 +1 @@\n-x\n+y\n",
                            "move_path": "renamed-to.txt",
                            "new_content": "y\n",
                        },
                    },
                }
            ),
            {
                Path("new.txt"): FileChange.add("new"),
                Path("gone.txt"): FileChange.delete("gone"),
                Path("renamed.txt"): FileChange.update(
                    "@@ -1 +1 @@\n-x\n+y\n",
                    move_path=Path("renamed-to.txt"),
                ),
            },
        )

    def test_convert_apply_patch_rejects_unknown_change_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown apply_patch file change type"):
            ApplyPatchFileChange(type="chmod")

    def test_create_apply_patch_freeform_tool_matches_default_grammar(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/apply_patch_spec.rs
        # Rust test: create_apply_patch_freeform_tool_matches_expected_spec
        tool = create_apply_patch_freeform_tool(False)

        self.assertEqual(
            tool.to_mapping(),
            {
                "type": "custom",
                "name": APPLY_PATCH_TOOL_NAME,
                "description": APPLY_PATCH_FREEFORM_DESCRIPTION,
                "format": {
                    "type": "grammar",
                    "syntax": "lark",
                    "definition": APPLY_PATCH_LARK_GRAMMAR,
                },
            },
        )

    def test_create_apply_patch_freeform_tool_can_accept_environment_id(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/apply_patch_spec.rs
        # Rust test: create_apply_patch_freeform_tool_includes_environment_id_when_requested
        definition = create_apply_patch_freeform_tool(True).to_mapping()["format"]["definition"]

        self.assertIn(
            "start: begin_patch environment_id? hunk+ end_patch",
            definition,
        )
        self.assertIn(
            'environment_id: "*** Environment ID: " filename LF',
            definition,
        )
        self.assertIn("*** Add File: ", definition)
        with self.assertRaisesRegex(TypeError, "include_environment_id must be a bool"):
            create_apply_patch_freeform_tool(1)  # type: ignore[arg-type]

    def test_apply_patch_handler_exposes_custom_tool(self) -> None:
        handler = ApplyPatchHandler.new(True)

        self.assertEqual(handler.tool_name(), ToolName.plain(APPLY_PATCH_TOOL_NAME))
        self.assertEqual(handler.spec(), create_apply_patch_freeform_tool(True))
        self.assertTrue(handler.matches_kind(ToolPayload.custom("*** Begin Patch\n")))
        self.assertFalse(handler.matches_kind(ToolPayload.function("{}")))

    def test_apply_patch_handler_hook_payloads_match_rust_custom_shape(self) -> None:
        handler = ApplyPatchHandler()
        patch = "*** Begin Patch\n*** Add File: hello.txt\n+hello\n*** End Patch\n"
        invocation = ToolInvocation(
            call_id="patch-1",
            tool_name=ToolName.plain("apply_patch"),
            payload=ToolPayload.custom(patch),
        )

        pre = handler.pre_tool_use_payload(invocation)

        self.assertIsNotNone(pre)
        self.assertEqual(pre.tool_name, HookToolName.apply_patch())
        self.assertEqual(pre.tool_input, {"command": patch})

        rewritten = handler.with_updated_hook_input(
            invocation,
            {"command": "*** Begin Patch\n*** Add File: rewritten.txt\n+new\n*** End Patch\n"},
        )

        self.assertEqual(
            rewritten.payload.input,
            "*** Begin Patch\n*** Add File: rewritten.txt\n+new\n*** End Patch\n",
        )

        output = ApplyPatchToolOutput.from_text("Success. Updated the following files:\nA hello.txt\n")
        post = handler.post_tool_use_payload(invocation, output)

        self.assertIsNotNone(post)
        self.assertEqual(post.tool_name, HookToolName.apply_patch())
        self.assertEqual(post.tool_use_id, "patch-1")
        self.assertEqual(post.tool_input, {"command": patch})
        self.assertEqual(post.tool_response, output.text)

    def test_apply_patch_argument_diff_consumer_emits_patch_apply_updates_when_feature_enabled(self) -> None:
        class Features:
            def enabled(self, feature) -> bool:
                return feature is Feature.APPLY_PATCH_STREAMING_EVENTS

        consumer = ApplyPatchArgumentDiffConsumer()
        patch = "*** Begin Patch\n*** Add File: streamed.txt\n+hello\n*** End Patch\n"

        event = consumer.consume_diff(SimpleNamespace(features=Features()), "patch-1", patch)

        self.assertIsNotNone(event)
        self.assertEqual(event.type, "patch_apply_updated")
        self.assertEqual(event.payload.call_id, "patch-1")
        self.assertEqual(event.payload.changes, {Path("streamed.txt"): FileChange.add("hello\n")})
        self.assertIsNone(consumer.finish())

    def test_apply_patch_argument_diff_consumer_streams_incremental_changes_like_rust(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/apply_patch.rs
        # Rust test: apply_patch_tests.rs::diff_consumer_streams_apply_patch_changes.
        class Features:
            def enabled(self, feature) -> bool:
                return feature is Feature.APPLY_PATCH_STREAMING_EVENTS

        turn = SimpleNamespace(features=Features())
        consumer = ApplyPatchArgumentDiffConsumer()

        self.assertIsNone(consumer.consume_diff(turn, "call-1", "*** Begin Patch\n"))

        event = consumer.consume_diff(
            turn,
            "call-1",
            "*** Add File: hello.txt\n+hello",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.payload.call_id, "call-1")
        self.assertEqual(event.payload.changes, {Path("hello.txt"): FileChange.add("")})

        self.assertIsNone(consumer.consume_diff(turn, "call-1", "\n+world"))
        self.assertIsNone(consumer.consume_diff(turn, "call-1", "\n*** End Patch"))

        event = consumer.finish()

        self.assertIsNotNone(event)
        self.assertEqual(event.payload.call_id, "call-1")
        self.assertEqual(event.payload.changes, {Path("hello.txt"): FileChange.add("hello\nworld\n")})

    def test_apply_patch_argument_diff_consumer_respects_streaming_feature_gate(self) -> None:
        consumer = ApplyPatchArgumentDiffConsumer()
        patch = "*** Begin Patch\n*** Add File: skipped.txt\n+hello\n*** End Patch\n"

        event = consumer.consume_diff(SimpleNamespace(features={}), "patch-1", patch)

        self.assertIsNone(event)

    def test_convert_apply_patch_hunks_to_protocol_formats_update_progress(self) -> None:
        hunks = (
            Hunk.update_file(
                "edit.txt",
                move_path="moved.txt",
                chunks=(UpdateFileChunk(None, old_lines=("old",), new_lines=("new",)),),
            ),
        )

        self.assertEqual(
            convert_apply_patch_hunks_to_protocol(hunks),
            {Path("edit.txt"): FileChange.update("@@\n-old\n+new\n", move_path=Path("moved.txt"))},
        )

    def test_resolve_apply_patch_invocation_uses_selected_environment(self) -> None:
        remote = SimpleNamespace(environment_id="remote", cwd=Path("/remote"))
        invocation = SimpleNamespace(
            turn=SimpleNamespace(
                environments=(
                    SimpleNamespace(environment_id="local", cwd=Path("/local")),
                    remote,
                )
            ),
            payload=ToolPayload.custom(
                "*** Begin Patch\n"
                "*** Environment ID: remote\n"
                "*** Add File: hello.txt\n"
                "+hello\n"
                "*** End Patch"
            ),
        )

        resolved = resolve_apply_patch_invocation(invocation, multi_environment=True)

        self.assertIs(resolved.turn_environment, remote)
        self.assertEqual(resolved.selected_environment_id, "remote")
        self.assertEqual(resolved.cwd, Path("/remote"))
        self.assertEqual(resolved.args.hunks, (Hunk.add_file("hello.txt", "hello\n"),))

    def test_resolve_apply_patch_invocation_defaults_to_primary_environment(self) -> None:
        primary = SimpleNamespace(environment_id="local", cwd=Path("/local"))
        invocation = SimpleNamespace(
            turn=SimpleNamespace(environments=(primary,)),
            payload=ToolPayload.custom(
                "*** Begin Patch\n"
                "*** Add File: hello.txt\n"
                "+hello\n"
                "*** End Patch"
            ),
        )

        resolved = resolve_apply_patch_invocation(invocation)

        self.assertIs(resolved.turn_environment, primary)
        self.assertIsNone(resolved.selected_environment_id)
        self.assertEqual(resolved.cwd, Path("/local"))

    def test_apply_patch_environment_selection_errors_match_rust(self) -> None:
        with self.assertRaises(FunctionCallError) as unavailable:
            resolve_apply_patch_invocation(
                SimpleNamespace(
                    turn=SimpleNamespace(environments=()),
                    payload=ToolPayload.custom(
                        "*** Begin Patch\n"
                        "*** Add File: hello.txt\n"
                        "+hello\n"
                        "*** End Patch"
                    ),
                )
            )
        self.assertEqual(str(unavailable.exception), "apply_patch is unavailable in this session")

        with self.assertRaises(FunctionCallError) as disabled:
            require_apply_patch_environment_id("remote", False)
        self.assertEqual(
            str(disabled.exception),
            "apply_patch environment selection is unavailable for this turn",
        )

    def test_apply_patch_handler_applies_verified_patch_to_selected_environment(self) -> None:
        with tempfile.TemporaryDirectory() as local_dir, tempfile.TemporaryDirectory() as remote_dir:
            local_root = Path(local_dir)
            remote_root = Path(remote_dir)
            (remote_root / "edit.txt").write_text("old\n", encoding="utf-8")
            (remote_root / "gone.txt").write_text("delete me\n", encoding="utf-8")
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    environments=(
                        SimpleNamespace(environment_id="local", cwd=local_root),
                        SimpleNamespace(environment_id="remote", cwd=remote_root),
                    )
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    "*** Environment ID: remote\n"
                    "*** Add File: nested/new.txt\n"
                    "+hello\n"
                    "*** Update File: edit.txt\n"
                    "@@\n"
                    "-old\n"
                    "+new\n"
                    "*** Delete File: gone.txt\n"
                    "*** End Patch"
                ),
            )

            output = ApplyPatchHandler.new(True).handle(invocation)

            self.assertIsInstance(output, ApplyPatchToolOutput)
            self.assertEqual((remote_root / "nested" / "new.txt").read_text(encoding="utf-8"), "hello\n")
            self.assertEqual((remote_root / "edit.txt").read_text(encoding="utf-8"), "new\n")
            self.assertFalse((remote_root / "gone.txt").exists())
            self.assertFalse((local_root / "nested" / "new.txt").exists())
            self.assertEqual(
                output.text,
                "Success. Updated the following files:\n"
                f"A {remote_root / 'nested' / 'new.txt'}\n"
                f"M {remote_root / 'edit.txt'}\n"
                f"D {remote_root / 'gone.txt'}\n",
            )

    def test_apply_patch_handler_reports_verification_errors_to_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    environments=(SimpleNamespace(environment_id="local", cwd=root),)
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    "*** Delete File: missing.txt\n"
                    "*** End Patch"
                ),
            )

            with self.assertRaises(FunctionCallError) as error:
                ApplyPatchHandler().handle(invocation)

            self.assertIn("apply_patch verification failed:", str(error.exception))

    def test_apply_patch_handler_requires_approval_for_read_only_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    approval_policy=AskForApproval.ON_REQUEST,
                    file_system_sandbox_policy=PermissionProfile.read_only().file_system_sandbox_policy(),
                    environments=(SimpleNamespace(environment_id="local", cwd=root),),
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    "*** Add File: created.txt\n"
                    "+blocked\n"
                    "*** End Patch"
                ),
            )

            with self.assertRaises(FunctionCallError) as error:
                ApplyPatchHandler().handle(invocation)

            self.assertIn("approval_required", str(error.exception))
            self.assertFalse((root / "created.txt").exists())

    def test_apply_patch_handler_forbids_read_only_policy_when_granular_disallows_sandbox_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    approval_policy=GranularApprovalConfig(
                        sandbox_approval=False,
                        rules=True,
                        skill_approval=False,
                        request_permissions=True,
                        mcp_elicitations=False,
                    ),
                    file_system_sandbox_policy=PermissionProfile.read_only().file_system_sandbox_policy(),
                    environments=(SimpleNamespace(environment_id="local", cwd=root),),
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    "*** Add File: created.txt\n"
                    "+blocked\n"
                    "*** End Patch"
                ),
            )

            with self.assertRaises(FunctionCallError) as error:
                ApplyPatchHandler().handle(invocation)

            self.assertIn("exit_code: forbidden", str(error.exception))
            self.assertIn("approval_policy: granular", str(error.exception))
            self.assertFalse((root / "created.txt").exists())

    def test_apply_patch_handler_allows_workspace_write_policy_for_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    approval_policy=AskForApproval.NEVER,
                    file_system_sandbox_policy=PermissionProfile.workspace_write().file_system_sandbox_policy(),
                    environments=(SimpleNamespace(environment_id="local", cwd=root),),
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    "*** Add File: created.txt\n"
                    "+allowed\n"
                    "*** End Patch"
                ),
            )

            output = ApplyPatchHandler().handle(invocation)

            self.assertIn("Success. Updated the following files:", output.text)
            self.assertEqual((root / "created.txt").read_text(encoding="utf-8"), "allowed\n")

    def test_apply_patch_handler_allows_granted_write_permissions_for_read_only_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            granted_permissions = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    (
                        FileSystemSandboxEntry(
                            FileSystemPath.explicit_path(root),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )
            invocation = SimpleNamespace(
                session=SimpleNamespace(_granted_turn_permissions=granted_permissions),
                turn=SimpleNamespace(
                    approval_policy=AskForApproval.ON_REQUEST,
                    file_system_sandbox_policy=PermissionProfile.read_only().file_system_sandbox_policy(),
                    environments=(SimpleNamespace(environment_id="local", cwd=root),),
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    "*** Add File: created.txt\n"
                    "+granted\n"
                    "*** End Patch"
                ),
            )

            output = ApplyPatchHandler().handle(invocation)

            self.assertIn("Success. Updated the following files:", output.text)
            self.assertEqual((root / "created.txt").read_text(encoding="utf-8"), "granted\n")

    def test_apply_patch_handler_move_update_reports_original_path_like_rust(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "old.txt").write_text("old\n", encoding="utf-8")
            invocation = SimpleNamespace(
                turn=SimpleNamespace(
                    environments=(SimpleNamespace(environment_id="local", cwd=root),)
                ),
                payload=ToolPayload.custom(
                    "*** Begin Patch\n"
                    "*** Update File: old.txt\n"
                    "*** Move to: renamed/new.txt\n"
                    "@@\n"
                    "-old\n"
                    "+new\n"
                    "*** End Patch"
                ),
            )

            output = ApplyPatchHandler().handle(invocation)

            self.assertFalse((root / "old.txt").exists())
            self.assertEqual((root / "renamed" / "new.txt").read_text(encoding="utf-8"), "new\n")
            self.assertEqual(
                output.text,
                "Success. Updated the following files:\n"
                f"M {root / 'old.txt'}\n",
            )

    def test_parse_patch_parses_multiple_hunk_variants(self) -> None:
        self.assertEqual(
            parse_patch(
                "*** Begin Patch\n"
                "*** Add File: path/add.py\n"
                "+abc\n"
                "+def\n"
                "*** Delete File: path/delete.py\n"
                "*** Update File: path/update.py\n"
                "*** Move to: path/update2.py\n"
                "@@ def f():\n"
                "-    pass\n"
                "+    return 123\n"
                "*** End Patch"
            ).hunks,
            (
                Hunk.add_file("path/add.py", "abc\ndef\n"),
                Hunk.delete_file("path/delete.py"),
                Hunk.update_file(
                    "path/update.py",
                    move_path="path/update2.py",
                    chunks=(
                        UpdateFileChunk(
                            change_context="def f():",
                            old_lines=("    pass",),
                            new_lines=("    return 123",),
                        ),
                    ),
                ),
            ),
        )

    def test_parse_patch_reports_boundary_and_hunk_errors(self) -> None:
        with self.assertRaises(ApplyPatchParseError) as first_line:
            parse_patch("bad")
        self.assertEqual(first_line.exception.kind, "invalid_patch")
        self.assertEqual(
            first_line.exception.message,
            "The first line of the patch must be '*** Begin Patch'",
        )

        with self.assertRaises(ApplyPatchParseError) as empty_update:
            parse_patch("*** Begin Patch\n*** Update File: test.py\n*** End Patch")
        self.assertEqual(empty_update.exception.kind, "invalid_hunk")
        self.assertEqual(empty_update.exception.line_number, 2)
        self.assertEqual(
            empty_update.exception.message,
            "Update file hunk for path 'test.py' is empty",
        )

    def test_parse_patch_accepts_lenient_heredoc_wrappers(self) -> None:
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: file2.py\n"
            " import foo\n"
            "+bar\n"
            "*** End Patch"
        )

        self.assertEqual(
            parse_patch(f"<<'EOF'\n{patch_text}\nEOF\n"),
            ApplyPatchArgs(
                patch=patch_text,
                hunks=(
                    Hunk.update_file(
                        "file2.py",
                        chunks=(
                            UpdateFileChunk(
                                change_context=None,
                                old_lines=("import foo",),
                                new_lines=("import foo", "bar"),
                            ),
                        ),
                    ),
                ),
            ),
        )

    def test_parse_patch_reads_environment_id_preamble(self) -> None:
        parsed = parse_patch(
            "*** Begin Patch\n"
            "*** Environment ID: remote\n"
            "*** Add File: hello.txt\n"
            "+hello\n"
            "*** End Patch"
        )

        self.assertEqual(parsed.environment_id, "remote")
        self.assertEqual(parsed.hunks, (Hunk.add_file("hello.txt", "hello\n"),))

        with self.assertRaises(ApplyPatchParseError) as empty_environment:
            parse_patch(
                "*** Begin Patch\n"
                "*** Environment ID:   \n"
                "*** Add File: hello.txt\n"
                "+hello\n"
                "*** End Patch"
            )
        self.assertEqual(
            empty_environment.exception.message,
            "apply_patch environment_id cannot be empty",
        )

    def test_parse_patch_update_chunks_match_upstream_leniency(self) -> None:
        parsed = parse_patch(
            "*** Begin Patch\n"
            "*** Update File: file.py\n"
            "@@\n"
            "+line\n"
            "*** Add File: other.py\n"
            "+content\n"
            "*** End Patch"
        )
        self.assertEqual(
            parsed.hunks,
            (
                Hunk.update_file(
                    "file.py",
                    chunks=(UpdateFileChunk(None, (), ("line",)),),
                ),
                Hunk.add_file("other.py", "content\n"),
            ),
        )

        parsed = parse_patch(
            "*** Begin Patch\n"
            "*** Update File: file2.py\n"
            " import foo\n"
            "+bar\n"
            "*** End Patch"
        )
        self.assertEqual(
            parsed.hunks,
            (
                Hunk.update_file(
                    "file2.py",
                    chunks=(
                        UpdateFileChunk(
                            None,
                            ("import foo",),
                            ("import foo", "bar"),
                        ),
                    ),
                ),
            ),
        )

    def test_derive_new_contents_from_chunks_matches_upstream_search_leniency(self) -> None:
        chunks = (
            UpdateFileChunk(
                "header",
                old_lines=("foo", "bar"),
                new_lines=("foo", "BAR"),
            ),
            UpdateFileChunk(
                None,
                old_lines=("plain - dash", "quote 'x'"),
                new_lines=("plain - dash", 'quote "x"'),
            ),
        )

        self.assertEqual(
            derive_new_contents_from_chunks(
                "file.txt",
                chunks,
                "header\nfoo   \nbar\nplain \u2014 dash\nquote \u2018x\u2019\n",
            ),
            'header\nfoo\nBAR\nplain - dash\nquote "x"\n',
        )

    def test_unified_diff_from_chunks_matches_upstream_multi_change(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: multi.txt\n"
            "@@\n"
            " foo\n"
            "-bar\n"
            "+BAR\n"
            "@@\n"
            " baz\n"
            "-qux\n"
            "+QUX\n"
            "*** End Patch"
        )

        self.assertEqual(
            unified_diff_from_chunks(
                "multi.txt",
                self.update_chunks_from_patch(patch),
                "foo\nbar\nbaz\nqux\n",
            ),
            ApplyPatchFileUpdate(
                unified_diff=(
                    "@@ -1,4 +1,4 @@\n"
                    " foo\n"
                    "-bar\n"
                    "+BAR\n"
                    " baz\n"
                    "-qux\n"
                    "+QUX\n"
                ),
                original_content="foo\nbar\nbaz\nqux\n",
                content="foo\nBAR\nbaz\nQUX\n",
            ),
        )

    def test_unified_diff_from_chunks_handles_edges_and_eof_insert(self) -> None:
        cases = (
            (
                "first.txt",
                "foo\nbar\nbaz\n",
                "*** Update File: first.txt\n@@\n-foo\n+FOO\n bar",
                "@@ -1,2 +1,2 @@\n-foo\n+FOO\n bar\n",
                "FOO\nbar\nbaz\n",
            ),
            (
                "last.txt",
                "foo\nbar\nbaz\n",
                "*** Update File: last.txt\n@@\n foo\n bar\n-baz\n+BAZ",
                "@@ -2,2 +2,2 @@\n bar\n-baz\n+BAZ\n",
                "foo\nbar\nBAZ\n",
            ),
            (
                "insert.txt",
                "foo\nbar\nbaz\n",
                "*** Update File: insert.txt\n@@\n+quux\n*** End of File",
                "@@ -3 +3,2 @@\n baz\n+quux\n",
                "foo\nbar\nbaz\nquux\n",
            ),
        )

        for path, original, body, expected_diff, expected_content in cases:
            with self.subTest(path=path):
                patch = f"*** Begin Patch\n{body}\n*** End Patch"
                self.assertEqual(
                    unified_diff_from_chunks(
                        path,
                        self.update_chunks_from_patch(patch),
                        original,
                    ),
                    ApplyPatchFileUpdate(
                        unified_diff=expected_diff,
                        original_content=original,
                        content=expected_content,
                    ),
                )

    def test_unified_diff_from_chunks_handles_interleaved_chunks(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: interleaved.txt\n"
            "@@\n"
            " a\n"
            "-b\n"
            "+B\n"
            "@@\n"
            " d\n"
            "-e\n"
            "+E\n"
            "@@\n"
            " f\n"
            "+g\n"
            "*** End of File\n"
            "*** End Patch"
        )

        self.assertEqual(
            unified_diff_from_chunks(
                "interleaved.txt",
                self.update_chunks_from_patch(patch),
                "a\nb\nc\nd\ne\nf\n",
            ),
            ApplyPatchFileUpdate(
                unified_diff=(
                    "@@ -1,6 +1,7 @@\n"
                    " a\n"
                    "-b\n"
                    "+B\n"
                    " c\n"
                    " d\n"
                    "-e\n"
                    "+E\n"
                    " f\n"
                    "+g\n"
                ),
                original_content="a\nb\nc\nd\ne\nf\n",
                content="a\nB\nc\nd\nE\nf\ng\n",
            ),
        )

    def test_unified_diff_from_chunks_reports_missing_context(self) -> None:
        chunks = (UpdateFileChunk(None, old_lines=("missing",), new_lines=("new",)),)

        with self.assertRaises(ApplyPatchError) as error:
            unified_diff_from_chunks("file.txt", chunks, "present\n")

        self.assertEqual(error.exception.kind, "compute_replacements")
        self.assertEqual(
            error.exception.message,
            "Failed to find expected lines in file.txt:\nmissing",
        )

    def test_verify_apply_patch_args_reads_files_and_resolves_paths(self) -> None:
        root = self.make_workspace_dir()
        workdir = root / "repo"
        workdir.mkdir()
        (workdir / "edit.txt").write_text("old\n", encoding="utf-8")
        (workdir / "gone.txt").write_text("delete me\n", encoding="utf-8")
        patch = (
            "*** Begin Patch\n"
            "*** Add File: added.txt\n"
            "+hello\n"
            "*** Delete File: gone.txt\n"
            "*** Update File: edit.txt\n"
            "*** Move to: moved.txt\n"
            "@@\n"
            "-old\n"
            "+new\n"
            "*** End Patch"
        )
        args = parse_patch(patch)

        result = verify_apply_patch_args(
            ApplyPatchArgs(
                patch=args.patch,
                hunks=args.hunks,
                workdir="repo",
            ),
            root,
        )

        self.assertEqual(result.type, "body")
        self.assertIsNotNone(result.body)
        action = result.body
        self.assertEqual(action.cwd, workdir)
        self.assertEqual(action.patch, patch)
        self.assertEqual(
            action.changes[workdir / "added.txt"],
            ApplyPatchFileChange.add("hello\n"),
        )
        self.assertEqual(
            action.changes[workdir / "gone.txt"],
            ApplyPatchFileChange.delete("delete me\n"),
        )
        self.assertEqual(
            action.changes[workdir / "edit.txt"],
            ApplyPatchFileChange.update(
                "@@ -1 +1 @@\n-old\n+new\n",
                move_path=workdir / "moved.txt",
                new_content="new\n",
                old_content="old\n",
            ),
        )

    def test_maybe_parse_apply_patch_verified_detects_implicit_patch(self) -> None:
        patch = "*** Begin Patch\n*** Add File: added.txt\n+hello\n*** End Patch"
        result = maybe_parse_apply_patch_verified((patch,), self.make_workspace_dir())

        self.assertEqual(result.type, "correctness_error")
        self.assertIsInstance(result.error, ApplyPatchError)
        self.assertEqual(result.error.kind, "implicit_invocation")

    def test_maybe_parse_apply_patch_verified_surfaces_missing_file(self) -> None:
        patch = "*** Begin Patch\n*** Delete File: missing.txt\n*** End Patch"
        result = maybe_parse_apply_patch_verified(
            ("apply_patch", patch),
            self.make_workspace_dir(),
        )

        self.assertEqual(result.type, "correctness_error")
        self.assertIsInstance(result.error, ApplyPatchError)
        self.assertEqual(result.error.kind, "io_error")

    def test_streaming_patch_parser_streams_complete_lines_before_end_patch(self) -> None:
        parser = StreamingPatchParser()
        self.assertEqual(
            parser.push_delta("*** Begin Patch\n*** Add File: src/hello.txt\n+hello\n+wor"),
            (Hunk.add_file("src/hello.txt", "hello\n"),),
        )
        self.assertEqual(
            parser.push_delta("ld\n"),
            (Hunk.add_file("src/hello.txt", "hello\nworld\n"),),
        )

        parser = StreamingPatchParser()
        self.assertEqual(
            parser.push_delta("*** Begin Patch\n*** Delete File: gone.txt"),
            (),
        )
        self.assertEqual(
            parser.push_delta("\n"),
            (Hunk.delete_file("gone.txt"),),
        )

    def test_streaming_patch_parser_update_move_and_environment_id(self) -> None:
        parser = StreamingPatchParser()
        self.assertEqual(
            parser.push_delta(
                "*** Begin Patch\n"
                "*** Environment ID: remote\n"
                "*** Update File: src/old.rs\n"
                "*** Move to: src/new.rs\n"
                "@@\n"
                "-old\n"
                "+new\n"
            ),
            (
                Hunk.update_file(
                    "src/old.rs",
                    move_path="src/new.rs",
                    chunks=(UpdateFileChunk(None, ("old",), ("new",)),),
                ),
            ),
        )

        parser = StreamingPatchParser()
        self.assertEqual(
            parser.push_delta("*** Begin Patch\n*** Environment ID:   \n"),
            (),
        )

    def test_streaming_patch_parser_large_patch_split_by_character(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Add File: docs/release-notes.md\n"
            "+# Release notes\n"
            "+\n"
            "+## CLI\n"
            "+- Surface apply_patch progress while arguments stream.\n"
            "*** Update File: src/config.rs\n"
            "@@ impl Config\n"
            "-    pub apply_patch_progress: bool,\n"
            "+    pub stream_apply_patch_progress: bool,\n"
            "*** Delete File: src/legacy_patch_progress.rs\n"
            "*** Update File: crates/cli/src/main.rs\n"
            "*** Move to: crates/cli/src/bin/codex.rs\n"
            "@@ fn run()\n"
            "-    let args = Args::parse();\n"
            "-    dispatch(args)\n"
            "+    let cli = Cli::parse();\n"
            "+    dispatch(cli)\n"
            "*** End Patch"
        )

        parser = StreamingPatchParser()
        max_hunk_count = 0
        saw_hunk_counts: list[int] = []
        hunks: tuple[Hunk, ...] = ()
        for ch in patch:
            updated_hunks = parser.push_delta(ch)
            if updated_hunks:
                hunk_count = len(updated_hunks)
                self.assertGreaterEqual(hunk_count, max_hunk_count)
                if hunk_count > max_hunk_count:
                    saw_hunk_counts.append(hunk_count)
                    max_hunk_count = hunk_count
                hunks = updated_hunks

        self.assertEqual(saw_hunk_counts, [1, 2, 3, 4])
        self.assertEqual([hunk.type for hunk in hunks], ["add", "update", "delete", "update"])
        self.assertEqual(hunks[-1].move_path, Path("crates/cli/src/bin/codex.rs"))

    def test_streaming_patch_parser_preserves_update_line_edge_cases(self) -> None:
        parser = StreamingPatchParser()
        self.assertEqual(
            parser.push_delta(
                "*** Begin Patch\r\n"
                "*** Update File: file.txt\r\n"
                "@@\r\n"
                "-old\r\r\n"
                "+new\r\n"
                "*** End Patch\r\n"
            ),
            (
                Hunk.update_file(
                    "file.txt",
                    chunks=(UpdateFileChunk(None, ("old\r",), ("new",)),),
                ),
            ),
        )

        parser = StreamingPatchParser()
        self.assertEqual(
            parser.push_delta(
                "*** Begin Patch\n"
                "*** Update File: a.txt\n"
                "@@\n"
                "-old a\n"
                "+new a\n"
                " *** Update File: b.txt\n"
                "@@\n"
                "-old b\n"
                "+new b\n"
                "*** End Patch\n"
            ),
            (
                Hunk.update_file(
                    "a.txt",
                    chunks=(
                        UpdateFileChunk(
                            None,
                            ("old a", "*** Update File: b.txt"),
                            ("new a", "*** Update File: b.txt"),
                        ),
                        UpdateFileChunk(None, ("old b",), ("new b",)),
                    ),
                ),
            ),
        )

    def test_streaming_patch_parser_finish_and_errors(self) -> None:
        parser = StreamingPatchParser()
        self.assertEqual(
            parser.push_delta("*** Begin Patch\n*** Add File: file.txt\n+hello\n*** End Patch"),
            (Hunk.add_file("file.txt", "hello\n"),),
        )
        self.assertEqual(parser.finish(), (Hunk.add_file("file.txt", "hello\n"),))

        parser = StreamingPatchParser()
        parser.push_delta("*** Begin Patch\n*** Add File: file.txt\n+hello\n")
        with self.assertRaises(ApplyPatchParseError) as missing_end:
            parser.finish()
        self.assertEqual(missing_end.exception.kind, "invalid_patch")
        self.assertEqual(
            missing_end.exception.message,
            "The last line of the patch must be '*** End Patch'",
        )

        parser = StreamingPatchParser()
        with self.assertRaises(ApplyPatchParseError) as empty_update:
            parser.push_delta("*** Begin Patch\n*** Update File: file.txt\n*** End Patch\n")
        self.assertEqual(empty_update.exception.kind, "invalid_hunk")
        self.assertEqual(empty_update.exception.line_number, 2)
        self.assertEqual(
            empty_update.exception.message,
            "Update file hunk for path 'file.txt' is empty",
        )

        parser = StreamingPatchParser()
        with self.assertRaises(ApplyPatchParseError) as bad_line:
            parser.push_delta("*** Begin Patch\n*** Update File: file.txt\n@@\n-old\nbad\n")
        self.assertEqual(bad_line.exception.line_number, 5)
        self.assertEqual(
            bad_line.exception.message,
            "Expected update hunk to start with a @@ context marker, got: 'bad'",
        )

    def test_maybe_parse_apply_patch_accepts_literal_invocations(self) -> None:
        patch = "*** Begin Patch\n*** Add File: foo\n+hi\n*** End Patch\n"

        for command in ("apply_patch", "applypatch"):
            body = self.assert_apply_patch_body(
                maybe_parse_apply_patch((command, patch))
            )
            self.assertEqual(body.hunks, (Hunk.add_file("foo", "hi\n"),))

    def test_maybe_parse_apply_patch_accepts_shell_heredoc_invocations(self) -> None:
        script = (
            "apply_patch <<'PATCH'\n"
            "*** Begin Patch\n"
            "*** Add File: foo\n"
            "+hi\n"
            "*** End Patch\n"
            "PATCH"
        )
        for argv in (
            ("bash", "-lc", script),
            ("bash", "-c", script),
            ("powershell.exe", "-Command", script),
            ("powershell.exe", "-NoProfile", "-Command", script),
            ("pwsh", "-NoProfile", "-Command", script),
        ):
            body = self.assert_apply_patch_body(maybe_parse_apply_patch(argv))
            self.assertEqual(body.hunks, (Hunk.add_file("foo", "hi\n"),))

    def test_maybe_parse_apply_patch_accepts_cd_prefixed_heredoc(self) -> None:
        for prefix, expected_workdir in (
            ("cd foo && ", "foo"),
            ("cd 'foo bar' && ", "foo bar"),
            ('cd "foo bar" && ', "foo bar"),
        ):
            script = (
                f"{prefix}applypatch <<'PATCH'\n"
                "*** Begin Patch\n"
                "*** Add File: foo\n"
                "+hi\n"
                "*** End Patch\n"
                "PATCH"
            )

            body = self.assert_apply_patch_body(
                maybe_parse_apply_patch(("bash", "-lc", script)),
                expected_workdir=expected_workdir,
            )
            self.assertEqual(body.hunks, (Hunk.add_file("foo", "hi\n"),))

    def test_maybe_parse_apply_patch_rejects_non_top_level_or_ambiguous_forms(self) -> None:
        def heredoc_script(prefix: str, suffix: str = "") -> str:
            return (
                f"{prefix}apply_patch <<'PATCH'\n"
                "*** Begin Patch\n"
                "*** Add File: foo\n"
                "+hi\n"
                "*** End Patch\n"
                f"PATCH{suffix}"
            )

        for script in (
            heredoc_script("cd foo; "),
            heredoc_script("cd bar || "),
            heredoc_script("cd bar | "),
            heredoc_script("echo foo && "),
            "apply_patch foo <<'PATCH'\n*** Begin Patch\n*** Add File: foo\n+hi\n*** End Patch\nPATCH",
            heredoc_script("cd foo && cd bar && "),
            heredoc_script("cd foo bar && "),
            heredoc_script("cd bar && ", " && echo done"),
            heredoc_script("echo foo; cd bar && "),
        ):
            self.assertEqual(
                maybe_parse_apply_patch(("bash", "-lc", script)).type,
                "not_apply_patch",
            )

    def test_maybe_parse_apply_patch_surfaces_patch_parse_errors(self) -> None:
        result = maybe_parse_apply_patch(("apply_patch", "bad"))

        self.assertEqual(result.type, "patch_parse_error")
        self.assertIsInstance(result.error, ApplyPatchParseError)
        self.assertEqual(
            result.error.message,
            "The first line of the patch must be '*** Begin Patch'",
        )

    def test_apply_patch_dataclasses_reject_mixed_rust_shapes(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_patch errors must not have a line_number"):
            ApplyPatchParseError("invalid_patch", "bad", 1)

        with self.assertRaisesRegex(TypeError, "old_lines must contain only strings"):
            UpdateFileChunk(None, old_lines=("ok", 1))  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "delete hunks must not have chunks"):
            Hunk(type="delete", path=Path("gone.txt"), chunks=(UpdateFileChunk(None),))

        with self.assertRaisesRegex(TypeError, "hunks must contain only Hunk values"):
            ApplyPatchArgs("patch", (object(),))  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "content is not valid for this variant"):
            ApplyPatchFileChange(type="update", unified_diff="@@\n", content="bad")

        with self.assertRaisesRegex(TypeError, "changes keys must be Paths"):
            ApplyPatchAction({"file.txt": ApplyPatchFileChange.add("x")})  # type: ignore[dict-item]

        with self.assertRaisesRegex(TypeError, "changes keys must be strings"):
            ApplyPatchAction.from_mapping(
                {
                    "changes": {Path("file.txt"): {"type": "add", "content": "x"}},
                }
            )


if __name__ == "__main__":
    unittest.main()
