# Claude-Flow Memory Management Guide

## Overview

Claude-flow provides session-based memory that persists across `/clear` commands and new sessions. This guide covers where memory is stored, how to use it, and the recommended workflow.

---

## Storage Locations

| Store | Path | Purpose |
|-------|------|---------|
| Auto-memory files | `~/.claude/projects/<encoded-project>/memory/*.md` | Markdown notes — auto-loaded at every session start |
| AgentDB / claude-flow | `<project>/.claude-flow/data/auto-memory-store.json` | Vector embeddings, session state |
| Sessions | `<project>/.claude-flow/sessions/*.json` | Named session snapshots + auto-generated lifecycle records |

- No external database process — ONNX vector embeddings run in-memory and persist to JSON
- `.claude-flow/` is inside the project but should be added to `.gitignore`

---

## Behavior with `/clear` and `/compact`

| Action | Effect on Memory |
|--------|-----------------|
| `/compact` | Context is compressed, memory unaffected — no action needed |
| `/clear` | Conversation wiped — memory persists but must be explicitly restored |
| New session | Auto-memory `.md` files are injected automatically |

---

## Recommended Workflow

### 1. Work on a task
Prompt normally. Complete the task.

### 2. Save the session (before `/clear`)
Tell Claude:
> "Save session as 'topic-YYYY-MM-DD' with description 'what was accomplished'"

Claude calls:
```
session_save {
  name: "fNIRS-preprocessing-2026-04-16",
  description: "Completed bandpass filter and GLM pipeline",
  includeMemory: true,
  includeTasks: true
}
```

### 3. Clear context
```
/clear
```

### 4. List saved sessions (in new conversation)
Tell Claude:
> "List my saved sessions"

Claude calls `session_list { sortBy: "date" }`.

### 5. Restore a specific session
Tell Claude:
> "Restore session 'fNIRS-preprocessing-2026-04-16'"

Claude calls:
```
session_restore { name: "fNIRS-preprocessing-2026-04-16" }
```

---

## Session Management Commands

| What you say | MCP tool called |
|--------------|----------------|
| "Save session as X" | `session_save { name, description, includeMemory, includeTasks }` |
| "List my sessions" | `session_list { sortBy: "date" }` |
| "Restore session X" | `session_restore { name: "X" }` |
| "Save session state" (quick) | `hooks_session-end { saveState: true }` |
| "Restore last session" (quick) | `hooks_session-start { restoreLatest: true }` |

---

## Naming Convention (Recommended)

```
<topic>-<YYYY-MM-DD>
```

Examples:
- `fNIRS-preprocessing-2026-04-16`
- `glm-pipeline-2026-04-20`
- `channel-selection-2026-04-25`

---

## Auto-Memory Files (Zero-Effort Persistence)

For context that should always be available without restoring — write a `.md` file once:

```
~/.claude/projects/-home-user-jeffrymahbuubi-PROJECTS-1-fNIRS-Grid-Base-Method/memory/
```

File format:
```markdown
---
name: My Note Title
description: One-line description for search relevance
type: project   # user | feedback | project | reference
---

Content here...
```

These load automatically at every session start — no restore command needed.

---

## Memory-Only CLI Commands (Terminal)

Use these outside of Claude conversations:
```bash
# Store a memory
npx @claude-flow/cli@latest memory store --key "my-key" --value "content" --namespace project

# Search semantically
npx @claude-flow/cli@latest memory search --query "fNIRS signal processing"

# List all stored memories
npx @claude-flow/cli@latest memory list --namespace project

# Retrieve by exact key
npx @claude-flow/cli@latest memory retrieve --key "my-key"
```

---

## Session vs Memory: Update Behavior

These two mechanisms behave differently when saving over existing data:

| Tool | Default behavior | To update in place |
|------|-----------------|-------------------|
| `session_save` | Always creates a **new** entry | Not possible — sessions are append-only snapshots |
| `memory_store` | **Fails** if key already exists | Use `upsert: true` |

Sessions accumulate like git commits — each save is a new point-in-time record. Memory entries are key-value pairs that can be updated in place.

---

## Workflow: Restore → Work → Save Back

When you restore a session, do additional work, then want to save:

```
1. memory_store  (same key, upsert: true)   ← updates memory entry in place
2. session_save  (same name)                ← creates a new session snapshot
3. (optional) session_delete old sessionId  ← clean up previous snapshot
```

---

## How to Phrase Requests for Upsert vs Create

You never write `upsert: true` yourself — Claude sets the parameter based on your wording:

| Your phrasing | What Claude does |
|---------------|-----------------|
| "Update the memory for X with..." | `memory_store { upsert: true }` |
| "Save to the existing memory entry" | `memory_store { upsert: true }` |
| "Add this new info to the existing session memory" | `memory_store { upsert: true }` |
| "Save this as a new memory" | `memory_store { upsert: false }` |
| "Create a new memory entry for..." | `memory_store { upsert: false }` |
| "Save this session" (ambiguous) | Claude checks if key exists first |

**Rule of thumb:** use **"update"** to trigger upsert; use **"create"** or **"new"** for a fresh entry.

---

## Session File Auto-Cleanup

### Background

Every time Claude Code starts and stops, claude-flow automatically creates lifecycle session files in `.claude-flow/sessions/`:

- **`SessionStart` hook** → writes `current.json` (tracks the active session)
- **`SessionEnd` hook** → archives `current.json` as `session-{timestamp}.json`

These auto-generated files have no `description` and no name — they are distinct from sessions you explicitly save with `session save`.

### Previous behavior

Every session left behind an archive file regardless of whether any work was done, resulting in accumulating unnamed files:

```
session-1776328262488.json   ← no description, idle session
session-1776328729626.json   ← no description, idle session
session-1776328763837.json   ← no description, idle session
```

### Current behavior (updated 2026-04-16)

`.claude/helpers/session.js` — `end()` function — now only archives a session if it had **actual activity** (edits or tasks > 0). Idle sessions (opened and closed without doing anything) are discarded automatically.

```
Rule: archive if (metrics.edits > 0 || metrics.tasks > 0)
      discard  if both are zero (idle session)
```

Named sessions saved explicitly via `session save` are unaffected — they use a separate save path and are always kept.

### What you see in `.claude-flow/sessions/` now

| File | Kept? | Reason |
|------|-------|--------|
| `current.json` | Always | Active session pointer |
| `session-{id}-{suffix}.json` | Always | Explicitly saved with a name + description |
| `session-{timestamp}.json` (edits > 0) | Yes | Had actual work |
| `session-{timestamp}.json` (edits = 0) | No | Idle — discarded on session end |

### No manual cleanup needed

You no longer need to run:
```bash
rm .claude-flow/sessions/session-*.json   # old manual approach
```

The cleanup is automatic on every `SessionEnd`.

---

## Key Takeaway

- You do **not** need to type `npx` commands during normal work — just tell Claude what to save or restore
- Use **named sessions** (`session_save`) to pinpoint specific work when restoring
- Use **auto-memory `.md` files** for context that should always be present
- Use **"update"** phrasing to overwrite an existing memory entry (`upsert: true`); sessions always append
- **Idle session files are auto-cleaned** — only sessions with edits or tasks are archived
