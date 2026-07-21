# claude-flow 101

A practical command reference for `npx ruflo@latest` (CLI) and the MCP tools available inside Claude Code sessions.

> **⚠ 2026-07-21 STATUS NOTE — read [README.md](README.md) first for setup/upgrade.**
> This document was written against ruflo **3.6.x**. The command reference below is still
> broadly useful, but every *setup* section — "Windows Environment Setup" (three patches),
> "Prevention — auto-memory-hook.mjs bug fix", "New Project Setup", "Setup Reference" —
> is **HISTORICAL**: upstream absorbed all the Windows patches and hook fixes, and this
> project now runs stock ruflo 3.32.9 helpers maintained by `npx ruflo init upgrade`.
> Do **not** re-apply any patch described below, and do not pin `ruflo@3.6.10` anywhere.
> Version-specific caveats ("not a subcommand in ruflo@3.6.10") may no longer hold —
> check `npx ruflo <cmd> --help` against the installed version.

> **Prefix note:** `claude-flow` is not globally installed. Always use `npx ruflo@latest <command>` from the terminal. Inside Claude Code, use MCP tools directly (no prefix needed).

---

## How to Run

```bash
# From terminal (outside Claude Code)
npx ruflo@latest <command> [subcommand] [options]

# Inside Claude Code — use MCP tools via ToolSearch
# e.g., mcp__claude-flow__memory_stats
```

---

## Memory

Manage the AgentDB vector store (sql.js + HNSW backend).

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `stats` | Show entry count, namespaces, backend info | `npx ruflo@latest memory stats` |
| `list` | List entries, optionally filter by namespace | `npx ruflo@latest memory list --namespace patterns` |
| `store` | Store a key/value with vector embedding | `npx ruflo@latest memory store -k "mykey" -v "my value"` |
| `retrieve` | Get a single entry by key | `npx ruflo@latest memory retrieve -k "mykey"` |
| `search` | Semantic vector search by query | `npx ruflo@latest memory search -q "auth patterns"` |
| `delete` | Delete an entry by key | `npx ruflo@latest memory delete -k "mykey"` |
| `cleanup` | Remove stale/expired entries | `npx ruflo@latest memory cleanup` |
| `compress` | Optimize storage (no data loss) | `npx ruflo@latest memory compress` |
| `init` | Initialize a fresh database | `npx ruflo@latest memory init` |
| `configure` | Set backend options | `npx ruflo@latest memory configure` |
| `export` | Export all entries to a file | `npx ruflo@latest memory export -o backup.json` |
| `import` | Import entries from a file | `npx ruflo@latest memory import backup.json` |

> **Note:** `memory consolidate` is not a subcommand in ruflo@3.6.10 — use `cleanup` + `compress` instead.

---

## Hooks

Self-learning hooks for workflow automation and pattern routing.

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `metrics` | View learning metrics dashboard | `npx ruflo@latest hooks metrics` |
| `route` | Route a task to the optimal agent | `npx ruflo@latest hooks route -t "implement feature"` |
| `explain` | Explain the last routing decision | `npx ruflo@latest hooks explain` |
| `intelligence` | RuVector SONA/HNSW intelligence system status | `npx ruflo@latest hooks intelligence` |
| `list` | List all registered hooks | `npx ruflo@latest hooks list` |
| `pretrain` | Bootstrap intelligence from the repo | `npx ruflo@latest hooks pretrain` |
| `build-agents` | Generate agent configs from pretrain data | `npx ruflo@latest hooks build-agents` |
| `model-route` | Route to optimal Claude model (haiku/sonnet/opus) | `npx ruflo@latest hooks model-route -t "complex task"` |
| `model-stats` | View model routing statistics | `npx ruflo@latest hooks model-stats` |
| `worker` | Manage 12 background workers | `npx ruflo@latest hooks worker list` |
| `session-end` | End session and persist state | `npx ruflo@latest hooks session-end` |
| `session-restore` | Restore a previous session | `npx ruflo@latest hooks session-restore` |
| `pre-task` | Record task start / get agent suggestions | `npx ruflo@latest hooks pre-task -t "implement X"` |
| `post-task` | Record task completion for learning | `npx ruflo@latest hooks post-task` |

> **intelligence-reset:** Not a subcommand in ruflo@3.6.10. Use the MCP tool `mcp__claude-flow__hooks_intelligence-reset` inside Claude Code instead.

---

## Agent

