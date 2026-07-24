# Versioning & Releases — VNA-Project

**Date:** 2026-07-24 · **Applies to:** the E5063A Data Collector GUI (`code/ena-dev/gui/`)
and any future distributable tool in this repo.
**Related:** `docs/e5063a-packaging.md` (how the `.exe` is built),
`docs/e5063a-timestamp-fix-spec.md` (the change driving v1.1.0).

---

## 1. Why version at all

Distributed `.exe` builds live on lab PCs long after the repo moves on. When a
collaborator reports a problem (e.g. the 20260715 timestamp report), the FIRST
question is "which build produced this data?" — versioning answers it from a
screenshot (window title), a filename (release zip), or the Releases tab,
without forensics. Each version's release notes record *why* it exists.

## 2. The scheme — Semantic Versioning `vMAJOR.MINOR.PATCH`

Three digits, each answering a different question for the people using the tool
and analyzing its output:

| Digit | Bump when… | Downstream meaning | Example |
|---|---|---|---|
| **MAJOR** | the **data contract breaks**: CSV/xlsx layout changes that `8_plot_monitor_data.py` / notebooks can't read, or the workflow changes enough to retrain users | "Do NOT update blindly — analysis scripts / habits break" | Dataflux header layout change |
| **MINOR** | new capability, or a **functional change to what gets recorded** (format unchanged) | "Update recommended; recorded data differs materially" | timestamp fix (same CSV layout, truthful timestamps) |
| **PATCH** | bug fixes / cosmetics that do **not** change recorded data | "Safe, drop-in" | UI polish, crash fix |

Plain `v1`/`v2` can't distinguish "safe update" from "your scripts will break" —
that distinction is the whole value for a lab tool. Pre-release builds use a
`-dev` suffix (e.g. `1.1.0-dev`) until tagged.

## 3. Version history (authoritative list)

| Version | Commit | Date | What / why |
|---|---|---|---|
| `v1.0.0` | `f1b0cf3` (retro-tagged) | 2026-06-04 | First field version: packaged GUI G-0…G-15 + G-6 `.exe`. The build behind the professor's 18 h/24 h recordings. **Known issue:** timestamp instability (20260715 report). |
| `v1.1.0` | *(pending)* | *(after live + multi-hour validation)* | Timestamp-integrity fix: QPC (`perf_counter_ns`) stamps at acquisition, streaming Dataflux CSV (bounded RAM, crash-durable), wall-vs-QPC drift audit. Filename stamp now = Start time. |

Keep this table AND `CHANGELOG.md` updated together; the changelog is the
detailed record, this table is the at-a-glance map.

## 4. Single source of truth: `mvp/version.py`

`code/ena-dev/gui/mvp/version.py` holds `__version__` — the ONLY place the
number lives. Consumers:

- **Window title**: `main_window.py` → `E5063A Data Collector v1.1.0` (any
  screenshot identifies the build).
- **Release zip name**: `E5063A-Data-Collector-v<X.Y.Z>-win64.zip` (identifiable
  after the file leaves GitHub — USB, email).
- ⛔ **NOT the Dataflux CSV header** — it is locked to the 12-line
  byte-compatible layout `8_plot_monitor_data.py` expects. Never add lines.

## 5. GitHub Releases — free, this is the sharing channel

- Releases are **free on every account, public AND private repos** (not a paid
  feature). Assets up to **2 GiB per file** — the zipped One-Directory build
  (~<100 MB) fits easily.
- Private repo ⇒ release visible to collaborators only; add the professor /
  labmates as collaborators, or use a public distribution repo.
- Repo: `github.com/jeffrymahbuubi/VNA-Project`.

## 6. Release workflow (checklist)

1. Finish + validate the change (for GUI releases: headless verify + live pass).
2. Bump `mvp/version.py` (drop `-dev`).
3. Update `CHANGELOG.md` (move Unreleased → the new version, date it) and the
   §3 table above.
