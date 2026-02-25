# MCP Server Setup Commands

Reconstructed `claude mcp add` commands based on `.mcp.json` configuration.
All commands assume `--scope project`.

---

## transcript-api

**Transport:** HTTP
**Note:** API key is hardcoded directly in the config header. Consider moving it to `.env` and using the `--env` pattern instead (see context7 below).

```bash
claude mcp add transcript-api \
  --transport http \
  --header "Authorization: Bearer YOUR_TRANSCRIPT_API_KEY" \
  --scope project \
  https://transcriptapi.com/mcp
```

---

## fetch

**Transport:** stdio via `uvx`

```bash
claude mcp add fetch --scope project -- uvx mcp-server-fetch
```

---

## filesystem

**Transport:** stdio via `npx`
**Note:** The trailing path argument restricts the server to a single project directory.

```bash
claude mcp add filesystem --scope project -- npx -y @modelcontextprotocol/server-filesystem /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer
```

---

## sequentialthinking

**Transport:** stdio via `npx`

> **Fix (2026-02-04):** The package name in `.mcp.json` was `@modelcontextprotocol/server-sequentialthinking`
> (no hyphen). That package does not exist on npm — the correct name is
> `@modelcontextprotocol/server-sequential-thinking` (hyphen between "sequential" and "thinking").
> Both `.mcp.json` and the command below have been corrected.

```bash
claude mcp add sequentialthinking --scope project -- npx -y @modelcontextprotocol/server-sequential-thinking
```

---

## context7

**Transport:** stdio via `npx`
**Note:** API key is stored as a runtime reference (`${CONTEXT7_API_KEY}`), resolved from `.env` when Claude Code starts. The single quotes around the variable prevent shell expansion at setup time.

```bash
claude mcp add context7 \
  --env CONTEXT7_API_KEY='${CONTEXT7_API_KEY}' \
  --scope project \
  -- npx -y @upstash/context7-mcp
```

---

## serena

**Transport:** stdio via `uvx`
**Note:** Serena needs the absolute project path passed via `--project`. On Windows, `$(pwd)` does not expand inside JSON configs, so either hardcode the path or use the shell variable at setup time.

```bash
# PowerShell
claude mcp add serena --scope project -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project "$PWD"
```

```cmd
:: cmd.exe
claude mcp add serena --scope project -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project "%CD%"
```

> **⚠️ Scope note:** Without `--scope project`, `claude mcp add` defaults to **user scope** (`~/.claude.json`).
> `--scope project` writes to `.claude/settings.json`. Both `.claude/settings.json` and `.mcp.json`
> are valid project-level MCP configs read by Claude Code — `.mcp.json` is preferred for
> shareability (already present in this repo).

> **Manual alternative:** Instead of running the CLI command, add the entry directly to `.mcp.json`:
> ```json
> "serena": {
>   "type": "stdio",
>   "command": "uvx",
>   "args": [
>     "--from", "git+https://github.com/oraios/serena",
>     "serena", "start-mcp-server",
>     "--context", "claude-code",
>     "--project", "D:\\path\\to\\your\\project"
>   ],
>   "env": {}
> }
> ```

---

## Recommended: Harden transcript-api

`transcript-api` is the only server with a hardcoded credential in `.mcp.json`. To align it with the context7 pattern:

1. Add the key to `.env`:
   ```
   TRANSCRIPT_API_KEY=<your-key>
   ```

2. Re-add with an env reference. Since this server uses HTTP transport with an `Authorization` header, the cleanest approach is to swap to a stdio setup if the package supports it, or accept that HTTP transport headers cannot use `${...}` references and manage the key via shell expansion at setup time:
   ```bash
   claude mcp add transcript-api \
     --transport http \
     --header "Authorization: Bearer $TRANSCRIPT_API_KEY" \
     --scope project \
     https://transcriptapi.com/mcp
   ```
   This expands `$TRANSCRIPT_API_KEY` from the environment at the time the command runs and stores the resolved value — same as the current state, but keeps the source of truth in `.env`.
