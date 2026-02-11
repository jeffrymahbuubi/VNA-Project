# Streaming Callback Patterns & Pitfalls

## Partial First Sweep (Fixed 2026-02-11)

**Bug**: When continuous mode starts via `ACQ:RUN`, the streaming server may
already be mid-sweep. The callback sees points starting at e.g. pointNum=150
instead of 0. When pointNum reaches num_points-1, `current_s11` only has
150 entries instead of 300, producing an inhomogeneous `all_s11_db` list that
crashes `np.array()` with `ValueError: inhomogeneous shape`.

**Fix applied in script 6** (two layers):
1. **Callback guard**: In `_make_callback`, only save a sweep when
   `len(collected) == state.num_points`. Partial sweeps are silently discarded
   and do not count toward `sweep_count`. The callback continues collecting
   until enough *complete* sweeps arrive.
2. **compute_metrics safety net**: Filter `result.all_s11_db` to only include
   sweeps with `len(s) == len(result.freq_hz)` before calling `np.array()`.
   Warns on console if any are dropped. Returns zeros if no valid sweeps remain.

**Key insight**: The streaming server delivers points independently of when the
host starts listening. Always validate sweep completeness before trusting the
point count.
