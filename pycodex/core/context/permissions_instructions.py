"""Permission prompt instructions ported from ``core/src/context/permissions_instructions.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    GranularApprovalConfig,
    NetworkAccess,
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxMode,
    WritableRoot,
    format_allow_prefixes,
)

from . import ContextualUserFragmentBase
from pycodex.execpolicy import Decision

APPROVAL_POLICY_NEVER = (
    "Approval policy is currently never. Do not provide the `sandbox_permissions` for any reason, commands will be rejected."
)
APPROVAL_POLICY_UNLESS_TRUSTED = (
    ' Approvals are your mechanism to get user consent to run shell commands without the sandbox. `approval_policy` is `unless-trusted`: The harness will escalate most commands for user approval, apart from a limited allowlist of safe "read" commands.'
)
APPROVAL_POLICY_ON_FAILURE = (
    "Approvals are your mechanism to get user consent to run shell commands without the sandbox. `approval_policy` is `on-failure`: The harness will allow all commands to run in the sandbox (if enabled), and failures will be escalated to the user for approval to run again without the sandbox."
)
APPROVAL_POLICY_ON_REQUEST_RULE = """# Escalation Requests

Commands are run outside the sandbox if they are approved by the user, or match an existing rule that allows it to run unrestricted. The command string is split into independent command segments at shell control operators, including but not limited to:

- Pipes: |
- Logical operators: &&, ||
- Command separators: ;
- Subshell boundaries: (...), $(...)

Each resulting segment is evaluated independently for sandbox restrictions and approval requirements.

Example:

git pull | tee output.txt

This is treated as two command segments:

["git", "pull"]

["tee", "output.txt"]

Commands that use more advanced shell features like redirection (>, >>, <), substitutions ($(...), ...), environment variables (FOO=bar), or wildcard patterns (*, ?) will not be evaluated against rules, to limit the scope of what an approved rule allows.

## How to request escalation

IMPORTANT: To request approval to execute a command that will require escalated privileges:

- Provide the `sandbox_permissions` parameter with the value `"require_escalated"`
- Include a short question asking the user if they want to allow the action in `justification` parameter. e.g. "Do you want to download and install dependencies for this project?"
- Optionally suggest a `prefix_rule` - this will be shown to the user with an option to persist the rule approval for future sessions.

If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with "require_escalated". ALWAYS proceed to use the `justification` parameter - do not message the user before requesting approval for the command.

## When to request escalation

While commands are running inside the sandbox, here are some scenarios that will require escalation outside the sandbox:

- You need to run a command that writes to a directory that requires it (e.g. running tests that write to /var)
- You need to run a GUI app (e.g., open/xdg-open/osascript) to open browsers or files.
- If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with `require_escalated`. ALWAYS proceed to use the `sandbox_permissions` and `justification` parameters. do not message the user before requesting approval for the command.
- You are about to take a potentially destructive action such as an `rm` or `git reset` that the user did not explicitly ask for.
- Be judicious with escalating, but if completing the user's request requires it, you should do so - don't try and circumvent approvals by using other tools.

## prefix_rule guidance

When choosing a `prefix_rule`, request one that will allow you to fulfill similar requests from the user in the future without re-requesting escalation. It should be categorical and reasonably scoped to similar capabilities. You should rarely pass the entire command into `prefix_rule`.

### Banned prefix_rules 
Avoid requesting overly broad prefixes that the user would be ill-advised to approve. For example, do not request ["python3"], ["python", "-"], or other similar prefixes that would allow arbitrary scripting.
NEVER provide a prefix_rule argument for destructive commands like rm.
NEVER provide a prefix_rule if your command uses a heredoc or herestring. 

### Examples
Good examples of prefixes:
- ["npm", "run", "dev"]
- ["gh", "pr", "check"]
- ["cargo", "test"]"""
APPROVAL_POLICY_ON_REQUEST_RULE_REQUEST_PERMISSION = """# Permission Requests

Commands may require user approval before execution. Prefer requesting sandboxed additional permissions instead of asking to run fully outside the sandbox.

## Preferred request mode

When you need extra sandboxed permissions for one command, use:

