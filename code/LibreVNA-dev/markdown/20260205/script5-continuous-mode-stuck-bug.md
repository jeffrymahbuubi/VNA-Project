# Bug Report — Script 5 Leaves GUI Stuck in Continuous Sweep Mode

**Date discovered:** 2026-02-05
**Discovered by:** Script 6 (`6_single_sweep_mode.py`) test run
**Affected script:** `5_continuous_sweep_speed.py`
**Severity:** High — silently corrupts every single-sweep timing measurement
run in the same GUI session after script 5.

---

## 1. What the bug is

`5_continuous_sweep_speed.py` sets the GUI into continuous sweep mode at the
start of its acquisition loop and never resets it back to single-sweep mode
before exiting.  The GUI remains in continuous mode for the rest of the
process lifetime.  Any script that runs afterward and relies on the
single-sweep trigger-and-poll pattern (scripts 3, 4, 6) will silently
measure the wrong thing.

---

## 2. Root cause — exact lines

### 2.1 Mode is set but never cleared

In `run_continuous_sweeps()`, line 389 sets continuous mode:

```python
# 5_continuous_sweep_speed.py  lines 385-389
# -- 2. Select continuous sweep mode -------------------------------------
# VNA:ACquisition:SINGLE FALSE  (ProgrammingGuide 4.3.20)
# When SINGLE is FALSE the GUI free-runs sweeps back-to-back without
# the per-sweep re-preparation that SINGLE TRUE imposes.
vna.cmd(":VNA:ACQ:SINGLE FALSE")
```

The teardown block (lines 429-435) stops acquisition and removes the
streaming callback, but does **not** restore single-sweep mode:

```python
# 5_continuous_sweep_speed.py  lines 429-435
# -- 6. Stop continuous acquisition -------------------------------------
# VNA:ACquisition:STOP  (ProgrammingGuide 4.3.12)
vna.cmd(":VNA:ACQ:STOP")
print("  Acquisition     : stopped")

# -- 7. Remove the streaming callback ------------------------------------
vna.remove_live_callback(STREAMING_PORT, callback)
print("  Streaming       : callback removed")
```

`ACQ:STOP` halts the sweep loop but does **not** change the value of
`ACQ:SINGLE`.  The GUI retains `SINGLE FALSE` until an explicit
`ACQ:SINGLE TRUE` is sent.

### 2.2 The timeout-error path has the same omission

The early-exit branch inside the `if not completed:` block (lines 419-427)
also only sends `ACQ:STOP` — no `ACQ:SINGLE TRUE`:

```python
# 5_continuous_sweep_speed.py  lines 419-427
if not completed:
    # Tear down before raising so the VNA is left in a clean state.
    vna.cmd(":VNA:ACQ:STOP")
    vna.remove_live_callback(STREAMING_PORT, callback)
    raise TimeoutError(...)
```

---

## 3. How the corruption manifests

The single-sweep scripts (3, 4, 6) use this timing protocol:

```
1. Send  :VNA:FREQuency:STOP <Hz>   ← intended to trigger one sweep
2. t_start = time.time()
3. Poll  :VNA:ACQ:FIN?  until "TRUE"
4. t_end = time.time()
```

When the GUI is stuck in `SINGLE FALSE`:

- Step 1 does **not** trigger a new single sweep.  The GUI is still
  free-running sweeps in the background.
- Step 3 returns `TRUE` from whichever background sweep happened to finish
  between step 2 and the first poll.  The poll exits almost immediately.
- The measured `t_end − t_start` is the time between two random background
  sweep completions, not the latency of a STOP-triggered single sweep.

The result is that all 30 measured sweep times collapse to ~41 ms
(the background sweep rate), making it look like the single-sweep path
is running at 24.4 Hz — a number that is physically impossible for the
single-sweep trigger path under normal conditions.

---

## 4. Verification evidence (2026-02-05)

| Step | Command / action | Result |
|---|---|---|
| 1 | Ran script 5 (30 continuous sweeps) | Completed normally |
| 2 | Queried `:VNA:ACQ:SINGLE?` | `FALSE` — mode was never restored |
| 3 | Ran script 6 **without** the fix | All 30 sweeps reported ~41 ms / 24.4 Hz |
| 4 | Added `ACQ:STOP` + `ACQ:SINGLE TRUE` to script 6's `configure_sweep` | Sweep 1 now shows correct cold-start overhead (~92 ms); sweeps 2–30 show the genuine hot-path re-trigger time (~41 ms) |
| 5 | Queried `:VNA:ACQ:SINGLE?` after script 6 fix | `TRUE` — mode correctly enforced |

Manual single-sweep timing after explicit `ACQ:SINGLE TRUE` (1 ms poll):

| Trigger | Measured time | Notes |
|---|---|---|
| 1st STOP after SINGLE TRUE | 0.2089 s | Cold: GUI "Step 2" preparation overhead |
| 2nd STOP (re-trigger) | 0.0409 s | Hot: sweep pipeline already warm |

The 0.041 s hot-path time is genuine — it reflects the raw ADC acquisition
floor (30 ms for 300 pts @ 10 k pts/s) plus ~11 ms GUI dispatch.  It is NOT
the corrupted value; the corruption made it appear on **all** 30 sweeps
including sweep 1, which should have been slow.

---

## 5. Proposed fix for script 5

Two locations in `run_continuous_sweeps()` need a single additional command.

### 5.1 Normal-exit path (after line 431)

```python
    # -- 6. Stop continuous acquisition -------------------------------------
    vna.cmd(":VNA:ACQ:STOP")
    print("  Acquisition     : stopped")

+   # -- 6b. Restore single-sweep mode ------------------------------------
+   # ACQ:STOP halts the sweep loop but does not change ACQ:SINGLE.
+   # Restore the default so that any script run afterward in the same
+   # GUI session gets the expected single-sweep trigger behaviour.
+   vna.cmd(":VNA:ACQ:SINGLE TRUE")
+   print("  Sweep mode      : restored to SINGLE (TRUE)")
```

### 5.2 Timeout-error path (before the raise, after line 421)

```python
    if not completed:
        vna.cmd(":VNA:ACQ:STOP")
+       vna.cmd(":VNA:ACQ:SINGLE TRUE")   # restore before raising
        vna.remove_live_callback(STREAMING_PORT, callback)
        raise TimeoutError(...)
```

### 5.3 SCPI reference

| Command | Section | Effect |
|---|---|---|
| `VNA:ACquisition:SINGLE TRUE` | ProgrammingGuide 4.3.20 | Restores single-sweep mode; STOP becomes a one-shot trigger |
| `VNA:ACquisition:STOP` | ProgrammingGuide 4.3.12 | Halts acquisition; does **not** change SINGLE state |

---

## 6. Defensive pattern for downstream scripts

Even after script 5 is fixed, any single-sweep script should explicitly
enforce its own preconditions rather than assuming prior scripts left the
GUI in a known state.  The pattern used in script 6's `configure_sweep`
is the recommended baseline:

```python
vna.cmd(":VNA:ACQ:STOP")          # halt any leftover acquisition
vna.cmd(":VNA:ACQ:SINGLE TRUE")   # force single-sweep mode
```

Send both commands before the rest of the sweep configuration, immediately
after `:DEV:MODE VNA`.
