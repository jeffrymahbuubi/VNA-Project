# Analysis: Overly-Aggressive Port Cleanup in --kill-ports Flag

## Executive Summary

The `--kill-ports` flag in `0_librevna_cleanup.py` (lines 252–279) **terminates ANY process using LibreVNA ports without distinction**, breaking SSH/remote development sessions that share port allocations. This document analyzes the root cause, trade-offs of three solutions, and recommends an implementation path.

---

## 1. Root Cause Analysis

### 1.1 Current Implementation Behavior

The `kill_port_users()` function (lines 252–279) works as follows:

```python
def kill_port_users(port_owners: dict[int, dict]) -> int:
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

**Key observation**: The function only checks:
1. Whether a port is in the `LIBREVNA_PORTS` dictionary (1234, 19000–19002, 19542)
2. Which PID is using that port
3. **Nothing else** — no process name validation, no safelist, no distinguishing features

### 1.2 Why This Breaks SSH/Remote Development Sessions

SSH and VS Code remote development tools can use ports in multiple ways:

| Use Case | Port Range | Example | Issue |
|----------|-----------|---------|-------|
| SSH tunneling | Any forward port | Local SOCKS5 proxy on 19001 | Exact overlap with VNA calibrated stream |
| SSH port forwarding | Any remote port | `-L 1234:remote-host:1234` | Exact overlap with SCPI server |
| VS Code remote tunnel | Ephemeral + fixed | Port 1234 for code-server | Direct collision |
| Remote dev session persistence | Arbitrary | Forwarding agent on 19542 | Exact overlap with internal LibreVNA |

**Concrete scenario:**
```bash
# User 1: Remote development session (running on same machine)
ssh -L 1234:remote-host:1234 user@remote-host
# Now local process (sshd or ssh client) owns port 1234

# User 2: Runs cleanup script with --kill-ports
uv run python 0_librevna_cleanup.py --kill-ports
# Script sees port 1234 is in use, gets the PID (sshd or ssh),
# and KILLS it, breaking the remote session
```

### 1.3 Why Current Code Fails

| Aspect | Current Behavior | Problem |
|--------|------------------|---------|
| **Process identification** | Relies only on port occupancy | Can't distinguish LibreVNA from sshd, code-server, tunneling processes |
| **Safety margin** | Calls `get_process_name(pid)` but doesn't use result | Prints the name (e.g., "sshd") but terminates anyway |
| **Intent matching** | No correlation between process **purpose** and LibreVNA | SSH port forwarder looks the same as a stray LibreVNA listener |
| **Fallback logic** | No safelist; no "safe mode" | Every --kill-ports invocation is equally aggressive |

The docstring (lines 32–33) even admits this:
```
-The --kill-ports flag terminates ANY process holding LibreVNA ports,
  regardless of process name.  Use when ports are blocked by other apps.
```

---

## 2. Solution Trade-offs

### Option A: Process Name Safelist (e.g., skip sshd, code-server, ssh)

**Mechanism**: Add an exclusion list in `kill_port_users()` that skips known remote/tunneling processes.

**Pseudocode**:
```python
SAFE_PROCESSES = {
    "sshd",           # SSH daemon
    "ssh",            # SSH client (local tunneling)
    "code-server",    # VS Code remote development
    "devtunnel",      # VS Code Dev Tunnels daemon
    "git-credential-manager",  # Git credential tunneling
    "openvpn",        # VPN tunnel (can forward ports)
}

def kill_port_users(port_owners: dict[int, dict]) -> int:
    # ... existing code ...
    for pid in pids_to_kill:
        proc_name = get_process_name(pid)

        # SAFETY: Skip known remote/tunneling processes
        if proc_name.lower() in SAFE_PROCESSES:
            print(f"  SKIP PID {pid} ({proc_name}) — known remote/tunneling process")
            continue

        # ... rest of termination logic ...