Manage individual agents.

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `spawn` | Spawn a new agent | `npx ruflo@latest agent spawn -t coder --name my-coder` |
| `list` | List all active agents | `npx ruflo@latest agent list` |
| `status` | Detailed status of an agent | `npx ruflo@latest agent status agent-001` |
| `stop` | Stop a running agent | `npx ruflo@latest agent stop agent-001` |
| `metrics` | Agent performance metrics | `npx ruflo@latest agent metrics agent-001` |
| `health` | Agent health summary | `npx ruflo@latest agent health` |
| `pool` | Manage agent pool for scaling | `npx ruflo@latest agent pool` |
| `logs` | Show agent activity logs | `npx ruflo@latest agent logs agent-001` |

---

## Swarm

Coordinate multi-agent swarms.

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `init` | Initialize a new swarm | `npx ruflo@latest swarm init --topology hierarchical --max-agents 8` |
| `start` | Start swarm execution | `npx ruflo@latest swarm start -o "Build API" -s development` |
| `status` | Show swarm status | `npx ruflo@latest swarm status` |
| `stop` | Stop swarm execution | `npx ruflo@latest swarm stop` |
| `scale` | Scale agent count | `npx ruflo@latest swarm scale --count 10` |
| `coordinate` | V3 15-agent hierarchical mesh | `npx ruflo@latest swarm coordinate --agents 15` |

---

## Session

Save and restore session state across runs.

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `list` | List all saved sessions | `npx ruflo@latest session list` |
| `current` | Show current active session | `npx ruflo@latest session current` |
| `save` | Save current session state | `npx ruflo@latest session save -n "checkpoint-1"` |
| `restore` | Restore a saved session | `npx ruflo@latest session restore session-123` |
| `delete` | Delete a saved session | `npx ruflo@latest session delete session-123` |
| `export` | Export session to file | `npx ruflo@latest session export -o backup.json` |
| `import` | Import session from file | `npx ruflo@latest session import backup.json` |

---

## Task

Create and manage tasks assigned to agents.

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `create` | Create a new task | `npx ruflo@latest task create -t implementation -d "Add user auth"` |
| `list` | List tasks | `npx ruflo@latest task list` |
| `status` | Get task details | `npx ruflo@latest task status task-123` |
| `assign` | Assign task to an agent | `npx ruflo@latest task assign task-123 --agent coder-1` |
| `cancel` | Cancel a running task | `npx ruflo@latest task cancel task-123` |
| `retry` | Retry a failed task | `npx ruflo@latest task retry task-123` |

---

## Hive-Mind

Queen-led, consensus-based multi-agent coordination (Byzantine fault-tolerant).

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `init` | Initialize a hive mind | `npx ruflo@latest hive-mind init -t hierarchical-mesh` |
| `spawn` | Spawn worker agents | `npx ruflo@latest hive-mind spawn -n 5` |
| `status` | Show hive status | `npx ruflo@latest hive-mind status` |
| `task` | Submit a task to the hive | `npx ruflo@latest hive-mind task -d "Build feature"` |
| `consensus` | Manage consensus proposals/voting | `npx ruflo@latest hive-mind consensus` |
| `broadcast` | Broadcast message to all workers | `npx ruflo@latest hive-mind broadcast -m "status check"` |
| `memory` | Access hive shared memory | `npx ruflo@latest hive-mind memory` |
| `shutdown` | Shutdown the hive mind | `npx ruflo@latest hive-mind shutdown` |

---

## Neural

Pattern training, model routing, and Flash Attention optimization.

| Subcommand | What it does | Example |
|------------|-------------|---------|
| `status` | Check neural system status | `npx ruflo@latest neural status` |
| `train` | Train patterns (MicroLoRA + Flash Attention) | `npx ruflo@latest neural train -p coordination` |
| `patterns` | List/analyze cognitive patterns | `npx ruflo@latest neural patterns --action list` |
| `predict` | Make predictions using trained models | `npx ruflo@latest neural predict` |
| `optimize` | Int8 quantization + memory compression | `npx ruflo@latest neural optimize` |
| `benchmark` | Benchmark WASM training performance | `npx ruflo@latest neural benchmark` |

---

## Other Useful Commands

| Command | What it does | Example |
|---------|-------------|---------|
| `npx ruflo@latest status` | System-wide status | |
| `npx ruflo@latest doctor --fix` | Diagnostics + auto-fix | |
| `npx ruflo@latest config list` | Show all config values | |
| `npx ruflo@latest analyze` | Code diff/risk analysis | |
| `npx ruflo@latest route` | Q-Learning task routing | |
| `npx ruflo@latest daemon start` | Start background daemon | |
| `npx ruflo@latest daemon stop` | Stop daemon | |

---

## Vector Accumulation — Prevention & Cleanup

Vectors accumulate in the session DB when the auto-memory hook re-imports MEMORY.md entries on every session start.

### Check current state

```bash
npx ruflo@latest memory stats
npx ruflo@latest memory list --namespace patterns
npx ruflo@latest memory list --namespace intelligence
```

