# LibreVNA Python Expert - Agent Memory

## Stuck Connection Cleanup Pattern (Windows)

When LibreVNA-GUI process from a previous script run stays alive, it holds the USB connection
and blocks all new connections. Diagnosis and fix:

1. **Find stale processes:** `Get-Process -Name '*LibreVNA*'` (PowerShell)
2. **Check ports:** `netstat -ano | Select-String '1234|19000|19001|19002|19542'`
3. **Kill:** `Stop-Process -Id <PID> -Force`
4. **Verify:** Re-run port check to confirm all ports freed

Reusable script: `scripts/0_librevna_cleanup.py` (--kill or --force flags)

Key ports: 1234 (SCPI), 19000-19002 (streaming), 19542 (internal TCP)

## PowerShell from Bash on Windows

The bash shell in Claude Code on Windows mangles `$_` (PowerShell pipeline variable).
Workarounds:
- Use `-Name` parameter directly: `Get-Process -Name '*pattern*'`
- Use `Select-String` instead of `Where-Object` for filtering text output
- For complex filtering, write inline PowerShell script blocks or use ConvertTo-Json

## Cal File as Single Source of Truth for Frequency/Points

Since 2026-02-10, frequency range and num_points are extracted from the .cal file
(JSON) rather than sweep_config.yaml.  This prevents sweep/cal boundary mismatches.

- `BaseVNASweep.parse_calibration_file(path)` -- static method on both script 6
  and gui/mvp/vna_backend.py copies.  Returns dict with start_frequency,
  stop_frequency, num_points (all int Hz).
- Cal file JSON path: `measurements[0].data.points[0].frequency` (first),
  `measurements[0].data.points[-1].frequency` (last), `len(points)` (count).
- sweep_config.yaml now only contains: stim_lvl_dbm, avg_count, num_sweeps,
  and target.ifbw_values.
- GUI model uses `SweepConfig.update_from_cal_file()` to populate freq/points
  from the detected cal file at startup and on manual cal file load.
