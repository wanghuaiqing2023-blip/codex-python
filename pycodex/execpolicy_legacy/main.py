"""Rust-aligned port of ``execpolicy-legacy/src/main.rs``."""



from __future__ import annotations

import os

import json

import re

import sys

from dataclasses import dataclass

from enum import Enum

from io import TextIOBase

from pathlib import Path

from re import Pattern



from .error import Error, InternalInvariantViolation

from .exec_call import ExecCall

from .policy import Policy

from .policy_parser import PolicyParser

from .program import Forbidden

from .valid_exec import ValidExec

from . import get_default_policy



MATCHED_BUT_WRITES_FILES_EXIT_CODE = 12

MIGHT_BE_SAFE_EXIT_CODE = 13

FORBIDDEN_EXIT_CODE = 14



@dataclass(frozen=True)
class ExecArg:
    """Rust ``main.rs`` ExecArg projection."""

    program: str
    args: tuple[str, ...] = ()

    @classmethod
    def new(cls, program: str, args: list[str] | tuple[str, ...] = ()) -> "ExecArg":
        return cls(program=str(program), args=tuple(str(arg) for arg in args))

    @classmethod
    def from_json(cls, value: str) -> "ExecArg":
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise TypeError("exec JSON must decode to an object")
        program = decoded.get("program")
        if not isinstance(program, str):
            raise TypeError("exec.program must be a string")
        args = decoded.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise TypeError("exec.args must be a list of strings")
        return cls.new(program, args)

    def to_exec_call(self) -> ExecCall:
        return ExecCall.new(self.program, self.args)

def check_command(policy: Policy, exec_arg: ExecArg, require_safe: bool = False) -> tuple[dict[str, object], int]:
    """Mirror Rust ``main.rs::check_command``."""

    exec_call = exec_arg.to_exec_call()
    try:
        matched = policy.check(exec_call)
    except Error as error:
        exit_code = MIGHT_BE_SAFE_EXIT_CODE if require_safe else 0
        return (
            {
                "result": "unverified",
                "error": error.to_mapping() if hasattr(error, "to_mapping") else str(error),
            },
            exit_code,
        )

    if matched.kind == "Match" and matched.exec is not None:
        if matched.exec.might_write_files():
            exit_code = MATCHED_BUT_WRITES_FILES_EXIT_CODE if require_safe else 0
            return (
                {"result": "match", "match": _valid_exec_to_rust_json(matched.exec)},
                exit_code,
            )
        return (
            {"result": "safe", "match": _valid_exec_to_rust_json(matched.exec)},
            0,
        )

    if matched.kind == "Forbidden" and matched.cause is not None:
        exit_code = FORBIDDEN_EXIT_CODE if require_safe else 0
        return (
            {
                "result": "forbidden",
                "reason": matched.reason or "",
                "cause": _forbidden_to_rust_json(matched.cause),
            },
            exit_code,
        )

    raise InternalInvariantViolation(f"unknown matched exec result: {matched!r}")

def run_main(
    argv: list[str] | tuple[str, ...],
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    """Dependency-light entry point for Rust ``src/main.rs`` behavior."""

    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    args = list(argv)
    require_safe = False
    policy_path: Path | None = None

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--require-safe":
            require_safe = True
            del args[index]
            continue
        if arg in {"--policy", "-p"}:
            if index + 1 >= len(args):
                raise ValueError(f"{arg} requires a path")
            policy_path = Path(args[index + 1])
            del args[index : index + 2]
            continue
        break

    if not args:
        print("no command provided", file=err)
        return 1

    command = args[0]
    if command == "check":
        if len(args) == 1:
            print("no command provided", file=err)
            return 1
        exec_arg = ExecArg.new(args[1], args[2:])
    elif command == "check-json":
        if len(args) != 2:
            raise ValueError("check-json requires one JSON argument")
        exec_arg = ExecArg.from_json(args[1])
    else:
        raise ValueError(f"unknown command: {command}")

    if policy_path is None:
        policy = get_default_policy()
    else:
        policy = PolicyParser.new(str(policy_path), policy_path.read_text(encoding="utf-8")).parse()

    output, exit_code = check_command(policy, exec_arg, require_safe)
    print(json.dumps(output, separators=(",", ":")), file=out)
    return exit_code

def main(
    argv: list[str] | tuple[str, ...] | None = None,
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    """Run the dependency-light legacy execpolicy CLI wrapper."""

    return run_main(tuple(sys.argv[1:] if argv is None else argv), stdout, stderr)

def _arg_type_to_rust_json(arg_type: ArgType) -> object:
    if arg_type.kind == "Literal":
        return {"Literal": arg_type.literal_value or ""}
    return str(arg_type.kind)

def _valid_exec_to_rust_json(valid_exec: ValidExec) -> dict[str, object]:
    return {
        "program": valid_exec.program,
        "flags": [{"name": flag.name} for flag in valid_exec.flags],
        "opts": [
            {
                "name": str(opt.name),
                "value": opt.value,
                "type": _arg_type_to_rust_json(opt.arg_type),
            }
            for opt in valid_exec.opts
        ],
        "args": [
            {
                "index": arg.index,
                "type": _arg_type_to_rust_json(arg.arg_type),
                "value": arg.value,
            }
            for arg in valid_exec.args
        ],
        "system_path": list(valid_exec.system_path),
    }

def _exec_call_to_rust_json(exec_call: ExecCall) -> dict[str, object]:
    return {"program": exec_call.program, "args": list(exec_call.args)}

def _forbidden_to_rust_json(forbidden: Forbidden) -> dict[str, object]:
    if forbidden.kind == "Program" and forbidden.exec_call is not None:
        return {
            "Program": {
                "program": forbidden.program,
                "exec_call": _exec_call_to_rust_json(forbidden.exec_call),
            }
        }
    if forbidden.kind == "Arg" and forbidden.exec_call is not None:
        return {
            "Arg": {
                "arg": forbidden.arg,
                "exec_call": _exec_call_to_rust_json(forbidden.exec_call),
            }
        }
    if forbidden.kind == "Exec" and forbidden.exec is not None:
        return {"Exec": {"exec": _valid_exec_to_rust_json(forbidden.exec)}}
    raise InternalInvariantViolation(f"unknown forbidden cause: {forbidden!r}")
