# Quick Reference: --kill-ports Safety Fix

## TL;DR

**Problem**: `--kill-ports` flag kills ANY process using LibreVNA ports (1234, 19000–19002, 19542), including SSH, VS Code remote, and VPN tunnels.

**Solution**: Add a safelist of known remote/tunneling process names; skip them during cleanup.

**Impact**: ~10 lines of code change; preserves active SSH/remote sessions while still killing stray LibreVNA processes.

---

## Exact Code Changes

### File: `/code/LibreVNA-dev/scripts/0_librevna_cleanup.py`

#### Change 1: Add Safelist Constant (after line 60)

```python
# Insert after LIBREVNA_PORTS definition, before SEPARATOR:

SAFE_PROCESS_NAMES = {
    "sshd",                    # SSH daemon
    "ssh",                     # SSH client (tunneling)
    "ssh-agent",               # SSH key agent
    "code-server",             # VS Code remote
    "devtunnel",               # VS Code Dev Tunnels
    "git-credential-manager",  # Git credential tunneling
    "openvpn",                 # OpenVPN tunnel
    "warp-cli",                # Cloudflare Warp
    "tailscaled",              # Tailscale daemon
}
```

#### Change 2: Modify `kill_port_users()` Function (lines 252–279)

**Replace the entire function** with:

```python
def kill_port_users(port_owners: dict[int, dict]) -> int:
    """Terminate processes using LibreVNA ports, skipping known remote/tunneling processes.

    Processes in SAFE_PROCESS_NAMES are skipped to preserve active SSH, VS Code remote,
    VPN, and other legitimate tunneling sessions that may use LibreVNA port numbers.

    Returns the number of processes terminated.
    """
    if not port_owners:
        return 0

    pids_to_kill = set(info["pid"] for info in port_owners.values())
    killed = 0
    skipped = 0

    for pid in pids_to_kill:
        ports_used = [port for port, info in port_owners.items() if info["pid"] == pid]
        port_list = ", ".join(f":{p}" for p in sorted(ports_used))

        proc_name = get_process_name(pid)

        # SAFETY: Skip known remote/tunneling processes
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

#### Change 3: Update Module Docstring (lines 32–33)

**From**:
```python
    -The --kill-ports flag terminates ANY process using LibreVNA ports,
      regardless of process name.  Use when ports are blocked by other apps.
```

**To**:
```python
    -The --kill-ports flag terminates processes using LibreVNA ports, but skips known
      remote/tunneling processes (sshd, SSH, VS Code remote, VPN, etc.) to preserve
      active sessions.  Use when ports are blocked by non-LibreVNA applications.
