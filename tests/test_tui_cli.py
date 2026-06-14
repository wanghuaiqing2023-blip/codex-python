# Parity source: codex-rs/tui/src/cli.rs

from pycodex.tui.cli import (
    Cli,
    TuiSharedCliOptions,
    augment_args,
    augment_args_for_update,
    deref,
    deref_mut,
    from_arg_matches,
    mark_tui_args,
    update_from_arg_matches,
)


def test_cli_defaults_match_skipped_and_flag_defaults():
    cli = Cli()

    assert cli.prompt is None
    assert cli.strict_config is False
    assert cli.resume_picker is False
    assert cli.resume_last is False
    assert cli.resume_session_id is None
    assert cli.resume_show_all is False
    assert cli.resume_include_non_interactive is False
    assert cli.fork_picker is False
    assert cli.fork_last is False
    assert cli.fork_session_id is None
    assert cli.fork_show_all is False
    assert cli.approval_policy is None
    assert cli.web_search is False
    assert cli.no_alt_screen is False
    assert cli.config_overrides == {}


def test_cli_deref_targets_shared_options():
    shared = TuiSharedCliOptions({"model": "gpt-5"})
    cli = Cli(shared=shared)

    assert cli.deref() is shared.value
    assert cli.deref_mut() is shared.value
    assert deref(cli) is shared.value
    assert deref_mut(cli) is shared.value


def test_tui_shared_cli_options_into_inner_returns_wrapped_value():
    wrapped = {"sandbox": "workspace-write"}
    shared = TuiSharedCliOptions(wrapped)

    assert shared.into_inner() is wrapped
    assert deref(shared) is wrapped


def test_from_and_update_arg_matches_delegate_to_shared_options_semantics():
    shared = from_arg_matches({"model": "gpt-5"})

    assert shared.value == {"model": "gpt-5"}
    update_from_arg_matches(shared, {"profile": "fast"})
    assert shared.value == {"model": "gpt-5", "profile": "fast"}


def test_update_arg_matches_sets_attributes_on_object_shared_options():
    class Shared:
        pass

    shared_obj = Shared()
    shared = TuiSharedCliOptions(shared_obj)

    update_from_arg_matches(shared, {"model": "gpt-5", "profile": "fast"})

    assert shared_obj.model == "gpt-5"
    assert shared_obj.profile == "fast"


def test_mark_tui_args_adds_conflict_with_approval_policy():
    cmd = {"args": {"dangerously_bypass_approvals_and_sandbox": {}}}

    marked = mark_tui_args(cmd)

    assert marked is cmd
    assert cmd["args"]["dangerously_bypass_approvals_and_sandbox"]["conflicts_with"] == ["approval_policy"]


def test_mark_tui_args_is_idempotent_and_creates_missing_arg_shape():
    cmd = {}

    mark_tui_args(cmd)
    mark_tui_args(cmd)

    assert cmd["args"]["dangerously_bypass_approvals_and_sandbox"]["conflicts_with"] == ["approval_policy"]


def test_augment_args_and_update_apply_same_tui_marking():
    assert augment_args({})["args"]["dangerously_bypass_approvals_and_sandbox"]["conflicts_with"] == ["approval_policy"]
    assert augment_args_for_update({})["args"]["dangerously_bypass_approvals_and_sandbox"]["conflicts_with"] == ["approval_policy"]