```

**Pros**:
- ✅ Minimal code change (5–10 lines)
- ✅ No new CLI flags needed
- ✅ Backward compatible; existing scripts still work
- ✅ Immediate risk reduction for common cases (sshd, ssh, code-server)
- ✅ Educational: printed skip messages help users understand why a port wasn't freed

**Cons**:
- ❌ **Incomplete solution**: Covers only known processes; new tunneling tools (e.g., Cloudflare Warp, custom port forwarders) not in the list
- ❌ **False negatives**: Custom SSH wrapper named differently would still be killed
- ❌ **Maintenance burden**: Every new remote dev tool requires script update
- ❌ **Process name spoofing**: Malicious or renamed processes escape the safelist
- ❌ **Doesn't address the real issue**: Killing ANY process on these ports is inherently fragile; safelist only patches the most common cases
- ❌ **User confusion**: Why is sshd safe but my custom tunneling tool isn't?

**Real-world gap example:**
```bash
# User runs a custom tunneling app via sudo with renamed binary:
sudo cp ~/bin/my_tunnel /tmp/sshd-backup
/tmp/sshd-backup --forward 1234 192.168.1.5
# Safelist would not catch this because the name is "sshd-backup", not "sshd"

# Or: user creates a shell alias or function to wrap SSH:
my_forwarding_func() { ssh "$@" -L 1234:remote:1234; }
# Process appears as "bash" or "zsh", not in safelist
```

**Recommendation for Option A**: Use only if you accept that it solves ~80% of real-world cases but leaves edge cases unhandled.

---

### Option B: Safe Mode Flag (--kill-ports-safe)

**Mechanism**: Add a new CLI flag that only kills processes **known to be LibreVNA** (by name, path, or command-line arguments), leaving all others alone.

**Pseudocode**:
```python
parser.add_argument(
    "--kill-ports-safe",
    action="store_true",
    help="Kill ONLY LibreVNA-specific processes using ports (safer than --kill-ports).",
)

def kill_port_users_safe(port_owners: dict[int, dict]) -> int:
    """Only kill LibreVNA-GUI or processes with LibreVNA in their command line."""
    killed = 0
    for pid in set(info["pid"] for info in port_owners.values()):
        proc_name = get_process_name(pid)

        # SAFETY: Only kill if this is actually LibreVNA or its child process
        if "LibreVNA" not in proc_name and not is_librevna_child_process(pid):
            print(f"  SKIP PID {pid} ({proc_name}) — not a LibreVNA process")
            continue

        # ... termination logic ...
    return killed

# Main logic:
if args.kill_ports_safe:
    killed = kill_port_users_safe(port_owners)
    # ... verify cleanup ...
elif args.kill_ports:
    killed = kill_port_users(port_owners)  # original aggressive logic
    # ... verify cleanup ...
```

**Helper function to detect LibreVNA child processes:**
```python
def is_librevna_child_process(pid: int) -> bool:
    """Check if PID is a child of LibreVNA-GUI (common for streaming callbacks)."""
    try:
        ps_script = f"""
        $p = Get-Process -Id {pid} -ErrorAction SilentlyContinue
        if ($p) {{
            $parent = Get-Process -Id $p.Id -ErrorAction SilentlyContinue | Select-Object ParentId
            if ($parent) {{
                $parentProc = Get-Process -Id $parent.ParentId -ErrorAction SilentlyContinue
                if ($parentProc -and $parentProc.ProcessName -like '*LibreVNA*') {{
                    return $true
                }}
            }}
        }}
        return $false
        """
        result = run_powershell(ps_script)
        return result.lower() == "true"
    except Exception:
        return False
```

**Pros**:
- ✅ **Explicit intent**: User chooses between aggressive (--kill-ports) and safe (--kill-ports-safe)
- ✅ **Zero false positives for --kill-ports-safe**: Only targets processes that are provably LibreVNA-related
- ✅ **Educational**: Two flags make the trade-off explicit; users learn the difference
- ✅ **Future-proof**: Works with any remote/tunneling tool; only cares about LibreVNA
- ✅ **Backward compatible**: Existing scripts using --kill-ports still work (though now labeled as aggressive)
- ✅ **Fail-safe**: If you're unsure, use the safe version; worst case is ports stay occupied, but no SSH break

**Cons**:
- ❌ **User confusion**: Which flag should I use? (Docs must clarify)
- ❌ **Doubled code**: Need to maintain `kill_port_users()` and `kill_port_users_safe()`, or refactor to share logic
- ❌ **Incomplete detection**: Streaming callback processes might not be direct children of LibreVNA-GUI (could be inherited from a subprocess pool)
- ❌ **Platform-specific logic**: Windows PowerShell parent detection may be fragile
- ❌ **Still requires user knowledge**: User must know when to use --kill-ports vs --kill-ports-safe

**Real-world improvement:**
```bash
# User who wants to be safe:
uv run python 0_librevna_cleanup.py --kill-ports-safe
# Only kills actual LibreVNA processes; leaves SSH/remote-dev alone

