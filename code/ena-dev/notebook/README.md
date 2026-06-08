# ena-dev / notebook

Post-run analysis notebooks for the E5063A migration. These mirror the LibreVNA
notebooks under `code/LibreVNA-dev/notebook/` but target E5063A data
(`code/ena-dev/data/`).

## Notebooks

| Notebook | Purpose | Data source |
|---|---|---|
| `1_single_vs_continuous_sweep_e5063a.ipynb` | Single vs continuous sweep-rate + measurement-quality comparison across 8 IFBW values (300/150/125/100/75/50/10/1 kHz). E5063A counterpart of `LibreVNA-dev/notebook/3_single_vs_continuous_sweep.ipynb`. | `data/20260602/{single,continuous}_sweep_test_e5063a_real32_20260602_124432.xlsx` (matched pair from one `bench_e5063a_realworld.py` run) |
| `2_sweep_rate_vs_config_e5063a.ipynb` | Instrument sweep-rate vs configuration: rate / mean-sweep-time vs **number of points** (101→1001) and **IFBW** (1→300 kHz); 2-D operating map with 20/25/30 Hz iso-rate contours; analytical sweep-time model fit `mean_ms ≈ c0 + N·(a + b/IFBW)` (R²≈1.0); frequency-span comparison; speed↔quality (noise-floor/jitter) tradeoff; live Monitor-CSV cross-check. Figures → `figures_20260604_sweep_rate/`. | `REPORT/20260604/20260604/` — 11 GUI Sanity-Check `.xlsx` + 2 `bloodvessel_monitor` Dataflux `.csv` (absolute paths in the notebook) |

## Running the notebooks (Jupyter MCP)

The Jupyter MCP server (`.mcp.json` → `jupyter-mcp-server`) connects to a Jupyter
server on `http://localhost:8888` with token `my_secure_token_123`. **Start that
server rooted at `code/`** (not at `LibreVNA-dev/notebook`) so both the LibreVNA
and ena-dev notebook trees are reachable from the MCP tools:

```bash
cd code
uv run jupyter lab --no-browser --port 8888 \
  --IdentityProvider.token=my_secure_token_123 \
  --ServerApp.root_dir="$(pwd)" \
  --ServerApp.disable_check_xsrf=True
```

With this root, Jupyter MCP `notebook_path` values are relative to `code/`, e.g.
`ena-dev/notebook/1_single_vs_continuous_sweep_e5063a.ipynb`.

Python code inside the cells uses **absolute** Windows paths to the xlsx data, so
data loading is independent of the Jupyter root or kernel cwd.

> Note: the project memory historically documented the Jupyter root as
> `code/LibreVNA-dev/notebook`. That root cannot see `ena-dev/notebook`; use the
> `code/`-rooted launch above when working on ena-dev notebooks.
