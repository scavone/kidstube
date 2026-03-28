# KidsTube Team Deployment Guide

How to spin up the 3-agent development team for working through GitHub issues.

## Prerequisites

- Claude Code v2.1.32+ (`claude --version`)
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` = `1` (already set in `~/.claude/settings.json`)
- Agent definitions in `.claude/agents/` (already checked into the repo)

## Agent Definitions

Three persistent agent definitions live in `.claude/agents/`:

| Agent | File | Domain | Memory |
|:------|:------|:-------|:-------|
| **frontend-dev** | `.claude/agents/frontend-dev.md` | `tvos/` — SwiftUI, models, services | `.claude/agent-memory/frontend-dev/` |
| **backend-dev** | `.claude/agents/backend-dev.md` | `server/` — FastAPI, SQLite, Telegram bot | `.claude/agent-memory/backend-dev/` |
| **qa-analyst** | `.claude/agents/qa-analyst.md` | Both — test plans, integration review | `.claude/agent-memory/qa-analyst/` |

### Memory

Each agent has `memory: project` enabled. This means:
- Agents accumulate knowledge in `.claude/agent-memory/<name>/` across sessions
- Memories persist between team deployments — agents remember past issues, patterns, and decisions
- Memory files are project-scoped and can be committed to version control to share across machines
- Agents are instructed to check their memory before starting work and update it after completing tasks

### Permissions

Agent definitions use `permissionMode: bypassPermissions` so teammates can run `source`, `python3`, `swift`, `pytest`, `xcodebuild`, `git`, `gh`, `pip`, `xcrun`, `xcodegen`, etc. without prompting.

The lead session's permissions are configured in `.claude/settings.local.json` with broad allow rules for the same commands. This file is local-only (not committed) since it contains machine-specific paths.

## Deploying the Team

### Step 1: Start Claude Code

```bash
cd /path/to/yt4kids
claude
```

For split-pane mode (requires tmux):
```bash
tmux
claude --teammate-mode split
```

### Step 2: Create the Team and Pick an Issue

Prompt Claude with something like:

```
Create an agent team called "yt4kids" with 3 teammates: frontend-dev, backend-dev, and qa-analyst.

We're working on GitHub issue #<NUMBER>. Review the issue, create tasks for each teammate, and assign them. Rules:
- frontend-dev only works in tvos/
- backend-dev only works in server/
- qa-analyst creates test plans first, then reviews integration after both devs complete
- No teammate should work on the same files as another
- Devs message qa-analyst when done with file lists
- QA messages team lead with the final report
```

### Step 3: Monitor and Steer

- `Ctrl+T` — Toggle task list
- `Shift+Down` — Cycle through teammates (in-process mode)
- `Enter` on a teammate — View their session
- `Escape` — Interrupt a teammate's turn

### Step 4: Commit After QA Passes

Wait for all teammate activity to settle (all idle, no pending messages), then:

```
Commit and push the changes for issue #<NUMBER>
```

### Step 5: Compact and Continue

Before the next issue:
```
Have all teammates compact their conversations, then start issue #<NEXT_NUMBER>
```

Or compact teammates yourself via `Shift+Down` → type `/compact` in each.

### Step 6: Cleanup When Done

```
Clean up the team
```

Shut down all teammates first — cleanup fails if any are still running.

## Workflow Rules

1. **One issue at a time** — Complete, commit, and push each issue before starting the next
2. **No file conflicts** — frontend-dev owns `tvos/`, backend-dev owns `server/`, QA writes tests and reports only
3. **QA gates the merge** — Don't commit until QA reports "ready for merge"
4. **Wait for settlement** — Don't commit while teammates are still exchanging messages
5. **Compact between issues** — Free up context space before starting the next issue
6. **Devs coordinate API contracts** — Backend messages frontend with endpoint schemas, frontend confirms alignment

## Issue Priority Order

When deciding which issue to work on next, consider:
1. Issues that build on recently completed work (natural progression)
2. Issues with both frontend + backend components (uses full team)
3. Issues that are well-scoped with clear acceptance criteria
4. Foundational issues before enhancement issues

## Using Agents Without a Team

For smaller tasks that don't need full team coordination, use agents as subagents:

```
@"frontend-dev (agent)" Add a loading spinner to the channel detail view
```

Or in the background:
```
Use the backend-dev agent to add input validation to the search endpoint, run it in the background
```

This is cheaper (no team overhead) and useful for single-domain tasks.

## Troubleshooting

| Problem | Solution |
|:--------|:---------|
| Teammate not picking up tasks | Send them a direct message with the task details |
| Lead commits too early | Wait for all idle notifications to stop before committing |
| Teammate context full | Have them run `/compact` or spawn a fresh teammate |
| Orphaned tmux sessions | `tmux ls` then `tmux kill-session -t <name>` |
| Agent memory stale | Check `.claude/agent-memory/<name>/` and prune outdated entries |