```

#### Change 4: Update Help Text (lines 342–346)

**From**:
```python
parser.add_argument(
    "--kill-ports",
    action="store_true",
    help="Terminate ANY process using LibreVNA ports (use with caution).",
)
```

**To**:
```python
parser.add_argument(
    "--kill-ports",
    action="store_true",
    help=(
        "Terminate processes using LibreVNA ports, skipping known remote/tunneling "
        "processes (sshd, SSH, VS Code remote, VPN, etc.)."
    ),
)
```

---

## Unified Diff

```diff
--- a/scripts/0_librevna_cleanup.py
+++ b/scripts/0_librevna_cleanup.py
@@ -30,8 +30,12 @@ When a previous script exits uncleanly (crash, KeyboardInterrupt, debugger
     -The --kill flag terminates only LibreVNA-GUI processes that match the
       expected binary path under this project tree.
     -The --force flag terminates ALL LibreVNA-GUI.exe processes regardless
       of path.  Use with care if you have multiple LibreVNA installations.
-    -The --kill-ports flag terminates ANY process holding LibreVNA ports,
-      regardless of process name.  Use when ports are blocked by other apps.
+    -The --kill-ports flag terminates processes using LibreVNA ports, but skips known
+      remote/tunneling processes (sshd, SSH, VS Code remote, VPN, etc.) to preserve
+      active sessions.  Use when ports are blocked by non-LibreVNA applications.
 """

 import argparse
@@ -60,6 +64,16 @@ LIBREVNA_PORTS = {
     19542: "Internal LibreVNA TCP",
 }

+# Processes to skip during --kill-ports cleanup
+SAFE_PROCESS_NAMES = {
+    "sshd", "ssh", "ssh-agent", "code-server", "devtunnel",
+    "git-credential-manager", "openvpn", "warp-cli", "tailscaled",
+}
+
 SEPARATOR = "-" * 72


@@ -252,7 +266,7 @@ def kill_processes(processes: list[dict], force: bool = False) -> int:

 def kill_port_users(port_owners: dict[int, dict]) -> int:
-    """Terminate processes using LibreVNA ports.
+    """Terminate processes using LibreVNA ports, skipping known remote/tunneling processes.
+
+    Processes in SAFE_PROCESS_NAMES are skipped to preserve active SSH, VS Code remote,
+    VPN, and other legitimate tunneling sessions that may use LibreVNA port numbers.

     Returns the number of processes terminated.
@@ -260,20 +274,30 @@ def kill_port_users(port_owners: dict[int, dict]) -> int:
     if not port_owners:
         return 0

-    # Collect unique PIDs
     pids_to_kill = set(info["pid"] for info in port_owners.values())
     killed = 0
+    skipped = 0

     for pid in pids_to_kill:
-        # Find which ports this PID is using
         ports_used = [port for port, info in port_owners.items() if info["pid"] == pid]
         port_list = ", ".join(f":{p}" for p in sorted(ports_used))

         proc_name = get_process_name(pid)
+
+        # SAFETY: Skip known remote/tunneling processes
+        if proc_name.lower() in SAFE_PROCESS_NAMES:
+            print(
+                f"  SKIP PID {pid} ({proc_name}) using ports {port_list}\n"
+                f"         (known remote/tunneling process — preserving active session)"
+            )
+            skipped += 1
+            continue
+
         print(f"  Terminating PID {pid} ({proc_name}) using ports {port_list} ...", end=" ")

         try:
             run_powershell(f"Stop-Process -Id {pid} -Force")
             print("OK")
             killed += 1
         except Exception as exc:
             print(f"FAILED: {exc}")
+
+    if skipped > 0:
+        print(f"\n  Summary: Terminated {killed} process(es), skipped {skipped} remote/tunneling process(es).")

     return killed
@@ -343,7 +367,9 @@ def main():
     parser.add_argument(
         "--kill-ports",
         action="store_true",
-        help="Terminate ANY process using LibreVNA ports (use with caution).",
+        help=(
+            "Terminate processes using LibreVNA ports, skipping known remote/tunneling processes (sshd, SSH, VS Code remote, VPN, etc.)."
+        ),
     )
     args = parser.parse_args()
```

---

## Validation

**Before commit**:
1. Syntax check: `uv run python -m py_compile scripts/0_librevna_cleanup.py`
2. Help text check: `uv run python scripts/0_librevna_cleanup.py --help | grep -A2 kill-ports`
3. Diagnostic mode: `uv run python scripts/0_librevna_cleanup.py` (should still work)

**After commit**:
1. Manual test with SSH forwarding (if testable)
2. Verify --kill still works for LibreVNA-GUI processes
3. Check output messages are informative

---

## Why This Works

| Scenario | Old Behavior | New Behavior |
|----------|--------------|--------------|
| SSH port forwarding on :1234 | KILLED (breaks SSH) | SKIPPED (SSH survives) |
| VS Code remote on :19001 | KILLED (breaks IDE) | SKIPPED (IDE survives) |
| LibreVNA-GUI orphaned on :1234 | KILLED ✓ | KILLED ✓ |
| Unknown custom app on :19542 | KILLED ✓ | KILLED ✓ |

---

## Files to Change

1. `/code/LibreVNA-dev/scripts/0_librevna_cleanup.py`
   - Add SAFE_PROCESS_NAMES constant (1 block, ~9 lines)
   - Modify kill_port_users() function (add safelist check, ~8 lines net)
   - Update 2 docstrings/help text (~3 lines net)

**Total**: ~20 lines added, ~10 lines modified, net +10 lines.

---

## Testing Commands

```bash
# Syntax validation
cd /code/LibreVNA-dev/scripts
uv run python -m py_compile 0_librevna_cleanup.py

# Show help
uv run python 0_librevna_cleanup.py --help | head -20

# Dry-run (diagnose only, safe)
uv run python 0_librevna_cleanup.py

# Test with SSH running (if available)
ssh -L 1234:localhost:22 user@host &  # In background
uv run python 0_librevna_cleanup.py --kill-ports
# Should show "SKIP PID ... (ssh) ... known remote/tunneling process"
```

---

## What's NOT Changing

- Windows-only platform assumption (script is PowerShell-based)
- `--kill` and `--force` flags (unchanged)
- Diagnosis mode (unchanged)
- Verify cleanup behavior (unchanged)
- Port and process detection logic (unchanged)

---

## Safelist Additions (Future)

If new remote/tunneling tools emerge, add to `SAFE_PROCESS_NAMES`:

```python
SAFE_PROCESS_NAMES = {
    "sshd", "ssh", "ssh-agent",              # SSH
    "code-server", "devtunnel",              # VS Code
    "git-credential-manager",                # Git
    "openvpn", "warp-cli", "tailscaled",    # VPN/Tunneling
    "new-tool-name",                         # <- Add here
}
```

No other code needs to change.

---

## Commit Message

```
fix: safelist remote/tunneling processes in --kill-ports cleanup

Skip known remote/tunneling tools (sshd, SSH, code-server, VPN, etc.)
when using --kill-ports to avoid breaking active SSH, remote dev, and
VPN sessions on a shared machine.

Adds SAFE_PROCESS_NAMES set with ~9 common tools; processes in the
safelist are skipped with an informative message. LibreVNA-GUI processes
and unknown apps are still terminated as before.

Fixes collateral damage to SSH port forwarding and VS Code remote
sessions when cleanup is run alongside active tunneling.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

## FAQ

**Q: Will this break the existing --kill-ports behavior?**
A: No. LibreVNA-GUI processes (which is what we want to kill) will still be terminated. Only known remote/tunneling tools are spared.

**Q: What if my process isn't in the safelist?**
A: It will be killed, as before. The safelist covers the top ~9 remote/tunneling tools; if you're using something else, you have two options:
   1. Run with --kill (not --kill-ports) to kill only LibreVNA-GUI
   2. Manually add your tool to the safelist in the code

**Q: Why not use Option B (--kill-ports-safe flag)?**
A: Because it adds complexity and decision paralysis ("which flag should I use?"). The safelist is a safer default that doesn't require a choice.

**Q: Why not use Option C (command-line analysis)?**
A: It's 50+ lines, platform-specific, and harder to debug. Phase 1 (Option A) gets 95% of the value with 10 lines. Phase 2 (Option C) can be done later if the safelist becomes unmaintainable.

**Q: What if a new tool emerges?**
A: Add it to SAFE_PROCESS_NAMES. No other code changes needed. In Phase 2, we'll migrate to intelligent detection and won't need a safelist at all.

**Q: Is this backward compatible?**
A: Yes. The --kill-ports flag still exists and still works; it's just safer now.
