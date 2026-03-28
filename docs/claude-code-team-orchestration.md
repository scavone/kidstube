# Claude Code Team Orchestration Reference

> Comprehensive reference for coordinating multiple Claude Code instances using agent teams, subagents, shared tasks, and inter-agent messaging.

**Source**: [code.claude.com/docs](https://code.claude.com/docs/en/agent-teams.md) (fetched 2026-03-23)

---

## Table of Contents

- [Agent Teams vs Subagents](#agent-teams-vs-subagents)
- [Agent Teams](#agent-teams)
  - [Enable Agent Teams](#enable-agent-teams)
  - [Starting a Team](#starting-a-team)
  - [Display Modes](#display-modes)
  - [Controlling Teams](#controlling-teams)
  - [Task Assignment and Claiming](#task-assignment-and-claiming)
  - [Talking to Teammates Directly](#talking-to-teammates-directly)
  - [Plan Approval for Teammates](#plan-approval-for-teammates)
  - [Shutting Down and Cleanup](#shutting-down-and-cleanup)
  - [Architecture](#architecture)
  - [Permissions](#permissions)
  - [Context and Communication](#context-and-communication)
  - [Token Usage](#token-usage)
  - [Quality Gates with Hooks](#quality-gates-with-hooks)
  - [Best Practices](#best-practices)
  - [Use Case Examples](#use-case-examples)
  - [Troubleshooting](#troubleshooting)
  - [Limitations](#limitations)
- [Subagents](#subagents)
  - [Built-in Subagents](#built-in-subagents)
  - [Creating Custom Subagents](#creating-custom-subagents)
  - [Subagent Configuration Reference](#subagent-configuration-reference)
  - [Working with Subagents](#working-with-subagents)
  - [Example Subagents](#example-subagents)

---

## Agent Teams vs Subagents

Both parallelize work, but they operate differently. Choose based on whether workers need to communicate with each other.

| Aspect            | Subagents                                        | Agent Teams                                         |
|:------------------|:-------------------------------------------------|:----------------------------------------------------|
| **Context**       | Own context window; results return to the caller | Own context window; fully independent               |
| **Communication** | Report results back to the main agent only       | Teammates message each other directly               |
| **Coordination**  | Main agent manages all work                      | Shared task list with self-coordination             |
| **Best for**      | Focused tasks where only the result matters      | Complex work requiring discussion and collaboration |
| **Token cost**    | Lower: results summarized back to main context   | Higher: each teammate is a separate Claude instance |

**Use subagents** when you need quick, focused workers that report back.
**Use agent teams** when teammates need to share findings, challenge each other, and coordinate on their own.

**Transition point**: If you're running parallel subagents but hitting context limits, or if your subagents need to communicate with each other, agent teams are the natural next step.

---

## Agent Teams

Agent teams let you coordinate multiple Claude Code instances working together. One session acts as the **team lead**, coordinating work, assigning tasks, and synthesizing results. **Teammates** work independently, each in its own context window, and communicate directly with each other.

Unlike subagents (which run within a single session and can only report back to the main agent), you can also interact with individual teammates directly without going through the lead.

> **Requires**: Claude Code v2.1.32 or later. Check with `claude --version`.

### Enable Agent Teams

Agent teams are **experimental and disabled by default**. Enable by setting `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` to `1`:

```json
// settings.json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

Or set via environment variable in your shell.

### Starting a Team

Tell Claude to create an agent team and describe the task and team structure in natural language:

```
I'm designing a CLI tool that helps developers track TODO comments across
their codebase. Create an agent team to explore this from different angles: one
teammate on UX, one on technical architecture, one playing devil's advocate.
```

Claude creates the team, spawns teammates, and coordinates work based on your prompt. There are two ways teams get started:

1. **You request a team**: explicitly ask for an agent team
2. **Claude proposes a team**: Claude may suggest creating a team if it determines your task would benefit; you confirm before it proceeds

Claude won't create a team without your approval.

### Display Modes

| Mode           | Description                                                    | Requirements           |
|:---------------|:---------------------------------------------------------------|:-----------------------|
| **In-process** | All teammates run inside your main terminal                    | Any terminal           |
| **Split panes**| Each teammate gets its own pane                                | tmux or iTerm2         |
| **Auto**       | Uses split panes if already in tmux, otherwise in-process      | Default                |

Configure in settings.json:

```json
{
  "teammateMode": "in-process"
}
```

Or per-session:

```bash
claude --teammate-mode in-process
```

**In-process navigation**: Use `Shift+Down` to cycle through teammates. After the last teammate, it wraps back to the lead.

**Split pane requirements**:
- **tmux**: Install via package manager. `tmux -CC` in iTerm2 is recommended on macOS.
- **iTerm2**: Install the `it2` CLI and enable Python API in iTerm2 Settings > General > Magic.

> Split-pane mode is NOT supported in VS Code's integrated terminal, Windows Terminal, or Ghostty.

### Controlling Teams

Tell the lead what you want in natural language. It handles coordination, task assignment, and delegation.

#### Specify teammates and models

```
Create a team with 4 teammates to refactor these modules in parallel.
Use Sonnet for each teammate.
```

Claude decides the number of teammates based on your task, or you can specify exactly.

### Task Assignment and Claiming

The shared task list coordinates work. Tasks have three states: **pending**, **in progress**, and **completed**. Tasks can depend on other tasks — a pending task with unresolved dependencies cannot be claimed.

- **Lead assigns**: Tell the lead which task to give to which teammate
- **Self-claim**: After finishing a task, a teammate picks up the next unassigned, unblocked task

Task claiming uses **file locking** to prevent race conditions.

Toggle the task list with `Ctrl+T`.

### Talking to Teammates Directly

Each teammate is a full, independent Claude Code session.

- **In-process mode**: `Shift+Down` to cycle, type to message. Press `Enter` to view a teammate's session, `Escape` to interrupt their current turn.
- **Split-pane mode**: Click into a teammate's pane to interact directly.

### Plan Approval for Teammates

Require teammates to plan before implementing:

```
Spawn an architect teammate to refactor the authentication module.
Require plan approval before they make any changes.
```

When a teammate finishes planning, it sends a plan approval request to the lead. The lead reviews and either approves or rejects with feedback. If rejected, the teammate revises and resubmits.

Influence the lead's judgment with criteria: "only approve plans that include test coverage" or "reject plans that modify the database schema."

### Shutting Down and Cleanup

**Shut down a teammate**:
```
Ask the researcher teammate to shut down
```
The teammate can approve (exits gracefully) or reject with an explanation.

**Clean up the team**:
```
Clean up the team
```
- Always use the **lead** to clean up (not teammates)
- Shut down all teammates first — cleanup fails if any are still running
- Cleanup removes shared team resources

### Architecture

An agent team consists of:

| Component     | Role                                                                                       |
|:--------------|:-------------------------------------------------------------------------------------------|
| **Team lead** | Main Claude Code session that creates the team, spawns teammates, and coordinates work     |
| **Teammates** | Separate Claude Code instances that each work on assigned tasks                            |
| **Task list** | Shared list of work items that teammates claim and complete                                |
| **Mailbox**   | Messaging system for communication between agents                                          |

**Storage locations**:
- Team config: `~/.claude/teams/{team-name}/config.json`
- Task list: `~/.claude/tasks/{team-name}/`

The team config contains a `members` array with each teammate's name, agent ID, and agent type. Teammates can read this file to discover other team members.

### Permissions

- Teammates start with the lead's permission settings
- If the lead runs with `--dangerously-skip-permissions`, all teammates do too
- After spawning, you can change individual teammate modes
- You can't set per-teammate modes at spawn time

### Context and Communication

Each teammate has its own context window. When spawned, a teammate loads the same project context as a regular session: CLAUDE.md, MCP servers, and skills. It also receives the spawn prompt from the lead. **The lead's conversation history does NOT carry over.**

**How teammates share information:**
- **Automatic message delivery**: Messages are delivered automatically to recipients
- **Idle notifications**: When a teammate finishes, it automatically notifies the lead
- **Shared task list**: All agents can see task status and claim available work

**Messaging types:**
- **message**: Send to one specific teammate
- **broadcast**: Send to all teammates simultaneously (use sparingly — costs scale with team size)

### Token Usage

Agent teams use **significantly more tokens** than a single session — approximately **7x more** when teammates run in plan mode.

**Cost management tips:**
- Use **Sonnet** for teammates (balances capability and cost)
- Keep teams **small** (3-5 teammates for most workflows)
- Keep spawn prompts **focused**
- **Clean up teams** when work is done (idle teammates still consume tokens)
- Have **5-6 tasks per teammate** to keep everyone productive

### Quality Gates with Hooks

Use hooks to enforce rules when teammates finish work or tasks complete:

#### TeammateIdle Hook

Runs when a teammate is about to go idle after finishing its turn.

**Input fields** (in addition to common fields):

| Field           | Description                                   |
|:----------------|:----------------------------------------------|
| `teammate_name` | Name of the teammate about to go idle         |
| `team_name`     | Name of the team                              |

```json
{
  "session_id": "abc123",
  "hook_event_name": "TeammateIdle",
  "teammate_name": "researcher",
  "team_name": "my-project"
}
```

**Decision control:**
- **Exit code 2**: Teammate receives stderr as feedback and continues working
- **JSON `{"continue": false, "stopReason": "..."}`**: Stops the teammate entirely

**Example** — require build artifact before going idle:
```bash
#!/bin/bash
if [ ! -f "./dist/output.js" ]; then
  echo "Build artifact missing. Run the build before stopping." >&2
  exit 2
fi
exit 0
```

> TeammateIdle hooks do NOT support matchers.

#### TaskCompleted Hook

Runs when a task is being marked as completed (either explicitly via TaskUpdate or when a teammate finishes its turn with in-progress tasks).

**Input fields** (in addition to common fields):

| Field              | Description                                             |
|:-------------------|:--------------------------------------------------------|
| `task_id`          | Identifier of the task being completed                  |
| `task_subject`     | Title of the task                                       |
| `task_description` | Detailed description (may be absent)                    |
| `teammate_name`    | Name of the teammate completing (may be absent)         |
| `team_name`        | Name of the team (may be absent)                        |

**Decision control:**
- **Exit code 2**: Task is NOT marked as completed; stderr fed back as feedback
- **JSON `{"continue": false, "stopReason": "..."}`**: Stops the teammate entirely

**Example** — require passing tests before task completion:
```bash
#!/bin/bash
INPUT=$(cat)
TASK_SUBJECT=$(echo "$INPUT" | jq -r '.task_subject')

if ! npm test 2>&1; then
  echo "Tests not passing. Fix failing tests before completing: $TASK_SUBJECT" >&2
  exit 2
fi
exit 0
```

> TaskCompleted hooks do NOT support matchers.

### Best Practices

1. **Give teammates enough context**: Include task-specific details in the spawn prompt. They don't inherit the lead's conversation history.

   ```
   Spawn a security reviewer teammate with the prompt: "Review the authentication
   module at src/auth/ for security vulnerabilities. Focus on token handling, session
   management, and input validation. The app uses JWT tokens stored in httpOnly cookies."
   ```

2. **Choose appropriate team size**: Start with **3-5 teammates**. Having **5-6 tasks per teammate** keeps everyone productive.

3. **Size tasks appropriately**:
   - Too small: coordination overhead exceeds benefit
   - Too large: teammates work too long without check-ins
   - Just right: self-contained units that produce a clear deliverable

4. **Wait for teammates to finish**: If the lead starts implementing tasks itself:
   ```
   Wait for your teammates to complete their tasks before proceeding
   ```

5. **Start with research and review**: If new to agent teams, begin with non-coding tasks (reviewing a PR, researching a library, investigating a bug).

6. **Avoid file conflicts**: Break work so each teammate owns different files.

7. **Monitor and steer**: Check in on progress, redirect approaches that aren't working.

### Use Case Examples

#### Parallel Code Review

```
Create an agent team to review PR #142. Spawn three reviewers:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```

Each reviewer applies a different filter. The lead synthesizes findings.

#### Investigating with Competing Hypotheses

```
Users report the app exits after one message instead of staying connected.
Spawn 5 agent teammates to investigate different hypotheses. Have them talk to
each other to try to disprove each other's theories, like a scientific debate.
Update the findings doc with whatever consensus emerges.
```

The debate structure fights anchoring bias — the theory that survives active challenge is more likely the actual root cause.

### Troubleshooting

| Problem                        | Solution                                                                                     |
|:-------------------------------|:---------------------------------------------------------------------------------------------|
| Teammates not appearing        | Press `Shift+Down` to check. Verify task complexity warrants a team. Check tmux is installed. |
| Too many permission prompts    | Pre-approve common operations in permission settings before spawning.                        |
| Teammates stopping on errors   | Check output via `Shift+Down`, give additional instructions, or spawn replacement.           |
| Lead shuts down prematurely    | Tell it to keep going or wait for teammates.                                                 |
| Orphaned tmux sessions         | `tmux ls` then `tmux kill-session -t <session-name>`                                        |

### Limitations

- **No session resumption** with in-process teammates (`/resume` and `/rewind` don't restore them)
- **Task status can lag**: teammates sometimes fail to mark tasks as completed
- **Shutdown can be slow**: teammates finish current request/tool call before shutting down
- **One team per session**: clean up the current team before starting a new one
- **No nested teams**: teammates cannot spawn their own teams
- **Lead is fixed**: can't promote a teammate or transfer leadership
- **Permissions set at spawn**: can change individual modes after, but not at spawn time
- **Split panes require tmux or iTerm2**
- **CLAUDE.md works normally**: teammates read CLAUDE.md from their working directory

---

## Subagents

Subagents are specialized AI assistants that handle specific tasks. Each runs in its own context window with a custom system prompt, specific tool access, and independent permissions. When Claude encounters a task matching a subagent's description, it delegates to that subagent, which works independently and returns results.

### Built-in Subagents

| Agent              | Model    | Tools      | Purpose                                           |
|:-------------------|:---------|:-----------|:--------------------------------------------------|
| **Explore**        | Haiku    | Read-only  | File discovery, code search, codebase exploration  |
| **Plan**           | Inherits | Read-only  | Codebase research for planning                     |
| **General-purpose**| Inherits | All tools  | Complex research, multi-step operations            |
| **Bash**           | Inherits | —          | Running terminal commands in separate context      |
| **statusline-setup**| Sonnet  | —          | Configuring status line                            |
| **Claude Code Guide**| Haiku  | —          | Answering questions about Claude Code features     |

### Creating Custom Subagents

Subagents are Markdown files with YAML frontmatter. Create them:
- Via `/agents` command (interactive, recommended)
- Manually as `.md` files
- Via `--agents` CLI flag (session-only, JSON)

#### Scope and Priority

| Location                     | Scope             | Priority (1=highest) |
|:-----------------------------|:-------------------|:---------------------|
| `--agents` CLI flag          | Current session    | 1                    |
| `.claude/agents/`            | Current project    | 2                    |
| `~/.claude/agents/`          | All your projects  | 3                    |
| Plugin's `agents/` directory | Where plugin enabled| 4                   |

#### File Format

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a code reviewer. When invoked, analyze the code and provide
specific, actionable feedback on quality, security, and best practices.
```

### Subagent Configuration Reference

| Field             | Required | Description                                                                      |
|:------------------|:---------|:---------------------------------------------------------------------------------|
| `name`            | Yes      | Unique identifier (lowercase, hyphens)                                           |
| `description`     | Yes      | When Claude should delegate to this subagent                                     |
| `tools`           | No       | Tools the subagent can use (inherits all if omitted)                             |
| `disallowedTools` | No       | Tools to deny                                                                    |
| `model`           | No       | `sonnet`, `opus`, `haiku`, full model ID, or `inherit` (default)                 |
| `permissionMode`  | No       | `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, or `plan`              |
| `maxTurns`        | No       | Maximum agentic turns before stopping                                            |
| `skills`          | No       | Skills to preload into subagent's context at startup                             |
| `mcpServers`      | No       | MCP servers available to this subagent                                           |
| `hooks`           | No       | Lifecycle hooks scoped to this subagent                                          |
| `memory`          | No       | Persistent memory scope: `user`, `project`, or `local`                           |
| `background`      | No       | `true` to always run as background task (default: `false`)                       |
| `effort`          | No       | Effort level: `low`, `medium`, `high`, `max`                                    |
| `isolation`       | No       | `worktree` to run in temporary git worktree                                      |

#### Tool Restriction with Agent(type)

When running with `claude --agent`, restrict which subagents can be spawned:

```yaml
---
name: coordinator
tools: Agent(worker, researcher), Read, Bash
---
```

#### Scoping MCP Servers

```yaml
---
name: browser-tester
mcpServers:
  - playwright:
      type: stdio
      command: npx
      args: ["-y", "@playwright/mcp@latest"]
  - github  # reference existing server
---
```

#### Persistent Memory

| Scope     | Location                                      | Use when                                      |
|:----------|:----------------------------------------------|:----------------------------------------------|
| `user`    | `~/.claude/agent-memory/<name>/`              | Learnings across all projects                 |
| `project` | `.claude/agent-memory/<name>/`                | Project-specific, shareable via VCS           |
| `local`   | `.claude/agent-memory-local/<name>/`          | Project-specific, not in version control      |

### Working with Subagents

#### Invocation Methods

1. **Natural language**: Name the subagent in your prompt
2. **@-mention**: `@"code-reviewer (agent)" look at the auth changes` (guaranteed delegation)
3. **Session-wide**: `claude --agent code-reviewer` (whole session uses that subagent)

#### Foreground vs Background

- **Foreground**: Blocks main conversation. Permission prompts pass through to you.
- **Background**: Runs concurrently. Pre-approves permissions upfront, auto-denies unapproved ones.

Press `Ctrl+B` to background a running task.

#### Resuming Subagents

Each subagent invocation creates a new instance. To continue existing work:
```
Continue that code review and now analyze the authorization logic
```
Claude uses `SendMessage` with the agent's ID to resume with full context preserved.

Transcripts stored at: `~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl`

#### Common Patterns

- **Isolate high-volume operations**: Delegate test runs, doc fetching, log processing
- **Run parallel research**: Spawn multiple subagents for independent investigations
- **Chain subagents**: Use in sequence for multi-step workflows

### Example Subagents

#### Code Reviewer (read-only)

```markdown
---
name: code-reviewer
description: Expert code review specialist. Proactively reviews code for quality, security, and maintainability.
tools: Read, Grep, Glob, Bash
model: inherit
---

You are a senior code reviewer ensuring high standards of code quality and security.
When invoked:
1. Run git diff to see recent changes
2. Focus on modified files
3. Begin review immediately
```

#### Debugger (can modify files)

```markdown
---
name: debugger
description: Debugging specialist for errors, test failures, and unexpected behavior.
tools: Read, Edit, Bash, Grep, Glob
---

You are an expert debugger specializing in root cause analysis.
When invoked:
1. Capture error message and stack trace
2. Identify reproduction steps
3. Isolate the failure location
4. Implement minimal fix
5. Verify solution works
```

#### Database Query Validator (hooks-based)

```markdown
---
name: db-reader
description: Execute read-only database queries.
tools: Bash
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-readonly-query.sh"
---

You are a database analyst with read-only access. Execute SELECT queries only.
```

Validation script reads JSON from stdin, extracts the command, and exits with code 2 to block write operations.

#### CLI-defined Subagents (session-only)

```bash
claude --agents '{
  "code-reviewer": {
    "description": "Expert code reviewer. Use proactively after code changes.",
    "prompt": "You are a senior code reviewer.",
    "tools": ["Read", "Grep", "Glob", "Bash"],
    "model": "sonnet"
  },
  "debugger": {
    "description": "Debugging specialist for errors and test failures.",
    "prompt": "You are an expert debugger."
  }
}'
```

---

## Interactive Mode: Team-Related Features

### Keyboard Shortcuts for Teams

| Shortcut      | Description                                      |
|:--------------|:-------------------------------------------------|
| `Shift+Down`  | Cycle through teammates (in-process mode)        |
| `Ctrl+T`      | Toggle task list view                            |
| `Enter`       | View a teammate's session                        |
| `Escape`      | Interrupt a teammate's current turn              |
| `Ctrl+B`      | Background running tasks (press twice in tmux)   |
| `Ctrl+F`      | Kill all background agents (press twice to confirm)|

### Task List

- Shows up to 10 tasks at a time with status indicators
- Persists across context compactions
- Share across sessions: `CLAUDE_CODE_TASK_LIST_ID=my-project claude`
- Ask Claude: "show me all tasks" or "clear all tasks"

---

## Quick Decision Guide

| Scenario                                           | Use                |
|:---------------------------------------------------|:-------------------|
| Quick focused task, only result matters             | Subagent           |
| Parallel work, no inter-worker communication needed | Subagents          |
| Workers need to share findings and debate           | Agent team         |
| Research with competing hypotheses                  | Agent team         |
| Cross-layer changes (frontend + backend + tests)    | Agent team         |
| Sequential, same-file edits                         | Single session     |
| Work with many dependencies                         | Single session     |
| High-volume output isolation                        | Subagent           |
| Quick question about current context                | `/btw`             |

---

## Documentation URLs

- Agent Teams: https://code.claude.com/docs/en/agent-teams.md
- Subagents: https://code.claude.com/docs/en/sub-agents.md
- Hooks: https://code.claude.com/docs/en/hooks.md
- Interactive Mode: https://code.claude.com/docs/en/interactive-mode.md
- Costs: https://code.claude.com/docs/en/costs.md
- Features Overview: https://code.claude.com/docs/en/features-overview.md
- Full docs index: https://code.claude.com/docs/llms.txt
