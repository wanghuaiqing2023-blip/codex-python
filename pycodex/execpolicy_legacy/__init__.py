"""Public facade for the Rust ``codex-execpolicy-legacy`` crate."""

from pathlib import Path

from .arg_matcher import ArgMatcher
from .arg_resolver import PositionalArg
from .arg_type import ArgType
from .error import Error
from .exec_call import ExecCall
from .execv_checker import ExecvChecker
from .opt import Opt
from .policy import Policy
from .policy_parser import PolicyParser
from .program import Forbidden
from .program import MatchedExec
from .program import NegativeExamplePassedCheck
from .program import PositiveExampleFailedCheck
from .program import ProgramSpec
from .sed_command import parse_sed_command
from .valid_exec import MatchedArg
from .valid_exec import MatchedFlag
from .valid_exec import MatchedOpt
from .valid_exec import ValidExec


def _default_policy_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "codex"
        / "codex-rs"
        / "execpolicy-legacy"
        / "src"
        / "default.policy"
    )


def get_default_policy() -> Policy:
    default_policy_path = _default_policy_path()
    return PolicyParser(
        "#default",
        default_policy_path.read_text(encoding="utf-8"),
    ).parse()


__all__ = [
    "ArgMatcher",
    "ArgType",
    "Error",
    "ExecCall",
    "ExecvChecker",
    "Forbidden",
    "MatchedArg",
    "MatchedExec",
    "MatchedFlag",
    "MatchedOpt",
    "NegativeExamplePassedCheck",
    "Opt",
    "Policy",
    "PolicyParser",
    "PositionalArg",
    "PositiveExampleFailedCheck",
    "ProgramSpec",
    "ValidExec",
    "get_default_policy",
    "parse_sed_command",
]
