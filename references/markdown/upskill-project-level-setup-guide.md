# Upskill Project-Level Setup Guide

**Date:** 2026-02-25
**Context:** How to install and configure HuggingFace `upskill` at the project level to improve existing Claude Code skills in `.claude/skills/`

---

## What is Upskill?

`upskill` is an open-source tool by HuggingFace for generating, evaluating, and refining **agent skills** — the `SKILL.md` instruction files used by AI code agents like Claude Code.

Key capability: it can take an **existing skill directory** and improve its `SKILL.md` by using a teacher model (e.g., Sonnet) to rewrite it, then evaluating the result against synthetic test cases.

- GitHub: https://github.com/huggingface/upskill
- Works with: Anthropic (Claude), OpenAI, and local models

---

## Project-Level vs Global Setup

| Thing | Global | Project-Level |
|---|---|---|
| `ANTHROPIC_API_KEY` | System environment variable | `.env` file in project root |
| `upskill.config.yaml` | `~/.config/upskill/config.yaml` | Project root (auto-detected) |
| `fastagent.config.yaml` | N/A | Project root (auto-detected) |
| `upskill` binary | `pip install upskill` globally | `uvx upskill` (no install) or `uv add upskill` |

**Recommendation:** Use project-level for everything. This keeps API keys isolated, config version-controlled, and avoids polluting the global Python environment.

---

## Step 1 — Install Upskill (Project-Level)

### Option A: No Install — Run with `uvx` (Recommended)

`uvx` runs a tool in an isolated temporary environment without installing it into your project:

```bash
uvx upskill --help
```

No `pyproject.toml` changes needed. Just run it when needed.

### Option B: Install into Project Venv

If you want `upskill` as a project dependency (e.g., for CI or reproducibility):

```bash
uv add --dev upskill
```

Then run via:

```bash
uv run upskill --help
```

---

## Step 2 — Set API Key at Project Level (`.env` file)

Instead of setting `ANTHROPIC_API_KEY` as a system environment variable, create a `.env` file in your **project root**:

```
# .env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

`upskill` is built on FastAgent which reads `.env` files automatically via `python-dotenv`. The key is loaded when you run `upskill` from the project directory.

### Protect the key — add to `.gitignore`

```
# .gitignore
.env
```

**Verify your `.gitignore` has this before committing anything.**

### If using Option B (`uv run`), use `--env-file` for explicit loading:

```bash
uv run --env-file .env upskill generate ...
```

This guarantees the `.env` is loaded even if `python-dotenv` auto-discovery fails.

---

## Step 3 — Create `upskill.config.yaml` in Project Root

This file controls which models to use, where skills live, and where logs go.

Create `upskill.config.yaml` at your project root:

```yaml
# upskill.config.yaml

# Teacher model: generates and refines the SKILL.md
skill_generation_model: sonnet

# Student model: evaluated against the skill (cheaper)
eval_model: haiku

# Point to your existing Claude Code skills directory
skills_dir: .claude/skills

# Where evaluation run logs are stored
runs_dir: .claude/upskill-runs

# How many refinement attempts before giving up
max_refine_attempts: 3
```

**Key line:** `skills_dir: .claude/skills` — this tells `upskill list` and `upskill eval` to use your existing skills instead of a separate `./skills/` folder.

### Config lookup order (upskill checks these in order):

1. `UPSKILL_CONFIG` environment variable (path to config file)
2. `./upskill.config.yaml` (project root — this is what we use)
3. `~/.config/upskill/config.yaml` (global fallback)

---

## Step 4 — (Optional) Create `fastagent.config.yaml`

FastAgent is the agent framework underlying `upskill`. You can customize its behavior:

```yaml
# fastagent.config.yaml

default_model: sonnet
logger:
  progress_display: true
  show_chat: false
  streaming: markdown
```

Place this in the project root alongside `upskill.config.yaml`. It is optional — defaults work fine.

---

## Step 5 — Back Up Your Skills Before Improving

`upskill generate --from` **overwrites** your `SKILL.md`. Always commit first:

```bash
git add .claude/skills/
git commit -m "backup: skills before upskill refinement"
```

---

## Step 6 — Verify Setup

List your existing skills to confirm `upskill` can find them:

```bash
uvx upskill list
```

Expected output:
```
.claude/skills
├── matplotlib
│   ├── Low-level plotting library for full customization...
│   └── files
│       └── SKILL.md
├── exploratory-data-analysis
│   ├── Perform comprehensive exploratory data analysis...
│   └── files
│       └── SKILL.md
└── ...
```

If your skills appear, the setup is working correctly.

---

## Step 7 — Improve an Existing Skill

### Basic improvement (uses config defaults):

```bash
uvx upskill generate "add more examples and edge cases" \
  --from .claude/skills/matplotlib/
