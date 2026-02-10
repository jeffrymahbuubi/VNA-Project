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