### Reduce accumulation

```bash
# Compress (size reduction, no data loss)
npx ruflo@latest memory compress

# Remove expired/stale entries
npx ruflo@latest memory cleanup

# Nuclear: delete an entire namespace
npx ruflo@latest memory delete --namespace patterns --all
```

> **Note:** `memory compress` operates on the MCP sql.js+HNSW backend only. It does NOT touch `.claude-flow/data/auto-memory-store.json`. If the statusbar shows high vector counts, follow the dedup procedure below instead.

---

### Vectors stay at 0 — bridge not loaded

**When to use:** statusbar shows `Vectors ●0` (dim) and `.claude-flow/data/` does NOT contain `auto-memory-store.json` (only `pending-insights.jsonl` and the `sessions/` folder). The session-start logs print *"Memory package not available — skipping auto memory import"*. This is the **opposite** failure of accumulation: the bridge can't load `@claude-flow/memory`, so the store file is never created.

**Diagnose:**

```bash
# 1. Is the package reachable from the project?
ls node_modules/@claude-flow/memory/dist/index.js 2>/dev/null && echo "OK" || echo "MISSING"

# 2. What does the hook actually print?
node .claude/helpers/auto-memory-hook.mjs import
```

If output 1 is `MISSING`, or output 2 says *"Memory package not available"*, the npm install is incomplete.

