"""Contextual user fragments ported from ``codex/codex-rs/core/src/context``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from pycodex.protocol import (
    AgentStatus,
    APPS_INSTRUCTIONS_CLOSE_TAG,
    APPS_INSTRUCTIONS_OPEN_TAG,
    COLLABORATION_MODE_CLOSE_TAG,
    COLLABORATION_MODE_OPEN_TAG,
    ENVIRONMENT_CONTEXT_CLOSE_TAG,
    ENVIRONMENT_CONTEXT_OPEN_TAG,
    ContentItem,
    HookPromptItem,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    PLUGINS_INSTRUCTIONS_CLOSE_TAG,
    PLUGINS_INSTRUCTIONS_OPEN_TAG,
    REALTIME_CONVERSATION_CLOSE_TAG,
    REALTIME_CONVERSATION_OPEN_TAG,
    ResponseInputItem,
    ResponseItem,
    SKILLS_INSTRUCTIONS_CLOSE_TAG,
    SKILLS_INSTRUCTIONS_OPEN_TAG,
    CollaborationMode,
    TurnContextItem,
    parse_hook_prompt_fragment,
)

CODEX_APPS_MCP_SERVER_NAME = "codex_apps"

REALTIME_START_INSTRUCTIONS = """Realtime conversation started.

You are operating as a backend executor behind an intermediary. The user does not talk to you directly. Any response you produce will be consumed by the intermediary and may be summarized before the user sees it.

When invoked, you receive the latest conversation transcript and any relevant mode or metadata. The intermediary may invoke you even when backend help is not actually needed. Use the transcript to decide whether you should do work. If backend help is unnecessary, avoid verbose responses that add user-visible latency.

When user text is routed from realtime, treat it as a transcript. It may be unpunctuated or contain recognition errors.

- Keep responses concise and action-oriented. Your updates should help the intermediary respond to the user."""
REALTIME_END_INSTRUCTIONS = """Realtime conversation ended.

