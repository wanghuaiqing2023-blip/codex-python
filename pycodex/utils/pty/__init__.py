"""Public facade for codex-utils-pty/src/lib.rs."""

from . import process_group
from .pipe import spawn_process as spawn_pipe_process
from .pipe import spawn_process_no_stdin as spawn_pipe_process_no_stdin
from .process import ProcessDriver
from .process import ProcessHandle
from .process import SpawnedProcess
from .process import TerminalSize
from .process import combine_output_receivers
from .process import spawn_from_driver
from .pty import conpty_supported
from .pty import spawn_process as spawn_pty_process

DEFAULT_OUTPUT_BYTES_CAP = 1024 * 1024
ExecCommandSession = ProcessHandle
SpawnedPty = SpawnedProcess

__all__ = [
    "DEFAULT_OUTPUT_BYTES_CAP",
    "ExecCommandSession",
    "ProcessDriver",
    "ProcessHandle",
    "SpawnedProcess",
    "SpawnedPty",
    "TerminalSize",
    "combine_output_receivers",
    "conpty_supported",
    "process_group",
    "spawn_from_driver",
    "spawn_pipe_process",
    "spawn_pipe_process_no_stdin",
    "spawn_pty_process",
]
