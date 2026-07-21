# claude-flow (ruflo) — Setup & Maintenance Guide

> **START HERE.** This is the entry point for any future Claude Code session that needs to
> set up, upgrade, or troubleshoot the ruflo/claude-flow tooling in this project (or bootstrap
> it in a new one). It reflects the **post-3.32 reality** — the era of hand-patching ruflo
> files on Windows is over.
>
> Last verified: **2026-07-21**, ruflo **3.32.9**, Windows 11 Pro 22631, Node 22.

---

## Current state of this project

Upgraded 2026-07-21 from ruflo 3.6.30 → **3.32.9** (mirroring the `nvidia-workshop` project's
setup). All helpers are **stock upstream files** — no local patches.

| Item | State |
|---|---|
| `package.json` | `"ruflo": "^3.32.9"` in `devDependencies` |
| `.mcp.json` → `claude-flow` entry | `cmd /c npx -y ruflo@latest mcp start`, V3 env (hierarchical-mesh, 15 agents, hybrid memory) |
| `.claude/helpers/` | Stock files written by `init upgrade` (version marker: `.claude/helpers/.helpers-version`) |
| `.claude/settings.json` | Custom SessionStart import hooks + rashomon plugin **preserved**; Agent Teams + SessionEnd sync **merged in** by `init upgrade --settings` |
| `.claude-flow/config.yaml` | V3 runtime config (modeled on nvidia-workshop) |
| Memory | `.swarm/memory.db` — 32 entries verified intact across the upgrade |
| Pre-upgrade backup | `.backups/ruflo-upgrade-20260721/` (gitignored) — includes before/after memory listings |

## The one rule that matters: protect the memory

ruflo's persistent state lives in files that no reinstall should ever touch:

| Path | What it holds |
|---|---|
| `.swarm/memory.db` (+ `-wal`, `-shm`) | **The vector memory store** (sql.js + HNSW). The crown jewels. |
| `.claude-flow/data/` | Auto-memory bridge store + import manifest |
| `.claude-flow/sessions/` | Session snapshots |
| `.claude/agent-memory/` | Per-agent memory files (git-tracked) |
| `~/.claude/projects/<encoded-path>/memory/` | Claude Code's own file-based memory (outside the repo; ruflo only *reads* it via the auto-memory hook) |

**Before any ruflo version change:** back up `.swarm/`, `.claude-flow/`, `.claude/`,
`CLAUDE.md`, `.mcp.json` to a dated folder under `.backups/`, and snapshot
`npx ruflo memory stats` + `npx ruflo memory list` output for post-upgrade comparison.

## Upgrading ruflo (verified procedure, 2026-07-21)

```bash
# 0. Backup (see above) + baseline
npx ruflo memory stats          # note the entry count
npx ruflo memory list > .backups/<date>/memory-list-BEFORE.txt

# 1. Update the local package
npm install -D ruflo@latest

# 2. Merge-based upgrade of helpers/skills/settings — NEVER `init --force`
npx ruflo init upgrade --add-missing --settings --verbose

# 3. Point .mcp.json at the new version (edit the claude-flow entry to ruflo@latest)

# 4. Verify
npx ruflo memory stats          # count must match step 0
npx ruflo memory list > .backups/<date>/memory-list-AFTER.txt && diff the two
npx ruflo memory search -q "anything relevant"   # HNSW semantic search works
npx ruflo doctor                # expect pass w/ only optional-feature warnings
```

`init upgrade` is additive and merge-based: it updates the four core helpers
(`auto-memory-hook.mjs`, `hook-handler.cjs`, `intelligence.cjs`, `statusline.cjs`),
adds missing skills/agents/commands, and *merges* new settings into
`.claude/settings.json` without removing custom hooks or plugins. It does **not**
touch `CLAUDE.md`, `.mcp.json`, `.swarm/`, or custom agent `.md` files.

⛔ **Never run `npx ruflo init --force` in this project.** It overwrites `CLAUDE.md`
(18 KB of project instructions), `.claude/settings.json`, and `.mcp.json` (8 servers,
only one of which is claude-flow).

## Fresh setup in a NEW project (latest version)

```bash
# 1. package.json: add "ruflo": "^3.30.0" (or later) to devDependencies, then:
npm install

# 2. Initialize (fresh project only — no files to clobber yet)
npx ruflo init

# 3. Register the MCP server — .mcp.json entry (Windows needs the cmd /c wrapper):
#  "claude-flow": {
#    "type": "stdio",
#    "command": "cmd",
#    "args": ["/c", "npx", "-y", "ruflo@latest", "mcp", "start"],
#    "env": {
#      "npm_config_update_notifier": "false",
#      "CLAUDE_FLOW_MODE": "v3",
#      "CLAUDE_FLOW_HOOKS_ENABLED": "true",
#      "CLAUDE_FLOW_TOPOLOGY": "hierarchical-mesh",
#      "CLAUDE_FLOW_MAX_AGENTS": "15",
#      "CLAUDE_FLOW_MEMORY_BACKEND": "hybrid"
#    }
#  }

# 4. Health check
npx ruflo doctor --fix
```

No patches are required on Windows anymore (see "What changed since 3.6.x" below).
Prerequisites that still apply: **Node 22 LTS** (native `better-sqlite3` build — Node ≥25
broke it in the 3.6 era; re-verify before trying a newer Node), **Git for Windows**
(`sh.exe` for the settings hooks), and MSVC build tools if no prebuilt binary matches.

## What changed since 3.6.x (why the old docs are historical)

The 3.6-era setup (documented in [claude-flow-101.md](claude-flow-101.md)) required three
hand-applied Windows patches plus a five-change bug fix to `auto-memory-hook.mjs`
(`--skip-if-exists` handling, `USERPROFILE` fallback, Windows project-key regex).
**Upstream absorbed all of it.** Evidence: the `nvidia-workshop` project (July 2026) runs
fully stock helpers whose hashes match ruflo's signed helper manifest, and this project's
2026-07-21 upgrade replaced the patched helpers with stock ones — memory imports,
skip-if-exists dedup, and the statusline all work unmodified on Windows.

Consequences:
- `archive/auto-memory-hook.mjs` (the old "canonical patched copy") must **never** be
  copied over `.claude/helpers/` again — it would downgrade a working stock file.
- The "re-apply patches after every init" ritual is dead; `init upgrade` replaced it.
- Version pinning in `.mcp.json` (once recommended) is dropped in favor of `ruflo@latest`.

## Daemon = token cost — opt-in only

`npx ruflo daemon start` runs interval workers that each spawn a **headless claude session**
(continuous token consumption). It is NOT started by default and `ruflo doctor` may create a
transient one during checks — confirm with `npx ruflo daemon status --all`. Start it only
deliberately; it self-stops after 12 h by default.

## Doc map

| File | Status | Use for |
|---|---|---|
| `README.md` (this file) | **Current** (2026-07-21, 3.32.9) | Setup, upgrade, memory safety |
| `claude-flow-101.md` | Command reference **current**; setup/patch sections **HISTORICAL** (banners inline) | CLI/MCP command lookup; 3.6-era archaeology |
| `claude-flow-memory-guide.md` | Current (concepts) | Memory/session workflow inside Claude Code |
| `claude-flow-sparc-guide.md` | Current (concepts) | SPARC modes and swarm usage patterns |
| `archive/auto-memory-hook.mjs` | **OBSOLETE** — do not restore | Historical reference only |
| `archive/settings.json` | **OBSOLETE** — superseded by live `.claude/settings.json` | Historical reference only |
