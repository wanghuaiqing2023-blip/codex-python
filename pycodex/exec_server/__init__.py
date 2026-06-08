"""Python interface for Rust ``codex-exec-server``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import base64


CODEX_EXEC_SERVER_URL_ENV_VAR = "CODEX_EXEC_SERVER_URL"
LOCAL_ENVIRONMENT_ID = "local"
REMOTE_ENVIRONMENT_ID = "remote"
CODEX_FS_HELPER_ARG1 = "--codex-run-as-fs-helper"
DEFAULT_LISTEN_URL = "ws://127.0.0.1:0"

INITIALIZE_METHOD = "initialize"
INITIALIZED_METHOD = "initialized"
EXEC_METHOD = "process/start"
EXEC_READ_METHOD = "process/read"
EXEC_WRITE_METHOD = "process/write"
EXEC_TERMINATE_METHOD = "process/terminate"
EXEC_OUTPUT_DELTA_METHOD = "process/output"
EXEC_EXITED_METHOD = "process/exited"
EXEC_CLOSED_METHOD = "process/closed"
FS_READ_FILE_METHOD = "fs/readFile"
FS_WRITE_FILE_METHOD = "fs/writeFile"
FS_CREATE_DIRECTORY_METHOD = "fs/createDirectory"
FS_GET_METADATA_METHOD = "fs/getMetadata"
FS_READ_DIRECTORY_METHOD = "fs/readDirectory"
FS_REMOVE_METHOD = "fs/remove"
FS_COPY_METHOD = "fs/copy"
HTTP_REQUEST_METHOD = "http/request"
HTTP_REQUEST_BODY_DELTA_METHOD = "http/request/bodyDelta"


class ExecServerError(Exception):
    pass


class ExecServerListenUrlParseError(ValueError):
    pass


@dataclass(frozen=True)
class ByteChunk:
    data: bytes

    def into_inner(self) -> bytes:
        return self.data

    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @classmethod
    def from_base64(cls, value: str) -> "ByteChunk":
        return cls(base64.b64decode(value))


ProcessId = str


@dataclass(frozen=True)
class InitializeParams:
    client_name: str
    resume_session_id: str | None = None


@dataclass(frozen=True)
class InitializeResponse:
    session_id: str


@dataclass(frozen=True)
class ExecEnvPolicy:
    inherit: Any
    ignore_default_excludes: bool
    exclude: list[str] = field(default_factory=list)
    set: dict[str, str] = field(default_factory=dict)
    include_only: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExecParams:
    process_id: ProcessId
    argv: list[str]
    cwd: str
    env: dict[str, str]
    tty: bool
    env_policy: ExecEnvPolicy | None = None
    pipe_stdin: bool = False
    arg0: str | None = None


@dataclass(frozen=True)
class ExecResponse:
    process_id: ProcessId


@dataclass(frozen=True)
class ReadParams:
    process_id: ProcessId
    after_seq: int | None = None
    max_bytes: int | None = None
    wait_ms: int | None = None


class ExecOutputStream(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    PTY = "pty"


@dataclass(frozen=True)
class ProcessOutputChunk:
    seq: int
    stream: ExecOutputStream
    chunk: ByteChunk


@dataclass(frozen=True)
class ReadResponse:
    chunks: list[ProcessOutputChunk]
    next_seq: int
    exited: bool
    exit_code: int | None
    closed: bool
    failure: str | None = None


@dataclass(frozen=True)
class WriteParams:
    process_id: ProcessId
    chunk: ByteChunk


class WriteStatus(str, Enum):
    ACCEPTED = "accepted"
    UNKNOWN_PROCESS = "unknownProcess"
    STDIN_CLOSED = "stdinClosed"
    STARTING = "starting"


@dataclass(frozen=True)
class WriteResponse:
    status: WriteStatus


@dataclass(frozen=True)
class TerminateParams:
    process_id: ProcessId


@dataclass(frozen=True)
class TerminateResponse:
    running: bool


@dataclass(frozen=True)
class FsReadFileParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsReadFileResponse:
    data_base64: str


@dataclass(frozen=True)
class FsWriteFileParams:
    path: str
    data_base64: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsWriteFileResponse:
    pass


@dataclass(frozen=True)
class FsCreateDirectoryParams:
    path: str
    recursive: bool | None = None
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsCreateDirectoryResponse:
    pass


@dataclass(frozen=True)
class FsGetMetadataParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsGetMetadataResponse:
    is_directory: bool
    is_file: bool
    is_symlink: bool
    created_at_ms: int
    modified_at_ms: int


@dataclass(frozen=True)
class FsReadDirectoryParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsReadDirectoryEntry:
    file_name: str
    is_directory: bool
    is_file: bool


@dataclass(frozen=True)
class FsReadDirectoryResponse:
    entries: list[FsReadDirectoryEntry]


@dataclass(frozen=True)
class FsRemoveParams:
    path: str
    recursive: bool | None = None
    force: bool | None = None
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsRemoveResponse:
    pass


@dataclass(frozen=True)
class FsCopyParams:
    source_path: str
    destination_path: str
    recursive: bool
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsCopyResponse:
    pass


@dataclass(frozen=True)
class HttpHeader:
    name: str
    value: str


@dataclass(frozen=True)
class HttpRequestParams:
    method: str
    url: str
    headers: list[HttpHeader]
    request_id: str
    body: ByteChunk | None = None
    timeout_ms: int | None = None
    stream_response: bool = False


@dataclass(frozen=True)
class HttpRequestResponse:
    status: int
    headers: list[HttpHeader]
    body: ByteChunk


@dataclass(frozen=True)
class HttpRequestBodyDeltaNotification:
    request_id: str
    seq: int
    delta: ByteChunk
    done: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ExecOutputDeltaNotification:
    process_id: ProcessId
    seq: int
    stream: ExecOutputStream
    chunk: ByteChunk


@dataclass(frozen=True)
class ExecExitedNotification:
    process_id: ProcessId
    seq: int
    exit_code: int


@dataclass(frozen=True)
class ExecClosedNotification:
    process_id: ProcessId
    seq: int


@dataclass(frozen=True)
class ExecServerRuntimePaths:
    fs_helper: str | None = None


@dataclass(frozen=True)
class Environment:
    exec_server_url_value: str | None = None

    @classmethod
    def default_for_tests(cls) -> "Environment":
        return cls()

    @classmethod
    def create_for_tests(cls, exec_server_url: str | None = None) -> "Environment":
        if exec_server_url == "none":
            raise ExecServerError("disabled mode does not create an Environment")
        return cls(exec_server_url)

    def is_remote(self) -> bool:
        return self.exec_server_url_value is not None

    def exec_server_url(self) -> str | None:
        return self.exec_server_url_value


class EnvironmentManager:
    def __init__(self, environments: dict[str, Environment] | None = None, default_environment: str | None = LOCAL_ENVIRONMENT_ID) -> None:
        self.environments = environments or {LOCAL_ENVIRONMENT_ID: Environment.default_for_tests()}
        self._default_environment = default_environment

    @classmethod
    def default_for_tests(cls) -> "EnvironmentManager":
        return cls()

    @classmethod
    def without_environments(cls) -> "EnvironmentManager":
        return cls({}, None)

    def default_environment(self) -> Environment | None:
        return self.get_environment(self._default_environment) if self._default_environment else None

    def default_environment_id(self) -> str | None:
        return self._default_environment

    def default_environment_ids(self) -> list[str]:
        if not self._default_environment:
            return []
        rest = [key for key in self.environments if key != self._default_environment]
        return [self._default_environment, *rest]

    def try_local_environment(self) -> Environment | None:
        return self.environments.get(LOCAL_ENVIRONMENT_ID)

    def default_or_local_environment(self) -> Environment | None:
        return self.default_environment() or self.try_local_environment()

    def get_environment(self, environment_id: str | None) -> Environment | None:
        return self.environments.get(environment_id or "")

    def upsert_environment(self, environment_id: str, exec_server_url: str) -> None:
        if not environment_id:
            raise ExecServerError("environment id cannot be empty")
        self.environments[environment_id] = Environment(exec_server_url)


class ExecServerClient:
    pass


class ReqwestHttpClient:
    pass


class HttpClient:
    pass


class ExecutorFileSystem:
    pass


class LocalFileSystem(ExecutorFileSystem):
    pass


LOCAL_FS = LocalFileSystem()
CopyOptions = CreateDirectoryOptions = FileMetadata = FileSystemResult = FileSystemSandboxContext = ReadDirectoryEntry = RemoveOptions = object
DefaultEnvironmentProvider = EnvironmentProvider = RemoteEnvironmentConfig = object
ExecBackend = ExecProcess = ExecProcessEvent = ExecProcessEventReceiver = StartedExecProcess = object


def run_main(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError("codex-exec-server process runtime is not ported")


def run_remote_environment(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError("codex-exec-server remote environment is not ported")


def run_fs_helper_main(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError("codex-exec-server filesystem helper is not ported")