- `sandbox_permissions: "with_additional_permissions"`
- `additional_permissions` with one or more of:
  - `network.enabled`: set to `true` to enable network access
  - `file_system.read`: list of paths that need read access
  - `file_system.write`: list of paths that need write access

When using the `request_permissions` tool directly, only request `network` and `file_system` permissions.

This keeps execution inside the current sandbox policy, while adding only the requested permissions for that command, unless an exec-policy allow rule applies and authorizes running the command outside the sandbox.

If the command already matches an exec-policy allow rule, the command can be auto-approved without an extra prompt. In that case, exec-policy allow behavior (including any sandbox bypass) takes precedence.

## Escalation Requests

Use full escalation only when sandboxed additional permissions cannot satisfy the task.

- `sandbox_permissions: "require_escalated"`
- Include `justification` as a short question asking for approval.
- Optionally include `prefix_rule` to suggest a reusable allow rule.

## Command segmentation reminder

The command string is split into independent command segments at shell control operators, including pipes (`|`), logical operators (`&&`, `||`), command separators (`;`), and subshell boundaries (`(...)`, `$()`).

Each segment is evaluated independently for sandbox restrictions and approval requirements."""
AUTO_REVIEW_APPROVAL_SUFFIX = "`approvals_reviewer` is `auto_review`: Sandbox escalations with require_escalated will be reviewed for compliance with the policy. If a rejection happens, you should proceed only with a materially safer alternative, or inform the user of the risk and send a final message to ask for approval."

SANDBOX_MODE_DANGER_FULL_ACCESS = "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `danger-full-access`: No filesystem sandboxing - all commands are permitted. Network access is {{network_access}}."
SANDBOX_MODE_WORKSPACE_WRITE = "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `workspace-write`: The sandbox permits reading files, and editing files in `cwd` and `writable_roots`. Editing files in other directories requires approval. Network access is {{network_access}}."
SANDBOX_MODE_READ_ONLY = "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `read-only`: The sandbox only permits reading files. Network access is {{network_access}}."


@dataclass(frozen=True)
class PermissionsPromptConfig:
    approval_policy: AskForApproval | GranularApprovalConfig
    approvals_reviewer: ApprovalsReviewer
    exec_policy: object | None = None
    exec_permission_approvals_enabled: bool = False
    request_permissions_tool_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.approval_policy, AskForApproval | GranularApprovalConfig):
            raise TypeError("approval_policy must be an AskForApproval or GranularApprovalConfig")
        if not isinstance(self.approvals_reviewer, ApprovalsReviewer):
            raise TypeError("approvals_reviewer must be an ApprovalsReviewer")
        if not isinstance(self.exec_permission_approvals_enabled, bool):
            raise TypeError("exec_permission_approvals_enabled must be a bool")
        if not isinstance(self.request_permissions_tool_enabled, bool):
            raise TypeError("request_permissions_tool_enabled must be a bool")


@dataclass(frozen=True)
class PermissionsInstructions(ContextualUserFragmentBase):
    text: str

    @classmethod
    def from_permission_profile(
        cls,
        permission_profile: PermissionProfile,
        approval_policy: AskForApproval | GranularApprovalConfig,
        approvals_reviewer: ApprovalsReviewer,
        exec_policy: object | None,
        cwd: Path | str,
        exec_permission_approvals_enabled: bool = False,
        request_permissions_tool_enabled: bool = False,
    ) -> "PermissionsInstructions":
        sandbox_mode, writable_roots = sandbox_prompt_from_profile(permission_profile, Path(cwd))
        return cls.from_permissions_with_network(
            sandbox_mode,
            network_access_from_policy(permission_profile.network_sandbox_policy()),
            PermissionsPromptConfig(
                approval_policy=approval_policy,
                approvals_reviewer=approvals_reviewer,
                exec_policy=exec_policy,
                exec_permission_approvals_enabled=exec_permission_approvals_enabled,
                request_permissions_tool_enabled=request_permissions_tool_enabled,
            ),
            writable_roots,
        )

    @classmethod
    def from_permissions_with_network(
        cls,
        sandbox_mode: SandboxMode,
        network_access: NetworkAccess,
        config: PermissionsPromptConfig,
        writable_roots: Iterable[WritableRoot] | None = None,
    ) -> "PermissionsInstructions":
        text = ""
        text = append_section(text, sandbox_text(sandbox_mode, network_access))
        text = append_section(
            text,
            approval_text(
                config.approval_policy,
                config.approvals_reviewer,
                config.exec_policy,
                config.exec_permission_approvals_enabled,
                config.request_permissions_tool_enabled,
            ),
        )
        writable_roots_section = writable_roots_text(tuple(writable_roots) if writable_roots is not None else None)
        if writable_roots_section is not None:
            text = append_section(text, writable_roots_section)
        if not text.endswith("\n"):
            text += "\n"
        return cls(text)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<permissions instructions>", "</permissions instructions>"

    def body(self) -> str:
        return self.text


@dataclass
class CommandPrefixPolicy:
    allowed_prefixes: list[tuple[str, ...]] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "CommandPrefixPolicy":
        return cls()

    def add_prefix_rule(self, prefix: Sequence[str], decision: Decision | str = Decision.ALLOW) -> None:
        if not prefix:
            raise ValueError("prefix cannot be empty")
        if not isinstance(decision, Decision):
            raise TypeError("decision must be a Decision")
        if decision is not Decision.ALLOW:
            return
        rendered = tuple(prefix)
        if any(not isinstance(token, str) for token in rendered):
            raise TypeError("prefix tokens must be strings")
        if rendered not in self.allowed_prefixes:
            self.allowed_prefixes.append(rendered)

    def get_allowed_prefixes(self) -> list[list[str]]:
        return [list(prefix) for prefix in sorted(set(self.allowed_prefixes))]


def append_section(text: str, section: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(section, str):
        raise TypeError("section must be a string")
    if not text.endswith("\n"):
        text += "\n"
    return text + section


def sandbox_prompt_from_profile(
    permission_profile: PermissionProfile,
    cwd: Path | str,
) -> tuple[SandboxMode, tuple[WritableRoot, ...] | None]:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    if not isinstance(cwd, Path | str):
        raise TypeError("cwd must be a path")
    if permission_profile.type in {"disabled", "external"}:
        return SandboxMode.DANGER_FULL_ACCESS, None

    file_system_policy = permission_profile.file_system_sandbox_policy()
    if file_system_policy.has_full_disk_write_access():
        return SandboxMode.DANGER_FULL_ACCESS, None

    writable_roots = file_system_policy.get_writable_roots_with_cwd(cwd)
    if not writable_roots:
        return SandboxMode.READ_ONLY, None
    return SandboxMode.WORKSPACE_WRITE, writable_roots


def network_access_from_policy(network_policy: NetworkSandboxPolicy) -> NetworkAccess:
    if not isinstance(network_policy, NetworkSandboxPolicy):
        raise TypeError("network_policy must be a NetworkSandboxPolicy")
    return NetworkAccess.ENABLED if network_policy.is_enabled() else NetworkAccess.RESTRICTED


def sandbox_text(mode: SandboxMode, network_access: NetworkAccess) -> str:
    if not isinstance(mode, SandboxMode):
        raise TypeError("mode must be a SandboxMode")
    if not isinstance(network_access, NetworkAccess):
        raise TypeError("network_access must be a NetworkAccess")
    template = {
        SandboxMode.DANGER_FULL_ACCESS: SANDBOX_MODE_DANGER_FULL_ACCESS,
        SandboxMode.WORKSPACE_WRITE: SANDBOX_MODE_WORKSPACE_WRITE,
        SandboxMode.READ_ONLY: SANDBOX_MODE_READ_ONLY,
    }[mode]
    return template.replace("{{network_access}}", network_access.value)


def writable_roots_text(writable_roots: Iterable[WritableRoot] | None) -> str | None:
    if writable_roots is None:
        return None
    if isinstance(writable_roots, str):
        raise TypeError("writable_roots must be an iterable of WritableRoot values")
    roots = tuple(writable_roots)
    if any(not isinstance(root, WritableRoot) for root in roots):
        raise TypeError("writable_roots must contain WritableRoot values")
    roots = tuple(sorted(roots, key=lambda root: str(root.root)))
    if not roots:
        return None
    roots_list = [f"`{root.root}`" for root in roots]
    if len(roots_list) == 1:
        return f" The writable root is {roots_list[0]}."
    return f" The writable roots are {', '.join(roots_list)}."


def approval_text(
    approval_policy: AskForApproval | GranularApprovalConfig,
    approvals_reviewer: ApprovalsReviewer,
    exec_policy: object | None = None,
    exec_permission_approvals_enabled: bool = False,
    request_permissions_tool_enabled: bool = False,
) -> str:
    approval_policy = _coerce_approval_policy(approval_policy)
    approvals_reviewer = _coerce_approvals_reviewer(approvals_reviewer)
    if not isinstance(exec_permission_approvals_enabled, bool):
        raise TypeError("exec_permission_approvals_enabled must be a bool")
    if not isinstance(request_permissions_tool_enabled, bool):
        raise TypeError("request_permissions_tool_enabled must be a bool")

    if isinstance(approval_policy, GranularApprovalConfig):
        text = granular_instructions(
            approval_policy,
            exec_policy,
            exec_permission_approvals_enabled,
            request_permissions_tool_enabled,
        )
    elif approval_policy is AskForApproval.NEVER:
        text = APPROVAL_POLICY_NEVER
    elif approval_policy is AskForApproval.UNLESS_TRUSTED:
        text = _with_request_permissions_tool(APPROVAL_POLICY_UNLESS_TRUSTED, request_permissions_tool_enabled)
    elif approval_policy is AskForApproval.ON_FAILURE:
        text = _with_request_permissions_tool(APPROVAL_POLICY_ON_FAILURE, request_permissions_tool_enabled)
    elif approval_policy is AskForApproval.ON_REQUEST:
        on_request_rule = (
            APPROVAL_POLICY_ON_REQUEST_RULE_REQUEST_PERMISSION
            if exec_permission_approvals_enabled
            else APPROVAL_POLICY_ON_REQUEST_RULE
        )
        sections = [on_request_rule]
        if request_permissions_tool_enabled:
            sections.append(request_permissions_tool_prompt_section())
        prefixes = approved_command_prefixes_text(exec_policy)
        if prefixes is not None:
            sections.append(f"## Approved command prefixes\nThe following prefix rules have already been approved: {prefixes}")
        text = "\n\n".join(sections)
    else:
        raise ValueError(f"unknown approval policy: {approval_policy!r}")

    if approvals_reviewer is ApprovalsReviewer.AUTO_REVIEW and approval_policy is not AskForApproval.NEVER:
        return f"{text}\n\n{AUTO_REVIEW_APPROVAL_SUFFIX}"
    return text


def approved_command_prefixes_text(exec_policy: object | None) -> str | None:
    prefixes = _allowed_prefixes_from_policy(exec_policy)
    rendered = format_allow_prefixes(prefixes)
    return rendered if rendered else None


def granular_prompt_intro_text() -> str:
    return "# Approval Requests\n\nApproval policy is `granular`. Categories set to `false` are automatically rejected instead of prompting the user."


def request_permissions_tool_prompt_section() -> str:
    return "# request_permissions Tool\n\nThe built-in `request_permissions` tool is available in this session. Invoke it when you need to request additional `network` or `file_system` permissions before later shell-like commands need them. Request only the specific permissions required for the task."


def granular_instructions(
    granular_config: GranularApprovalConfig,
    exec_policy: object | None = None,
    exec_permission_approvals_enabled: bool = False,
    request_permissions_tool_enabled: bool = False,
) -> str:
    if not isinstance(granular_config, GranularApprovalConfig):
        raise TypeError("granular_config must be a GranularApprovalConfig")
    if not isinstance(exec_permission_approvals_enabled, bool):
        raise TypeError("exec_permission_approvals_enabled must be a bool")
    if not isinstance(request_permissions_tool_enabled, bool):
        raise TypeError("request_permissions_tool_enabled must be a bool")
    sandbox_approval_prompts_allowed = granular_config.allows_sandbox_approval()
    shell_permission_requests_available = exec_permission_approvals_enabled and sandbox_approval_prompts_allowed
    request_permissions_tool_prompts_allowed = (
        request_permissions_tool_enabled and granular_config.allows_request_permissions()
    )
    categories: list[tuple[bool, str]] = [
        (granular_config.allows_sandbox_approval(), "`sandbox_approval`"),
        (granular_config.allows_rules_approval(), "`rules`"),
        (granular_config.allows_skill_approval(), "`skill_approval`"),
    ]
    if request_permissions_tool_enabled:
        categories.append((granular_config.allows_request_permissions(), "`request_permissions`"))
    categories.append((granular_config.allows_mcp_elicitations(), "`mcp_elicitations`"))

    prompted_categories = [f"- {category}" for is_allowed, category in categories if is_allowed]
    rejected_categories = [f"- {category}" for is_allowed, category in categories if not is_allowed]
    sections = [granular_prompt_intro_text()]

    if prompted_categories:
        sections.append(
            "These approval categories may still prompt the user when needed:\n"
            + "\n".join(prompted_categories)
        )
    if rejected_categories:
        sections.append(
            "These approval categories are automatically rejected instead of prompting the user:\n"
            + "\n".join(rejected_categories)
        )
    if shell_permission_requests_available:
        sections.append(APPROVAL_POLICY_ON_REQUEST_RULE_REQUEST_PERMISSION)
    if request_permissions_tool_prompts_allowed:
        sections.append(request_permissions_tool_prompt_section())
    prefixes = approved_command_prefixes_text(exec_policy)
    if prefixes is not None:
        sections.append(f"## Approved command prefixes\nThe following prefix rules have already been approved: {prefixes}")

    return "\n\n".join(sections)


def _with_request_permissions_tool(text: str, request_permissions_tool_enabled: bool) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(request_permissions_tool_enabled, bool):
        raise TypeError("request_permissions_tool_enabled must be a bool")
    if request_permissions_tool_enabled:
        return f"{text}\n\n{request_permissions_tool_prompt_section()}"
    return text


def _allowed_prefixes_from_policy(exec_policy: object | None) -> list[list[str]]:
    if exec_policy is None:
        return []
    if hasattr(exec_policy, "get_allowed_prefixes"):
        raw_prefixes = exec_policy.get_allowed_prefixes()
    else:
        raw_prefixes = exec_policy
    prefixes = list(raw_prefixes)  # type: ignore[arg-type]
    if not prefixes:
        return []
    if all(isinstance(token, str) for token in prefixes):
        return [list(prefixes)]
    rendered: list[list[str]] = []
    for prefix in prefixes:
        if isinstance(prefix, str):
            raise TypeError("approved prefix entries must be string sequences")
        prefix_tokens = list(prefix)
        if any(not isinstance(token, str) for token in prefix_tokens):
            raise TypeError("approved prefix tokens must be strings")
        rendered.append(prefix_tokens)
    return rendered


def _coerce_approval_policy(
    approval_policy: AskForApproval | GranularApprovalConfig | str,
) -> AskForApproval | GranularApprovalConfig:
    if isinstance(approval_policy, GranularApprovalConfig):
        return approval_policy
    if isinstance(approval_policy, AskForApproval):
        return approval_policy
    raise TypeError("approval_policy must be an AskForApproval or GranularApprovalConfig")


def _coerce_approvals_reviewer(approvals_reviewer: ApprovalsReviewer | str) -> ApprovalsReviewer:
    if isinstance(approvals_reviewer, ApprovalsReviewer):
        return approvals_reviewer
    raise TypeError("approvals_reviewer must be an ApprovalsReviewer")


__all__ = [
    "APPROVAL_POLICY_NEVER",
    "APPROVAL_POLICY_ON_FAILURE",
    "APPROVAL_POLICY_ON_REQUEST_RULE",
    "APPROVAL_POLICY_ON_REQUEST_RULE_REQUEST_PERMISSION",
    "APPROVAL_POLICY_UNLESS_TRUSTED",
    "AUTO_REVIEW_APPROVAL_SUFFIX",
    "CommandPrefixPolicy",
    "PermissionsInstructions",
    "PermissionsPromptConfig",
    "approved_command_prefixes_text",
    "approval_text",
    "append_section",
    "granular_instructions",
    "granular_prompt_intro_text",
    "network_access_from_policy",
    "request_permissions_tool_prompt_section",
    "sandbox_prompt_from_profile",
    "sandbox_text",
    "writable_roots_text",
]

