from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pycodex.protocol import TurnContextItem


@dataclass(frozen=True)
class EnvironmentContextEnvironment:
    id: str
    cwd: Path
    shell: str

    @classmethod
    def legacy(cls, cwd: Path | str, shell: str) -> "EnvironmentContextEnvironment":
        return cls(id="", cwd=Path(cwd), shell=shell)


@dataclass(frozen=True)
class EnvironmentContextEnvironments:
    kind: str
    single: EnvironmentContextEnvironment | None = None
    multiple: tuple[EnvironmentContextEnvironment, ...] = ()

    @classmethod
    def none(cls) -> "EnvironmentContextEnvironments":
        return cls("none")

    @classmethod
    def from_iterable(cls, environments: Iterable[EnvironmentContextEnvironment]) -> "EnvironmentContextEnvironments":
        items = tuple(environments)
        if not items:
            return cls.none()
        if len(items) == 1:
            return cls("single", single=items[0])
        return cls("multiple", multiple=items)

    def equals_except_shell(self, other: "EnvironmentContextEnvironments") -> bool:
        if self.kind != other.kind:
            return False
        if self.kind == "none":
            return True
        if self.kind == "single":
            return self.single is not None and other.single is not None and self.single.cwd == other.single.cwd
        return len(self.multiple) == len(other.multiple) and all(
            left.id == right.id and left.cwd == right.cwd
            for left, right in zip(self.multiple, other.multiple)
        )


@dataclass(frozen=True)
class NetworkContext:
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_domains, tuple):
            object.__setattr__(self, "allowed_domains", tuple(self.allowed_domains))
        if not isinstance(self.denied_domains, tuple):
            object.__setattr__(self, "denied_domains", tuple(self.denied_domains))

    def render(self) -> str:
        rendered = '<network enabled="true">'
        rendered += self._render_domain_element("allowed", self.allowed_domains)
        rendered += self._render_domain_element("denied", self.denied_domains)
        return f"{rendered}</network>"

    @staticmethod
    def _render_domain_element(name: str, domains: tuple[str, ...]) -> str:
        if not domains:
            return ""
        return f"<{name}>{','.join(domains)}</{name}>"


def network_from_turn_context_item(turn_context_item: TurnContextItem) -> NetworkContext | None:
    if turn_context_item.network is None:
        return None
    return NetworkContext(
        allowed_domains=tuple(turn_context_item.network.allowed_domains),
        denied_domains=tuple(turn_context_item.network.denied_domains),
    )


__all__ = [
    "EnvironmentContextEnvironment",
    "EnvironmentContextEnvironments",
    "NetworkContext",
    "network_from_turn_context_item",
]
