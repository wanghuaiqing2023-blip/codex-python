"""Agent path protocol type.

Ported from ``codex/codex-rs/protocol/src/agent_path.rs``.
"""

from __future__ import annotations


class AgentPath(str):
    ROOT = "/root"
    MORPHEUS = "/morpheus"
    ROOT_SEGMENT = "root"

    def __new__(cls, path: str) -> "AgentPath":
        if not isinstance(path, str):
            raise TypeError("agent path must be a string")
        _validate_absolute_path(path)
        return str.__new__(cls, path)

    @classmethod
    def root(cls) -> "AgentPath":
        return cls(cls.ROOT)

    @classmethod
    def morpheus(cls) -> "AgentPath":
        return cls(cls.MORPHEUS)

    @classmethod
    def from_string(cls, path: str) -> "AgentPath":
        return cls(path)

    def as_str(self) -> str:
        return str(self)

    def is_root(self) -> bool:
        return self.as_str() == self.ROOT

    def name(self) -> str:
        if self.is_root():
            return self.ROOT_SEGMENT
        segment = self.as_str().rsplit("/", 1)[-1]
        return segment or self.ROOT_SEGMENT

    def join(self, agent_name: str) -> "AgentPath":
        _validate_agent_name(agent_name)
        return AgentPath(f"{self}/{agent_name}")

    def resolve(self, reference: str) -> "AgentPath":
        if not isinstance(reference, str):
            raise TypeError("agent path reference must be a string")
        if reference == "":
            raise ValueError("agent path must not be empty")
        if reference == self.ROOT:
            return AgentPath.root()
        if reference.startswith("/"):
            return AgentPath(reference)

        _validate_relative_reference(reference)
        return AgentPath(f"{self}/{reference}")


def _validate_agent_name(agent_name: str) -> None:
    if not isinstance(agent_name, str):
        raise TypeError("agent_name must be a string")
    if agent_name == "":
        raise ValueError("agent_name must not be empty")
    if agent_name == AgentPath.ROOT_SEGMENT:
        raise ValueError("agent_name `root` is reserved")
    if agent_name in {".", ".."}:
        raise ValueError(f"agent_name `{agent_name}` is reserved")
    if "/" in agent_name:
        raise ValueError("agent_name must not contain `/`")
    if not all(character.isascii() and (character.islower() or character.isdigit() or character == "_") for character in agent_name):
        raise ValueError("agent_name must use only lowercase letters, digits, and underscores")


def _validate_absolute_path(path: str) -> None:
    if path == AgentPath.MORPHEUS:
        return
    if not path.startswith("/"):
        raise ValueError("absolute agent paths must start with `/root` or be `/morpheus`")

    stripped = path[1:]
    if stripped == "":
        raise ValueError("absolute agent path must not be empty")
    segments = stripped.split("/")
    if segments[0] != AgentPath.ROOT_SEGMENT:
        raise ValueError("absolute agent paths must start with `/root` or be `/morpheus`")
    if stripped.endswith("/"):
        raise ValueError("absolute agent path must not end with `/`")
    for segment in segments[1:]:
        _validate_agent_name(segment)


def _validate_relative_reference(reference: str) -> None:
    if reference.endswith("/"):
        raise ValueError("relative agent path must not end with `/`")
    for segment in reference.split("/"):
        _validate_agent_name(segment)
