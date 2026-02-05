# Single Mode vs Continuous Mode — Implementation Summary

**Source:** `scripts/6_librevna_gui_mode_sweep_test.py`
**Date:** 2026-02-05

---

## 1. SCPI Command Differences

| Step | Single Mode | Continuous Mode |
|------|-------------|-----------------|
| Device / sweep type | `:DEV:MODE VNA` | `:DEV:MODE VNA` |
| | `:VNA:SWEEP FREQUENCY` | `:VNA:SWEEP FREQUENCY` |
| Stimulus & IF | `:VNA:STIM:LVL <dBm>` | `:VNA:STIM:LVL <dBm>` |
| | `:VNA:ACQ:IFBW <Hz>` | `:VNA:ACQ:IFBW <Hz>` |
| Averaging & points | `:VNA:ACQ:AVG <n>` | `:VNA:ACQ:AVG <n>` |
| | `:VNA:ACQ:POINTS <n>` | `:VNA:ACQ:POINTS <n>` |
| Frequency range | `:VNA:FREQuency:START <Hz>` | `:VNA:FREQuency:START <Hz>` |
| | STOP **withheld** from configure; sent per-sweep as the trigger | `:VNA:FREQuency:STOP <Hz>` (sent once in configure) |
| Mode flag | *(not explicitly set — inherits GUI state)* | `:VNA:ACQ:SINGLE FALSE` (before each IFBW run) |
| Acquisition start | `:VNA:FREQuency:STOP <Hz>` — repeated once per sweep | `:VNA:ACQ:RUN` — once per IFBW block |
| Completion check | `:VNA:ACQ:FIN?` — polled every 10 ms | Not used; sweep boundaries detected via streaming `pointNum` |
| Trace read | `:VNA:TRACE:DATA? S11` — queried once per sweep | Not used; S11 arrives via streaming callback |
| Pre-loop setup | None | `:VNA:ACQ:STOP` (drain residual) |
| Post-loop teardown | None | `:VNA:ACQ:STOP` + `:VNA:ACQ:SINGLE TRUE` (restore single mode) |

### Key distinction

`configure_sweep` in single mode deliberately **omits** `FREQuency:STOP`. The stop frequency is the per-sweep trigger: each call to `vna.cmd(":VNA:FREQuency:STOP ...")` both sets the endpoint and kicks off acquisition. Continuous mode includes STOP in `configure_sweep` because the trigger is `ACQ:RUN`, not the frequency write.

---

## 2. Core Logic Differences

### Single Mode — Synchronous, polling

```
Main thread owns the entire sweep lifecycle.
```

- **Trigger:** `FREQuency:STOP` is sent, then the main thread immediately enters a poll loop on `ACQ:FIN?`.
- **Timing window:** starts *after* the trigger command returns; ends when `FIN? == TRUE`. The trace read and dB conversion happen *outside* the timed window.
- **Data retrieval:** `TRACE:DATA? S11` returns `[freq, re, im]` tuples over SCPI. The frequency axis is extracted directly from the response — no assumption about spacing.
- **Concurrency:** none. One sweep at a time, fully sequential.

### Continuous Mode — Asynchronous, streaming callback

```
Main thread starts acquisition; a background thread collects data.
```

- **Trigger:** `ACQ:RUN` starts back-to-back sweeps in the GUI. The main thread then blocks on a `threading.Event`.
- **Timing window:** starts when the callback sees `pointNum == 0`; ends when it sees `pointNum == num_points - 1`. Both timestamps are recorded inside the callback under a `Lock`.
- **Data retrieval:** each streaming JSON point on TCP port 19001 carries `pointNum`, `frequency`, and `measurements.S11` (complex). The callback accumulates S11 values into a list; dB conversion runs on the main thread *after* all sweeps are collected.
- **Concurrency:** the callback closure reads a mutable `_SweepState` object through a one-element list (`_state_holder[0]`). Between IFBWs the main thread swaps in a fresh state object; the callback picks it up on the next point without needing to be re-registered. A `threading.Lock` guards all writes; a `threading.Event` signals completion.

### State management comparison