```

### Explicit model selection:

```bash
uvx upskill generate "improve error handling guidance" \
  --model sonnet \
  --eval-model haiku \
  --from .claude/skills/exploratory-data-analysis/
```

### Generate without evaluation (cheaper, faster):

```bash
uvx upskill generate "add RF/VNA-specific examples" \
  --from .claude/skills/exploratory-data-analysis/ \
  --no-eval
```

### What happens during generation:

1. Reads your existing `SKILL.md`
2. Teacher model (Sonnet) rewrites/expands it based on your goal
3. Generates synthetic test cases for the skill
4. Evaluates: measures **baseline** (no skill) vs **with skill** pass rate
5. Iterates up to `max_refine_attempts` times until improvement is found
6. Overwrites `SKILL.md` with the improved version

### Example output:

```
Generating skill with sonnet...
Generating test cases...
Evaluating on haiku... (attempt 1)
60% -> 85% (+25%) OK

matplotlib
Low-level plotting library for full customization.

SKILL.md  ~620 tokens

baseline  ████████████░░░░░░░░  60%
with skill ████████████████░░░░  85% (+25%)
tokens: 1200 → 900 (-25%)

Saved to .claude/skills/matplotlib
```

---

## Step 8 — View Evaluation Results

After running, review how much the skill improved:

```bash
# View results for a specific skill
uvx upskill runs --skill matplotlib

# Compare across models
uvx upskill runs --skill matplotlib -m haiku -m sonnet

# Export to CSV
uvx upskill runs --csv .claude/upskill-runs/results.csv
```

---

## Project File Structure After Setup

```
VNA-Project/                         ← project root
├── .env                             ← API key (gitignored)
├── upskill.config.yaml              ← upskill config (committed)
├── fastagent.config.yaml            ← fastagent config (committed, optional)
├── .gitignore                       ← must include .env
│
└── .claude/
    ├── skills/                      ← your existing skills (unchanged)
    │   ├── matplotlib/
    │   │   └── SKILL.md             ← gets overwritten on improve
    │   ├── exploratory-data-analysis/
    │   │   └── SKILL.md
    │   └── ...
    └── upskill-runs/                ← evaluation logs (auto-created)
        └── 2026_02_25_10_30/
            ├── run_1/
            │   ├── run_metadata.json
            │   └── run_result.json
            └── batch_summary.json
```

---

## What Gets Modified vs What Is Safe

| File/Folder | Modified by upskill? | Notes |
|---|---|---|
| `SKILL.md` | **Yes — overwritten** | Commit before running |
| `references/` | No | Untouched |
| `scripts/` | No | Untouched |
| `assets/` | No | Untouched |
| `.env` | No | You manage this |
| `upskill.config.yaml` | No | You manage this |

---

## Quick Reference — Common Commands

```bash
# List all skills
uvx upskill list

# Improve a skill (with eval)
uvx upskill generate "your improvement goal" --from .claude/skills/<skill-name>/

# Improve a skill (no eval, cheaper)
uvx upskill generate "your improvement goal" --from .claude/skills/<skill-name>/ --no-eval

# Evaluate a skill without changing it
uvx upskill eval .claude/skills/<skill-name>/

# Benchmark across models
uvx upskill eval .claude/skills/<skill-name>/ -m haiku -m sonnet --runs 3

# View past results
uvx upskill runs --skill <skill-name>
```

---

## Troubleshooting

### API key not found

**Error:**
```
AuthenticationError: No API key provided
```

**Solution:**
- Check `.env` exists in the directory where you run `upskill`
- Verify content: `ANTHROPIC_API_KEY=sk-ant-...` (no quotes, no spaces)
- Use explicit env loading: `uv run --env-file .env upskill ...`

---

### Skills not found / wrong directory

**Error:**
```
No skills found in ./skills/
```

**Solution:**
- Check `upskill.config.yaml` has `skills_dir: .claude/skills`
- Verify you are running from the project root (not a subdirectory)
- Or pass path explicitly: `uvx upskill list -d .claude/skills/`

---

### SKILL.md accidentally overwritten

**Solution:**
```bash
# Restore from git
git checkout .claude/skills/<skill-name>/SKILL.md
```

This is why committing before running is essential.

---

## Summary: Minimum Setup Checklist

- [ ] Create `.env` with `ANTHROPIC_API_KEY=sk-ant-...`
- [ ] Add `.env` to `.gitignore`
- [ ] Create `upskill.config.yaml` with `skills_dir: .claude/skills`
- [ ] Commit current skills: `git add .claude/skills/ && git commit -m "backup: skills"`
- [ ] Verify: `uvx upskill list` shows your skills
- [ ] Run improvement: `uvx upskill generate "..." --from .claude/skills/<name>/`

---

**Last Updated:** 2026-02-25
**Project:** LibreVNA Vector Network Analyzer
**Reference:** https://github.com/huggingface/upskill
