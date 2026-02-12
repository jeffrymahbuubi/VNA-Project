# Implementation Guide: --kill-ports Safety Fix

This document provides step-by-step instructions to implement the recommended solution (Option A: Safelist).

---

## Part 1: Option A Implementation (Recommended for Phase 1)

### Step 1: Add Safelist Constant

**Location**: After line 60 in `0_librevna_cleanup.py`, before the `SEPARATOR` constant definition.

**Current code (lines 53–62)**:
```python
# Ports used by LibreVNA-GUI
LIBREVNA_PORTS = {
    1234:  "SCPI server",
    19000: "VNA Raw streaming",
    19001: "VNA Calibrated streaming",
    19002: "VNA De-embedded streaming",
    19542: "Internal LibreVNA TCP",
}

SEPARATOR = "-" * 72
```

**Add after `LIBREVNA_PORTS` and before `SEPARATOR`**:
```python
# Processes to skip during --kill-ports cleanup
# These are legitimate processes that may use LibreVNA port numbers for tunneling/forwarding
SAFE_PROCESS_NAMES = {
    "sshd",                    # SSH daemon (accepts port forwarding from clients)
    "ssh",                     # SSH client (local/remote tunnel via -L/-R flags)
    "ssh-agent",               # SSH key agent (may facilitate forwarded connections)
    "code-server",             # VS Code remote development server
    "devtunnel",               # VS Code Dev Tunnels daemon
    "git-credential-manager",  # Git credential helper (can forward requests)
    "openvpn",                 # OpenVPN tunnel (routes traffic including forwarded ports)
    "warp-cli",                # Cloudflare Warp client
    "tailscaled",              # Tailscale daemon (virtual network tunnel)
}
```

### Step 2: Update `kill_port_users()` Function

**Location**: Lines 252–279

**Current code**:
```python
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
```

**Replace with**:
```python
def kill_port_users(port_owners: dict[int, dict]) -> int:
    """Terminate processes using LibreVNA ports, skipping known remote/tunneling processes.

    Processes in SAFE_PROCESS_NAMES are skipped to preserve active SSH, VS Code remote,
    VPN, and other legitimate tunneling sessions that may use LibreVNA port numbers.

    Returns the number of processes terminated.
    """
    if not port_owners:
        return 0

    # Collect unique PIDs
    pids_to_kill = set(info["pid"] for info in port_owners.values())
    killed = 0
    skipped = 0

    for pid in pids_to_kill:
        # Find which ports this PID is using
        ports_used = [port for port, info in port_owners.items() if info["pid"] == pid]
        port_list = ", ".join(f":{p}" for p in sorted(ports_used))

        proc_name = get_process_name(pid)

        # SAFETY: Skip known remote/tunneling processes to avoid breaking active sessions
        if proc_name.lower() in SAFE_PROCESS_NAMES:
            print(
                f"  SKIP PID {pid} ({proc_name}) using ports {port_list}\n"
                f"         (known remote/tunneling process — preserving active session)"
            )
            skipped += 1
            continue

        print(f"  Terminating PID {pid} ({proc_name}) using ports {port_list} ...", end=" ")

        try:
            run_powershell(f"Stop-Process -Id {pid} -Force")
            print("OK")
            killed += 1
        except Exception as exc:
            print(f"FAILED: {exc}")

    if skipped > 0:
        print(f"\n  Summary: Terminated {killed} process(es), skipped {skipped} remote/tunneling process(es).")

    return killed
```

### Step 3: Update Docstring

**Location**: Lines 32–33 (module-level docstring)

**Current**:
```python
    -The --kill-ports flag terminates ANY process using LibreVNA ports,
      regardless of process name.  Use when ports are blocked by other apps.
```

**Replace with**:
```python
    -The --kill-ports flag terminates processes using LibreVNA ports, but skips known
      remote/tunneling processes (sshd, SSH, VS Code remote, VPN, etc.) to preserve
      active sessions.  Use when ports are blocked by non-LibreVNA applications.
```

---

## Part 2: Testing (After Implementation)

### Manual Test 1: Verify Safelist Skips SSH

