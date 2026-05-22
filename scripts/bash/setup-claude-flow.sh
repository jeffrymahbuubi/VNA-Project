#!/bin/bash
# setup-claude-flow.sh
# One-shot setup for a new claude-flow project.
#
# What it does (idempotent — safe to re-run):
#   1. Generates the Claude Code scaffold (.claude/agents, .claude/commands,
#      .claude/skills) via `ruflo init --only-claude` if missing. This is what
#      gives Claude Code the preconfigured subagents and slash commands; the
#      MCP server alone does not provide them.
#   2. Sweeps stale npm rename artifacts from the shared npx cache that cause
#      ENOTEMPTY errors and -32000 MCP connection failures.
#   3. Pre-warms the @claude-flow/cli@latest install in one uninterrupted run
#      so the first Claude Code session does not race with npm.
#   4. Installs the AgentDB embedding model (~90 MB, one-time) needed for real
#      vector search instead of mock embeddings.
#   5. Verifies the MCP server actually starts (stdio handshake, then kill).
#
# Run this on any new project (replaces the older "run ruflo init first" step)
# and re-run any time `-32000` reappears or the scaffold goes missing.
#
# Usage:
#   ./scripts/setup-claude-flow.sh

set -euo pipefail

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[setup]${NC} $*"; }
ok()    { echo -e "${GREEN}[ ok ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
fail()  { echo -e "${RED}[fail]${NC} $*" >&2; }

# --- 1. Generate Claude Code scaffold (.claude/agents, commands, skills) -----
# The MCP server (.mcp.json) and the Claude Code scaffold (.claude/*) are two
# independent layers. A project can have a healthy MCP connection but still be
# missing the subagent and slash-command markdown files — those come from
# `ruflo init`, not from the MCP server.
#
# `--only-claude` scopes the init to the .claude/* scaffold and skips runtime.
# `--force` is required: ruflo refuses to init when `.claude/settings.json` or
# `.claude-flow/config.yaml` already exist, and both are present in any project
# that has already had the MCP layer set up.
#
# Because --force WILL overwrite settings.json, settings.local.json, and the
# patched helpers/* files (notably auto-memory-hook.mjs with the
# --skip-if-exists fix), we snapshot the whole `.claude/` directory before
# init and restore the patched bits afterwards.
info "Checking Claude Code scaffold (.claude/agents)…"
if [ ! -d ".claude/agents" ]; then
  info "Scaffold missing — running 'ruflo init --only-claude --force'…"
  CLAUDE_BACKUP=""
  if [ -d ".claude" ]; then
    CLAUDE_BACKUP=$(mktemp -d)
    cp -a .claude/. "$CLAUDE_BACKUP/"
  fi
  if npx -y @claude-flow/cli@latest init --only-claude --force >/dev/null 2>&1; then
    # Restore patched files that may have been overwritten by --force.
    if [ -n "$CLAUDE_BACKUP" ]; then
      for f in settings.json settings.local.json; do
        if [ -f "$CLAUDE_BACKUP/$f" ]; then
          cp "$CLAUDE_BACKUP/$f" ".claude/$f"
        fi
      done
      if [ -d "$CLAUDE_BACKUP/helpers" ]; then
        cp -a "$CLAUDE_BACKUP/helpers/." ".claude/helpers/"
      fi
      rm -rf "$CLAUDE_BACKUP"
    fi
    ok "Scaffold generated; restored patched settings.json + helpers/."
  else
    [ -n "$CLAUDE_BACKUP" ] && rm -rf "$CLAUDE_BACKUP"
    fail "ruflo init failed. Inspect with: npx ruflo@latest init --only-claude --force"
    exit 1
  fi
else
  ok "Scaffold present — skipping init."
fi

# --- 1b. Install all skills if .claude/skills/ is empty ----------------------
# `init --only-claude` creates the agents/ and commands/ trees but does not
# populate skills/. Skills are installed via the dedicated subcommand.
#
# Pinned to 3.6.27 on purpose: `@latest` resolves to the v3 alpha track
# (3.7.0-alpha.*), where `init skills --all` reports "Installed 0 skills" —
# a regression confirmed against 3.7.0-alpha.69 on 2026-05-19. 3.6.27 is the
# highest stable release and installs ~33 skills. Once the alpha track ships
# a working skills installer, revert to @latest. The MCP runtime is still
# pulled from @latest elsewhere in this script and in .mcp.json — only this
# one-off content generation is pinned.
SKILLS_INSTALLER_VERSION="3.6.27"
SKILL_COUNT=$(ls .claude/skills 2>/dev/null | wc -l || echo 0)
SKILL_COUNT="${SKILL_COUNT:-0}"
if [[ "$SKILL_COUNT" =~ ^[0-9]+$ ]] && [ "$SKILL_COUNT" -lt 5 ]; then
  info "Installing all skills via @claude-flow/cli@${SKILLS_INSTALLER_VERSION} (alpha installer is broken)…"
  if npx -y "@claude-flow/cli@${SKILLS_INSTALLER_VERSION}" init skills --all >/dev/null 2>&1; then
    NEW_COUNT=$(ls .claude/skills 2>/dev/null | wc -l || echo 0)
    if [ "$NEW_COUNT" -ge 5 ]; then
      ok "Skills installed (${NEW_COUNT} entries)."
    else
      warn "Skill install completed but only ${NEW_COUNT} entries present."
    fi
  else
    warn "Skill install reported non-zero exit. Inspect: npx @claude-flow/cli@${SKILLS_INSTALLER_VERSION} init skills --all"
  fi
else
  ok "Skills present (${SKILL_COUNT} entries) — skipping."
fi

# --- 2. Sweep stale npx cache rename artifacts -------------------------------
# These come from interrupted/parallel `npx -y @claude-flow/cli@latest` installs
# across sibling projects. Pattern: .{name}-{8 random alphanumeric chars}.
# Safe: only matches npm's atomic-rename leftovers, not legitimate dotdirs.
#
# No -maxdepth: nested deps (e.g. node_modules/ruvector/node_modules/@ruvector/
# .attention-XXXXXXXX) live at depth 6+. Earlier versions of this script used
# -maxdepth 4 and silently missed them, causing pre-warm to fail repeatedly.
#
# `|| echo 0` guards against transient find errors yielding an empty
# STALE_COUNT under `set -euo pipefail`, which previously made the script
# misreport "Cache is clean" when artifacts actually existed.
info "Sweeping stale npx cache rename artifacts…"
NPX_ROOT="${HOME}/.npm/_npx"
if [ -d "$NPX_ROOT" ]; then
  STALE_COUNT=$(find "$NPX_ROOT" -type d \
    -regex '.*/\.[^/]+-[A-Za-z0-9]\{8\}$' 2>/dev/null | wc -l || echo 0)
  STALE_COUNT="${STALE_COUNT:-0}"
  if [[ "$STALE_COUNT" =~ ^[0-9]+$ ]] && [ "$STALE_COUNT" -gt 0 ]; then
    find "$NPX_ROOT" -type d \
      -regex '.*/\.[^/]+-[A-Za-z0-9]\{8\}$' -exec rm -rf {} + 2>/dev/null || true
    ok "Removed $STALE_COUNT stale artifact(s)."
  else
    ok "Cache is clean — nothing to remove."
  fi
else
  warn "No npx cache yet at $NPX_ROOT — first run will create it."
fi

# --- 3. Pre-warm @claude-flow/cli@latest -------------------------------------
# Running --version in a controlled terminal forces npm to finish writing the
# full dependency tree without another Claude Code session interrupting it.
info "Pre-warming @claude-flow/cli@latest (this can take a few minutes the first time)…"
if npx -y @claude-flow/cli@latest --version >/dev/null 2>&1; then
  CF_VERSION=$(npx -y @claude-flow/cli@latest --version 2>/dev/null | tail -n 1)
  ok "@claude-flow/cli ready (version: ${CF_VERSION:-unknown})."
else
  fail "Pre-warm failed. Re-run this script; transient npm errors usually clear on retry."
  exit 1
fi

# --- 4. Install AgentDB embedding model --------------------------------------
# Without this, ruflo falls back to mock embeddings and semantic search is
# non-functional. Idempotent — re-running is a no-op.
info "Installing AgentDB embedding model (one-time, ~90 MB)…"
if npx -y agentdb install-embeddings >/dev/null 2>&1; then
  ok "Embedding model installed."
else
  warn "Embedding install reported non-zero exit — semantic search may use mock embeddings."
  warn "Run manually to inspect: npx agentdb install-embeddings"
fi

# --- 5. Verify MCP server actually starts ------------------------------------
# The MCP server is a long-running stdio process. We start it, wait briefly,
# and confirm it stayed alive (no immediate crash). SIGTERM is the success
# signal here — it means the server was running and we killed it cleanly.
#
# `sleep 30 | npx …` holds the server's stdin open. Without it, the MCP
# server immediately reads EOF on stdin and exits cleanly, producing a false
# negative ("MCP server exited immediately") even though the server itself
# is healthy.
info "Verifying MCP server starts cleanly…"
MCP_LOG=$(mktemp)
sleep 30 | npx -y @claude-flow/cli@latest mcp start >"$MCP_LOG" 2>&1 &
MCP_PID=$!
sleep 4
if kill -0 "$MCP_PID" 2>/dev/null; then
  kill "$MCP_PID" 2>/dev/null || true
  wait "$MCP_PID" 2>/dev/null || true
  ok "MCP server started and accepted stdio — setup complete."
  rm -f "$MCP_LOG"
else
  fail "MCP server exited immediately. Log:"
  cat "$MCP_LOG" >&2
  rm -f "$MCP_LOG"
  exit 1
fi

echo
ok "Done. Next steps:"
echo "    1. Open Claude Code in this project."
echo "    2. Run /mcp and confirm claude-flow shows as connected."
echo "    3. If you ever see '-32000' again, re-run this script."
