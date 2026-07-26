# Windows Sandbox Manual Acceptance

Use this checklist when native Windows behavior changed or when automated E2E
cannot prove the host boundary. Record results in the relevant issue or commit,
not by appending dated logs here.

## Preparation

Start from the repository root:

```powershell
python -m pycodex --no-alt-screen -C C:\Users\27605\codex-python `
  -s workspace-write `
  -a on-request `
  --enable exec_permission_approvals
```

Use disposable filenames and remove them after the run.

## Required Scenarios

| Scenario | Expected result |
| --- | --- |
| Read Only workspace write | An approval is required; rejecting it leaves no file. |
| Default workspace write | A workspace file can be created and removed. |
| Default outside-workspace write | An approval is required; rejecting it leaves no file. |
| Full Access outside-workspace write | The operation succeeds without a sandbox escalation prompt. |
| Default external network without approval | Connection fails or times out; it must not silently succeed. |
| Network approval and reuse | First request asks; an equivalent permission profile may reuse approval; a materially different profile asks again. |
| Timed command with descendants | The parent times out and the delayed child cannot create its marker file. |
| No-argument startup | The default permission profile follows workspace trust and persisted configuration. |
| Resize during active UI | Composer, status, approval view, and transcript remain usable and do not duplicate rows. |

## Approval Isolation

After approving a network request, submit an equivalent request and verify that
the approval is reused. Then request a different filesystem permission and
verify that a new approval view opens. Press `Esc`; the target file must not
exist. Finally submit ordinary English and Chinese prompts to verify that the
conversation session recovered intact.

## Descendant Termination

For this scenario, disable unified exec so `shell_command.timeout_ms` exercises
the Rust-owned expiration path:

```powershell
python -m pycodex --no-alt-screen -C C:\Users\27605\codex-python `
  -s workspace-write `
  -a on-request `
  --enable exec_permission_approvals `
  --disable unified_exec
```

Run a parent PowerShell process that starts a child which waits ten seconds
before writing `.tmp\sandbox-manual-descendant.txt`; set the parent tool timeout
to 2000 ms. Wait at least twelve seconds after timeout, then verify:

```powershell
Test-Path .tmp\sandbox-manual-descendant.txt
```

Expected output: `False`.

## Final Cleanup

Confirm that all disposable workspace and home-directory files are absent.
Unexpected success, missing stderr, surviving descendants, approval-profile
reuse across different permissions, or a damaged TUI session is a failed
acceptance result.
