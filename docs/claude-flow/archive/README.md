# Archive — 3.6-era claude-flow files (OBSOLETE)

Moved here 2026-07-21 during the ruflo 3.6.30 → 3.32.9 upgrade. Kept for historical
reference only.

- **`auto-memory-hook.mjs`** — the hand-patched "canonical copy" from the 3.6 era
  (skip-if-exists fix, USERPROFILE fallback, Windows project-key regex). Upstream absorbed
  all of these fixes. ⛔ **Do NOT copy this over `.claude/helpers/auto-memory-hook.mjs`** —
  the live file is a newer stock version maintained by `npx ruflo init upgrade`.
- **`settings.json`** — 3.6-era reference copy of the hook wiring. Superseded by the live
  `.claude/settings.json`, which `init upgrade --settings` now maintains by merging.

See `../README.md` for current setup and upgrade procedure.