| Concern | Single Mode | Continuous Mode |
|---------|-------------|-----------------|
| Sweep data accumulation | Main thread appends to plain lists | Callback appends under `Lock`; lists live in `_SweepState` |
| Completion signal | Poll return value (`"TRUE"`) | `Event.set()` called by callback when `sweep_count >= num_sweeps` |
| Frequency axis source | Parsed from `TRACE:DATA?` response | Computed via `np.linspace(start, stop, num_points)` |
| Callback lifecycle | N/A | Registered **once** in `pre_loop_reset`; removed **once** in `post_loop_teardown`. Persists across all IFBWs to avoid a known bug in `libreVNA.py` line 148 |

---

## 3. End-to-End Flow

### Single Mode

```
start_gui()
  └─ poll TCP:1234 until SCPI server is ready

connect_and_verify()
  └─ *IDN?, DEV:CONN?

load_calibration()
  └─ VNA:CAL:LOAD? <path>

pre_loop_reset()          ← no-op for single mode

FOR each IFBW value:
  │
  ├─ configure_sweep()
  │    DEV:MODE VNA
  │    VNA:SWEEP FREQUENCY
  │    VNA:STIM:LVL, ACQ:IFBW, ACQ:AVG, ACQ:POINTS
  │    FREQuency:START          ← STOP is intentionally omitted here
  │
  └─ run_sweeps() → _single_sweep_loop()
       FOR i in 1..num_sweeps:
         │
         ├─ vna.cmd("VNA:FREQuency:STOP <Hz>")   ← triggers acquisition
         ├─ t_start = time.time()
         ├─ POLL loop: query ACQ:FIN? every 10 ms
         │    └─ break when "TRUE"
         ├─ t_end = time.time()                    ← sweep_time recorded
         ├─ vna.query("VNA:TRACE:DATA? S11")       ← outside timed window
         └─ parse freq + complex → dB

post_loop_teardown()      ← no-op for single mode

print_summary() / save_xlsx()

stop_gui()
```

### Continuous Mode

```
start_gui()
  └─ poll TCP:1234 until SCPI server is ready

connect_and_verify()
  └─ *IDN?, DEV:CONN?

load_calibration()
  └─ VNA:CAL:LOAD? <path>

pre_loop_reset()                          ← one-time streaming setup
  ACQ:STOP                                  (drain any residual sweep)
  add_live_callback(port=19001, cb)         (opens TCP stream; cb runs on background thread)

FOR each IFBW value:
  │
  ├─ configure_sweep()
  │    DEV:MODE VNA
  │    VNA:SWEEP FREQUENCY
  │    VNA:STIM:LVL, ACQ:IFBW, ACQ:AVG, ACQ:POINTS
  │    FREQuency:START
  │    FREQuency:STOP                       ← included here; not used as trigger
  │
  └─ run_sweeps() → _continuous_sweep_loop()
       │
       ├─ ACQ:STOP                          ← halt previous IFBW's sweeps
       ├─ sleep(0.1 s)                      ← let stale streaming points drain
       ├─ _state_holder[0] = fresh _SweepState   ← atomic swap; callback sees new state
       ├─ ACQ:SINGLE FALSE                  ← continuous mode
       ├─ ACQ:RUN                           ← starts back-to-back sweeps
       │
       │   [background thread — per streaming point]
       │     cb receives JSON: { pointNum, frequency, Z0, measurements: {S11} }
       │     if pointNum == 0  → record sweep_start_time, reset current_s11
       │     append S11 complex to current_s11
       │     if pointNum == num_points-1 → record sweep_end_time, increment sweep_count
       │                                    if sweep_count >= target → Event.set()
       │
       ├─ main thread: Event.wait(timeout=300 s)   ← blocks until done
       ├─ ACQ:STOP                          ← halt after target reached
       └─ convert all collected complex S11 → dB (main thread)

post_loop_teardown()                      ← one-time cleanup
  ACQ:STOP
  ACQ:SINGLE TRUE                         ← restore single mode for next script
  remove_live_callback(port=19001, cb)

print_summary() / save_xlsx()

stop_gui()
```

---

## Summary of Trade-offs

| Dimension | Single Mode | Continuous Mode |
|-----------|-------------|-----------------|
| Latency model | Dominated by poll granularity + GUI Step 2 | Dominated by ADC scan time + TCP dispatch |
| SCPI traffic per sweep | 3 round-trips (trigger + poll(s) + trace read) | 0 round-trips after RUN (data arrives via streaming) |
| Complexity | Low — everything on one thread | Higher — Lock, Event, state-swap pattern |
| Trace frequency axis | Ground truth from GUI response | Assumed linear via `np.linspace` |
| Streaming server required | No | Yes (port 19001 must be enabled) |
