"""Implicit skill invocation helpers ported from Codex core-skills.

This mirrors the standard-library behavior in
``codex-rs/core-skills/src/invocation_utils.rs``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
import shlex
from typing import Any

from pycodex.core_skills.model import SkillMetadata
from pycodex.protocol import Product

JsonValue = Any
SCRIPT_RUNNERS = frozenset({"bash", "deno", "node", "perl", "pwsh", "python", "python3", "ruby", "sh", "zsh"})
SCRIPT_EXTENSIONS = (".py", ".sh", ".js", ".ts", ".rb", ".pl", ".ps1")
FILE_READERS = frozenset({"awk", "bat", "cat", "head", "less", "more", "sed", "tail"})


@dataclass(frozen=True)
class SkillPolicy:
    allow_implicit_invocation: bool | None = None
    products: tuple[Product, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "products", tuple(_coerce_product(product) for product in self.products))


@dataclass(frozen=True)
class SkillLoadOutcome:
    skills: tuple[SkillMetadata, ...] = ()
    errors: tuple[object, ...] = ()
    disabled_paths: frozenset[Path] = frozenset()
    skill_roots: tuple[Path, ...] = ()
    skill_root_by_path: Mapping[Path, Path] = field(default_factory=dict)
    implicit_skills_by_scripts_dir: Mapping[Path, SkillMetadata] = field(default_factory=dict)
    implicit_skills_by_doc_path: Mapping[Path, SkillMetadata] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", tuple(_coerce_skill_metadata(skill) for skill in self.skills))
        object.__setattr__(self, "disabled_paths", frozenset(Path(str(path)) for path in self.disabled_paths))
        object.__setattr__(self, "skill_roots", tuple(Path(str(path)) for path in self.skill_roots))
        object.__setattr__(
            self,
            "skill_root_by_path",
            {Path(str(path)): Path(str(root)) for path, root in self.skill_root_by_path.items()},
        )
        object.__setattr__(
            self,
            "implicit_skills_by_scripts_dir",
            {
                Path(str(path)): _coerce_skill_metadata(skill)
                for path, skill in self.implicit_skills_by_scripts_dir.items()
            },
        )
        object.__setattr__(
            self,
            "implicit_skills_by_doc_path",
            {
                Path(str(path)): _coerce_skill_metadata(skill)
                for path, skill in self.implicit_skills_by_doc_path.items()
            },
        )

    def is_skill_enabled(self, skill: SkillMetadata) -> bool:
        path = _skill_path(skill)
        return path is not None and path not in self.disabled_paths

    def is_skill_allowed_for_implicit_invocation(self, skill: SkillMetadata) -> bool:
        return self.is_skill_enabled(skill) and skill_allows_implicit_invocation(skill)

    def allowed_skills_for_implicit_invocation(self) -> tuple[SkillMetadata, ...]:
        return tuple(skill for skill in self.skills if self.is_skill_allowed_for_implicit_invocation(skill))

    def skills_with_enabled(self) -> tuple[tuple[SkillMetadata, bool], ...]:
        return tuple((skill, self.is_skill_enabled(skill)) for skill in self.skills)


def skill_allows_implicit_invocation(skill: SkillMetadata) -> bool:
    policy = skill.policy
    if policy is None:
        return True
    if isinstance(policy, Mapping):
        raw = policy.get("allow_implicit_invocation", policy.get("allowImplicitInvocation"))
    else:
        raw = getattr(policy, "allow_implicit_invocation", None)
    return True if raw is None else bool(raw)


def skill_matches_product_restriction(
    skill: SkillMetadata,
    restriction_product: Product | str | None,
) -> bool:
    policy = skill.policy
    if policy is None:
        return True
    products = _policy_products(policy)
    if not products:
        return True
    if restriction_product is None:
        return False
    product = _coerce_product(restriction_product)
    return product.matches_product_restriction(products)


def filter_skill_load_outcome_for_product(
    outcome: SkillLoadOutcome,
    restriction_product: Product | str | None,
) -> SkillLoadOutcome:
    retained_skills = tuple(
        skill
        for skill in outcome.skills
        if skill_matches_product_restriction(skill, restriction_product)
    )
    retained_paths = {
        path
        for skill in retained_skills
        for path in (_skill_path(skill),)
        if path is not None
    }
    retained_skill_root_by_path = {
        path: root
        for path, root in outcome.skill_root_by_path.items()
        if path in retained_paths
    }
    retained_roots = set(retained_skill_root_by_path.values())
    return replace(
        outcome,
        skills=retained_skills,
        skill_root_by_path=retained_skill_root_by_path,
        skill_roots=tuple(root for root in outcome.skill_roots if root in retained_roots),
        implicit_skills_by_scripts_dir={
            path: skill
            for path, skill in outcome.implicit_skills_by_scripts_dir.items()
            if skill_matches_product_restriction(skill, restriction_product)
        },
        implicit_skills_by_doc_path={
            path: skill
            for path, skill in outcome.implicit_skills_by_doc_path.items()
            if skill_matches_product_restriction(skill, restriction_product)
        },
    )


def build_implicit_skill_path_indexes(
    skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
) -> tuple[dict[Path, SkillMetadata], dict[Path, SkillMetadata]]:
    by_scripts_dir: dict[Path, SkillMetadata] = {}
    by_skill_doc_path: dict[Path, SkillMetadata] = {}
    for value in skills:
        skill = _coerce_skill_metadata(value)
        skill_doc_path = _skill_path(skill)
        if skill_doc_path is None:
            continue
        normalized_doc_path = canonicalize_if_exists(skill_doc_path)
        by_skill_doc_path[normalized_doc_path] = skill
        skill_dir = skill_doc_path.parent
        scripts_dir = canonicalize_if_exists(skill_dir / "scripts")
        by_scripts_dir[scripts_dir] = skill
    return by_scripts_dir, by_skill_doc_path


def detect_implicit_skill_invocation_for_command(
    outcome: SkillLoadOutcome,
    command: str,
    workdir: Path | str,
) -> SkillMetadata | None:
    normalized_workdir = canonicalize_if_exists(Path(workdir))
    tokens = tokenize_command(command)
    candidate = detect_skill_script_run(outcome, tokens, normalized_workdir)
    if candidate is not None:
        return candidate
    return detect_skill_doc_read(outcome, tokens, normalized_workdir)


def tokenize_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def script_run_token(tokens: Iterable[str]) -> str | None:
    items = list(tokens)
    if not items:
        return None
    runner = command_basename(items[0]).lower()
    if runner.endswith(".exe"):
        runner = runner[:-4]
    if runner not in SCRIPT_RUNNERS:
        return None

    script_token = None
    for token in items[1:]:
        if token == "--" or token.startswith("-"):
            continue
        script_token = token
        break
    if script_token is None:
        return None
    if script_token.lower().endswith(SCRIPT_EXTENSIONS):
        return script_token
    return None


def detect_skill_script_run(
    outcome: SkillLoadOutcome,
    tokens: Iterable[str],
    workdir: Path | str,
) -> SkillMetadata | None:
    script_token = script_run_token(tokens)
    if script_token is None:
        return None
    script_path = canonicalize_if_exists(Path(workdir) / Path(script_token))

    for path in (script_path, *script_path.parents):
        candidate = outcome.implicit_skills_by_scripts_dir.get(path)
        if candidate is not None:
            return candidate
    return None


def detect_skill_doc_read(
    outcome: SkillLoadOutcome,
    tokens: Iterable[str],
    workdir: Path | str,
) -> SkillMetadata | None:
    items = list(tokens)
    if not command_reads_file(items):
        return None

    for token in items[1:]:
        if token.startswith("-"):
            continue
        candidate_path = canonicalize_if_exists(Path(workdir) / Path(token))
        candidate = outcome.implicit_skills_by_doc_path.get(candidate_path)
        if candidate is not None:
            return candidate
    return None


def command_reads_file(tokens: Iterable[str]) -> bool:
    items = list(tokens)
    if not items:
        return False
    return command_basename(items[0]).lower() in FILE_READERS


def command_basename(command: str) -> str:
    return Path(command).name or command


def canonicalize_if_exists(path: Path | str) -> Path:
    value = Path(path)
    if not value.exists():
        return value
    return value.resolve()


def skill_load_outcome_with_implicit_indexes(outcome: SkillLoadOutcome) -> SkillLoadOutcome:
    by_scripts_dir, by_doc_path = build_implicit_skill_path_indexes(outcome.allowed_skills_for_implicit_invocation())
    return replace(
        outcome,
        implicit_skills_by_scripts_dir=by_scripts_dir,
        implicit_skills_by_doc_path=by_doc_path,
    )


def _coerce_skill_metadata(value: SkillMetadata | Mapping[str, JsonValue] | Any) -> SkillMetadata:
    if isinstance(value, SkillMetadata):
        return value
    if isinstance(value, Mapping):
        path = value.get("path_to_skills_md", value.get("path"))
        return SkillMetadata(
            name=str(value["name"]),
            dependencies=value.get("dependencies"),
            description=str(value.get("description", "")),
            short_description=_optional_str(value.get("short_description", value.get("shortDescription"))),
            interface=value.get("interface"),
            policy=_coerce_skill_policy(value.get("policy")),
            path_to_skills_md=None if path is None else Path(str(path)),
            scope=str(value.get("scope", "user")),
            plugin_id=_optional_str(value.get("plugin_id", value.get("pluginId"))),
        )
    path = _field_value(value, "path_to_skills_md", _field_value(value, "path"))
    return SkillMetadata(
        name=str(_field_value(value, "name")),
        dependencies=_field_value(value, "dependencies"),
        description=str(_field_value(value, "description", "")),
        short_description=_optional_str(_field_value(value, "short_description")),
        interface=_field_value(value, "interface"),
        policy=_coerce_skill_policy(_field_value(value, "policy")),
        path_to_skills_md=None if path is None else Path(str(path)),
        scope=str(_field_value(value, "scope", "user")),
        plugin_id=_optional_str(_field_value(value, "plugin_id")),
    )


def _skill_path(skill: SkillMetadata) -> Path | None:
    if skill.path_to_skills_md is None:
        return None
    return Path(str(skill.path_to_skills_md))


def _coerce_skill_policy(value: Any) -> SkillPolicy | Any | None:
    if value is None or isinstance(value, SkillPolicy):
        return value
    if isinstance(value, Mapping):
        return SkillPolicy(
            allow_implicit_invocation=value.get("allow_implicit_invocation", value.get("allowImplicitInvocation")),
            products=tuple(_coerce_product(product) for product in value.get("products", ())),
        )
    return value


def _policy_products(policy: SkillPolicy | Mapping[str, JsonValue] | Any) -> tuple[Product, ...]:
    if isinstance(policy, SkillPolicy):
        return policy.products
    if isinstance(policy, Mapping):
        raw_products = policy.get("products", ())
    else:
        raw_products = getattr(policy, "products", ())
    return tuple(_coerce_product(product) for product in raw_products)


def _coerce_product(value: Product | str | Any) -> Product:
    if isinstance(value, Product):
        return value
    return Product.parse(str(value))


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "FILE_READERS",
    "SCRIPT_EXTENSIONS",
    "SCRIPT_RUNNERS",
    "SkillPolicy",
    "SkillLoadOutcome",
    "build_implicit_skill_path_indexes",
    "canonicalize_if_exists",
    "command_basename",
    "command_reads_file",
    "detect_implicit_skill_invocation_for_command",
    "detect_skill_doc_read",
    "detect_skill_script_run",
    "filter_skill_load_outcome_for_product",
    "script_run_token",
    "skill_allows_implicit_invocation",
    "skill_matches_product_restriction",
    "skill_load_outcome_with_implicit_indexes",
    "tokenize_command",
]