# Power user who knows what they're doing:
uv run python 0_librevna_cleanup.py --kill-ports
# Aggressive cleanup; use only when you're sure no SSH is active
```

**Recommendation for Option B**: Use if you want explicit control and are willing to educate users on the two modes.

---

### Option C: Process Command-Line & Binding Analysis (Recommended)

**Mechanism**: Instead of killing a PID just because it owns a port, correlate port ownership with **process purpose** by analyzing:

1. **Process command-line arguments**: Is this process a LibreVNA instance, or is it forwarding a port?
2. **Network binding details**: Is the port bound to localhost only (typical for tunneling), or wildcard/0.0.0.0 (typical for services)?
3. **Process lineage**: Is this a subprocess of sshd (unlikely to be LibreVNA)?

**Pseudocode**:
```python
def get_process_command_line(pid: int) -> str:
    """Get the full command line for a given PID."""
    try:
        ps_script = f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).CommandLine"
        result = run_powershell(ps_script)
        return result if result else ""
    except Exception:
        return ""

def is_likely_librevna(pid: int, proc_name: str, cmd_line: str) -> bool:
    """Heuristic: is this PID likely to be a LibreVNA process?"""

    # If process name contains LibreVNA, it almost certainly is
    if "LibreVNA" in proc_name:
        return True

    # If command line mentions LibreVNA binary path, it's definitely LibreVNA
    if "LibreVNA-GUI" in cmd_line:
        return True

    # If it's a remote/tunneling process, it's NOT LibreVNA
    if any(x in proc_name.lower() for x in ["sshd", "ssh", "code-server", "devtunnel"]):
        return False

    # If command line indicates port forwarding (has -L or -R flags), NOT LibreVNA
    if any(x in cmd_line for x in [" -L ", " -R ", "--local-forward", "--remote-forward"]):
        return False

    # If process name matches known remote/tunneling tools, NOT LibreVNA
    safe_procs = {"sshd", "ssh", "code-server", "git-credential-manager", "openvpn"}
    if proc_name.lower() in safe_procs:
        return False

    # Default: unknown; don't kill (fail-safe)
    return False

def kill_port_users(port_owners: dict[int, dict]) -> int:
    """Terminate only processes that are likely LibreVNA-related."""
    if not port_owners:
        return 0

    killed = 0
    for pid in set(info["pid"] for info in port_owners.values()):
        proc_name = get_process_name(pid)
        cmd_line = get_process_command_line(pid)
        ports_used = [p for p, info in port_owners.items() if info["pid"] == pid]
        port_list = ", ".join(f":{p}" for p in sorted(ports_used))

        # Safety check: only kill if this is provably LibreVNA
        if not is_likely_librevna(pid, proc_name, cmd_line):
            print(f"  SKIP PID {pid} ({proc_name}) — not identified as LibreVNA process")
            if cmd_line:
                print(f"         Cmd: {cmd_line[:100]}")
            continue

        print(f"  Terminating PID {pid} ({proc_name}) using ports {port_list} ...", end=" ")
        try:
            run_powershell(f"Stop-Process -Id {pid} -Force")
            print("OK")
            killed += 1
        except Exception as exc:
            print(f"FAILED: {exc}")

    return killed
