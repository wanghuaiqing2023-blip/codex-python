"""Contextual user fragments ported from ``codex/codex-rs/core/src/context``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from pycodex.protocol import (
    ENVIRONMENT_CONTEXT_CLOSE_TAG,
    ENVIRONMENT_CONTEXT_OPEN_TAG,
    ContentItem,
    HookPromptItem,
    REALTIME_CONVERSATION_CLOSE_TAG,
    REALTIME_CONVERSATION_OPEN_TAG,
    TurnContextItem,
    parse_hook_prompt_fragment,
)
from pycodex.utils.string import truncate_middle_with_token_budget

from .fragment import (
    ContextualUserFragment,
    ContextualUserFragmentBase,
    FragmentRegistration,
    FragmentRegistrationProxy,
    matches_marked_text,
)
from .environment_context import (
    EnvironmentContextEnvironment,
    EnvironmentContextEnvironments,
    NetworkContext,
    network_from_turn_context_item,
)
from .fragments import (
    ADDITIONAL_CONTEXT_END_MARKER_SUFFIX,
    ADDITIONAL_CONTEXT_START_MARKER_PREFIX,
    MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS,
)
from .realtime_end_instructions import REALTIME_END_INSTRUCTIONS
from .realtime_start_instructions import REALTIME_START_INSTRUCTIONS
from .approved_command_prefix_saved import ApprovedCommandPrefixSaved
from .apps_instructions import AppsInstructions
from .available_plugins_instructions import AvailablePluginsInstructions
from .available_skills_instructions import AvailableSkillsInstructions
from .collaboration_mode_instructions import CollaborationModeInstructions
from .guardian_followup_review_reminder import GuardianFollowupReviewReminder
from .hook_additional_context import HookAdditionalContext
from .image_generation_instructions import ImageGenerationInstructions
from .legacy_apply_patch_exec_command_warning import LegacyApplyPatchExecCommandWarning
from .legacy_model_mismatch_warning import LegacyModelMismatchWarning
from .legacy_unified_exec_process_limit_warning import LegacyUnifiedExecProcessLimitWarning
from .model_switch_instructions import ModelSwitchInstructions
from .network_rule_saved import NetworkRuleSaved
from .personality_spec_instructions import PersonalitySpecInstructions
from .plugin_instructions import PluginInstructions
from .realtime_start_with_instructions import RealtimeStartWithInstructions
from .skill_instructions import SkillInstructions
from .subagent_notification import SubagentNotification
from .turn_aborted import TurnAborted
from .user_instructions import UserInstructions
from .user_shell_command import UserShellCommand


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


@dataclass(frozen=True)
class GoalContext(ContextualUserFragmentBase):
    prompt: str

    @classmethod
    def new(cls, prompt: str) -> "GoalContext":
        return cls(prompt)

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<goal_context>", "</goal_context>"

    def body(self) -> str:
        return f"\n{self.prompt}\n"


@dataclass(frozen=True)
class AdditionalContextUserFragment(ContextualUserFragmentBase):
    key: str
    value: str

    @classmethod
    def new(cls, key: str, value: str) -> "AdditionalContextUserFragment":
        return cls(key, value)

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return ADDITIONAL_CONTEXT_START_MARKER_PREFIX, ADDITIONAL_CONTEXT_END_MARKER_SUFFIX

    @classmethod
    def matches_text(cls, text: str) -> bool:
        trimmed = text.strip()
        if not trimmed.startswith(ADDITIONAL_CONTEXT_START_MARKER_PREFIX):
            return False
        rest = trimmed[len(ADDITIONAL_CONTEXT_START_MARKER_PREFIX) :]
        key, separator, value_and_close = rest.partition(ADDITIONAL_CONTEXT_END_MARKER_SUFFIX)
        if not separator:
            return False
        return value_and_close.endswith(f"</external_{key}>")

    def body(self) -> str:
        value = truncate_middle_with_token_budget(self.value, MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS)[0]
        return f"{self.key}>{value}</external_{self.key}"


@dataclass(frozen=True)
class AdditionalContextDeveloperFragment(ContextualUserFragmentBase):
    key: str
    value: str

    @classmethod
    def new(cls, key: str, value: str) -> "AdditionalContextDeveloperFragment":
        return cls(key, value)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        value = truncate_middle_with_token_budget(self.value, MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS)[0]
        return f"<{self.key}>{value}</{self.key}>"


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


CONTEXTUAL_USER_FRAGMENT_TYPES = (
    UserInstructions,
    EnvironmentContext,
    AdditionalContextUserFragment,
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
from .contextual_user_message import (
    CONTEXTUAL_USER_FRAGMENTS,
    STANDARD_CONTEXTUAL_USER_FRAGMENTS,
    is_standard_contextual_user_text,
)


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


from .permissions_instructions import PermissionsInstructions


__all__ = [
    "CONTEXTUAL_USER_FRAGMENT_TYPES",
    "CONTEXTUAL_USER_FRAGMENTS",
    "ADDITIONAL_CONTEXT_END_MARKER_SUFFIX",
    "ADDITIONAL_CONTEXT_START_MARKER_PREFIX",
    "MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS",
    "AdditionalContextDeveloperFragment",
    "AdditionalContextUserFragment",
    "ContextualUserFragment",
    "ContextualUserFragmentBase",
    "FragmentRegistration",
    "FragmentRegistrationProxy",
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
    "PermissionsInstructions",
    "PluginInstructions",
    "RealtimeEndInstructions",
    "RealtimeStartInstructions",
    "RealtimeStartWithInstructions",
    "SkillInstructions",
    "STANDARD_CONTEXTUAL_USER_FRAGMENT_TYPES",
    "STANDARD_CONTEXTUAL_USER_FRAGMENTS",
    "SubagentNotification",
    "TurnAborted",
    "UserInstructions",
    "UserShellCommand",
    "is_contextual_user_fragment",
    "is_standard_contextual_user_text",
    "matches_marked_text",
    "network_from_turn_context_item",
    "parse_visible_hook_prompt_message",
]
