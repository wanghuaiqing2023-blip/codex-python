"""Rust-aligned port of ``execpolicy-legacy/src/execv_checker.rs``."""



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



from .arg_type import ArgTypeKind

from .error import CannotCanonicalizePath, CannotCheckRelativePath, ReadablePathNotInReadableFolders, WriteablePathNotInWriteableFolders

from .exec_call import ExecCall

from .policy import Policy

from .program import MatchedExec

from .valid_exec import ValidExec



@dataclass(frozen=True)
class ExecvChecker:
    """Rust ``ExecvChecker`` projection.

    The caller supplies readable/writeable folders in canonical form, matching
    the Rust module contract.
    """

    execv_policy: Policy

    @classmethod
    def new(cls, execv_policy: Policy) -> "ExecvChecker":
        return cls(execv_policy=execv_policy)

    def match(self, exec_call: ExecCall) -> MatchedExec:
        return self.execv_policy.check(exec_call)

    def check(
        self,
        valid_exec: ValidExec,
        cwd: str | Path | None,
        readable_folders: list[str | Path] | tuple[str | Path, ...],
        writeable_folders: list[str | Path] | tuple[str | Path, ...],
    ) -> str:
        readable_roots = tuple(Path(folder) for folder in readable_folders)
        writeable_roots = tuple(Path(folder) for folder in writeable_folders)

        for arg_type, value in [
            *((arg.arg_type, arg.value) for arg in valid_exec.args),
            *((opt.arg_type, opt.value) for opt in valid_exec.opts),
        ]:
            if arg_type.kind == ArgTypeKind.READABLE_FILE.value:
                readable_file = _ensure_absolute_path(value, cwd)
                _check_path_in_folders(
                    readable_file,
                    readable_roots,
                    ReadablePathNotInReadableFolders,
                )
            elif arg_type.kind == ArgTypeKind.WRITEABLE_FILE.value:
                writeable_file = _ensure_absolute_path(value, cwd)
                _check_path_in_folders(
                    writeable_file,
                    writeable_roots,
                    WriteablePathNotInWriteableFolders,
                )

        program = valid_exec.program
        for system_path in valid_exec.system_path:
            if _is_executable_file(system_path):
                program = system_path
                break
        return program

def _ensure_absolute_path(path: str, cwd: str | Path | None) -> Path:
    file = Path(path)
    try:
        if not file.is_absolute():
            if cwd is None:
                raise CannotCheckRelativePath(file)
            file = Path(cwd) / file
        return file.resolve(strict=False)
    except CannotCheckRelativePath:
        raise
    except OSError as exc:
        raise CannotCanonicalizePath(path, exc.__class__.__name__) from exc

def _check_path_in_folders(
    file: Path,
    folders: tuple[Path, ...],
    error_type: type[ReadablePathNotInReadableFolders]
    | type[WriteablePathNotInWriteableFolders],
) -> None:
    for folder in folders:
        try:
            file.relative_to(folder)
            return None
        except ValueError:
            continue
    raise error_type(file, folders)

def _is_executable_file(path: str) -> bool:
    file = Path(path)
    if not file.is_file():
        return False
    if os.name == "nt":
        return True
    return os.access(file, os.X_OK)