**Setup**:
```bash
# Terminal 1: Start SSH port forwarding
ssh -L 1234:localhost:22 username@remotehost
# (Keep this running)
```

**Terminal 2: Run cleanup**:
```bash
cd /path/to/scripts
uv run python 0_librevna_cleanup.py --kill-ports
```

**Expected output**:
```
[...]
  SKIP PID 1234 (ssh) using ports :1234
         (known remote/tunneling process — preserving active session)

  Summary: Terminated 0 process(es), skipped 1 remote/tunneling process(es).
[...]
```

**Verification**: SSH session in Terminal 1 should remain active; no connection break.

### Manual Test 2: Verify LibreVNA Processes Are Still Killed

**Setup**:
```bash
# Start LibreVNA-GUI in headless mode (or start it manually on Windows)
QT_QPA_PLATFORM=offscreen /path/to/LibreVNA-GUI --port 1234 &
sleep 2

# Verify it's listening
netstat -ano | grep 1234
# Should show LibreVNA-GUI holding the port
```

**Run cleanup**:
```bash
uv run python 0_librevna_cleanup.py --kill-ports
```

**Expected output**:
```
[...]
  Terminating PID 5678 (LibreVNA-GUI) using ports :1234 ...OK

  Summary: Terminated 1 process(es), skipped 0 remote/tunneling process(es).
[...]
```

**Verification**: `netstat -ano | grep 1234` should show port is now FREE.

### Manual Test 3: Edge Case — Unknown Process

**Setup** (if you have a test app that listens on a LibreVNA port):
```bash
# Some custom app listening on port 19542 (not in safelist)
./my_app --listen 19542 &
```

**Run cleanup**:
```bash
uv run python 0_librevna_cleanup.py --kill-ports
```