**Fix:** Follow [New Project Setup](#new-project-setup) — add `"ruflo": "^3.30.0"` (or later; this project uses `^3.32.9`) to `devDependencies` in `package.json` and run `npm install`. The `.mcp.json` config alone does not install the package locally; the auto-memory hook needs `@claude-flow/memory` physically present in `node_modules/`.

**Real case (2026-05-08, this project):** `package.json` had no `devDependencies` field. `node_modules/@claude-flow/` existed as an empty stub. After adding the dep + `npm install`, manual import produced `Imported 90 entries` and `auto-memory-store.json` (148 KB) was created with 13 MEMORY.md files sliced into 90 entries.

| State | Before | After |
|---|---|---|
| `node_modules/@claude-flow/memory/` | empty stub dir | populated with `dist/` |
| `auto-memory-store.json` | does not exist | 148 KB, 90 entries |
| `import-manifest.json` | does not exist | created with content hash |
| Hook output | "Memory package not available" | "Imported 90 entries" |
| Statusbar | `Vectors ●0` | `Vectors ●90` |

---

### Emergency Cleanup — Deduplication Procedure (verified 2026-04-30)

**When to use:** The statusbar shows `Vectors ●N⚡` in the hundreds-to-thousands range and `npx ruflo@latest memory stats` shows only a handful of entries. This means the MCP backend is fine but the **JSON file backend** (`.claude-flow/data/auto-memory-store.json`) has accumulated duplicates.

**Why it happens:** Before the `--skip-if-exists` bug fix, the hook imported all N memory files on every session open with no deduplication check. Each session added N more entries on top of the existing ones.

#### Step 1 — Diagnose

Check how many entries are in the JSON store and how they break down:

```bash
# File size
ls -lh .claude-flow/data/auto-memory-store.json

# Entry count + namespace breakdown
python3 -c "
import json
from collections import Counter
data = json.load(open('.claude-flow/data/auto-memory-store.json'))
ns = Counter(e.get('namespace','?') for e in data)
print(f'Total: {len(data)}')
print('By namespace:', dict(ns.most_common(10)))
"
```

**Healthy state:** `Total: ~30` (27 memory files + a few insights)
**Accumulated state:** `Total: 500+` — almost all `auto-memory` namespace duplicates

#### Step 2 — Preview deduplication

Run the dedup dry-run (no writes) to confirm what will be removed:

```bash
python3 -c "
import json
from collections import Counter
data = json.load(open('.claude-flow/data/auto-memory-store.json'))
seen = {}
for entry in data:
    key = entry.get('key') or entry.get('id')
    prev = seen.get(key)
    if prev is None or entry.get('updatedAt', 0) >= prev.get('updatedAt', 0):
        seen[key] = entry
deduped = list(seen.values())
print(f'Before: {len(data)} entries')
print(f'After:  {len(deduped)} entries')
print(f'Removed: {len(data) - len(deduped)} duplicates')
print('By namespace:', dict(Counter(e.get('namespace','?') for e in deduped)))
"
```

#### Step 3 — Apply deduplication

If the preview looks right, write the deduped file:

```bash
python3 -c "
import json
path = '.claude-flow/data/auto-memory-store.json'
data = json.load(open(path))
seen = {}
for entry in data:
    key = entry.get('key') or entry.get('id')
    prev = seen.get(key)
    if prev is None or entry.get('updatedAt', 0) >= prev.get('updatedAt', 0):
        seen[key] = entry
deduped = list(seen.values())
json.dump(deduped, open(path, 'w'), indent=2)
print(f'Done: {len(deduped)} entries written')
"
```

#### Step 4 — Remove stale derived files

The graph and ranking files were built from the bloated store — delete them so they regenerate from the clean data on next session:

```bash
rm -f .claude-flow/data/graph-state.json
rm -f .claude-flow/data/ranked-context.json
```

**What to keep:**

| File | Keep? | Why |
|---|---|---|
| `auto-memory-store.json` | Yes | Just cleaned |
| `import-manifest.json` | Yes | Prevents re-accumulation |
| `intelligence-snapshot.json` | Yes | Learned patterns — valuable |
| `pending-insights.jsonl` | Yes | Insights pending merge |
| `graph-state.json` | Delete | Stale; regenerates automatically |
| `ranked-context.json` | Delete | Stale; regenerates automatically |

#### Step 5 — Verify

```bash
ls -lh .claude-flow/data/
# Before: ~2.4 MB total
# After:  ~180 KB total
```

**Real case result (2026-04-30, this project):**

| Metric | Before | After |
|---|---|---|
| `auto-memory-store.json` | 730 KB | 41 KB |
| `graph-state.json` | 990 KB → deleted | — |
| `ranked-context.json` | 1.2 MB → deleted | — |
| Total `.claude-flow/data/` | 2.4 MB | 180 KB |
| Vector count (statusbar) | 513 | 30 |
| Unique entries | 30 | 30 |
| Duplicates removed | — | 483 |

### Prevention — settings.json hooks (already applied to this project)

All three `SessionStart` hooks in `.claude/settings.json` use the `--skip-if-exists` flag:

```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "sh -c 'exec node \"${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/hook-handler.cjs\" session-restore'",
        "timeout": 15000
      },
      {
        "type": "command",
        "command": "sh -c 'exec node \"${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/auto-memory-hook.mjs\" import --skip-if-exists'",
        "timeout": 8000
      },
      {
        "type": "command",
        "command": "sh -c 'exec node \"${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/auto-memory-hook.mjs\" import-all --skip-if-exists'",
        "timeout": 8000
      }
    ]
  }
]
```

**Why the `sh -c 'exec node "${CLAUDE_PROJECT_DIR:-.}/..."'` pattern matters:**
- `CLAUDE_PROJECT_DIR` resolves the project root correctly even if Claude Code spawns the hook from a different working directory
- `exec` replaces the shell process with node (no extra fork)
- Bare `node .claude/helpers/...` (relative path) only works when CWD is the project root — fragile

### Prevention — auto-memory-hook.mjs bug fix (critical) — ⚠ HISTORICAL (fixed upstream)

> **⚠ OBSOLETE as of ruflo ≥3.30 (this project: 3.32.9, 2026-07-21).** The stock
> `auto-memory-hook.mjs` shipped by `init upgrade` handles `--skip-if-exists` and
> `import-all` correctly on all platforms. Do NOT re-apply the five changes below, and do
> NOT restore `archive/auto-memory-hook.mjs` — it is older than the current stock file.
> Kept for historical context only.

> **Bug fixed 2026-04-30.** The `--skip-if-exists` flag in the hooks above was silently ignored until this fix was applied. Without it, 27 entries were imported unconditionally on every session open.

**Root cause (two bugs):**

1. `auto-memory-hook.mjs` only read `process.argv[2]` (the command name) and never read `process.argv[3]`. The `--skip-if-exists` flag passed by the hook was thrown away.
2. The `import-all` command (hook #3) fell through to the `default` case — it just printed usage text and did nothing.

**Fix applied to `.claude/helpers/auto-memory-hook.mjs`:**

```javascript
// 1. Parse the flag properly
const skipIfExists = process.argv.includes('--skip-if-exists');

// 2. Content-hash helper — reads all *.md in the project's memory dir
function getMemoryDirHash() {
  const projectKey = PROJECT_ROOT.replace(/\//g, '-');
  const memoryDir = join(process.env.HOME, '.claude', 'projects', projectKey, 'memory');
  // hashes sorted file names + contents with MD5
}

// 3. Skip guard at the top of doImport()
if (skipIfExists && existsSync(IMPORT_MANIFEST_PATH)) {
  if (manifest.memoryHash === currentHash) {
    dim('Skip-if-exists: memory files unchanged since last import');
    return;  // ← prevents accumulation
  }
}

// 4. Save manifest after successful import
writeFileSync(IMPORT_MANIFEST_PATH, JSON.stringify({ memoryHash, lastImport: Date.now() }));

// 5. import-all handled as an alias
case 'import-all': await doImport(skipIfExists); break;
```

The manifest is stored at `.claude-flow/data/import-manifest.json`.

**Behavior after fix:**
- First session: imports once, saves content-hash manifest
- Idle sessions (no work done): hash unchanged → import skipped → no accumulation
- Sessions where memory files actually changed (sync wrote new insights): hash differs → import runs → manifest updated

**When setting up claude-flow in a new project, verify all five changes above are present in `.claude/helpers/auto-memory-hook.mjs`.** If the file was generated by `npx ruflo@latest init` before this fix, it will be missing them and vectors will still accumulate.

At session start you should see either `N imported` (first time or after changes) or the "memory files unchanged" dim message — never "N imported (0 skipped)" on every single open.

---

## Windows Environment Setup — ⚠ PATCHES HISTORICAL, PREREQUISITES STILL VALID

> **⚠ 2026-07-21:** The **three patches** below are OBSOLETE — ruflo ≥3.30 ships them
> upstream (`init upgrade` writes stock, Windows-correct helpers; recent `init` also
> generates the `cmd /c npx` MCP wrapper). The **prerequisites table** (Node 22, Git for
> Windows `sh.exe`, MSVC build tools, long paths) is still valid and worth checking.
> For current setup see [README.md](README.md).

> **Read this BEFORE running `npm install` if you're on Windows.** The default doc above is Linux-flavoured. Windows needs three prerequisite tools and three patches to project files. Verified end-to-end on Windows 11 Pro 22631 on 2026-05-22 against ruflo@3.6.10.

### Prerequisites

| Tool | Version | Why |
|---|---|---|
| **Node.js** | **22 LTS** (any 22.x). NOT Node 25 or 26. | `better-sqlite3@11.10.0` (pinned by `@claude-flow/memory`) uses V8 APIs `Object::GetPrototype`, `Context::GetIsolate`, and `PropertyCallbackInfo::This` that were removed in V8 13.x (Node ≥25). Compile fails with `error C2039`. |
| **Git for Windows** | Any recent | Provides `sh.exe` at `C:\Program Files\Git\usr\bin\sh.exe` — the SessionStart hook pattern `sh -c 'exec node …'` will silently no-op without it. |
| **Visual Studio 2022 Community / Build Tools** | with **Desktop development with C++** workload | node-gyp falls back to source build when no prebuilt binary matches Node 22 ABI 127. Must include MSBuild + Windows 10/11 SDK + MSVC v143. |
| **Windows long paths** | `HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1` | Nested `node_modules/@claude-flow/*/node_modules/...` paths routinely exceed 260 chars. Without this, npm cleanup raises `EPERM rmdir` and partially extracted packages stay broken. |

**Check from PowerShell before installing:**

```powershell
node --version                                   # must report v22.x
where.exe sh                                     # must show C:\Program Files\Git\usr\bin\sh.exe
where.exe msbuild                                # any VS2022 path is fine
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' LongPathsEnabled).LongPathsEnabled  # 1
```

### Switching Node version (if you have Node ≥25 active)

`nvm-windows` makes this a 30-second operation:

```powershell
nvm install 22
nvm use 22.22.3        # or whatever the latest 22.x is
node --version         # confirm v22.x
```

> **PATH gotcha:** Some Windows machines have multiple Node installs (`C:\Program Files\node\`, `scoop\apps\nodejs\`, and the nvm-managed one). `where.exe node` will list them in PATH order. If the wrong one is first, fix PATH or delete the standalone before relying on `nvm use`.

### Three patches needed on Windows

#### Patch 1 — `.mcp.json` MCP entry uses `cmd /c npx`, not bare `npx`

On Windows `npx` is `npx.cmd`. Direct `"command": "npx"` fails for several MCP runtimes. Use the `cmd /c` wrapper that the rest of your `.mcp.json` already uses:

```jsonc
"claude-flow": {
  "type": "stdio",
  "command": "cmd",
  "args": ["/c", "npx", "-y", "ruflo@3.6.10", "mcp", "start"],
  "env": {
    "CLAUDE_FLOW_MODE": "v3",
    "CLAUDE_FLOW_HOOKS_ENABLED": "true",
    "CLAUDE_FLOW_TOPOLOGY": "hierarchical-mesh",
    "CLAUDE_FLOW_MAX_AGENTS": "15",
    "CLAUDE_FLOW_MEMORY_BACKEND": "hybrid"
  }
}
```

#### Patch 2 — `.claude/helpers/auto-memory-hook.mjs` cross-platform fixes (two bugs)

The hook ships with two Linux-only assumptions in `getMemoryDirHash()`. The fix branches on `process.platform` so the same file is correct on both Windows and Linux/macOS — keep the file tracked in git rather than gitignoring per platform:

```javascript
// BEFORE (Linux-only — silently broken on Windows)
const homeDir = process.env.HOME || '';
const projectKey = PROJECT_ROOT.replace(/\//g, '-');

// AFTER (cross-platform, OS-conditional)
const homeDir = process.env.HOME || process.env.USERPROFILE || '';
// Claude Code derives the project key by replacing filename-unsafe path characters with '-'.
// The exact character set differs per OS:
//   - Linux/macOS: only '/' (paths don't contain ':' or '\')
//   - Windows: '/', '\', ':', '.', and ' ' all map to '-'
//     (verified: `D:\AUNUUN ...\54. LibreVNA ...` -> `D--AUNUUN-...-54--LibreVNA-...`)
const projectKey = process.platform === 'win32'
  ? PROJECT_ROOT.replace(/[\\\/:. ]/g, '-')
  : PROJECT_ROOT.replace(/\//g, '-');
```

**Why both fixes are needed:**
- `process.env.HOME` is rarely set on Windows; `USERPROFILE` (e.g. `C:\Users\<name>`) is the canonical replacement. Linux/macOS always have `HOME`, so the `||` chain selects correctly per OS.
- The `/\//g` regex alone never matched on Windows (Windows paths use backslashes, not forward slashes). A naïve broadened regex like `/[\\\/:. ]/g` would also over-convert Linux paths containing dots or spaces (e.g. `/home/user/.config/My Project` → `-home-user--config-My-Project` would not match the directory Claude Code actually creates on Linux, which is `-home-user-.config-My Project`). Branching on `process.platform` keeps each OS's behaviour intact.

Without both fixes, the dedup manifest can never match on Windows, so the hook silently re-imports on every session (the "0 imported (0 skipped)" pathology).

**Verify the patch works** before continuing (works on both Windows and Linux):

```bash
node -e "
const root = process.cwd();
const home = process.env.HOME || process.env.USERPROFILE || '';
const key = process.platform === 'win32'
  ? root.replace(/[\\\\\/:. ]/g, '-')
  : root.replace(/\\//g, '-');
console.log('platform :', process.platform);
console.log('memoryDir:', require('path').join(home, '.claude', 'projects', key, 'memory'));
console.log('exists   :', require('fs').existsSync(require('path').join(home, '.claude', 'projects', key, 'memory')));
"
```

The reported `memoryDir` must match the real path under `~/.claude/projects/` (Linux/macOS) or `C:\Users\<you>\.claude\projects\` (Windows) and `exists: true`.

#### Patch 3 — `.claude/settings.json` SessionStart hooks (same as Linux, but verify Git Bash is on PATH)

The `sh -c 'exec node "${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/auto-memory-hook.mjs" import --skip-if-exists'` pattern is unchanged from Linux. Claude Code resolves `sh` via the system PATH — Git Bash places it there automatically.

If `where.exe sh` returns nothing, either reinstall Git for Windows with "Use Git Bash from Command Prompt" enabled, or rewrite the hooks to call `node.exe` directly without the shell wrapper.

---

### Statusline Panel — Wiring the RuFlo Status Bar

> **Verified 2026-05-22 against ruflo@3.6.30 on Windows 11 Pro 22631.**

The multi-line status panel that appears at the top of every Linux Claude Code session:

```
 ▊ RuFlo V3.6.30 ● User  │  ⏇ main  │  Opus 4.7  │  ⏱ 0s
  🏗️   DDD Domains    [○○○○○]  0/5    ⚡ HNSW 10x
  🤖 Swarm  ○ [ 0/15]  👥 0    🪝  5/5    🔴 CVE 0/0    💾 4MB    🧠   0%
  🔧 Architecture    ADRs ●0/0  │  DDD ●  0%  │  Security ●PENDING
  📊 AgentDB    Vectors ●1⚡  │  Size 144KB  │  Tests ●0 (~0 cases)  │  MCP ●7/7  ◆DB  ◆API
```

…does **not** appear on Windows by default even after a successful install. The script is present and functional — it just is not wired into Claude Code's terminal UI.

**Root cause:** Claude Code displays a statusline only when the `statusLine` key exists in settings. `npx ruflo init` writes this key automatically on Linux; on Windows the init step is typically skipped, so the key is never written.

**Diagnosis — confirm the script itself works:**

```powershell
node .claude/helpers/statusline.cjs
```

If the coloured panel appears in the terminal, the script is fine. The only missing piece is the Claude Code settings key.

> **If the command errors** with "Cannot find module", the project's `node_modules/` install is incomplete — follow [New Project Setup](#new-project-setup) first.

**Fix — add `statusLine` to your global Claude Code settings:**

Edit `C:\Users\<you>\.claude\settings.json`:

```json
{
  "autoUpdatesChannel": "latest",
  "statusLine": {
    "type": "command",
    "command": "node .claude/helpers/statusline.cjs"
  }
}
```

Then **restart the Claude Code session**. The panel appears on next open in any project that contains `.claude/helpers/statusline.cjs`.

**Scope options:**

| Settings file | Effect |
|---|---|
| `C:\Users\<you>\.claude\settings.json` **(global)** | Panel appears in all projects on this Windows machine |
| Project `.claude/settings.json` | Committed to git — enables the panel on Linux too if Linux doesn't already have the key |

> **Why forward slashes work on Windows:** Node.js accepts both `\` and `/` in paths, so `node .claude/helpers/statusline.cjs` is portable across both OSes without modification.

**Comparison table — before and after:**

| | Linux | Windows (before) | Windows (after) |
|---|---|---|---|
| ruflo version in `.mcp.json` | 3.6.30 | 3.6.30 | 3.6.30 |
| `.claude/helpers/statusline.cjs` present | ✓ | ✓ | ✓ |
| `statusLine` key in settings | ✓ | **missing** | **added ✓** |
| Panel visible on session open | ✓ | ✗ | ✓ |

---

### Common Windows install failures

#### Symptom: `error C2039: 'GetPrototype' is not a member of 'v8::Object'`

**Cause:** Active Node version is ≥25. Switch to Node 22 LTS (see above) and re-install. The complete error signature also includes:
- `'GetIsolate': is not a member of 'v8::Context'`
- `'This': is not a member of 'v8::PropertyCallbackInfo<v8::Value>'`

#### Symptom: `npm warn cleanup EPERM: operation not permitted, rmdir '…\node_modules\@claude-flow\memory\node_modules\better-sqlite3\build\…'`

**Cascade effect** of a failed native build, not the root cause. Don't waste time chasing AV exclusions — fix the underlying compile error (usually Node version). Once `better-sqlite3` builds clean, the EPERM warnings vanish.

If they persist *after* a clean build:
- Confirm `LongPathsEnabled = 1` (registry key above)
- Close any IDE/Explorer windows that have `node_modules/` open
- Add the project root to Windows Defender exclusions (`Add-MpPreference -ExclusionPath ...`)

#### Symptom: Statusbar `Vectors ●0` despite successful install

The hook silently fails to find the user's memory directory because of Patch 2 not being applied. Run:

```powershell
node .claude/helpers/auto-memory-hook.mjs import
```

If the output is the green `✓ Imported 0 entries` but `.claude-flow/data/import-manifest.json` shows `"memoryHash": null`, the regex in `getMemoryDirHash()` still has the Linux-only `/\//g` pattern — re-apply Patch 2.

#### Symptom: `npm install` succeeds (exit 0) but some `@claude-flow/*` packages have no `package.json`

Specifically: `hooks`, `memory`, `neural` show only an empty `node_modules/` subdir. This is the EPERM cascade from a failed `better-sqlite3` native build. The packages are **never installed**, just stubs. `npm install` falsely reports success because the failure happens during cleanup, not extraction. **Fix:** delete `node_modules/` and `package-lock.json`, switch to Node 22, then `npm install` again.

### Windows-tailored install sequence

Combines [New Project Setup](#new-project-setup) Steps 1–5 with the patches above:

```powershell
# 1. Prerequisite check
node --version          # expect v22.x — if not, `nvm install 22; nvm use 22`
where.exe sh            # expect C:\Program Files\Git\usr\bin\sh.exe
where.exe msbuild       # any VS2022 path

# 2. Clean any prior failed install
if (Test-Path node_modules) { Remove-Item -Recurse -Force node_modules }
if (Test-Path package-lock.json) { Remove-Item -Force package-lock.json }

# 3. Add ruflo dep, install
# (edit package.json to add "ruflo": "^3.6.10" to devDependencies)
npm install

# 4. Apply Patch 2 to .claude/helpers/auto-memory-hook.mjs (HOME fallback + regex)
# Apply Patch 1 to .mcp.json (cmd /c npx wrapper)

# 5. Verify
node .claude/helpers/auto-memory-hook.mjs import     # must say "Imported N entries"
npx ruflo@3.6.10 memory stats                        # must show sql.js + HNSW backend

# 6. Download embedding model (~90 MB, one-time)
npx agentdb install-embeddings
```

Expected total time on a 100 Mbit connection: ~3 minutes (~2 min for `npm install` including native compile, ~1 min for embedding deps).

---

## New Project Setup — ⚠ VERSION REFERENCES HISTORICAL

> **⚠ 2026-07-21:** The structure of this section is still right (the hook needs ruflo in
> local `node_modules/`, npm install, verify the bridge), but use `"ruflo": "^3.30.0"` or
> later — **never** `^3.6.10` — and skip Step 3's "hook patch" (obsolete; stock files are
> correct). Current procedure: [README.md](README.md) § "Fresh setup in a NEW project".

> **Read this first when setting up claude-flow on a fresh project.** The auto-memory bridge has a foundational dependency that the `.mcp.json` and `settings.json` snippets in [Setup Reference](#setup-reference) do **not** cover.

The SessionStart hook (`.claude/helpers/auto-memory-hook.mjs`) loads `@claude-flow/memory` via plain Node module resolution from the project root. The MCP server config in `.mcp.json` is irrelevant to this — that only spawns ruflo as an external MCP process via `npx`. The hook is a separate Node script that needs the package physically present in `node_modules/`.

If the package isn't installed locally, the hook silently no-ops with *"Memory package not available — skipping auto memory import"*. `auto-memory-store.json` is never created, and the statusbar shows `Vectors ●0` forever. See [Vectors stay at 0 — bridge not loaded](#vectors-stay-at-0--bridge-not-loaded) for the diagnostic.

### Step 1 — Add ruflo as a devDependency

```json
{
  "devDependencies": {
    "ruflo": "^3.6.10"
  }
}
```

`ruflo` pulls `@claude-flow/memory` (and `neural`, `hooks`, `embeddings`, etc.) as transitive deps, so a single line covers everything the hook needs.

### Step 2 — Install

```bash
npm install
```

First run takes ~1–2 minutes because `better-sqlite3` compiles natively. Pulls ~900 packages.

If `node_modules/@claude-flow/` already exists as an empty stub directory (from a prior failed install), delete it first: `rm -rf node_modules/@claude-flow && npm install`.

### Step 3 — Apply `.mcp.json`, `settings.json`, and the hook patch

Follow [Setup Reference](#setup-reference) for `.mcp.json` and `npx agentdb install-embeddings`, and [Prevention — auto-memory-hook.mjs bug fix](#prevention--auto-memory-hookmjs-bug-fix-critical) for the 5 changes to the hook script.

### Step 4 — Verify the bridge loads

```bash
# 1. Confirm the package resolves
ls node_modules/@claude-flow/memory/dist/index.js

# 2. Trigger an import manually
node .claude/helpers/auto-memory-hook.mjs import
```

**Success:**

```
[AutoMemory] Importing auto memory files into bridge...
[AutoMemory] ✓ Imported N entries (0 skipped)
  ├─ Backend entries: N
  ├─ Learning: active
  ├─ Graph: active
  └─ Agent scopes: active
```

**Failure (package not installed):**

```
[AutoMemory] Importing auto memory files into bridge...
  Memory package not available — skipping auto memory import
```

After a successful import, `.claude-flow/data/auto-memory-store.json` and `import-manifest.json` exist, and the statusbar `Vectors ●N` reflects the entry count on next session start.

### Step 5 — Commit

```bash
git add package.json package-lock.json
```

The lockfile pins exact versions of `@claude-flow/memory`, `agentdb`, `better-sqlite3`, `sql.js` — required for reproducibility across machines.

---

## Setup Reference — ⚠ HISTORICAL (pinned 3.6.10)

> **⚠ 2026-07-21:** Superseded. Current `.mcp.json` uses `ruflo@latest` with the Windows
> `cmd /c` wrapper and `npm_config_update_notifier=false` — see [README.md](README.md).
> The "pin the version" advice below is dropped; `@latest` matches the nvidia-workshop
> reference setup.

### Project `.mcp.json` (ruflo as MCP server)

```json
{
  "mcpServers": {
    "claude-flow": {
      "command": "npx",
      "args": ["-y", "ruflo@3.6.10", "mcp", "start"],
      "env": {
        "CLAUDE_FLOW_MODE": "v3",
        "CLAUDE_FLOW_HOOKS_ENABLED": "true",
        "CLAUDE_FLOW_TOPOLOGY": "hierarchical-mesh",
        "CLAUDE_FLOW_MAX_AGENTS": "15",
        "CLAUDE_FLOW_MEMORY_BACKEND": "hybrid"
      }
    }
  }
}
```

> Pin the version (`ruflo@3.6.10`) to avoid unexpected re-downloads when `@latest` bumps.

### First-time embedding model download

```bash
# Required for real vector embeddings (~90 MB, one-time download)
npx agentdb install-embeddings
```

Without this, ruflo falls back to mock embeddings and semantic search is non-functional.
