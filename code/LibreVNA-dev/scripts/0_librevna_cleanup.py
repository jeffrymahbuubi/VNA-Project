#!/usr/bin/env python3
"""
0_librevna_cleanup.py
---------------------
Diagnostic and cleanup utility for stuck LibreVNA connections on Windows.

When a previous script exits uncleanly (crash, KeyboardInterrupt, debugger
detach), the LibreVNA-GUI process can remain running and hold the USB
connection to the instrument.  This prevents any new script from connecting.

What it does (in order):
  1. Scans for running LibreVNA-GUI.exe processes.
  2. Checks whether the SCPI port (1234), streaming ports (19000-19002),
     and internal port (19542) are in use and by which PID.
  3. Reports a full diagnostic table.
  4. Optionally terminates stale LibreVNA-GUI processes (with --kill flag).
  5. Verifies that all ports have been freed after termination.

Usage:
    uv run python 0_librevna_cleanup.py                 # diagnose only (safe)
    uv run python 0_librevna_cleanup.py --kill           # diagnose + kill stale LibreVNA-GUI processes
    uv run python 0_librevna_cleanup.py --force          # kill ALL LibreVNA-GUI instances
    uv run python 0_librevna_cleanup.py --kill-ports     # kill ANY process using LibreVNA ports

Notes:
    - "Diagnose only" mode never terminates anything.  It is always safe to
      run without arguments.
    - The --kill flag terminates only LibreVNA-GUI processes that match the
      expected binary path under this project tree.
    - The --force flag terminates ALL LibreVNA-GUI.exe processes regardless
      of path.  Use with care if you have multiple LibreVNA installations.
    - The --kill-ports flag terminates ANY process holding LibreVNA ports,
      regardless of process name.  Use when ports are blocked by other apps.
"""

import argparse
import os
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Expected binary path (for --kill safety check)
EXPECTED_GUI_PATH = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "tools", "LibreVNA-GUI", "release", "LibreVNA-GUI.exe")
)

# Ports used by LibreVNA-GUI
LIBREVNA_PORTS = {
    1234:  "SCPI server",
    19000: "VNA Raw streaming",
    19001: "VNA Calibrated streaming",
    19002: "VNA De-embedded streaming",
    19542: "Internal LibreVNA TCP",
}

SEPARATOR = "-" * 72


# ---------------------------------------------------------------------------
# Helpers — process and port discovery via PowerShell
# ---------------------------------------------------------------------------