**Expected behavior**: The custom app will be terminated (since it's not in the safelist and not named LibreVNA). This is correct — if the safelist doesn't recognize it, it's fair game.

---

## Part 3: Enhanced Version (Option C Roadmap)

If you want to future-proof the script, you can prepare for a migration to Option C (command-line analysis). Here's a sketch of what Phase 2 would look like:

### Future Addition: Command-Line Inspection Helper

**Add this function after `get_process_name()` (around line 218)**:

```python
def get_process_command_line(pid: int) -> str:
    """Get the full command-line arguments for a process (Windows PowerShell)."""
    try:
        ps_script = f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).CommandLine"
        result = run_powershell(ps_script)
        return result if result else ""
    except Exception:
        return ""


def is_likely_librevna_process(pid: int, proc_name: str, cmd_line: str) -> bool:
    """
    Heuristic: Determine if a PID is likely a LibreVNA process.

    Used in Phase 2 to replace the safelist with intelligent detection.
    """
    # If process name contains LibreVNA, it definitely is
    if "LibreVNA" in proc_name:
        return True

    # If command line explicitly mentions the LibreVNA binary, it is
    if "LibreVNA-GUI" in cmd_line:
        return True

    # If it's a known remote/tunneling process, it's NOT LibreVNA
    safe_names = SAFE_PROCESS_NAMES.union({"systemd", "init", "svchost"})
    if proc_name.lower() in safe_names:
        return False

    # If command line shows port forwarding syntax, NOT LibreVNA
    if any(x in cmd_line for x in [" -L ", " -R ", "--local-forward", "--remote-forward"]):
        return False

    # Default: unknown — skip (fail-safe)
    return False
```

Then, in Phase 2, you'd replace the safelist check in `kill_port_users()` with:

```python
# Instead of:
if proc_name.lower() in SAFE_PROCESS_NAMES:
    # Skip...

# Use (in Phase 2):
if not is_likely_librevna_process(pid, proc_name, get_process_command_line(pid)):
    # Skip...
```

This keeps the safelist as a fallback but adds intelligent detection.

---

## Part 4: Communication and Documentation

### Update Help Text (Lines 342–346)

**Current**:
```python
parser.add_argument(
    "--kill-ports",
    action="store_true",
    help="Terminate ANY process using LibreVNA ports (use with caution).",
)
```

**Update to**:
```python
parser.add_argument(
    "--kill-ports",
    action="store_true",
    help=(
        "Terminate processes using LibreVNA ports, skipping known remote/tunneling processes "
        "(sshd, SSH, VS Code remote, VPN, etc.) to avoid breaking active sessions."
    ),
)
```

### Update Usage Example (Lines 19–23)

**Current**:
```python
Usage:
    uv run python 0_librevna_cleanup.py                 # diagnose only (safe)
    uv run python 0_librevna_cleanup.py --kill           # diagnose + kill stale LibreVNA-GUI processes
    uv run python 0_librevna_cleanup.py --force          # kill ALL LibreVNA-GUI instances
    uv run python 0_librevna_cleanup.py --kill-ports     # kill ANY process using LibreVNA ports
```

**Update to**:
```python
Usage:
    uv run python 0_librevna_cleanup.py                 # diagnose only (safe)
    uv run python 0_librevna_cleanup.py --kill           # diagnose + kill stale LibreVNA-GUI processes
    uv run python 0_librevna_cleanup.py --force          # kill ALL LibreVNA-GUI instances
    uv run python 0_librevna_cleanup.py --kill-ports     # kill non-LibreVNA processes using ports
```

---

## Validation Checklist

Before committing, verify:

- [ ] Safelist constant added after `LIBREVNA_PORTS` definition
- [ ] `kill_port_users()` function updated with safelist check
- [ ] Module docstring updated to reflect the safelist behavior
- [ ] `--help` text updated to mention preserved remote/tunneling processes
- [ ] Test 1 passed: SSH session survives --kill-ports (if testable)
- [ ] Test 2 passed: LibreVNA-GUI is still killed by --kill-ports
- [ ] Code follows existing style (2-space indentation, docstring format)
- [ ] No new dependencies introduced
- [ ] Backward compatibility maintained (--kill-ports still works, just safer)

---

## Git Commit Template

```
fix: safelist remote/tunneling processes in --kill-ports cleanup

Add SAFE_PROCESS_NAMES set containing known remote/tunneling tools
(sshd, SSH, code-server, VS Code Dev Tunnels, VPN, etc.) to the
kill_port_users() function. These processes are skipped during
--kill-ports cleanup to preserve active SSH, remote dev, and VPN
sessions that may use LibreVNA port numbers for forwarding.

Fixes issue where --kill-ports would break SSH port forwarding,
VS Code remote sessions, and other legitimate tunneling on a
shared machine. Ports held by safelist processes remain occupied
but the critical user sessions survive.

Files modified:
  - scripts/0_librevna_cleanup.py

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

## Appendix: Safelist Rationale

| Process | Reason for Safelist |
|---------|-------------------|
| `sshd` | SSH server daemon; may have clients with port forwarding active |
| `ssh` | SSH client; `-L` and `-R` flags create port forwarding |
| `ssh-agent` | SSH key agent; can facilitate forwarded connections |
| `code-server` | VS Code remote development server (runs on arbitrary ports) |
| `devtunnel` | VS Code Dev Tunnels daemon (creates tunneled connections) |
| `git-credential-manager` | Git credential helper (can tunnel requests) |
| `openvpn` | VPN tunnel daemon (routes all traffic, including forwarded ports) |
| `warp-cli` | Cloudflare Warp client (virtual network, port forwarding) |
| `tailscaled` | Tailscale daemon (mesh VPN, can forward ports) |

---

## Appendix: Why Not Option B (--kill-ports-safe)?

Option B adds a second flag, which increases cognitive load:

```bash
# Which should the user choose?
uv run python 0_librevna_cleanup.py --kill-ports        # Aggressive?
uv run python 0_librevna_cleanup.py --kill-ports-safe   # Safe?
```

Option A requires no decision — the default `--kill-ports` is already safe, and users get explicit feedback (SKIP messages) when a process is spared.

---

## Appendix: Why Not Jump Straight to Option C?

Option C (command-line analysis) is more robust but introduces:
- 50+ lines of new code
- Platform-specific PowerShell logic (fragile)
- Heuristic-based detection (not foolproof)
- Debugging difficulty (why did you skip my app?)

**Option A gets ~95% of the value with 10 lines of code.**

Migrate to Option C only if the safelist becomes unmaintainable (too many new tools to add).