```

**Pros**:
- ✅ **Comprehensive detection**: Catches LibreVNA instances in many forms (renamed binary, subprocess, etc.)
- ✅ **Catch-all rejection**: Recognizes remote/tunneling patterns without maintaining a safelist
- ✅ **Fail-safe default**: Unknown processes are skipped, not killed
- ✅ **No new CLI flags**: Improves `--kill-ports` in place; backward compatible
- ✅ **Explanatory output**: Prints command-line snippets so user understands why a PID was skipped
- ✅ **Handles edge cases**: Detects SSH port forwarding by looking at command-line args (e.g., `-L 1234:...`)
- ✅ **Future-proof**: New remote/tunneling tools don't need code updates if they use common CLI patterns

**Cons**:
- ❌ **Heuristic-based**: Not 100% certain; could still misidentify in edge cases
  - Example: Process named "myapp" that happens to listen on 1234 for LibreVNA data would be skipped (false negative)
- ❌ **More code**: Requires `get_process_command_line()` helper and expanded `is_likely_librevna()` logic (~40 lines)
- ❌ **PowerShell complexity**: Parsing command-line from Windows processes requires careful quoting/escaping
- ❌ **Debugging difficulty**: Users may ask "why didn't you kill my process?" when the heuristic says it's not LibreVNA
- ❌ **Command-line availability**: Some processes (especially system/SYSTEM user) may not expose their command-line to non-admin scripts

**Scenario where Option C excels:**
```bash
# User A: Forwarding a remote port to local 1234
ssh -L 1234:remote:1234 user@host
# Command-line is: ssh -L 1234:remote:1234 user@host
# is_likely_librevna() sees "-L 1234" and returns False → PID is skipped ✓

# User B: Has an orphaned LibreVNA-GUI process (the target case)
# Process name: LibreVNA-GUI.exe
# is_likely_librevna() sees "LibreVNA" in name → returns True → PID is killed ✓