Subsequent user input will return to typed text rather than transcript-style text. Do not assume recognition errors or missing punctuation once realtime has ended. Resume normal chat behavior."""

SKILLS_INTRO_WITH_ABSOLUTE_PATHS = "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill."
SKILLS_INTRO_WITH_ALIASES = "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and a short path that can be expanded into an absolute path using the skill roots table."
SKILLS_HOW_TO_USE_WITH_ABSOLUTE_PATHS = """- Discovery: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the skill directory listed above first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue."""
SKILLS_HOW_TO_USE_WITH_ALIASES = """- Discovery: The list above is the skills available in this session (name + description + short path). Skill bodies live on disk at the listed paths after expanding the matching alias from `### Skill roots`.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, expand the listed short `path` with the matching alias from `### Skill roots`, then open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the directory containing that expanded `SKILL.md` first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue."""


class ContextualUserFragment(Protocol):
    @classmethod
    def role(cls) -> str: ...

    def markers(self) -> tuple[str, str]: ...

    @classmethod
    def type_markers(cls) -> tuple[str, str]: ...

    @classmethod
    def matches_text(cls, text: str) -> bool: ...

    def body(self) -> str: ...

    def render(self) -> str: ...

    def into_response_input_item(self) -> ResponseInputItem: ...

    def into_response_item(self) -> ResponseItem: ...


def matches_marked_text(start_marker: str, end_marker: str, text: str) -> bool:
    if not start_marker or not end_marker:
        return False
    leading_trimmed = text.lstrip()
    trailing_trimmed = leading_trimmed.rstrip()
    return leading_trimmed[: len(start_marker)].lower() == start_marker.lower() and trailing_trimmed[
        len(trailing_trimmed) - len(end_marker) :
    ].lower() == end_marker.lower()


@dataclass(frozen=True)
class ContextualUserFragmentBase:
    @classmethod
    def role(cls) -> str:
        return "user"

    def markers(self) -> tuple[str, str]:
        return self.type_markers()

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "", ""

    @classmethod
    def matches_text(cls, text: str) -> bool:
        start_marker, end_marker = cls.type_markers()
        return matches_marked_text(start_marker, end_marker, text)

    def body(self) -> str:
        return ""

    def render(self) -> str:
        start_marker, end_marker = self.markers()
        body = self.body()
        if not start_marker and not end_marker:
            return body
        return f"{start_marker}{body}{end_marker}"

    def into_response_input_item(self) -> ResponseInputItem:
        return ResponseInputItem.message(self.role(), (ContentItem.input_text(self.render()),))

    def into_response_item(self) -> ResponseItem:
        return ResponseItem.message(self.role(), (ContentItem.input_text(self.render()),))


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


@dataclass(frozen=True)
class EnvironmentContext(ContextualUserFragmentBase):
    environments: EnvironmentContextEnvironments = field(default_factory=EnvironmentContextEnvironments.none)
    current_date: str | None = None
    timezone: str | None = None
    network: NetworkContext | None = None
    subagents: str | None = None

    @classmethod
    def new(
        cls,
        environments: Iterable[EnvironmentContextEnvironment],
        current_date: str | None = None,
        timezone: str | None = None,
        network: NetworkContext | None = None,
        subagents: str | None = None,
    ) -> "EnvironmentContext":
        return cls(
            environments=EnvironmentContextEnvironments.from_iterable(environments),
            current_date=current_date,
            timezone=timezone,
            network=network,
            subagents=subagents or None,
        )

    @classmethod
    def from_turn_context_item(cls, turn_context_item: TurnContextItem, shell: str) -> "EnvironmentContext":
        return cls.new(
            (EnvironmentContextEnvironment.legacy(turn_context_item.cwd, shell),),
            current_date=turn_context_item.current_date,
            timezone=turn_context_item.timezone,
            network=network_from_turn_context_item(turn_context_item),
        )

    @classmethod
    def diff_from_turn_context_item(
        cls,
        before: TurnContextItem,
        after: "EnvironmentContext",
    ) -> "EnvironmentContext":
        before_network = network_from_turn_context_item(before)
        if after.environments.kind == "single" and after.environments.single is not None:
            environment = after.environments.single
            if before.cwd != environment.cwd:
                environments = EnvironmentContextEnvironments.from_iterable(
                    (EnvironmentContextEnvironment.legacy(environment.cwd, environment.shell),)
                )
            else:
                environments = EnvironmentContextEnvironments.none()
        elif after.environments.kind == "multiple":
            environments = after.environments
        else:
            environments = EnvironmentContextEnvironments.none()

        network = after.network if before_network != after.network else before_network
        return cls(
            environments=environments,
            current_date=after.current_date,
            timezone=after.timezone,
            network=network,
            subagents=None,
        )

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return ENVIRONMENT_CONTEXT_OPEN_TAG, ENVIRONMENT_CONTEXT_CLOSE_TAG

    def equals_except_shell(self, other: "EnvironmentContext") -> bool:
        return (
            self.environments.equals_except_shell(other.environments)
            and self.current_date == other.current_date
            and self.timezone == other.timezone
            and self.network == other.network
            and self.subagents == other.subagents
        )

    def with_subagents(self, subagents: str) -> "EnvironmentContext":
        return EnvironmentContext(
            environments=self.environments,
            current_date=self.current_date,
            timezone=self.timezone,
            network=self.network,
            subagents=subagents or self.subagents,
        )

    def body(self) -> str:
        lines: list[str] = []
        if self.environments.kind == "single" and self.environments.single is not None:
            environment = self.environments.single
            lines.append(f"  <cwd>{environment.cwd}</cwd>")
            lines.append(f"  <shell>{environment.shell}</shell>")
        elif self.environments.kind == "multiple":
            lines.append("  <environments>")
            for environment in self.environments.multiple:
                lines.append(f'    <environment id="{environment.id}">')
                lines.append(f"      <cwd>{environment.cwd}</cwd>")
                lines.append(f"      <shell>{environment.shell}</shell>")
                lines.append("    </environment>")
            lines.append("  </environments>")

        if self.current_date is not None:
            lines.append(f"  <current_date>{self.current_date}</current_date>")
        if self.timezone is not None:
            lines.append(f"  <timezone>{self.timezone}</timezone>")
        if self.network is not None:
            lines.append(f"  {self.network.render()}")
        if self.subagents is not None:
            lines.append("  <subagents>")
            lines.extend(f"    {line}" for line in self.subagents.splitlines())
            lines.append("  </subagents>")
        joined = "\n".join(lines)
        return f"\n{joined}\n"


def network_from_turn_context_item(turn_context_item: TurnContextItem) -> NetworkContext | None:
    if turn_context_item.network is None:
        return None
    return NetworkContext(
        allowed_domains=tuple(turn_context_item.network.allowed_domains),
        denied_domains=tuple(turn_context_item.network.denied_domains),
    )


@dataclass(frozen=True)
class UserInstructions(ContextualUserFragmentBase):
    directory: str
    text: str

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "# AGENTS.md instructions for ", "</INSTRUCTIONS>"

    def body(self) -> str:
        return f"{self.directory}\n\n<INSTRUCTIONS>\n{self.text}\n"


@dataclass(frozen=True)
class SkillInstructions(ContextualUserFragmentBase):
    name: str
    path: str
    contents: str

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<skill>", "</skill>"

    def body(self) -> str:
        return f"\n<name>{self.name}</name>\n<path>{self.path}</path>\n{self.contents}\n"


@dataclass(frozen=True)
class UserShellCommand(ContextualUserFragmentBase):
    command: str
    exit_code: int
    duration_seconds: float
    output: str

    @classmethod
    def new(
        cls,
        command: str,
        exit_code: int,
        duration: timedelta,
        output: str,
    ) -> "UserShellCommand":
        return cls(command, exit_code, duration.total_seconds(), output)

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<user_shell_command>", "</user_shell_command>"

    def body(self) -> str:
        return (
            f"\n<command>\n{self.command}\n</command>\n<result>\n"
            f"Exit code: {self.exit_code}\nDuration: {self.duration_seconds:.4f} seconds\n"
            f"Output:\n{self.output}\n</result>\n"
        )


@dataclass(frozen=True)
class TurnAborted(ContextualUserFragmentBase):
    guidance: str

    INTERRUPTED_GUIDANCE = (
        "The user interrupted the previous turn on purpose. Any running unified exec processes may still be "
        "running in the background. If any tools/commands were aborted, they may have partially executed."
    )
    INTERRUPTED_DEVELOPER_GUIDANCE = (
        "The previous turn was interrupted on purpose. Any running unified exec processes may still be "
        "running in the background. If any tools/commands were aborted, they may have partially executed."
    )

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<turn_aborted>", "</turn_aborted>"

    def body(self) -> str:
        return f"\n{self.guidance}\n"


@dataclass(frozen=True)
class SubagentNotification(ContextualUserFragmentBase):
    agent_reference: str
    status: AgentStatus

    @classmethod
    def new(cls, agent_reference: str, status: AgentStatus) -> "SubagentNotification":
        return cls(agent_reference, status)

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<subagent_notification>", "</subagent_notification>"

    def body(self) -> str:
        status_value = self.status.to_mapping()
        payload = {"agent_path": self.agent_reference, "status": status_value}
        return f"\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n"


@dataclass(frozen=True)
class GoalContext(ContextualUserFragmentBase):
    prompt: str

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<goal_context>", "</goal_context>"

    def body(self) -> str:
        return f"\n{self.prompt}\n"


@dataclass(frozen=True)
class ApprovedCommandPrefixSaved(ContextualUserFragmentBase):
    prefixes: str

    @classmethod
    def new(cls, prefixes: str) -> "ApprovedCommandPrefixSaved":
        return cls(prefixes)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return f"Approved command prefix saved:\n{self.prefixes}"


@dataclass(frozen=True)
class NetworkRuleSaved(ContextualUserFragmentBase):
    action: NetworkPolicyRuleAction
    host: str

    def __post_init__(self) -> None:
        if not isinstance(self.action, NetworkPolicyRuleAction):
            object.__setattr__(self, "action", NetworkPolicyRuleAction(str(self.action)))

    @classmethod
    def new(cls, amendment: NetworkPolicyAmendment) -> "NetworkRuleSaved":
        return cls(amendment.action, amendment.host)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        action, list_name = (
            ("Allowed", "allowlist") if self.action is NetworkPolicyRuleAction.ALLOW else ("Denied", "denylist")
        )
        return f"{action} network rule saved in execpolicy ({list_name}): {self.host}"


class GuardianFollowupReviewReminder(ContextualUserFragmentBase):
    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return (
            "Use prior reviews as context, not binding precedent. "
            "Follow the Workspace Policy. "
            "If the user explicitly approves a previously rejected action after being informed of the "
            'concrete risks, set outcome to "allow" unless the policy explicitly disallows user '
            "overwrites in such cases."
        )


@dataclass(frozen=True)
class HookAdditionalContext(ContextualUserFragmentBase):
    text: str

    @classmethod
    def new(cls, text: str) -> "HookAdditionalContext":
        return cls(text)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return self.text


@dataclass(frozen=True)
class AppsInstructions(ContextualUserFragmentBase):
    @classmethod
    def from_connectors(cls, connectors: Iterable[Any]) -> "AppsInstructions | None":
        for connector in connectors:
            if bool(_field_value(connector, "is_accessible", False)) and bool(
                _field_value(connector, "is_enabled", False)
            ):
                return cls()
        return None

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return APPS_INSTRUCTIONS_OPEN_TAG, APPS_INSTRUCTIONS_CLOSE_TAG

    def body(self) -> str:
        return (
            "\n## Apps (Connectors)\n"
            "Apps (Connectors) can be explicitly triggered in user messages in the format "
            "`[$app-name](app://{connector_id})`. Apps can also be implicitly triggered as long as the context suggests usage of available apps.\n"
            f"An app is equivalent to a set of MCP tools within the `{CODEX_APPS_MCP_SERVER_NAME}` MCP.\n"
            "An installed app's MCP tools are either provided to you already, or can be lazy-loaded through the `tool_search` tool. If `tool_search` is available, the apps that are searchable by `tools_search` will be listed by it.\n"
            "Do not additionally call list_mcp_resources or list_mcp_resource_templates for apps.\n"
        )


@dataclass(frozen=True)
class PluginCapabilitySummary:
    config_name: str
    display_name: str
    description: str | None = None
    has_skills: bool = False
    mcp_server_names: tuple[str, ...] = ()
    app_connector_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_name", str(self.config_name))
        object.__setattr__(self, "display_name", str(self.display_name))
        if self.description is not None:
            object.__setattr__(self, "description", str(self.description))
        if not isinstance(self.mcp_server_names, tuple):
            object.__setattr__(self, "mcp_server_names", tuple(str(item) for item in self.mcp_server_names))
        if not isinstance(self.app_connector_ids, tuple):
            object.__setattr__(self, "app_connector_ids", tuple(str(item) for item in self.app_connector_ids))

    @classmethod
    def from_value(cls, value: "PluginCapabilitySummary | Mapping[str, Any] | Any") -> "PluginCapabilitySummary":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            display_name = value.get("display_name", value.get("displayName", value.get("config_name", "")))
            return cls(
                config_name=str(value.get("config_name", value.get("configName", display_name))),
                display_name=str(display_name),
                description=None if value.get("description") is None else str(value.get("description")),
                has_skills=bool(value.get("has_skills", value.get("hasSkills", False))),
                mcp_server_names=tuple(str(item) for item in value.get("mcp_server_names", value.get("mcpServerNames", ()))),
                app_connector_ids=tuple(str(item) for item in value.get("app_connector_ids", value.get("appConnectorIds", ()))),
            )
        display_name = str(_field_value(value, "display_name", _field_value(value, "config_name", "")))
        return cls(
            config_name=str(_field_value(value, "config_name", display_name)),
            display_name=display_name,
            description=_optional_str(_field_value(value, "description", None)),
            has_skills=bool(_field_value(value, "has_skills", False)),
            mcp_server_names=tuple(str(item) for item in _field_value(value, "mcp_server_names", ())),
            app_connector_ids=tuple(str(item) for item in _field_value(value, "app_connector_ids", ())),
        )


@dataclass(frozen=True)
class AvailablePluginsInstructions(ContextualUserFragmentBase):
    plugins: tuple[PluginCapabilitySummary, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plugins, tuple):
            object.__setattr__(self, "plugins", tuple(PluginCapabilitySummary.from_value(item) for item in self.plugins))

    @classmethod
    def from_plugins(cls, plugins: Iterable[PluginCapabilitySummary | Mapping[str, Any] | Any]) -> "AvailablePluginsInstructions | None":
        items = tuple(PluginCapabilitySummary.from_value(plugin) for plugin in plugins)
        return cls(items) if items else None

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return PLUGINS_INSTRUCTIONS_OPEN_TAG, PLUGINS_INSTRUCTIONS_CLOSE_TAG

    def body(self) -> str:
        lines = [
            "## Plugins",
            "A plugin is a local bundle of skills, MCP servers, and apps. Below is the list of plugins that are enabled and available in this session.",
            "### Available plugins",
        ]
        for plugin in self.plugins:
            if plugin.description is None:
                lines.append(f"- `{plugin.display_name}`")
            else:
                lines.append(f"- `{plugin.display_name}`: {plugin.description}")
        lines.append("### How to use plugins")
        lines.append(
            "- Discovery: The list above is the plugins available in this session.\n"
            "- Skill naming: If a plugin contributes skills, those skill entries are prefixed with `plugin_name:` in the Skills list.\n"
            "- Trigger rules: If the user explicitly names a plugin, prefer capabilities associated with that plugin for that turn.\n"
            "- Relationship to capabilities: Plugins are not invoked directly. Use their underlying skills, MCP tools, and app tools to help solve the task.\n"
            "- Preference: When a relevant plugin is available, prefer using capabilities associated with that plugin over standalone capabilities that provide similar functionality.\n"
            "- Missing/blocked: If the user requests a plugin that is not listed above, or the plugin does not have relevant callable capabilities for the task, say so briefly and continue with the best fallback."
        )
        joined = "\n".join(lines)
        return f"\n{joined}\n"


@dataclass(frozen=True)
class AvailableSkillsInstructions(ContextualUserFragmentBase):
    skill_root_lines: tuple[str, ...] = ()
    skill_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.skill_root_lines, tuple):
            object.__setattr__(self, "skill_root_lines", tuple(str(line) for line in self.skill_root_lines))
        if not isinstance(self.skill_lines, tuple):
            object.__setattr__(self, "skill_lines", tuple(str(line) for line in self.skill_lines))

    @classmethod
    def from_available_skills(cls, available_skills: Any) -> "AvailableSkillsInstructions":
        return cls(
            tuple(str(line) for line in _field_value(available_skills, "skill_root_lines", ())),
            tuple(str(line) for line in _field_value(available_skills, "skill_lines", ())),
        )

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return SKILLS_INSTRUCTIONS_OPEN_TAG, SKILLS_INSTRUCTIONS_CLOSE_TAG

    def body(self) -> str:
        return render_available_skills_body(self.skill_root_lines, self.skill_lines)


@dataclass(frozen=True)
class CollaborationModeInstructions(ContextualUserFragmentBase):
    instructions: str

    @classmethod
    def from_collaboration_mode(cls, collaboration_mode: CollaborationMode | Any) -> "CollaborationModeInstructions | None":
        settings = _field_value(collaboration_mode, "settings", None)
        instructions = _field_value(settings, "developer_instructions", None)
        if not instructions:
            return None
        return cls(str(instructions))

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return COLLABORATION_MODE_OPEN_TAG, COLLABORATION_MODE_CLOSE_TAG

    def body(self) -> str:
        return self.instructions


@dataclass(frozen=True)
class ImageGenerationInstructions(ContextualUserFragmentBase):
    image_output_dir: str
    image_output_path: str

    @classmethod
    def new(cls, image_output_dir: object, image_output_path: object) -> "ImageGenerationInstructions":
        return cls(str(image_output_dir), str(image_output_path))

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return (
            f"Generated images are saved to {self.image_output_dir} as {self.image_output_path} by default.\n"
            "If you need to use a generated image at another path, copy it and leave the original in place unless the user explicitly asks you to delete it."
        )


@dataclass(frozen=True)
class ModelSwitchInstructions(ContextualUserFragmentBase):
    model_instructions: str

    @classmethod
    def new(cls, model_instructions: str) -> "ModelSwitchInstructions":
        return cls(model_instructions)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<model_switch>", "</model_switch>"

    def body(self) -> str:
        return (
            "\nThe user was previously using a different model. Please continue the conversation according to the following instructions:\n\n"
            f"{self.model_instructions}\n"
        )


@dataclass(frozen=True)
class PersonalitySpecInstructions(ContextualUserFragmentBase):
    spec: str

    @classmethod
    def new(cls, spec: str) -> "PersonalitySpecInstructions":
        return cls(spec)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<personality_spec>", "</personality_spec>"

    def body(self) -> str:
        return f" The user has requested a new communication style. Future messages should adhere to the following personality: \n{self.spec} "


@dataclass(frozen=True)
class PluginInstructions(ContextualUserFragmentBase):
    text: str

    @classmethod
    def new(cls, text: str) -> "PluginInstructions":
        return cls(text)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return self.text


class RealtimeStartInstructions(ContextualUserFragmentBase):
    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return REALTIME_CONVERSATION_OPEN_TAG, REALTIME_CONVERSATION_CLOSE_TAG

    def body(self) -> str:
        return f"\n{REALTIME_START_INSTRUCTIONS.strip()}\n"


@dataclass(frozen=True)
class RealtimeEndInstructions(ContextualUserFragmentBase):
    reason: str

    @classmethod
    def new(cls, reason: str) -> "RealtimeEndInstructions":
        return cls(reason)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return REALTIME_CONVERSATION_OPEN_TAG, REALTIME_CONVERSATION_CLOSE_TAG

    def body(self) -> str:
        return f"\n{REALTIME_END_INSTRUCTIONS.strip()}\n\nReason: {self.reason}\n"


@dataclass(frozen=True)
class RealtimeStartWithInstructions(ContextualUserFragmentBase):
    instructions: str

    @classmethod
    def new(cls, instructions: str) -> "RealtimeStartWithInstructions":
        return cls(instructions)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return REALTIME_CONVERSATION_OPEN_TAG, REALTIME_CONVERSATION_CLOSE_TAG

    def body(self) -> str:
        return f"\n{self.instructions}\n"


def render_available_skills_body(skill_root_lines: Iterable[str], skill_lines: Iterable[str]) -> str:
    roots = tuple(str(line) for line in skill_root_lines)
    skills = tuple(str(line) for line in skill_lines)
    lines = ["## Skills"]
    if not roots:
        lines.append(SKILLS_INTRO_WITH_ABSOLUTE_PATHS)
    else:
        lines.append(SKILLS_INTRO_WITH_ALIASES)
        lines.append("### Skill roots")
        lines.extend(roots)
    lines.append("### Available skills")
    lines.extend(skills)
    lines.append("### How to use skills")
    lines.append(SKILLS_HOW_TO_USE_WITH_ALIASES if roots else SKILLS_HOW_TO_USE_WITH_ABSOLUTE_PATHS)
    joined = "\n".join(lines)
    return f"\n{joined}\n"


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


class LegacyUnifiedExecProcessLimitWarning(ContextualUserFragmentBase):
    @classmethod
    def matches_text(cls, text: str) -> bool:
        return text.strip().startswith("Warning: The maximum number of unified exec processes you can keep open is")


class LegacyApplyPatchExecCommandWarning(ContextualUserFragmentBase):
    @classmethod
    def matches_text(cls, text: str) -> bool:
        trimmed = text.strip()
        return trimmed.startswith("Warning: apply_patch was requested via ") and trimmed.endswith(
            "Use the apply_patch tool instead of exec_command."
        )


class LegacyModelMismatchWarning(ContextualUserFragmentBase):
    @classmethod
    def matches_text(cls, text: str) -> bool:
        return text.strip().startswith("Warning: Your account was flagged for potentially high-risk cyber activity")


CONTEXTUAL_USER_FRAGMENT_TYPES = (
    UserInstructions,
    EnvironmentContext,
    SkillInstructions,
    UserShellCommand,
    TurnAborted,
    SubagentNotification,
    GoalContext,
    LegacyUnifiedExecProcessLimitWarning,
    LegacyApplyPatchExecCommandWarning,
    LegacyModelMismatchWarning,
)
STANDARD_CONTEXTUAL_USER_FRAGMENT_TYPES = CONTEXTUAL_USER_FRAGMENT_TYPES


def is_standard_contextual_user_text(text: str) -> bool:
    return any(fragment_type.matches_text(text) for fragment_type in CONTEXTUAL_USER_FRAGMENT_TYPES)


def is_contextual_user_fragment(content_item: ContentItem) -> bool:
    if not isinstance(content_item, ContentItem) or content_item.type != "input_text":
        return False
    text = content_item.text or ""
    return parse_hook_prompt_fragment(text) is not None or is_standard_contextual_user_text(text)


def parse_visible_hook_prompt_message(id: str | None, content: Iterable[ContentItem]) -> HookPromptItem | None:
    fragments = []
    for content_item in content:
        if not isinstance(content_item, ContentItem) or content_item.type != "input_text":
            return None
        text = content_item.text or ""
        fragment = parse_hook_prompt_fragment(text)
        if fragment is not None:
            fragments.append(fragment)
            continue
        if is_standard_contextual_user_text(text):
            continue
        return None
    if not fragments:
        return None
    return HookPromptItem.from_fragments(id, tuple(fragments))


__all__ = [
    "CONTEXTUAL_USER_FRAGMENT_TYPES",
    "ContextualUserFragment",
    "ContextualUserFragmentBase",
    "EnvironmentContext",
    "EnvironmentContextEnvironment",
    "EnvironmentContextEnvironments",
    "GoalContext",
    "ApprovedCommandPrefixSaved",
    "AppsInstructions",
    "AvailablePluginsInstructions",
    "AvailableSkillsInstructions",
    "CollaborationModeInstructions",
    "GuardianFollowupReviewReminder",
    "HookAdditionalContext",
    "ImageGenerationInstructions",
    "LegacyApplyPatchExecCommandWarning",
    "LegacyModelMismatchWarning",
    "LegacyUnifiedExecProcessLimitWarning",
    "ModelSwitchInstructions",
    "NetworkContext",
    "NetworkRuleSaved",
    "PersonalitySpecInstructions",
    "PluginCapabilitySummary",
    "PluginInstructions",
    "RealtimeEndInstructions",
    "RealtimeStartInstructions",
    "RealtimeStartWithInstructions",
    "SkillInstructions",
    "STANDARD_CONTEXTUAL_USER_FRAGMENT_TYPES",
    "SubagentNotification",
    "TurnAborted",
    "UserInstructions",
    "UserShellCommand",
    "is_contextual_user_fragment",
    "is_standard_contextual_user_text",
    "matches_marked_text",
    "network_from_turn_context_item",
    "parse_visible_hook_prompt_message",
    "render_available_skills_body",
]
