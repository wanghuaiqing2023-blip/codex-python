"""Rust-derived tests for ``codex-execpolicy-legacy/src/main.rs``."""

from __future__ import annotations

import io
import json
from pathlib import Path

from pycodex.execpolicy_legacy import FORBIDDEN_EXIT_CODE
from pycodex.execpolicy_legacy import MATCHED_BUT_WRITES_FILES_EXIT_CODE
from pycodex.execpolicy_legacy import MIGHT_BE_SAFE_EXIT_CODE
from pycodex.execpolicy_legacy import ExecArg
from pycodex.execpolicy_legacy import PolicyParser
from pycodex.execpolicy_legacy import check_command
from pycodex.execpolicy_legacy import get_default_policy
from pycodex.execpolicy_legacy import run_main


def test_check_command_safe_output_matches_main_rs_contract() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/main.rs.
    # Contract: check_command returns Output::Safe with exit 0 when a matched
    # command has no writable file args.
    output, exit_code = check_command(
        get_default_policy(),
        ExecArg.new("ls", ["-l", "foo"]),
        require_safe=True,
    )

    assert exit_code == 0
    assert output == {
        "result": "safe",
        "match": {
            "program": "ls",
            "flags": [{"name": "-l"}],
            "opts": [],
            "args": [{"index": 1, "type": "ReadableFile", "value": "foo"}],
            "system_path": ["/bin/ls", "/usr/bin/ls"],
        },
    }


def test_check_command_match_exit_code_when_require_safe() -> None:
    # Rust README/main.rs contract: writable matches print result=match; exit is
    # 12 only when --require-safe is active.
    policy = get_default_policy()

    output, exit_code = check_command(
        policy,
        ExecArg.new("cp", ["src1", "src2", "dest"]),
        require_safe=False,
    )
    assert output["result"] == "match"
    assert exit_code == 0
    assert output["match"]["args"][-1] == {
        "index": 2,
        "type": "WriteableFile",
        "value": "dest",
    }

    _output, strict_exit = check_command(
        policy,
        ExecArg.new("cp", ["src1", "src2", "dest"]),
        require_safe=True,
    )
    assert strict_exit == MATCHED_BUT_WRITES_FILES_EXIT_CODE


def test_check_command_forbidden_and_unverified_exit_codes() -> None:
    # Rust main.rs contract: forbidden and unverified results exit 0 by default
    # and 14/13 respectively under --require-safe.
    policy = PolicyParser.new(
        "inline",
        """
define_program(
    program="applied",
    args=["deploy"],
    forbidden="Infrastructure Risk",
)
""",
    ).parse()

    forbidden, forbidden_exit = check_command(
        policy,
        ExecArg.new("applied", ["deploy"]),
        require_safe=True,
    )
    assert forbidden_exit == FORBIDDEN_EXIT_CODE
    assert forbidden == {
        "result": "forbidden",
        "reason": "Infrastructure Risk",
        "cause": {
            "Exec": {
                "exec": {
                    "program": "applied",
                    "flags": [],
                    "opts": [],
                    "args": [
                        {"index": 0, "type": {"Literal": "deploy"}, "value": "deploy"}
                    ],
                    "system_path": [],
                }
            }
        },
    }

    unverified, unverified_exit = check_command(
        policy,
        ExecArg.new("unknown", []),
        require_safe=True,
    )
    assert unverified_exit == MIGHT_BE_SAFE_EXIT_CODE
    assert unverified == {
        "result": "unverified",
        "error": {"type": "NoSpecForProgram", "program": "unknown"},
    }


def test_run_main_check_json_and_policy_file(tmp_path: Path) -> None:
    # Rust anchors: Command::CheckJson deserialize_from_json and --policy file
    # loading through PolicyParser::new(policy_source, file_contents).
    policy_path = tmp_path / "policy.star"
    policy_path.write_text(
        'define_program(program="cat", args=[ARG_RFILES])\n',
        encoding="utf-8",
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_main(
        [
            "--policy",
            str(policy_path),
            "check-json",
            json.dumps({"program": "cat", "args": ["README.md"]}),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue()) == {
        "result": "safe",
        "match": {
            "program": "cat",
            "flags": [],
            "opts": [],
            "args": [{"index": 0, "type": "ReadableFile", "value": "README.md"}],
            "system_path": [],
        },
    }


def test_run_main_check_requires_a_command() -> None:
    # Rust main.rs: Command::Check exits 1 after printing "no command provided"
    # when no execv program is present.
    stdout = io.StringIO()
    stderr = io.StringIO()

    assert run_main(["check"], stdout=stdout, stderr=stderr) == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "no command provided\n"