4. Commit: `chore(release): vX.Y.Z`.
5. Tag: `git tag vX.Y.Z` → `git push origin main --tags` (push only after user
   approval — repo rule).
6. Rebuild the `.exe` per `docs/e5063a-packaging.md`; zip `dist/E5063A-Data-Collector/`
   as `E5063A-Data-Collector-vX.Y.Z-win64.zip`.
7. Create the GitHub Release on the tag (gh CLI or GitHub MCP): title
   `vX.Y.Z — <one-liner>`, notes = the changelog section, attach the zip.
8. Sanity: download the asset on another machine, check the window title shows
   the same version.

## 6.1 Exact commands — releasing v1.1.0 (copy-paste playbook)

Prerequisite once per machine: `gh auth status` shows "Logged in" (it does on
this PC — account `jeffrymahbuubi`). All commands from the repo root
(`CODE/VNA-Project/`) in PowerShell unless noted.

```powershell
# ── 1. Bump the version (drop -dev) ──────────────────────────────
#   Edit code/ena-dev/gui/mvp/version.py →  __version__ = "1.1.0"

# ── 2. Update the records ────────────────────────────────────────
#   CHANGELOG.md : retitle "[Unreleased] — v1.1.0 draft" → "[1.1.0] — YYYY-MM-DD"
#   docs/versioning-and-releases.md §3 : fill v1.1.0's commit + date

# ── 3. Commit + tag + push ───────────────────────────────────────
git add code/ena-dev/gui/mvp/version.py CHANGELOG.md docs/versioning-and-releases.md
git commit -m "chore(release): v1.1.0"
git tag -a v1.1.0 -m "v1.1.0 - timestamp-integrity fix (QPC stamps + streaming CSV)"
git push origin main v1.1.0

# ── 4. Rebuild + zip the exe with the final version ─────────────
cd code\ena-dev\gui
..\..\..\code\.venv\Scripts\pyinstaller.exe --noconfirm E5063A-Data-Collector.spec
Compress-Archive -Path dist\E5063A-Data-Collector `
                 -DestinationPath dist\E5063A-Data-Collector-v1.1.0-win64.zip -Force
#   Sanity: run dist\E5063A-Data-Collector\E5063A-Data-Collector.exe once —
#   title must read "E5063A Data Collector v1.1.0" (no -dev).
cd ..\..\..

# ── 5. Create the GitHub Release with the zip attached ──────────
gh release create v1.1.0 `
  "code\ena-dev\gui\dist\E5063A-Data-Collector-v1.1.0-win64.zip" `
  --title "v1.1.0 - Timestamp-integrity fix" `
  --notes-file release-notes.md          # or: --notes "text..."
#   release-notes.md = the [1.1.0] section copied from CHANGELOG.md
#   (write it anywhere temporary; it is not committed).

# ── 6. Verify ────────────────────────────────────────────────────
gh release view v1.1.0 --web    # opens the release page in the browser
```

Useful variants:

```powershell
gh release list                                  # all releases
gh release edit v1.1.0 --notes-file new.md       # fix the notes afterwards
gh release upload v1.1.0 path\to\extra.zip       # attach another asset
gh release create v1.1.0 --draft ...             # draft first, publish from the web UI
```

Notes-only release (no binary) — how v1.0.0 was published, since its original
2026-06-04 exe was not preserved (dist/ is rebuilt in place and gitignored):

```powershell
gh release create v1.0.0 --title "..." --notes-file notes.md   # tag must already exist
```

## 7. Conventions

- Tags: `vX.Y.Z` (leading `v`), annotated (`git tag -a`).
- Retro-tagging is fine and was used for `v1.0.0` (`git tag -a v1.0.0 f1b0cf3`)
  — the de-facto distributed build deserves a name even though tagging came later.
- `CHANGELOG.md` at repo root, [Keep a Changelog](https://keepachangelog.com)
  format: `Added / Changed / Fixed / Known issues` per version, newest first,
  with an `[Unreleased]` section accumulating work in progress.