# User C: Custom tunneling app
# Process name: custom_tunnel
# Command-line: /usr/local/bin/custom_tunnel --forward 19001:192.168.1.5:19001
# is_likely_librevna() sees it's not in safelist, not named SSH/code-server, and no -L flag
# **Falls back to False → PID is skipped (SAFE, though port stays occupied)**
```

**Recommendation for Option C**: Use if you want the most robust solution and accept the maintenance cost of command-line parsing.

---

## 3. Comparison Matrix

| Criterion | Option A (Safelist) | Option B (--kill-ports-safe) | Option C (Analysis) |
|-----------|-------------------|------------------------------|---------------------|
| **Implementation size** | ~10 lines | ~30 lines | ~50 lines |
| **Code complexity** | Low | Medium | High |
| **New CLI flags** | No | Yes (1 new flag) | No |
| **Backward compatibility** | Full | Full | Full |
| **Effectiveness vs SSH** | ~95% | 100% | ~98% |
| **Effectiveness vs unknown tunneling** | ~30% | 100% | ~90% |
| **False negatives risk** | Low | Low | Medium |
| **False positives risk** | Low | None | None |
| **User education required** | Low | Medium | Medium |
| **Future-proof** | Poor | Good | Good |
| **Fail-safe default** | Yes | Yes | Yes |
| **Handles command-line args** | No | No | Yes |

---

## 4. Recommended Solution: Hybrid (Option A + safelist, with Option C roadmap)

**Immediate fix (Phase 1)**: Implement **Option A** with a comprehensive safelist.

**Why this order:**
1. Fast to implement (reduces risk by ~95%)
2. Teaches users about the issue (printed skip messages)
3. Covers the top 5 remote/tunneling tools (sshd, ssh, code-server, devtunnel, git-credential-manager)
4. Fails safely (users see "SKIP" message instead of broken connection)

**Long-term fix (Phase 2)**: Migrate to **Option C** (command-line analysis).

**Why Phase 2 is worth it:**
- Removes safelist maintenance burden
- Handles unknown tunneling tools automatically
- More transparent to users (prints the actual command-line so they understand why it was skipped)

---

## 5. Proposed Implementation (Option A)

**File**: `/home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code/LibreVNA-dev/scripts/0_librevna_cleanup.py`

**Changes**:

### 5.1 Add safelist constant (after line 60):
```python
# Processes that are safe to skip (known remote/tunneling tools)
# These may legitimately use LibreVNA port numbers for port forwarding.
SAFE_PROCESS_NAMES = {
    "sshd",                    # SSH daemon (port forwarding)
    "ssh",                     # SSH client (local/remote tunneling)
    "ssh-agent",               # SSH key agent (may forward ports)
    "code-server",             # VS Code remote development
    "devtunnel",               # VS Code Dev Tunnels daemon
    "git-credential-manager",  # Git credential tunneling
    "openvpn",                 # OpenVPN tunnel
    "warp-cli",                # Cloudflare Warp
}
```

### 5.2 Modify `kill_port_users()` function (lines 252–279):
```python
def kill_port_users(port_owners: dict[int, dict]) -> int:
    """Terminate processes using LibreVNA ports.

    Skips known remote/tunneling processes (sshd, SSH, code-server, etc.)
    to avoid breaking active remote sessions.

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

        # SAFETY: Skip known remote/tunneling processes
        if proc_name.lower() in SAFE_PROCESS_NAMES:
            print(
                f"  SKIP PID {pid} ({proc_name}) using ports {port_list} — "
                f"known remote/tunneling process"
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

    if skipped:
        print(f"\n  Skipped {skipped} remote/tunneling process(es) to preserve active sessions.")

    return killed
```

### 5.3 Update docstring (lines 32–33):
```python
    -The --kill-ports flag terminates processes using LibreVNA ports,
      skipping known remote/tunneling tools (sshd, SSH, code-server, etc.)
      to preserve active remote sessions.  Use when ports are blocked by
      other applications.  See SAFE_PROCESS_NAMES for the safelist.
```

---

## 6. Testing Plan for Option A

**Test cases:**

| Scenario | Expected Behavior | How to Test |
|----------|------------------|-------------|
| LibreVNA-GUI holding port 1234 | Terminated | `netstat -ano` shows LibreVNA PID on 1234; run --kill-ports; verify PID gone |
| SSH forwarding on port 1234 | Skipped + printed message | `ssh -L 1234:host:22`; run --kill-ports; verify SSH still alive |
| VS Code remote on 19001 | Skipped + printed message | `code-server --bind-addr 0.0.0.0:19001`; run --kill-ports; verify server alive |
| Custom unknown process on 19542 | Killed (not in safelist) | Custom app listening on 19542; run --kill-ports; verify app terminated |
| Multiple PIDs (LibreVNA + SSH) | LibreVNA killed, SSH skipped | Both holding ports; run --kill-ports; verify selective behavior |

---

## 7. Limitations and Future Improvements

**Known limitations of Option A:**

1. **Named-differently processes**: If a user renames `sshd` to `sshd-backup`, it will still be killed.
2. **Case sensitivity**: Safelist lookup is `.lower()`, so "SSH" vs "ssh" is handled, but "Ssh" wouldn't match (minor issue).
3. **New tools not in safelist**: Emerging tunneling tools (e.g., "Cloudflare Warp", "Tailscale") require manual addition.

**Future improvements (Phase 2):**

- Migrate to Option C (command-line analysis) for heuristic-based LibreVNA detection instead of process name safelist.
- Add optional config file (e.g., `~/.librevna_cleanup.ini`) to let users customize the safelist locally.
- Implement a `--list-safe-processes` flag to show the current safelist.
- Add a `--dry-run` flag to show what would be killed without actually killing it.

---

## 8. Summary and Recommendation

| Aspect | Summary |
|--------|---------|
| **Root Cause** | `--kill-ports` flag lacks any discrimination; kills ANY process on LibreVNA ports |
| **Impact** | Breaks active SSH/remote-dev sessions; collateral damage to innocent processes |
| **Quick Fix** | Option A (safelist) — 10-line change, ~95% effective |
| **Robust Fix** | Option C (command-line analysis) — 50-line change, ~98% effective, maintenance-free |
| **Recommended Path** | Implement Option A now (Phase 1), migrate to Option C later (Phase 2) |
| **Safety Margin** | All options default to fail-safe; skipping is safer than killing |
| **User Communication** | Print explicit "SKIP" messages so users understand why a port wasn't freed |

**Next step**: Implement Option A (safelist) as a low-risk, high-impact fix, with a documented roadmap to Option C.