def run_powershell(command: str) -> str:
    """Run a PowerShell command and return its stdout."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


def find_librevna_processes() -> list[dict]:
    """Return a list of dicts with Id, ProcessName, Path, StartTime for
    every running LibreVNA-GUI.exe process."""
    # PowerShell script block avoids bash variable interpolation issues
    ps_script = (
        "Get-Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.ProcessName -like '*LibreVNA*' } | "
        "Select-Object Id, ProcessName, Path, StartTime | "
        "ConvertTo-Json -Compress"
    )
    raw = run_powershell(ps_script)
    if not raw:
        return []

    import json
    data = json.loads(raw)
    # PowerShell returns a single object (not list) when there is exactly one match
    if isinstance(data, dict):
        data = [data]
    return data


def find_port_owners() -> dict[int, dict]:
    """Return {port: {pid, state, protocol}} for each LibreVNA port that is
    currently in use."""
    # Get all netstat output without pre-filtering to avoid false matches
    ps_script = "netstat -ano"
    raw = run_powershell(ps_script)
    if not raw:
        return {}

    results = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue

        # Skip header lines
        if parts[0] not in ("TCP", "UDP"):
            continue

        proto = parts[0]        # TCP or UDP
        local = parts[1]        # e.g. 0.0.0.0:19001
        state = parts[3] if proto == "TCP" else "N/A"

        try:
            pid = int(parts[-1])
        except ValueError:
            continue

        # Extract port number from local address
        try:
            port = int(local.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue

        # Only include ports we care about, first match wins
        if port in LIBREVNA_PORTS and port not in results:
            results[port] = {"pid": pid, "state": state, "protocol": proto}

    return results


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------

def diagnose() -> tuple[list[dict], dict[int, dict]]:
    """Run full diagnostic and print results.  Returns (processes, port_owners)."""
    print(SEPARATOR)
    print("  LibreVNA Connection Diagnostic")
    print(SEPARATOR)
    print()

    # -- Processes --
    processes = find_librevna_processes()
    print(f"[1] LibreVNA-GUI processes: {len(processes)} found")
    if processes:
        for proc in processes:
            pid = proc.get("Id", "?")
            name = proc.get("ProcessName", "?")
            path = proc.get("Path", "unknown")
            start = proc.get("StartTime", "unknown")
            # PowerShell datetime comes as "/Date(...)/" — simplify display
            if isinstance(start, str) and start.startswith("/Date("):
                import datetime
                ms = int(start.split("(")[1].split(")")[0].split("+")[0].split("-")[0])
                start = datetime.datetime.fromtimestamp(ms / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            print(f"      PID {pid:>6}  {name}")
            print(f"               Path:  {path}")
            print(f"               Start: {start}")
    else:
        print("      (none)")
    print()

    # -- Ports --
    port_owners = find_port_owners()
    print(f"[2] LibreVNA port status:")
    for port, label in sorted(LIBREVNA_PORTS.items()):
        if port in port_owners:
            info = port_owners[port]
            status = f"IN USE  (PID {info['pid']}, {info['state']}, {info['protocol']})"
        else:
            status = "FREE"
        print(f"      :{port:<6} {label:<30} {status}")
    print()

    # -- Summary --
    if not processes and not port_owners:
        print("[*] RESULT: All clear.  No stale LibreVNA processes or ports detected.")
        print("    You should be able to start a new sweep script without issues.")
    elif processes:
        pids = [str(p["Id"]) for p in processes]
        print(f"[!] RESULT: Stale LibreVNA-GUI detected (PID {', '.join(pids)}).")
        print("    This is likely blocking new connections to the instrument.")
        print("    Re-run with --kill to terminate, or --force to kill all instances.")
    else:
        print("[?] RESULT: No LibreVNA-GUI process found, but ports are occupied.")
        print("    Another application may be using these ports.")

    print()
    return processes, port_owners


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------

def get_process_name(pid: int) -> str:
    """Get the process name for a given PID."""
    try:
        ps_script = f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).ProcessName"
        result = run_powershell(ps_script)
        return result if result else "unknown"
    except Exception:
        return "unknown"


def kill_processes(processes: list[dict], force: bool = False) -> int:
    """Terminate LibreVNA-GUI processes.

    With force=False, only kills processes whose path matches the expected
    binary location.  With force=True, kills all of them.

    Returns the number of processes terminated.
    """
    killed = 0
    for proc in processes:
        pid = proc.get("Id")
        path = proc.get("Path", "")

        if not force:
            # Safety check: only kill if the path matches our project tree
            if path and os.path.normpath(path) != EXPECTED_GUI_PATH:
                print(f"  SKIP PID {pid} — path does not match project binary:")
                print(f"         Expected: {EXPECTED_GUI_PATH}")
                print(f"         Actual:   {path}")
                continue

        print(f"  Terminating PID {pid} ...", end=" ")
        try:
            run_powershell(f"Stop-Process -Id {pid} -Force")
            print("OK")
            killed += 1
        except Exception as exc:
            print(f"FAILED: {exc}")

    return killed


def kill_port_users(port_owners: dict[int, dict]) -> int:
    """Terminate processes using LibreVNA ports.

    Returns the number of processes terminated.
    """
    if not port_owners:
        return 0

    # Collect unique PIDs
    pids_to_kill = set(info["pid"] for info in port_owners.values())
    killed = 0

    for pid in pids_to_kill:
        # Find which ports this PID is using
        ports_used = [port for port, info in port_owners.items() if info["pid"] == pid]
        port_list = ", ".join(f":{p}" for p in sorted(ports_used))

        proc_name = get_process_name(pid)
        print(f"  Terminating PID {pid} ({proc_name}) using ports {port_list} ...", end=" ")

        try:
            run_powershell(f"Stop-Process -Id {pid} -Force")
            print("OK")
            killed += 1
        except Exception as exc:
            print(f"FAILED: {exc}")

    return killed


def verify_cleanup() -> bool:
    """After termination, verify that processes are gone and ports are free."""
    # Give the OS a moment to release resources
    time.sleep(1.0)

    print(SEPARATOR)
    print("  Post-Cleanup Verification")
    print(SEPARATOR)
    print()

    processes = find_librevna_processes()
    port_owners = find_port_owners()

    ok = True

    if processes:
        pids = [str(p["Id"]) for p in processes]
        print(f"  [WARN] LibreVNA-GUI still running: PID {', '.join(pids)}")
        ok = False
    else:
        print("  [OK]   No LibreVNA-GUI processes running.")

    occupied = [p for p in LIBREVNA_PORTS if p in port_owners]
    if occupied:
        print(f"  [WARN] Ports still occupied: {occupied}")
        ok = False
    else:
        print("  [OK]   All LibreVNA ports are free.")

    print()
    if ok:
        print("  CLEANUP SUCCESSFUL.  Ready for a new sweep script.")
    else:
        print("  CLEANUP INCOMPLETE.  Some resources may need manual intervention.")
        print("  Try running with --force, or use Task Manager to end the process.")

    print()
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Diagnose and clean up stuck LibreVNA-GUI connections.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--kill",
        action="store_true",
        help="Terminate stale LibreVNA-GUI processes (matching project path only).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Terminate ALL LibreVNA-GUI.exe processes regardless of path.",
    )
    parser.add_argument(
        "--kill-ports",
        action="store_true",
        help="Terminate ANY process using LibreVNA ports (use with caution).",
    )
    args = parser.parse_args()

    processes, port_owners = diagnose()

    # Handle --kill-ports flag
    if args.kill_ports:
        if not port_owners:
            print("Nothing to kill — no processes are using LibreVNA ports.")
            return 0

        print(SEPARATOR)
        print("  Terminating processes using LibreVNA ports")
        print(SEPARATOR)
        print()

        killed = kill_port_users(port_owners)
        print(f"\n  Terminated {killed} process(es) using LibreVNA ports.\n")

        success = verify_cleanup()
        return 0 if success else 1

    # Handle --kill / --force flags (LibreVNA-GUI processes only)
    if args.kill or args.force:
        if not processes:
            print("Nothing to kill — no LibreVNA-GUI processes found.")
            return 0

        print(SEPARATOR)
        print("  Terminating stale LibreVNA-GUI processes")
        print(SEPARATOR)
        print()

        killed = kill_processes(processes, force=args.force)
        print(f"\n  Terminated {killed} of {len(processes)} process(es).\n")

        success = verify_cleanup()
        return 0 if success else 1

    # Diagnose-only mode — provide hints
    if processes or port_owners:
        if processes:
            print("  TIP: Run with --kill to terminate LibreVNA-GUI process(es).")
        if port_owners:
            print("  TIP: Run with --kill-ports to terminate ANY process using the ports.")
        print()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
