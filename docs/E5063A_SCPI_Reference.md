# Keysight E5063A ENA — SCPI Command Reference (Consolidated)

> **Purpose:** A single, categorized reference of the SCPI commands available for
> remotely controlling the Keysight E5063A ENA-series Vector Network Analyzer,
> with syntax, parameters, and usage notes, for developing custom control
> programs (the `code/ena-dev/` migration and any future tooling).

---

## 0. Provenance, scope & the E5062A-vs-E5063A caveat (READ FIRST)

| Source | Role in this document |
|--------|-----------------------|
| `references/reports/20260602/E5062A_Programmers_Guide_E5061-90042_Part*.pdf` (28 chunks) | **Primary text.** This is the *Agilent E5061A/E5062A ENA-Series RF Network Analyzers Programmer's Guide*, 5th ed., P/N E5061-90042, Oct 2008, firmware A.03.00. It is a true *Programmer's Guide* (explanations + sample programs + a full Chapter 13 SCPI command reference). |
| `references/reports/20260504/E5063A_參考資料/E5063A_SCPI常用命令整理.md` | E5063A-specific cheat-sheet (cross-verification). |
| `references/reports/20260522/keysight-ena-e5063a-python-automation/core/scpi_commands.py` | Working PyVISA SCPI constants used in a real E5063A control suite (= `code/ena_qt6_suite/`). |

> ⛔ **DO NOT USE `9018-07931_E5063A_SCPI_Command_Reference.pdf`.** Despite the
> filename, that PDF is the *Agilent 4155B/4156B Semiconductor Parameter
> Analyzer SCPI Command Reference* — a completely different instrument. It was
> mislabeled and is **not** an E5063A document. (Confirmed 2026-06-02: its
> extracted pages were verbatim 4155B/4156B content.) **All copies — under
> `20260504/E5063A_參考資料/official_docs/`, `20260528/`, the extracted-page
> chunks, and `code/ena-dev/scpi_ch4_test.txt` — were deleted 2026-06-02.** Do
> not re-download it (the Keysight 9018-07931 asset itself resolves to the 4155B
> manual). For any genuine E5063A SCPI question,
> use the E5062A Programmer's Guide above, this consolidated reference, the
> E5063A cheat-sheet, the working `ena_qt6_suite` constants, or — for
> instrument-specific numeric ranges/options — the live `:SYST:ERR?` queue and
> instrument readback.

### ⚠️ Instrument-family caveat

The **bulk of this reference is sourced from the E5061A/E5062A Programmer's Guide**,
a *sibling* instrument in the same Keysight ENA family. The E5061/E5062 and the
E5063A share the overwhelming majority of their SCPI tree (same SCPI architecture,
same subsystem names, identical core measurement/sweep/trace/marker/calibration/
data-transfer commands). **Commands in this document are therefore applicable to
the E5063A unless flagged otherwise**, but the following differences are known or
plausible and are called out inline where relevant:

- **Ports:** E5061/E5062 are 2-port instruments → `:SENS:CORR:EXT:PORT{1-2}`,
  port indices 1–2. E5063A is also 2-port, so this matches. (Higher-port ENA
  models extend the ranges; the guide's `SOLT3/SOLT4` references and
  `:CALC{1-4}:PAR{1-4}` ranges reflect family-wide firmware.)
- **Frequency range** differs by model (an E5063A option spans 100 kHz–4.5/8.5/14/18 GHz;
  the E5061/E5062 differ). Frequency *commands* are identical; only the valid
  numeric ranges differ — always read back limits from the instrument.
- **Telnet/socket ports:** the E5062A guide documents telnet port **23** and
  program socket port **5025**. The E5063A collaborator material documents
  telnet **5024** and program socket **5025**. **Use 5025 for programmatic SCPI
  on the E5063A** (confirmed in both sources). See §3.
- A few cosmetic/option commands (handler I/O `:CONT:HAND:*`, certain
  `:DISP` colour/window items, `:SOUR:POW:ATT` power-range options) may not
  apply or may have different option gating on the E5063A.

**When E5063A accuracy is critical** (numeric ranges, option availability,
exact enum spelling), verify against the **E5062A Programmer's Guide**
(`references/reports/20260602/E5062A_Programmers_Guide_E5061-90042_Part*.pdf`),
the E5063A cheat-sheet, the working `ena_qt6_suite` constants, and above all the
live instrument (`:SYST:ERR?` queue + value readback — the only true authority
for E5063A-specific numeric limits and option gating). There is **no** standalone
E5063A SCPI PDF in this repo; do **not** reach for `9018-07931…pdf` (it is a
4155B manual — see the ⛔ note in §0).

---

## 1. How to read this reference (notational conventions)

From the guide's Chapter 13 "Notational conventions":

- **Abbreviated (short) form** is shown in UPPER case; the remaining long-form
  letters are optional. SCPI is **case-insensitive**. e.g. `:SENSe1:FREQuency:STARt`
  may be sent as `:SENS1:FREQ:STAR`.
- **`{1-4}`** after a mnemonic = a numeric suffix range you must substitute
  (channel 1–4, trace 1–4, marker 1–10, standard 1–21, etc.). If omitted it
  defaults to 1. e.g. `:CALC{1-4}:...` → `:CALC1:...`.
- **`?`** suffix = the **query** form (reads a value). Many nodes support both
  a set form (`:SENS1:FREQ:STAR 1e9`) and a query (`:SENS1:FREQ:STAR?`).
- **`[ ]`** (in the official syntax) = optional syntax element.
- **`<...>`** = a parameter you supply (value, string, enum).
- Multiple parameters are comma-separated; a space separates the command from
  its first parameter.

### Command groups

1. **IEEE 488.2 common commands** — begin with `*` (e.g. `*IDN?`, `*CLS`,
   `*OPC?`). No hierarchy.
2. **E5061A/E5062A/E5063A instrument commands** — colon-separated hierarchical
   tree (e.g. `:SENS1:FREQ:STAR`).

### Command-tree path rules (matter when chaining with `;`)

- A **message terminator** (newline) resets the current path to root.
- A leading **colon `:`** sets the following mnemonic as root-level.
- A **semicolon `;`** separates two commands *in the same message without
  changing the path*. e.g. `*CLS;:STAT:PRES`. Safest practice for portability:
  start every command with `:` and send one command per write.

---

## 2. Quick-start connection check (PoC)

```
*IDN?            → expect "Keysight Technologies,E5063A,<serial>,<fw>"
*CLS             → clear status / error queue
:SYST:ERR?       → expect 0,"No error"
```

Use `*OPC?` (returns `1`) to block until queued overlapped operations
(e.g. a sweep or calibration) finish.

---

## 3. Transport & connection

The E5063A supports three physical interfaces; all carry the same SCPI strings.

| Interface | VISA resource string | Notes |
|-----------|----------------------|-------|
| **LAN (TCPIP / VXI-11 / HiSLIP)** | `TCPIP0::<ip>::inst0::INSTR` | Configure IP on the analyzer; most common for the lab setup. |
| **LAN raw socket** | `TCPIP0::<ip>::5025::SOCKET` | Program-control socket **port 5025**. Lowest-overhead path; you must append `\n` and handle binary blocks yourself. |
| **USB (USBTMC)** | `USB0::0x0957::0x1309::<serial>::INSTR` | Auto-detected USBTMC; sidesteps router config. (`0x0957` = Keysight VID.) |
| **GPIB** | `GPIB0::17::INSTR` | Default address 17; needs a GPIB adapter. |

### LAN remote-control servers (must be enabled on the instrument)

- **SICL-LAN server** — VISA/SICL control. On the instrument:
  `[System] - Misc Setup - Network Setup - SICL-LAN Server [ON]`, set
  `SICL-LAN Address`. Restart firmware after toggling.
- **Telnet / socket server** — `[System] - Misc Setup - Network Setup -
  Telnet Server [ON]`.
  - **Port 23** (E5062A) / **5024** (E5063A): interactive telnet (type SCPI by hand).
  - **Port 5025**: programmatic socket control (both models). **Use this for code.**
- **Raw socket minimal test:** `connect <ip>:5025` → send `*IDN?\n` → read line.
- **Caveat (E5063A):** the web server and the socket server cannot run
  simultaneously; open ports 5024/5025 in the instrument's Windows firewall.

### Notes / gotchas

- The E5061/E5062 has **no GPIB "remote mode"** and no local-lockout key; to
  prevent front-panel interference during automation, lock input with
  `:SYST:KLOC:KBD` and `:SYST:KLOC:MOUS`.
- Some features available over GPIB (e.g. SRQ service requests) are **not
  available over the telnet/socket server** — for SRQ-driven flows prefer
  GPIB/USBTMC/VXI-11.

---

## 4. Data transfer formats (critical for speed)

Set with `:FORM:DATA` and (for binary) `:FORM:BORD`:

| Command | Meaning | When to use |
|---------|---------|-------------|
| `:FORM:DATA ASC` | ASCII | PoC / debugging — human-readable, slowest (large transfers). |
| `:FORM:DATA REAL` | 64-bit IEEE-488.2 binary block | Large traces, max precision. |
| `:FORM:DATA REAL32` | 32-bit IEEE-488.2 binary block | **Fastest** for high sweep-rate logging (bench-validated as the speed lever for the E5063A migration). |
| `:FORM:BORD NORM` / `SWAP` | Byte order for binary: big-endian (NORM) / little-endian (SWAP) | `SWAP` for little-endian hosts (x86). |

Binary blocks use the IEEE-488.2 **definite-length block** format
(`#<n><len><bytes>`); the host must parse the `#` header and read exactly `len`
bytes. ASCII returns comma-separated values terminated by newline.

### Internal data arrays (what you can read back) — from Ch.7

Per-trace data flows: raw → error-corrected (**SDATa**, complex) → formatted
for display (**FDATa**, depends on trace format). Key read commands:

- `:CALC{ch}:DATA:FDAT?` — **formatted** data array (matches the trace's display
  format: log-mag, phase, etc.). Real values (display) — but note FDATA returns
  pairs (primary,secondary) per point for many formats.
- `:CALC{ch}:DATA:SDAT?` — **corrected** data array, **complex** (real/imag pairs)
  — use this for S-parameter post-processing (magnitude/phase computed host-side).
- `:CALC{ch}:DATA:FMEM?` / `:SMEM?` — memory-trace formatted / corrected arrays.
- `:SENS{ch}:FREQ:DATA?` — the **stimulus (frequency) array**, one value per point.

Always log alongside the data: start/stop/center/span freq, IF bandwidth, points,
channel, trace, and data format (the FDATA interpretation depends on format).

---

## 5. Workflow recipes (task-oriented)

These are distilled from the Programmer's Guide Chapters 3–11, the E5063A
cheat-sheet PoC sequences, and the working `ena_qt6_suite` app modules.

### 5.1 Configure a linear S11 sweep

```
:SYST:PRES                       ; preset
:CALC1:PAR:COUN 1                ; 1 trace on channel 1
:CALC1:PAR1:DEF S11              ; trace 1 = S11
:CALC1:PAR1:SEL                  ; make trace active
:CALC1:FORM MLOG                 ; display format = log magnitude
:SENS1:SWE:TYPE LIN              ; linear sweep (LIN|LOG|SEGM|POW)
:SENS1:FREQ:STAR 2.0E8           ; or CENT/SPAN
:SENS1:FREQ:STOP 2.5E8
:SENS1:SWE:POIN 801              ; points
:SENS1:BAND 30E3                 ; IF bandwidth (=:SENS1:BWID)
:SOUR1:POW -10                   ; stimulus level dBm
```

### 5.2 Triggered single sweep + read trace (host-paced)

```
:TRIG:SOUR BUS                   ; bus/manual trigger source (INT|EXT|MAN|BUS)
:INIT1:CONT OFF                  ; stop free-run on channel 1
:INIT1:IMM                       ; (a.k.a. :INIT1) arm one sweep   ← see note
:TRIG:SING                       ; issue the bus trigger
*OPC?                            ; block until sweep complete (returns 1)
:FORM:DATA ASC
:SENS1:FREQ:DATA?                ; frequency axis
:CALC1:DATA:FDAT?                ; formatted data (or :SDAT? for complex)
:SYST:ERR?                       ; confirm 0,"No error"
```

> The bench scripts (`code/ena-dev/scripts/bench_e5063a_rates.py`) use exactly
> this **BUS + INIT:CONT OFF + per-sweep :INIT:IMM / :TRIG:SING + *OPC?**
> host-paced single-sweep loop. For continuous free-run, set `:INIT1:CONT ON`
> and poll the operation status register (see §7) instead of `*OPC?`.

### 5.3 Full 2-port SOLT calibration (mechanical kit)

```
:SENS1:CORR:COLL:CKIT 1                  ; select cal kit
:SENS1:CORR:COLL:METH:SOLT2 1,2          ; full 2-port on ports 1,2
; --- measure each standard, waiting for completion each time ---
:SENS1:CORR:COLL:OPEN 1   → *OPC?
:SENS1:CORR:COLL:SHOR 1   → *OPC?
:SENS1:CORR:COLL:LOAD 1   → *OPC?
:SENS1:CORR:COLL:OPEN 2   → *OPC?
:SENS1:CORR:COLL:SHOR 2   → *OPC?
:SENS1:CORR:COLL:LOAD 2   → *OPC?
:SENS1:CORR:COLL:THRU 1,2 → *OPC?
:SENS1:CORR:COLL:THRU 2,1 → *OPC?       ; both directions
:SENS1:CORR:COLL:SAVE                    ; compute coefficients + auto-enable correction
```
For **response (1-standard)** cal use `:METH:OPEN|SHOR|THRU` then the matching
`:COLL:OPEN|SHOR|THRU` then `:SAVE`. Only one `:COLL:*` measurement may run at a
time — always gate with `*OPC?`. `:SENS1:CORR:STAT ON|OFF` toggles correction.

### 5.4 ECal (electronic calibration — no standard swapping)

```
:SENS1:CORR:COLL:ECAL:SOLT1 1            ; full 1-port via ECal on port 1
;  or  :SENS1:CORR:COLL:ECAL:SOLT2 1,2   ; full 2-port
;  or  :SENS1:CORR:COLL:ECAL:THRU / :ERES
:SYST:ERR?                                ; ECal auto-does measure+compute+enable; poll error queue/*OPC?
```
`:SENS1:CORR:COLL:ECAL:ISOL ON|OFF` controls isolation measurement.

### 5.5 Save / recall

```
:MMEM:STOR:STYP CST                       ; include cal coefficients in saved state (STYP)
:MMEM:STOR "D:\state.sta"                 ; save instrument state
:MMEM:LOAD "D:\state.sta"                 ; recall
:MMEM:STOR:FDAT "D:\trace.csv"            ; save active trace as CSV
:MMEM:TRAN "<path>"                       ; transfer file bytes to/from host
```

### 5.6 Speed tips (Ch.11 "Working with Automatic Test Systems")

- `:DISP:ENAB OFF` — stop LCD trace updates → faster command processing.
- `:FORM:DATA REAL32` + `:FORM:BORD SWAP` — binary transfer.
- Lock front panel with `:SYST:KLOC:KBD/:MOUS`.
- Detect errors via the status reporting system or `:SYST:ERR?` (see §7).

---

## 6. Complete categorized command index

Every command in the Programmer's Guide Chapter 13 reference, grouped by
subsystem, with a one-line purpose. Numeric suffixes shown as ranges
(`{1-4}` channel/trace, `{1-10}` marker, `{1-21}` standard, `{1-2}` port/colour).
Detailed parameters/enums for the high-traffic commands are in §8.

### 6.1 IEEE 488.2 common commands

| Command | Purpose |
|---------|---------|
| `*CLS` | Clear status byte, event registers, and error queue. |
| `*ESE` / `*ESE?` | Set/query Standard Event Status **Enable** register. |
| `*ESR?` | Read (and clear) Standard Event Status register. |
| `*IDN?` | Identification string (vendor, model, serial, firmware). |
| `*OPC` | Set OPC bit in ESR when pending overlapped ops complete. |
| `*OPC?` | Return `1` when all pending overlapped ops complete (blocks). |
| `*OPT?` | Installed-option string. |
| `*RST` | Reset to factory preset state (cf. `:SYST:PRES`). |
| `*SRE` / `*SRE?` | Set/query Service Request **Enable** register. |
| `*STB?` | Read Status Byte register. |
| `*TRG` | Bus trigger (equivalent to a `:TRIG:SING` over GPIB). |
| `*WAI` | Wait until all pending overlapped ops complete. |

### 6.2 Root / trigger / initiation

| Command | Purpose |
|---------|---------|
| `:ABOR` | Abort the measurement in progress; reset trigger system to idle. |
| `:INIT{1-4}` | Trigger one channel's measurement (with `:CONT OFF`, arms a single sweep). |
| `:INIT{1-4}:CONT` | Continuous-initiation ON/OFF (free-run vs single). |
| `:TRIG` | (root trigger node) |
| `:TRIG:SING` | Generate a trigger and start one measurement cycle. |
| `:TRIG:SOUR` | Trigger source: `INT` / `EXT` / `MAN` / `BUS`. |
| `:OUTP` | Stimulus (RF source) output ON/OFF (power-trip recovery). |

### 6.3 `:CALC{1-4}` — analysis / trace / markers / limits

**Trace definition & format**

| Command | Purpose |
|---------|---------|
| `:CALC{1-4}:PAR:COUN` | Number of traces on the channel. |
| `:CALC{1-4}:PAR{1-4}:DEF` | Define a trace's measurement parameter (S11/S21/S12/S22…). |
| `:CALC{1-4}:PAR{1-4}:SEL` | Select (activate) a trace. |
| `:CALC{1-4}:FORM` | Trace data format (MLOG/PHAS/GDEL/MLIN/SWR/REAL/IMAG/SMIT/POL…). |
| `:CALC{1-4}:MATH:FUNC` | Data-vs-memory math (NORM/ADD/SUB/MUL/DIV). |
| `:CALC{1-4}:MATH:MEM` | Copy data trace → memory trace. |
| `:CALC{1-4}:CONV` | Parameter conversion ON/OFF (Z/Y/1-S etc.). |
| `:CALC{1-4}:CONV:FUNC` | Conversion function selection. |
| `:CALC{1-4}:CORR:EDEL:TIME` | Electrical-delay time (s) for the trace. |
| `:CALC{1-4}:CORR:OFFS:PHAS` | Phase offset (deg) for the trace. |
| `:CALC{1-4}:SMO` | Smoothing ON/OFF. |
| `:CALC{1-4}:SMO:APER` | Smoothing aperture (% of span). |

**Data arrays**

| Command | Purpose |
|---------|---------|
| `:CALC{1-4}:DATA:FDAT` | Formatted data array (read/write). |
| `:CALC{1-4}:DATA:SDAT` | Corrected (complex) data array (read/write). |
| `:CALC{1-4}:DATA:FMEM` | Formatted memory array. |
| `:CALC{1-4}:DATA:SMEM` | Corrected memory array. |

**Markers** (per-marker `{1-10}`; also channel-wide marker-function nodes)

| Command | Purpose |
|---------|---------|
| `:CALC{1-4}:MARK{1-10}` | Marker ON/OFF. |
| `:CALC{1-4}:MARK{1-10}:X` | Marker stimulus (X) position (set/query). |
| `:CALC{1-4}:MARK{1-10}:Y?` | Marker response (Y) value (query). |
| `:CALC{1-4}:MARK{1-10}:ACT` | Make marker active. |
| `:CALC{1-4}:MARK{1-10}:SET` | Set a sweep parameter from the marker (e.g. marker→center). |
| `:CALC{1-4}:MARK{1-10}:DISC` | Discrete marker mode ON/OFF. |
| `:CALC{1-4}:MARK{1-10}:FUNC:TYPE` | Search type (MAX/MIN/PEAK/TARG…). |
| `:CALC{1-4}:MARK{1-10}:FUNC:EXEC` | Execute the marker search. |
| `:CALC{1-4}:MARK{1-10}:FUNC:PEXC` | Peak excursion. |
| `:CALC{1-4}:MARK{1-10}:FUNC:PPOL` | Peak polarity. |
| `:CALC{1-4}:MARK{1-10}:FUNC:TARG` | Target value for target search. |
| `:CALC{1-4}:MARK{1-10}:FUNC:TRAC` | Search-tracking ON/OFF. |
| `:CALC{1-4}:MARK{1-10}:FUNC:TTR` | Target transition (left/right). |
| `:CALC{1-4}:MARK{1-10}:BWID:DATA?` | Bandwidth-search result (BW, center, Q, loss…). |
| `:CALC{1-4}:MARK{1-10}:BWID:THR` | Bandwidth threshold (dB). |
| `:CALC{1-4}:MARK{1-10}:NOTC:DATA?` | Notch-search result. |
| `:CALC{1-4}:MARK{1-10}:NOTC:THR` | Notch threshold. |
| `:CALC{1-4}:MARK:BWID` | Bandwidth-search ON/OFF (channel). |
| `:CALC{1-4}:MARK:NOTC` | Notch-search ON/OFF (channel). |
| `:CALC{1-4}:MARK:COUP` | Marker coupling across traces ON/OFF. |
| `:CALC{1-4}:MARK:REF` | Reference-marker mode ON/OFF. |
| `:CALC{1-4}:MARK:FUNC:DOM` / `:DOM:COUP` / `:DOM:STAR` / `:DOM:STOP` | Search domain (partial-search range) settings. |
| `:CALC{1-4}:MARK:FUNC:MULT:PEXC` / `PPOL` / `TARG` / `TRAC` / `TTR` / `TYPE` | Multi-peak/multi-target search settings. |
| `:CALC{1-4}:MARK:MATH:FLAT` / `:FLAT:DATA?` | Flatness analysis on/off / result. |
| `:CALC{1-4}:MARK:MATH:FST` / `:FST:DATA?` | Filter-stat analysis on/off / result. |
| `:CALC{1-4}:MARK:MATH:STAT` / `:STAT:DATA?` | Statistics (mean/std/p-p) on/off / result. |
| `:CALC{1-4}:FUNC:DATA?` | Analysis-command result data. |
| `:CALC{1-4}:FUNC:DOM` / `:DOM:COUP` / `:DOM:STAR` / `:DOM:STOP` | Analysis search domain. |
| `:CALC{1-4}:FUNC:EXEC` | Execute analysis command. |
| `:CALC{1-4}:FUNC:PEXC` / `:PPOL` / `:POIN?` / `:TARG` / `:TTR` / `:TYPE` | Analysis search params / result count / type. |
| `:CALC{1-4}:MST` / `:MST:DATA?` | Marker statistics on/off / data. |

**Limit & ripple-limit test**

| Command | Purpose |
|---------|---------|
| `:CALC{1-4}:LIM` | Limit test ON/OFF. |
| `:CALC{1-4}:LIM:DATA` | Limit-line table (set/query). |
| `:CALC{1-4}:LIM:DISP` | Show/hide limit lines. |
| `:CALC{1-4}:LIM:DISP:CLIP` | Clip limit lines to graph. |
| `:CALC{1-4}:LIM:FAIL?` | Limit-test pass/fail for the trace. |
| `:CALC{1-4}:LIM:REP?` / `:REP:ALL?` / `:REP:POIN?` | Failure report (trace / all / failing points). |
| `:CALC{1-4}:LIM:OFFS:AMPL` / `:MARK` / `:STIM` | Limit-line offsets (amplitude / marker / stimulus). |
| `:CALC{1-4}:RLIM` | Ripple-limit test ON/OFF. |
| `:CALC{1-4}:RLIM:DATA` | Ripple-limit table. |
| `:CALC{1-4}:RLIM:DISP:LINE` / `:SEL` / `:VAL` | Ripple-limit display line / band select / value display. |
| `:CALC{1-4}:RLIM:FAIL?` / `:REP?` | Ripple-limit pass/fail / report. |
| `:CALC{1-4}:BLIM` … | Bandwidth-limit test family (`:DB`, `:DISP:MARK`, `:DISP:VAL`, `:FAIL?`, `:MAX`, `:MIN`, `:REP?`). |

### 6.4 `:CONT:HAND` — Handler I/O port (production handler)

| Command | Purpose |
|---------|---------|
| `:CONT:HAND:A` / `:B` / `:C` / `:D` / `:E` / `:F` | Read/write handler I/O port banks. |
| `:CONT:HAND:C:MODE` / `:D:MODE` | Port C/D direction (input/output). |
| `:CONT:HAND:OUTP{1-2}` | Output line state. |
| `:CONT:HAND:IND:STAT` | Index signal state. |
| `:CONT:HAND:RTR:STAT` | Ready-to-receive signal state. |

> Likely option-gated / not central to the E5063A logging use-case.

### 6.5 `:DISP` — display & screen

| Command | Purpose |
|---------|---------|
| `:DISP:ENAB` | LCD trace-update ON/OFF (turn OFF for speed). |
| `:DISP:UPD` | Display update control. |
| `:DISP:SPL` | Window (channel) layout selection. |
| `:DISP:MAX` | Maximize active window. |
| `:DISP:WIND{1-4}:SPL` | Graph (trace) layout within a window. |
| `:DISP:WIND{1-4}:MAX` | Maximize active trace. |
| `:DISP:WIND{1-4}:ACT` | Make a channel/window active. |
| `:DISP:WIND{1-4}:TRAC{1-4}:STAT` | Show/hide data trace. |
| `:DISP:WIND{1-4}:TRAC{1-4}:MEM` | Show/hide memory trace. |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:AUTO` | Auto-scale a trace. |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:PDIV` | Scale per division (or full-scale for Smith/polar). |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:RLEV` | Reference-line value. |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:RPOS` | Reference-line position. |
| `:DISP:WIND{1-4}:Y:DIV` | Number of Y divisions (channel-wide). |
| `:DISP:WIND{1-4}:X:SPAC` | X-axis spacing (lin/log). |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:TRAC:FREQ` / `:MODE` | Trace-vs-frequency Y settings. |
| `:DISP:WIND{1-4}:TRAC{1-4}:ANN:YAX:MODE` | Y-axis annotation mode. |
| `:DISP:WIND{1-4}:TRAC{1-4}:ANN:MARK:POS:X` / `:Y` | Marker annotation position. |
| `:DISP:WIND{1-4}:ANN:MARK:ALIG` / `:SING` | Marker readout alignment / single. |
| `:DISP:WIND{1-4}:LAB` | Graticule label show/hide. |
| `:DISP:WIND{1-4}:TITL` / `:TITL:DATA` | Title show/hide / text. |
| `:DISP:ANN:FREQ` | Show/hide frequency annotation. |
| `:DISP:CLOC` | Show/hide clock. |
| `:DISP:CCL` | Clear (something) — see §8/PDF. |
| `:DISP:ECHO` / `:ECHO:CLE` | Print to / clear the echo window. |
| `:DISP:FSIG` | Frequency-blanking / "frequencies hidden" toggle. |
| `:DISP:IMAG` | Normal/inverted display mode. |
| `:DISP:SKEY` | Softkey-label show/hide. |
| `:DISP:TABL` / `:TABL:TYPE` | Bottom table show/hide / type. |
| `:DISP:COL{1-2}:BACK` / `:GRAT{1-2}` / `:LIM{1-2}` / `:RES` / `:TRAC{1-4}:DATA` / `:TRAC{1-4}:MEM` | Display colours (normal/invert sets) / reset. |

### 6.6 `:FORM` — data format

| Command | Purpose |
|---------|---------|
| `:FORM:DATA` | Transfer format: `ASC` / `REAL` (64-bit) / `REAL32` (32-bit). |
| `:FORM:BORD` | Binary byte order: `NORM` / `SWAP`. |

### 6.7 `:HCOP` — hardcopy / screen image

| Command | Purpose |
|---------|---------|
| `:HCOP` | Hardcopy (print). |
| `:HCOP:ABOR` | Abort hardcopy. |
| `:HCOP:IMAG` | Image colour mode for hardcopy. |
| `:HCOP:SDUM:DATA?` | **Screen-dump image data** (used by screen-capture tooling). |

### 6.8 `:MMEM` — mass memory / files

| Command | Purpose |
|---------|---------|
| `:MMEM:CAT?` | Directory catalog. |
| `:MMEM:MDIR` | Make directory. |
| `:MMEM:COPY` | Copy file. |
| `:MMEM:DEL` | Delete file. |
| `:MMEM:TRAN` | Transfer file bytes (host ↔ instrument). |
| `:MMEM:STOR` | Save instrument state (`.sta`). |
| `:MMEM:STOR:STYP` | What a state save includes (e.g. `CST` = with cal coefficients). |
| `:MMEM:STOR:FDAT` | Save formatted trace data to file (CSV). |
| `:MMEM:STOR:SALL` | Save all-trace data. |
| `:MMEM:STOR:IMAG` | Save screen image. |
| `:MMEM:STOR:CHAN` / `:CHAN:CLE` / `:CHAN:COEF` | Save channel data / clear / cal coefficients. |
| `:MMEM:STOR:LIM` / `:RLIM` / `:SEGM` / `:PROG` | Save limit / ripple-limit / segment / VBA program. |
| `:MMEM:LOAD` | Recall instrument state. |
| `:MMEM:LOAD:CHAN` / `:CHAN:COEF` | Load channel data / cal coefficients. |
| `:MMEM:LOAD:LIM` / `:RLIM` / `:SEGM` / `:PROG` | Load limit / ripple-limit / segment / program. |

### 6.9 `:PROG` — built-in VBA program control

| Command | Purpose |
|---------|---------|
| `:PROG:CAT?` | Catalog of loaded programs. |
| `:PROG:NAME` | Select program by name. |
| `:PROG:STAT` | Run/stop program state. |

### 6.10 `:SENS{1-4}` — measurement (sweep / IFBW / averaging / calibration)

**Frequency & sweep**

| Command | Purpose |
|---------|---------|
| `:SENS{1-4}:FREQ` | CW (fixed) frequency (power-sweep mode). |
| `:SENS{1-4}:FREQ:STAR` | Start frequency. |
| `:SENS{1-4}:FREQ:STOP` | Stop frequency. |
| `:SENS{1-4}:FREQ:CENT` | Center frequency. |
| `:SENS{1-4}:FREQ:SPAN` | Span. |
| `:SENS{1-4}:FREQ:DATA?` | Stimulus (frequency) array. |
| `:SENS{1-4}:SWE:POIN` | Number of points. |
| `:SENS{1-4}:SWE:TYPE` | Sweep type: `LIN` / `LOG` / `SEGM` / `POW`. |
| `:SENS{1-4}:SWE:TIME` | Sweep time. |
| `:SENS{1-4}:SWE:TIME:AUTO` | Auto sweep-time ON/OFF. |
| `:SENS{1-4}:SWE:DEL` | Sweep delay time. |
| `:SENS{1-4}:BAND` / `:BWID` | IF bandwidth (synonyms). |
| `:SENS{1-4}:ROSC:SOUR?` | Reference-oscillator source (INT/EXT). |

**Averaging**

| Command | Purpose |
|---------|---------|
| `:SENS{1-4}:AVER` | Averaging ON/OFF. |
| `:SENS{1-4}:AVER:COUN` | Averaging factor. |
| `:SENS{1-4}:AVER:CLE` | Clear/restart averaging. |

**Segment sweep**

| Command | Purpose |
|---------|---------|
| `:SENS{1-4}:SEGM:DATA` | Whole segment-sweep table (set/query). |
| `:SENS{1-4}:SEGM:SWE:POIN?` | Total points in segment table. |
| `:SENS{1-4}:SEGM:SWE:TIME?` | Total segment sweep time. |

**System impedance / port extension**

| Command | Purpose |
|---------|---------|
| `:SENS:CORR:IMP` | System characteristic impedance Z0 (fw ≥ 3.01). |
| `:SENS{1-4}:CORR:EXT` | Port-extension ON/OFF. |
| `:SENS{1-4}:CORR:EXT:PORT{1-2}` | Per-port extension delay. |
| `:SENS{1-4}:CORR:PROP` | Media/propagation (port-extension velocity context). |
| `:SENS{1-4}:CORR:RVEL:COAX` | Velocity factor (coax). |

**Calibration (error correction)**

| Command | Purpose |
|---------|---------|
| `:SENS{1-4}:CORR:STAT` | Error correction ON/OFF. |
| `:SENS{1-4}:CORR:CLE` | Clear calibration. |
| `:SENS{1-4}:CORR:COEF?` | Read calibration coefficients. |
| `:SENS{1-4}:CORR:TYPE{1-4}?` | Applied calibration type per trace. |
| `:SENS{1-4}:CORR:COLL:METH:OPEN` / `:SHOR` / `:THRU` | Select response-cal method. |
| `:SENS{1-4}:CORR:COLL:METH:ERES` | Enhanced-response method. |
| `:SENS{1-4}:CORR:COLL:METH:SOLT1` / `:SOLT2` | Full 1-/2-port method. |
| `:SENS{1-4}:CORR:COLL:METH:TYPE?` | Query selected cal method. |
| `:SENS{1-4}:CORR:COLL:OPEN` / `:SHOR` / `:LOAD` / `:THRU` / `:ISOL` | Measure a standard. |
| `:SENS{1-4}:CORR:COLL:SAVE` | Compute coefficients + enable correction. |
| `:SENS{1-4}:CORR:COLL:ECAL:SOLT1` / `:SOLT2` / `:ERES` / `:THRU` | ECal one-shot calibration. |
| `:SENS{1-4}:CORR:COLL:ECAL:ISOL` / `:ERES` | ECal isolation / enhanced-response options. |
| `:SENS:CORR:COLL:ECAL:PATH?` | ECal module path/port info. |

**Calibration-kit definition** (`:SENS{1-4}:CORR:COLL:CKIT…`)

| Command | Purpose |
|---------|---------|
| `:CKIT` | Select calibration kit. |
| `:CKIT:LAB` | Cal-kit label/name. |
| `:CKIT:RES` | Reset cal-kit definition. |
| `:CKIT:ORD:OPEN` / `:SHOR` / `:LOAD` / `:THRU` | Standard-class assignment (which standard for each measurement). |
| `:CKIT:STAN{1-21}:TYPE` | Standard type (OPEN/SHORT/LOAD/THRU/ARBI). |
| `:CKIT:STAN{1-21}:LAB` | Standard label. |
| `:CKIT:STAN{1-21}:C0` / `:C1` / `:C2` / `:C3` | OPEN fringing-capacitance polynomial. |
| `:CKIT:STAN{1-21}:L0` / `:L1` / `:L2` / `:L3` | SHORT residual-inductance polynomial. |
| `:CKIT:STAN{1-21}:DEL` | Offset delay. |
| `:CKIT:STAN{1-21}:LOSS` | Offset loss. |
| `:CKIT:STAN{1-21}:Z0` | Offset Z0. |
| `:CKIT:STAN{1-21}:ARB` | Arbitrary impedance value. |

### 6.11 `:SERV` — service / topology queries

| Command | Purpose |
|---------|---------|
| `:SERV:CHAN:ACT?` | Active channel number. |
| `:SERV:CHAN:COUN?` | Number of channels. |
| `:SERV:CHAN{1-4}:TRAC:ACT?` | Active trace of a channel. |
| `:SERV:CHAN:TRAC:COUN?` | Trace count. |
| `:SERV:PORT:COUN?` | Number of test ports. |

### 6.12 `:SOUR{1-4}` — stimulus source / power

| Command | Purpose |
|---------|---------|
| `:SOUR{1-4}:POW` | Power level (dBm). |
| `:SOUR{1-4}:POW:ATT` | Power-range attenuator (option-gated). |
| `:SOUR{1-4}:POW:PORT:COUP` | Couple power across ports ON/OFF. |
| `:SOUR{1-4}:POW:PORT{1-2}` | Per-port power level. |
| `:SOUR{1-4}:POW:SLOP` / `:SLOP:STAT` | Power-slope value / ON-OFF. |
| `:SOUR{1-4}:POW:STAR` / `:STOP` / `:CENT` / `:SPAN` | Power-sweep range (power-sweep mode). |

### 6.13 `:STAT` — status reporting

| Command | Purpose |
|---------|---------|
| `:STAT:PRES` | Preset status enable/transition registers. |
| `:STAT:OPER?` / `:OPER:COND?` | Operation status event / condition. |
| `:STAT:OPER:ENAB` | Operation status enable. |
| `:STAT:OPER:NTR` / `:PTR` | Operation negative/positive transition filters. |
| `:STAT:QUES?` / `:QUES:COND?` | Questionable status event / condition. |
| `:STAT:QUES:ENAB` / `:NTR` / `:PTR` | Questionable enable / transition filters. |
| `:STAT:QUES:LIM?` … (`:CHAN{1-4}` `:COND?` `:ENAB` `:NTR` `:PTR`) | Limit-test questionable sub-register tree. |
| `:STAT:QUES:RLIM?` … | Ripple-limit questionable sub-register tree. |
| `:STAT:QUES:BLIM?` … | Bandwidth-limit questionable sub-register tree. |

### 6.14 `:SYST` — system

| Command | Purpose |
|---------|---------|
| `:SYST:PRES` | Preset (like `*RST`). |
| `:SYST:ERR?` | Read oldest entry from the error queue (`<code>,"<msg>"`). |
| `:SYST:DATE` / `:SYST:TIME` | Set date / time. |
| `:SYST:BEEP:COMP:IMM` / `:STAT` | Completion beep now / enable. |
| `:SYST:BEEP:WARN:IMM` / `:STAT` | Warning beep now / enable. |
| `:SYST:BACK` | LCD backlight ON/OFF. |
| `:SYST:KLOC:KBD` / `:KLOC:MOUS` | Lock keyboard / mouse (front-panel lockout). |
| `:SYST:POFF` | Power off / shutdown. |
| `:SYST:SEC:LEV` | Security level. |
| `:SYST:SERV?` | Service query. |
| `:SYST:UPR` | (User preset / startup state.) |

---

## 7. Status reporting & error handling

The E5061/E5062/E5063A use the standard IEEE-488.2 status model
(Appendix B of the guide):

- **Status Byte** (`*STB?`, `*SRE`) → summary bits for SRQ generation.
- **Standard Event Status** (`*ESR?`, `*ESE`) → command/execution/query errors,
  OPC.
- **Operation Status** (`:STAT:OPER…`) → includes the *measuring/averaging/sweep*
  bits. For free-run sweep-completion detection without `*OPC?`, watch the
  Operation status with edge-latched transition filters
  (`:STAT:OPER:PTR` / `:NTR` then poll `:STAT:OPER:EVEN?`/`:COND?`).
- **Questionable Status** (`:STAT:QUES…`) → limit/ripple/bandwidth test results,
  with per-channel sub-registers.
- **Error queue:** `:SYST:ERR?` returns `0,"No error"` when empty; read in a loop
  to drain. Always check after calibration, format switches, and data reads.

**Recommended logging per command:** timestamp, command, response summary,
elapsed time, error code, retry count.

---

## 8. Detailed command reference (Chapter 13)

> The per-command **syntax / parameters / range / query response** detail,
> transcribed subsystem-by-subsystem from the Programmer's Guide Chapter 13.
> Compact form: each entry gives the set/query syntax, parameter enum/range/
> preset/unit, and the query-response token. `{1-4}` = channel/trace suffix.
> Where a command takes `{ON|OFF|1|0}` the query returns `{1|0}`.
>
> **Chapter-13 notation:** `<>` = required parameter, `[]` = optional syntax
> element, `{a|b}` = choose one. Lowercase letters in a mnemonic are optional
> (short form). Out-of-range numerics are clamped to min/max (or AND'd with
> 0xFF for register values) unless noted.

### 8.1 IEEE 488.2 common commands

| Command | Syntax / params | Query response | Notes |
|---------|-----------------|----------------|-------|
| `*CLS` | `*CLS` (no query) | — | Clears error queue + Status Byte + all event registers (Standard Event, Operation, Questionable, Questionable-Limit, Questionable-Limit-Channel{1-4}). |
| `*ESE` | `*ESE <numeric>` / `*ESE?` | `{numeric}` | Standard Event Status **Enable** reg. Range 0–255, preset 0, res 1 (out-of-range → AND 0xFF). |
| `*ESR?` | `*ESR?` (query only) | `{numeric}` | Reads & clears Standard Event Status reg. |
| `*IDN?` | `*IDN?` (query only) | `{mfr},{model},{serial},{fw}` | e.g. `Agilent Technologies,E5061A,JP1KI00101,03.00`. On E5063A: `Keysight Technologies,E5063A,…`. |
| `*OPC` | `*OPC` (no query) | — | Sets OPC bit (ESR bit 0) when pending overlapped ops finish. |
| `*OPC?` | `*OPC?` (query only) | `{1}` | Returns `1` when all pending ops complete (the blocking-wait idiom). |
| `*OPT?` | `*OPT?` (query only) | `{numeric/string}` | Installed-option ID; `0` if none. |
| `*RST` | `*RST` (no query) | — | Preset. Differs from `:SYST:PRES`: also sets channel-1 continuous-initiation **OFF**. |
| `*SRE` | `*SRE <numeric>` / `*SRE?` | `{numeric}` | Service Request Enable reg. 0–255, preset 0 (bit 6 can't be set). `*SRE 128` enables SRQ on bit 7 (operation status summary). |
| `*STB?` | `*STB?` (query only) | `{numeric}` | Reads Status Byte register. |
| `*TRG` | `*TRG` (no query) | — | Bus-trigger the instrument (only when `:TRIG:SOUR BUS`). Cannot be `*OPC?`-waited. |
| `*WAI` | `*WAI` (no query) | — | Wait until all prior commands complete. |

### 8.2 Root / trigger / initiation

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:ABOR` | `:ABORt` (no query) | — | Abort measurement, set all channels' trigger sequence to idle; channels with `:INIT:CONT ON` re-enter initiate. Equiv. `[Trigger]-Restart`. |
| `:INIT{1-4}` | `:INITiate{1-4}[:IMMediate]` (no query) | — | Put channel into initiate (arm one sweep when `:CONT OFF`). |
| `:INIT{1-4}:CONT` | `:INITiate{1-4}:CONTinuous {ON\|OFF\|1\|0}` | `{1\|0}` | Continuous initiation (free-run). Preset: ch1 ON (`*RST`→OFF), others OFF. |
| `:TRIG` (`:TRIG[:IMMediate]`) | `:TRIGger[:SEQuence][:IMMediate]` (no query) | — | Trigger when "waiting for trigger" (any source). Not `*OPC?`-waitable. |
| `:TRIG:SING` | `:TRIGger[:SEQuence]:SINGle` (no query) | — | Generate one trigger + measure. **Can** be `*OPC?`-waited. Works for EXT/BUS/MAN sources. |
| `:TRIG:SOUR` | `:TRIGger[:SEQuence]:SOURce {INTernal\|EXTernal\|MANual\|BUS}` | `{INT\|EXT\|MAN\|BUS}` | Trigger source. `BUS` for host-paced (`*TRG`/`:TRIG`/`:TRIG:SING`). |
| `:OUTP` | `:OUTPut[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | RF stimulus output on/off (power-trip recovery). |

### 8.3 `:CALC{1-4}` — trace format, conversion, scale-correction

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CALC{1-4}:FORM` | `…:FORMat {MLOGarithmic\|PHASe\|GDELay\|SLINear\|SLOGarithmic\|SCOMplex\|SMITh\|SADMittance\|PLINear\|PLOGarithmic\|POLar\|MLINear\|SWR\|REAL\|IMAGinary\|UPHase\|PPHase}` | `{MLOG\|PHAS\|GDEL\|SLIN\|SLOG\|SCOM\|SMIT\|SADM\|PLIN\|PLOG\|POL\|MLIN\|SWR\|REAL\|IMAG\|UPH\|PPH}` | Trace display format (preset **MLOG**). Determines FDATA secondary-value meaning (see §4). |
| `:CALC{1-4}:CONV` | `…:CONVersion[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Parameter conversion on/off (preset OFF). |
| `:CALC{1-4}:CONV:FUNC` | `…:CONVersion:FUNCtion {ZREFlection\|ZTRansmit\|YREFlection\|YTRansmit\|INVersion}` | `{ZREF\|ZTR\|YREF\|YTR\|INV}` | Conversion target (preset ZREF): Z/Y reflection/transmission, or 1/S. |
| `:CALC{1-4}:CORR:EDEL:TIME` | `…:CORRection:EDELay:TIME <numeric>` | `{numeric}` | Electrical delay, −10…10 s, preset 0. |
| `:CALC{1-4}:CORR:OFFS:PHAS` | `…:CORRection:OFFSet:PHASe <numeric>` | `{numeric}` | Phase offset, −360…360°, preset 0. |
| `:CALC{1-4}:MATH:FUNC` | `…:MATH:FUNCtion {NORMal\|ADD\|SUBtract\|MULTiply\|DIVide}` | `{NORM\|ADD\|SUBT\|MULT\|DIV}` | Data-vs-memory math (preset NORM). |
| `:CALC{1-4}:MATH:MEM` | `…:MATH:MEMorize` (no query) | — | Copy data trace → memory trace. |
| `:CALC{1-4}:SMO` | `…:SMOothing[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Smoothing on/off. |
| `:CALC{1-4}:SMO:APER` | `…:SMOothing:APERture <numeric>` | `{numeric}` | Smoothing aperture (% of span). |

### 8.4 `:CALC{1-4}` — data arrays

| Command | Syntax | Query response | Notes |
|---------|--------|----------------|-------|
| `:CALC{1-4}:DATA:FDAT` | `…:DATA:FDATa <n1>,…,<n_{NOP×2}>` / `?` | `{n1},…,{n_{NOP×2}}` | **Formatted** array: 2 values/point — primary, secondary (secondary=0 unless Smith/polar). Transfer per `:FORM:DATA`. Writable. |
| `:CALC{1-4}:DATA:SDAT` | `…:DATA:SDATa <…>` / `?` | `{Re1},{Im1},…` | **Corrected** array: complex Re/Im pairs (2/point). Use for S-param math. Writable. |
| `:CALC{1-4}:DATA:FMEM` | `…:DATA:FMEMory <…>` / `?` | as FDAT | Formatted memory array. |
| `:CALC{1-4}:DATA:SMEM` | `…:DATA:SMEMory?` | as SDAT | Corrected memory array (copy made by `:MATH:MEM`). |

### 8.5 `:CALC{1-4}:FUNC` — analysis (search/stats on the trace)

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CALC{1-4}:FUNC:TYPE` | `…:FUNCtion:TYPE {PTPeak\|STDEV\|MEAN\|MAXimum\|MINimum\|PEAK\|APEak\|ATARget}` | `{PTP\|STDEV\|MEAN\|MAX\|MIN\|PEAK\|APE\|ATAR}` | Analysis type (preset PTPeak). |
| `:CALC{1-4}:FUNC:EXEC` | `…:FUNCtion:EXECute` (no query) | — | Run the analysis. |
| `:CALC{1-4}:FUNC:DATA?` | `…:FUNCtion:DATA?` | `{val1},{stim1},…` | Result pairs (response/result, stimulus). Stimulus=0 for max/min/std/mean. |
| `:CALC{1-4}:FUNC:POIN?` | `…:FUNCtion:POINts?` | `{numeric}` | # result pairs (1 for mean/max; N for all-peaks/all-targets). |
| `:CALC{1-4}:FUNC:PEXC` | `…:FUNCtion:PEXCursion <numeric>` | `{numeric}` | Peak excursion, 0…5E8, preset 3. Unit per format (dB/°/s/none). |
| `:CALC{1-4}:FUNC:PPOL` | `…:FUNCtion:PPOLarity {POSitive\|NEGative\|BOTH}` | `{POS\|NEG\|BOTH}` | Peak polarity (preset POS). |
| `:CALC{1-4}:FUNC:TARG` | `…:FUNCtion:TARGet <numeric>` | `{numeric}` | Target value, −5E8…5E8, preset 0. |
| `:CALC{1-4}:FUNC:TTR` | `…:FUNCtion:TTRansition {POSitive\|NEGative\|BOTH}` | `{POS\|NEG\|BOTH}` | Target transition (preset BOTH). |
| `:CALC{1-4}:FUNC:DOM` | `…:FUNCtion:DOMain[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Use arbitrary analysis range (preset OFF=whole sweep). |
| `:CALC{1-4}:FUNC:DOM:COUP` | `…:FUNCtion:DOMain:COUPle {ON\|OFF\|1\|0}` | `{1\|0}` | Couple analysis range across traces (preset ON). |
| `:CALC{1-4}:FUNC:DOM:STAR` / `:STOP` | `…:FUNCtion:DOMain:STARt\|STOP <numeric>` | `{numeric}` | Analysis range start/stop (Hz/dBm/s), preset 0. |

### 8.6 `:CALC{1-4}:LIM` — limit test

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CALC{1-4}:LIM` | `…:LIMit[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Limit test on/off (preset OFF). |
| `:CALC{1-4}:LIM:DATA` | `…:LIMit:DATA <N>,<type,xs,xe,ys,ye>×N` / `?` | echoes table | Limit table. type: 0=off,1=upper,2=lower. N=0 clears. 5 numerics per line. |
| `:CALC{1-4}:LIM:DISP` | `…:LIMit:DISPlay[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Show limit lines (test still runs if hidden). |
| `:CALC{1-4}:LIM:DISP:CLIP` | `…:LIMit:DISPlay:CLIP {ON\|OFF\|1\|0}` | `{1\|0}` | Clip unused part of lines (preset ON). |
| `:CALC{1-4}:LIM:FAIL?` | `…:LIMit:FAIL?` | `{1\|0}` | 1=FAIL, 0=PASS (0 if test off). |
| `:CALC{1-4}:LIM:REP?` | `…:LIMit:REPort[:DATA]?` | `{stim…}` | Stimulus values of failed points (format per `:FORM:DATA`). |
| `:CALC{1-4}:LIM:REP:POIN?` | `…:LIMit:REPort:POINts?` | `{numeric}` | # failed points. |
| `:CALC{1-4}:LIM:OFFS:AMPL` | `…:LIMit:OFFSet:AMPLitude <numeric>` | `{numeric}` | Amplitude offset, −5E8…5E8 dB, preset 0. |
| `:CALC{1-4}:LIM:OFFS:STIM` | `…:LIMit:OFFSet:STIMulus <numeric>` | `{numeric}` | Stimulus offset, −1E12…1E12, preset 0. |
| `:CALC{1-4}:LIM:OFFS:MARK` | `…:LIMit:OFFSet:MARKer` (no query) | — | Set amplitude offset from active marker. |

### 8.7 `:CALC{1-4}:BLIM` — bandwidth-limit test

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CALC{1-4}:BLIM` | `…:BLIMit[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Bandwidth test on/off. |
| `:CALC{1-4}:BLIM:DB` | `…:BLIMit:DB <numeric>` | `{numeric}` | N-dB threshold, 0…5E8 dB, preset 3. |
| `:CALC{1-4}:BLIM:MAX` / `:MIN` | `…:BLIMit:MAXimum\|MINimum <numeric>` | `{numeric}` | Max/min bandwidth, 0…1E12 (Hz/dB/s); preset 10k / 300k. |
| `:CALC{1-4}:BLIM:FAIL?` | `…:BLIMit:FAIL?` | `{1\|0}` | 1=FAIL (0 if off). |
| `:CALC{1-4}:BLIM:REP?` | `…:BLIMit:REPort[:DATA]?` | `{numeric}` | Measured bandwidth value. |
| `:CALC{1-4}:BLIM:DISP:MARK` / `:VAL` | `…:BLIMit:DISPlay:MARKer\|VALue {ON\|OFF\|1\|0}` | `{1\|0}` | Show BW marker / value. |

### 8.8 `:CALC{1-4}:MARK` — markers (per-marker `{1-10}`; marker 10 = reference)

Markers 1–9 plus reference marker (index **10**). `:MARK` (no index) = channel-wide
marker-function nodes. All target the active trace (`:PAR{1-4}:SEL`).

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CALC{1-4}:MARK{1-10}` | `…:MARKer{1-10}[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Show/hide marker (10=reference, toggled by REF mode). |
| `:CALC{1-4}:MARK{1-10}:ACT` | `…:MARKer{1-10}:ACTivate` (no query) | — | Make active marker (auto-turns ON if off). |
| `:CALC{1-4}:MARK{1-10}:X` | `…:MARKer{1-10}:X <numeric>` | `{numeric}` | Stimulus pos. Range start…stop freq (Hz/dBm/s). Relative if REF mode on. |
| `:CALC{1-4}:MARK{1-10}:Y?` | `…:MARKer{1-10}:Y?` | `{prim},{sec}` | Response value (2 values; secondary=0 unless Smith/polar). Relative if REF on. |
| `:CALC{1-4}:MARK{1-10}:SET` | `…:MARKer{1-10}:SET {STARt\|STOP\|CENTer\|RLEVel\|DELay}` (no query) | — | Marker→ start/stop/center/ref-level/delay. |
| `:CALC{1-4}:MARK{1-10}:DISC` | `…:MARKer{1-10}:DISCrete {ON\|OFF\|1\|0}` | `{1\|0}` | Discrete mode (marker snaps to measured points). |
| `:CALC{1-4}:MARK{1-10}:FUNC:TYPE` | `…:FUNCtion:TYPE {MAXimum\|MINimum\|PEAK\|LPEak\|RPEak\|TARGet\|LTARget\|RTARget}` | `{MAX\|MIN\|PEAK\|LPE\|RPE\|TARG\|LTAR\|RTAR}` | Per-marker search type (preset MAX). |
| `:CALC{1-4}:MARK{1-10}:FUNC:EXEC` | `…:FUNCtion:EXECute` (no query) | — | Run the search → marker moves to result. |
| `:CALC{1-4}:MARK{1-10}:FUNC:PEXC` | `…:FUNCtion:PEXCursion <numeric>` | `{numeric}` | Peak excursion 0…5E8, preset 3 (unit per format). |
| `:CALC{1-4}:MARK{1-10}:FUNC:PPOL` | `…:FUNCtion:PPOLarity {POSitive\|NEGative\|BOTH}` | `{POS\|NEG\|BOTH}` | Peak polarity (preset POS). |
| `:CALC{1-4}:MARK{1-10}:FUNC:TARG` | `…:FUNCtion:TARGet <numeric>` | `{numeric}` | Target value −5E8…5E8, preset 0. |
| `:CALC{1-4}:MARK{1-10}:FUNC:TTR` | `…:FUNCtion:TTRansition {POSitive\|NEGative\|BOTH}` | `{POS\|NEG\|BOTH}` | Target transition (preset BOTH). |
| `:CALC{1-4}:MARK{1-10}:FUNC:TRAC` | `…:FUNCtion:TRACking {ON\|OFF\|1\|0}` | `{1\|0}` | Search-tracking (re-search every sweep). |
| `:CALC{1-4}:MARK{1-10}:BWID:DATA?` | `…:BWIDth:DATA?` | `{BW},{cent},{Q},{loss}` | Bandwidth-search result (errors+ignored if search impossible). |
| `:CALC{1-4}:MARK{1-10}:BWID:THR` | `…:BWIDth:THReshold <numeric>` | `{numeric}` | BW definition −5E8…5E8, preset **−3** (unit per format). |
| `:CALC{1-4}:MARK{1-10}:NOTC:DATA?` | `…:NOTCh:DATA?` | `{BW},{cent},{Q},{loss}` | Notch-search result. |
| `:CALC{1-4}:MARK{1-10}:NOTC:THR` | `…:NOTCh:THReshold <numeric>` | `{numeric}` | Notch definition −5E8…5E8, preset −3. |
| `:CALC{1-4}:MARK:BWID` | `…:MARKer:BWIDth[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Show bandwidth-search result (channel). |
| `:CALC{1-4}:MARK:NOTC` | `…:MARKer:NOTCh[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Show notch-search result (channel). |
| `:CALC{1-4}:MARK:COUP` | `…:MARKer:COUPle {ON\|OFF\|1\|0}` | `{1\|0}` | Marker coupling across traces (preset ON). |
| `:CALC{1-4}:MARK:REF` | `…:MARKer:REFerence[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Reference-marker (relative) mode. |
| `:CALC{1-4}:MARK:FUNC:DOM` | `…:MARKer:FUNCtion:DOMain[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Marker-search arbitrary range on/off. |
| `:CALC{1-4}:MARK:FUNC:DOM:COUP` | `…:DOMain:COUPle {ON\|OFF\|1\|0}` | `{1\|0}` | Couple search range across traces (preset ON). |
| `:CALC{1-4}:MARK:FUNC:DOM:STAR` / `:STOP` | `…:DOMain:STARt\|STOP <numeric>` | `{numeric}` | Search range start/stop (Hz/dBm/s). |
| `:CALC{1-4}:MARK:FUNC:MULT:TYPE` | `…:MULTi:TYPE {OFF\|PEAK\|TARGet}` | `{OFF\|PEAK\|TARG}` | Multi-peak / multi-target mode. |
| `:CALC{1-4}:MARK:FUNC:MULT:PEXC` / `:PPOL` | `…:MULTi:PEXCursion <numeric>` / `:PPOLarity {POS\|NEG\|BOTH}` | num / `{POS\|NEG\|BOTH}` | Multi-peak excursion (0…5E8, preset 3) / polarity. |
| `:CALC{1-4}:MARK:FUNC:MULT:TARG` / `:TTR` | `…:MULTi:TARGet <numeric>` / `:TTRansition {POS\|NEG\|BOTH}` | num / enum | Multi-target value (−5E8…5E8) / transition. |
| `:CALC{1-4}:MARK:FUNC:MULT:TRAC` | `…:MULTi:TRACking {ON\|OFF\|1\|0}` | `{1\|0}` | Multi-search tracking. |
| `:CALC{1-4}:MARK:MATH:FLAT` / `:DATA?` | `…:MATH:FLATness[:STATe] {ON\|OFF}` / `:DATA?` | `{1\|0}` / `{span},{gain},{slope},{flatness}` | Flatness analysis on/off + result. |
| `:CALC{1-4}:MARK:MATH:FST` / `:DATA?` | `…:MATH:FSTatistics[:STATe] {ON\|OFF}` / `:DATA?` | `{1\|0}` / `{loss},{ripple},{atten}` | Filter-stats on/off + result. |
| `:CALC{1-4}:MARK:MATH:STAT` / `:DATA?` | `…:MATH:STATistics[:STATe] {ON\|OFF}` / `:DATA?` | `{1\|0}` / `{span},{avg},{stddev},{p-p}` | Statistics on/off + result. |
| `:CALC{1-4}:LIM:REP:ALL?` | `…:LIMit:REPort:ALL?` | `{stim},{res},{upper},{lower}×N` | Per-point limit result (res: 1=pass,0=fail,−1=no-limit). N = sweep points. |

### 8.9 `:CALC{1-4}` — trace count / parameter / math / stats / ripple-limit / smoothing

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CALC{1-4}:PAR:COUN` | `…:PARameter:COUNt <numeric>` | `{numeric}` | # traces 1–4, preset 1. |
| `:CALC{1-4}:PAR{1-4}:DEF` | `…:PARameter{1-4}:DEFine {S11\|S21\|S12\|S22}` | `{S11\|S21\|S12\|S22}` | Trace measurement parameter (preset S11). |
| `:CALC{1-4}:PAR{1-4}:SEL` | `…:PARameter{1-4}:SELect` (no query) | — | Activate trace (must be displayed, else error). |
| `:CALC{1-4}:MATH:FUNC` | `…:MATH:FUNCtion {NORMal\|DIVide\|MULTiply\|SUBTract\|ADD}` | `{NORM\|DIV\|MULT\|SUBT\|ADD}` | Data⟷memory math (preset NORM). |
| `:CALC{1-4}:MATH:MEM` | `…:MATH:MEMorize` (no query) | — | Data → memory. |
| `:CALC{1-4}:MST` | `…:MSTatistics[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Statistics display on/off. |
| `:CALC{1-4}:MST:DATA?` | `…:MSTatistics:DATA?` | `{mean},{stddev},{p-p}` | Statistics result. |
| `:CALC{1-4}:SMO` | `…:SMOothing[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Smoothing on/off. |
| `:CALC{1-4}:SMO:APER` | `…:SMOothing:APERture <numeric>` | `{numeric}` | Aperture 0.05–25 %, preset 1.5. |
| `:CALC{1-4}:RLIM` | `…:RLIMit[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Ripple test on/off. |
| `:CALC{1-4}:RLIM:DATA` | `…:RLIMit:DATA <N>,<type,xs,xe,maxripple>×N` / `?` | echoes | Ripple table (N bands 0–12; type 0/1; maxripple dB). N=0 clears. |
| `:CALC{1-4}:RLIM:DISP:LINE` | `…:RLIMit:DISPlay:LINE {ON\|OFF\|1\|0}` | `{1\|0}` | Show ripple lines. |
| `:CALC{1-4}:RLIM:DISP:SEL` | `…:RLIMit:DISPlay:SELect <numeric>` | `{numeric}` | Band for value display, 1–12, preset 1. |
| `:CALC{1-4}:RLIM:DISP:VAL` | `…:RLIMit:DISPlay:VALue {OFF\|ABS\|MAR}` | `{OFF\|ABS\|MAR}` | Ripple value display: off/absolute/margin. |
| `:CALC{1-4}:RLIM:FAIL?` | `…:RLIMit:FAIL?` | `{1\|0}` | 1=FAIL (0 if off). |
| `:CALC{1-4}:RLIM:REP?` | `…:RLIMit:REPort[:DATA]?` | `{N},{band,ripple,res}×N` | Ripple results (res 0=pass,1=fail). |

### 8.10 `:CONT:HAND` — handler I/O (production handler; option/model-dependent)

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CONT:HAND:A` / `:B` | `:CONTrol:HANDler:A\|B[:DATA] <numeric>` (no query) | — | 8-bit output port A/B, 0–255. |
| `:CONT:HAND:C` / `:D` | `:CONTrol:HANDler:C\|D[:DATA] <numeric>` / `?` | `{numeric}` | 4-bit bidir port, 0–15 (dir per `:MODE`). |
| `:CONT:HAND:E` | `:CONTrol:HANDler:E[:DATA] <numeric>` / `?` | `{numeric}` | 8-bit bidir (C+D), 0–255. |
| `:CONT:HAND:F` | `:CONTrol:HANDler:F[:DATA] <numeric>` (no query) | — | 16-bit output (A+B), 0–65535. |
| `:CONT:HAND:C:MODE` / `:D:MODE` | `…:C\|D:MODE {INPut\|OUTPut}` | `{INP\|OUTP}` | Port direction (preset INP). |
| `:CONT:HAND:OUTP{1-2}` | `…:OUTPut{1-2}[:DATA] {1\|0}` | `{1\|0}` | OUTPUT1/2 line (1=LOW, 0=HIGH). |
| `:CONT:HAND:IND:STAT` | `…[:EXTension]:INDex:STATe {ON\|OFF\|1\|0}` | `{1\|0}` | /INDEX signal output (B6). |
| `:CONT:HAND:RTR:STAT` | `…[:EXTension]:RTRigger:STATe {ON\|OFF\|1\|0}` | `{1\|0}` | /READY-FOR-TRIGGER output (B7). |

### 8.11 `:DISP` — display & screen

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:DISP:ENAB` | `:DISPlay:ENABle {ON\|OFF\|1\|0}` | `{1\|0}` | LCD update on/off (preset ON). **OFF = faster SCPI** (then `:DISP:UPD` to refresh once). |
| `:DISP:UPD` | `:DISPlay:UPDate[:IMMediate]` (no query) | — | Refresh LCD once (when ENAB OFF). |
| `:DISP:SPL` | `:DISPlay:SPLit {D1\|D12\|D1_2\|D112\|D1_1_2\|D123\|D1_2_3\|D12_33\|D11_23\|D13_23\|D12_13\|D1234\|D1_2_3_4\|D12_34}` | same set | Channel-window layout (preset D1). |
| `:DISP:MAX` | `:DISPlay:MAXimize {ON\|OFF\|1\|0}` | `{1\|0}` | Maximize active channel window. |
| `:DISP:WIND{1-4}:ACT` | `:DISPlay:WINDow{1-4}:ACTivate` (no query) | — | Set active channel (must be displayed). |
| `:DISP:WIND{1-4}:SPL` | `:DISPlay:WINDow{1-4}:SPLit {…14 graph layouts…}` | same | Graph (trace) layout within window. |
| `:DISP:WIND{1-4}:MAX` | `:DISPlay:WINDow{1-4}:MAXimize {ON\|OFF}` | `{1\|0}` | Maximize active trace. |
| `:DISP:WIND{1-4}:TRAC{1-4}:STAT` | `…:TRACe{1-4}[:STATe] {ON\|OFF}` | `{1\|0}` | Show data trace. |
| `:DISP:WIND{1-4}:TRAC{1-4}:MEM` | `…:TRACe{1-4}:MEMory {ON\|OFF}` | `{1\|0}` | Show memory trace. |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:AUTO` | `…:Y[:SCALe]:AUTO` (no query) | — | Auto-scale trace. |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:PDIV` | `…:Y:PDIVision <numeric>` | `{numeric}` | Scale/div (or full-scale Smith/polar). |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:RLEV` | `…:Y:RLEVel <numeric>` | `{numeric}` | Reference-line value. |
| `:DISP:WIND{1-4}:TRAC{1-4}:Y:RPOS` | `…:Y:RPOSition <numeric>` | `{numeric}` | Reference-line position. |
| `:DISP:WIND{1-4}:Y:DIV` | `…:Y[:SCALe]:DIVisions <numeric>` | `{numeric}` | # Y divisions (channel-wide). |
| `:DISP:WIND{1-4}:X:SPAC` | `…:X:SPACing {LINear\|LOGarithmic}` | enum | X spacing. |
| `:DISP:WIND{1-4}:LAB` | `…:LABel {ON\|OFF}` | `{1\|0}` | Graticule label. |
| `:DISP:WIND{1-4}:TITL` / `:TITL:DATA` | `…:TITLe[:STATe] {ON\|OFF}` / `:TITLe:DATA <string>` | `{1\|0}` / string | Title show / text. |
| `:DISP:WIND{1-4}:ANN:MARK:ALIG` | `…:ANNotation:MARKer:ALIGn {ON\|OFF}` | `{1\|0}` | Align marker readouts to trace 1 (preset ON). |
| `:DISP:WIND{1-4}:ANN:MARK:SING` | `…:ANNotation:MARKer:SINGle {ON\|OFF}` | `{1\|0}` | Show only active-trace marker (preset ON). |
| `:DISP:ANN:FREQ` | `:DISPlay:ANNotation:FREQuency {ON\|OFF}` | `{1\|0}` | Frequency annotation (preset ON; OFF blanks freq). |
| `:DISP:CLOC` | `:DISPlay:CLOCk {ON\|OFF}` | `{1\|0}` | Clock display (preset ON). |
| `:DISP:CCL` | `:DISPlay:CCLear` (no query) | — | Clear error-message line. |
| `:DISP:ECHO` / `:ECHO:CLE` | `:DISPlay:ECHO[:DATA] <string>` / `:ECHO:CLEar` | — | Print to / clear echo window (≤254 chars). |
| `:DISP:FSIG` | `:DISPlay:FSIGn {ON\|OFF}` | `{1\|0}` | "Fail" sign on limit fail (preset ON). |
| `:DISP:IMAG` | `:DISPlay:IMAGe {NORMal\|INVert}` | `{NORM\|INV}` | Normal/inverted display. |
| `:DISP:SKEY` | `:DISPlay:SKEY[:STATe] {ON\|OFF}` | `{1\|0}` | Softkey labels (preset ON). |
| `:DISP:TABL` / `:TABL:TYPE` | `:DISPlay:TABLe[:STATe] {ON\|OFF}` / `:TABLe:TYPE {MARKer\|LIMit\|SEGMent\|ECHO}` | `{1\|0}` / enum | Bottom table show / which table. |
| `:DISP:COL{1-2}:BACK` / `:GRAT{1-2}` / `:LIM{1-2}` / `:TRAC{1-4}:DATA` / `:TRAC{1-4}:MEM` | `…:COLor{1-2}:…  <r>,<g>,<b>` (each 0–5) | `{r},{g},{b}` | Display colours (COL1 normal / COL2 invert). |
| `:DISP:COL{1-2}:RES` | `:DISPlay:COLor{1-2}:RESet` (no query) | — | Reset colours to factory. |

**`:DISP:WIND{1-4}` Y-scale & annotation extras:**
`…:Y:PDIVision` (scale/div or Smith/polar full-scale; range 1E-18…1E8; format-dependent preset),
`…:Y:RLEVel` (reference value −5E8…5E8), `…:Y:RPOSition` (ref line # 0…divisions, preset 5),
`…:Y:DIVisions` (4–30, preset 10, res 2), `…:X:SPACing {LINear|OBASe}` (segment x-axis; preset OBASe),
`…:TRAC{1-4}:Y:TRACk:MODE {OFF|PEAK|FREQuency}` + `:Y:TRACk:FREQuency <Hz>` (reference tracking),
`…:TRAC{1-4}:ANN:MARK:POS:X|Y <%>` (marker readout position, −15…100), `…:ANN:YAX:MODE {AUTO|RELative}`.

### 8.12 `:FORM` — data format ; `:HCOP` — hardcopy

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:FORM:DATA` | `:FORMat:DATA {ASCii\|REAL\|REAL32}` | `{ASC\|REAL\|REAL32}` | Transfer format (preset ASCii). REAL=64-bit, REAL32=32-bit IEEE block. Applies to FDAT/FMEM/SDAT/SMEM/FUNC:DATA/LIM:DATA/LIM:REP/FREQ:DATA/SEGM:DATA. **Not** reset by `*RST`/`:SYST:PRES`. |
| `:FORM:BORD` | `:FORMat:BORDer {NORMal\|SWAPped}` | `{NORM\|SWAP}` | Binary byte order (preset NORM=big-endian; **SWAP** for x86 little-endian). Not reset by preset. |
| `:HCOP` | `:HCOPy[:IMMediate]` (no query) | — | Print LCD image to printer. |
| `:HCOP:ABOR` | `:HCOPy:ABORt` (no query) | — | Abort print. |
| `:HCOP:IMAG` | `:HCOPy:IMAGe {NORMal\|INVert}` | `{NORM\|INV}` | Print colour (preset INVert). |
| `:HCOP:SDUM:DATA?` | `:HCOPy:SDUMp:DATA?` | binary image | Screen-dump image bytes (used by screen-capture tooling). |

### 8.13 `:MMEM` — mass-memory / files

Paths: `.sta` state, `.csv` data/limit/segment, `.bmp`/`.png` image, `.vba`/`.bas`/`.frm`/`.cls` program.
Prefix `A:` for floppy; `/` or `\` separators. Overwrites silently. All set forms are no-query.

| Command | Syntax / params | Notes |
|---------|-----------------|-------|
| `:MMEM:CAT?` | `:MMEMory:CATalog? <dir>` | Returns `"{used},{free},{name1},,{size1},,…"` (size 0 = directory). **⚠ GOTCHA (live-confirmed 2026-06-04, G-15): a directory arg with a TRAILING BACKSLASH times out** — `:MMEM:CAT? "D:\"` → `VI_ERROR_TMO` (and leaves the session addressed-to-talk → stale −420). Query the drive with NO trailing separator: `:MMEM:CAT? "D:"`. Parse `.sta`/file names from the comma-list. |
| `:MMEM:MDIR` | `:MMEMory:MDIRectory <dir>` | Make directory. |
| `:MMEM:COPY` | `:MMEMory:COPY <src>,<dst>` | Copy file. |
| `:MMEM:DEL` | `:MMEMory:DELete <name>` | Delete file/dir (recursive for dir). |
| `:MMEM:TRAN` | `:MMEMory:TRANsfer <file>,<block>` / `? <file>` | Write/read raw file bytes host↔instrument (definite-length block). |
| `:MMEM:STOR` | `:MMEMory:STORe[:STATe] <file.sta>` | Save state (content per `:STOR:STYP`). `autorec.sta` auto-recalls at power-on. |
| `:MMEM:STOR:STYP` | `:MMEMory:STORe:STYPe {STATe\|CSTate\|DSTate\|CDSTate}` | What a state save includes: state / +cal / +data / +cal+data. **`CST` to include cal coefficients.** |
| `:MMEM:STOR:FDAT` | `:MMEMory:STORe:FDATa <file.csv>` | Save active trace formatted data → CSV (not recallable). |
| `:MMEM:STOR:SALL` | `:MMEMory:STORe:SALL {ON\|OFF}` | Save all vs displayed channels/traces. |
| `:MMEM:STOR:IMAG` | `:MMEMory:STORe:IMAGe <file.bmp\|.png>` | Save screen image. |
| `:MMEM:STOR:CHAN` / `:CHAN:CLE` / `:CHAN:COEF` | `…:CHANnel[:STATe] {A\|B\|C\|D}` / `:CLEar` / `:COEFficient {A\|B\|C\|D}` | Save active channel state / clear all registers / cal coeff to register (volatile). |
| `:MMEM:STOR:LIM` / `:RLIM` / `:SEGM` / `:PROG` | `…:LIMit\|RLIMit\|SEGMent\|PROGram <file>` | Save limit / ripple-limit / segment table / VBA project. |
| `:MMEM:LOAD` | `:MMEMory:LOAD[:STATe] <file.sta>` | Recall state. |
| `:MMEM:LOAD:CHAN` / `:CHAN:COEF` | `…:CHANnel[:STATe] {A\|B\|C\|D}` / `:COEFficient {A\|B\|C\|D}` | Recall channel state / cal coeff register into active channel. |
| `:MMEM:LOAD:LIM` / `:RLIM` / `:SEGM` / `:PROG` | `…:LIMit\|RLIMit\|SEGMent\|PROGram <file>` | Load limit / ripple / segment / program (program ext decides import type). |

`:MMEM:TRAN` block size limits: GPIB ≤20 MB, LAN ≤100 KB per transfer.

### 8.14 `:OUTP` / `:PROG`

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:OUTP` | `:OUTPut[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Stimulus RF output (preset ON). No measurement possible when OFF. |
| `:PROG:CAT?` | `:PROGram:CATalog?` | `"{macro1},…"` | List of public VBA macros (module.procedure). |
| `:PROG:NAME` | `:PROGram[:SELected]:NAME <string>` | `{string}` | Select VBA macro to control. |
| `:PROG:STAT` | `:PROGram[:SELected]:STATe {STOP\|RUN}` | `{STOP\|RUN}` | Run/stop the selected macro. |

### 8.15 `:SENS{1-4}` — frequency / sweep / IFBW / averaging

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:SENS{1-4}:FREQ:STAR` | `:SENSe{1-4}:FREQuency:STARt <numeric>` | `{numeric}` | Start freq (Hz). Range = instrument freq span (model-dependent). |
| `:SENS{1-4}:FREQ:STOP` | `…:FREQuency:STOP <numeric>` | `{numeric}` | Stop freq (Hz). |
| `:SENS{1-4}:FREQ:CENT` | `…:FREQuency:CENTer <numeric>` | `{numeric}` | Center freq (Hz). |
| `:SENS{1-4}:FREQ:SPAN` | `…:FREQuency:SPAN <numeric>` | `{numeric}` | Span (Hz). |
| `:SENS{1-4}:FREQ` | `…:FREQuency[:CW\|:FIXed] <numeric>` | `{numeric}` | CW (fixed) freq for power sweep. |
| `:SENS{1-4}:FREQ:DATA?` | `…:FREQuency:DATA?` | `{f1},…,{f_NOP}` | Stimulus (frequency) array (read-only). Format per `:FORM:DATA`. |
| `:SENS{1-4}:SWE:POIN` | `:SENSe{1-4}:SWEep:POINts <numeric>` | `{numeric}` | # points. (E5061/E5062 max 1601; **E5063A max 1601**.) |
| `:SENS{1-4}:SWE:TYPE` | `…:SWEep:TYPE {LINear\|LOGarithmic\|SEGMent\|POWer}` | `{LIN\|LOG\|SEGM\|POW}` | Sweep type (preset LIN). |
| `:SENS{1-4}:SWE:TIME` | `…:SWEep:TIME <numeric>` | `{numeric}` | Sweep time (s). |
| `:SENS{1-4}:SWE:TIME:AUTO` | `…:SWEep:TIME:AUTO {ON\|OFF\|1\|0}` | `{1\|0}` | Auto sweep-time. |
| `:SENS{1-4}:SWE:DEL` | `…:SWEep:DELay <numeric>` | `{numeric}` | Sweep delay (s). |
| `:SENS{1-4}:BAND` / `:BWID` | `:SENSe{1-4}:BANDwidth[:RESolution] <numeric>` (synonym `:BWIDth`) | `{numeric}` | **IF bandwidth.** ⚠️ E5061/E5062 range **10–30000 Hz, preset 30000**, steps of 1/3. **E5063A goes higher (≥300 kHz; bench-validated 300 kHz)** — verify exact max on hardware. On E5063A the cheat-sheet form is `:SENS:BAND:RES`. |
| `:SENS{1-4}:AVER` | `:SENSe{1-4}:AVERage[:STATe] {ON\|OFF\|1\|0}` | `{1\|0}` | Averaging on/off (preset OFF). |
| `:SENS{1-4}:AVER:COUN` | `…:AVERage:COUNt <numeric>` | `{numeric}` | Averaging factor 1–999, preset 16. |
| `:SENS{1-4}:AVER:CLE` | `…:AVERage:CLEar` (no query) | — | Restart averaging. |
| `:SENS{1-4}:SEGM:DATA` | `…:SEGMent:DATA <header,segments…>` / `?` | echoes | Whole segment-sweep table (format per `:FORM:DATA`). |
| `:SENS{1-4}:SEGM:SWE:POIN?` | `…:SEGMent:SWEep:POINts?` | `{numeric}` | Total points in segment table. |
| `:SENS{1-4}:SEGM:SWE:TIME?` | `…:SEGMent:SWEep:TIME?` | `{numeric}` | Total segment sweep time. |
| `:SENS{1-4}:ROSC:SOUR?` | `…:ROSCillator:SOURce?` | `{INT\|EXT}` | Reference-oscillator source. |
| `:SENS:CORR:IMP` | `:SENSe:CORRection:IMPedance[:INPut][:MAGNitude] <numeric>` | `{numeric}` | System Z0, 1E-3…1000 Ω, preset 50/75 (fw ≥3.01). |

### 8.16 `:SENS{1-4}:CORR` — calibration / error correction

**Measure & compute** (each `:COLL:*` measurement is overlapped → gate with `*OPC?`):

| Command | Syntax / params | Notes |
|---------|-----------------|-------|
| `:SENS{1-4}:CORR:COLL:METH:OPEN` / `:SHOR` / `:THRU` | `…:METHod:OPEN\|SHORt <port>` / `:THRU <p1>,<p2>` | Select response-cal method. |
| `:SENS{1-4}:CORR:COLL:METH:ERES` | `…:METHod:ERES <resp>,<stim>` | Enhanced-response method. |
| `:SENS{1-4}:CORR:COLL:METH:SOLT1` / `:SOLT2` | `…:METHod:SOLT1 <port>` / `:SOLT2 <p1>,<p2>` | Full 1-/2-port method. |
| `:SENS{1-4}:CORR:COLL:METH:TYPE?` | `…:METHod:TYPE?` | Query selected method. |
| `:SENS{1-4}:CORR:COLL:OPEN` / `:SHOR` / `:LOAD` | `…:COLLect[:ACQuire]:OPEN\|SHORt\|LOAD <port>` (no query) | Measure reflection standard. |
| `:SENS{1-4}:CORR:COLL:THRU` / `:ISOL` | `…:COLLect[:ACQuire]:THRU\|ISOLation <resp>,<stim>` (no query) | Measure thru / isolation. |
| `:SENS{1-4}:CORR:COLL:SAVE` | `…:COLLect:SAVE` (no query) | Compute coefficients + auto-enable correction; clears cal-type selection. |
| `:SENS{1-4}:CORR:COLL:ECAL:SOLT1` / `:SOLT2` | `…:ECAL:SOLT1 <port>` / `:SOLT2 <p1>,<p2>` (no query) | ECal full 1-/2-port (one-shot). |
| `:SENS{1-4}:CORR:COLL:ECAL:ERES` / `:THRU` | `…:ECAL:ERES\|THRU <resp>,<stim>` (no query) | ECal enhanced-response / thru. |
| `:SENS{1-4}:CORR:COLL:ECAL:ISOL` | `…:ECAL:ISOLation[:STATe] {ON\|OFF}` | ECal isolation measurement (preset OFF). |
| `:SENS:CORR:COLL:ECAL:PATH?` | `…:ECAL:PATH? <port>` | Which ECal module port (A/B/C/D=1/2/3/4, 0=none) is on instrument port. |

**State & coefficients:**

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:SENS{1-4}:CORR:STAT` | `…:CORRection:STATe {ON\|OFF\|1\|0}` | `{1\|0}` | Error correction on/off. |
| `:SENS{1-4}:CORR:CLE` | `…:CORRection:CLEar` (no query) | — | Clear all cal coefficients + standard data. |
| `:SENS{1-4}:CORR:COEF?` | `…:CORRection:COEFficient[:DATA]? {ES\|ER\|ED\|EL\|ET\|EX},<resp>,<stim>` | Re/Im pairs | Read error terms: ES=source-match, ER=refl-track, ED=directivity, EL=load-match, ET=trans-track, EX=isolation. (ES/ER/ED: same port; EL/ET/EX: different.) |
| `:SENS{1-4}:CORR:TYPE{1-4}?` | `…:CORRection:TYPE{1-4}?` | type | Applied cal type per trace. |
| `:SENS{1-4}:CORR:EXT` | `…:CORRection:EXTension[:STATe] {ON\|OFF}` | `{1\|0}` | Port extension on/off. |
| `:SENS{1-4}:CORR:EXT:PORT{1-2}` | `…:CORRection:EXTension:PORT{1-2} <numeric>` | `{numeric}` | Per-port extension delay. |
| `:SENS{1-4}:CORR:RVEL:COAX` | `…:CORRection:RVELocity:COAX <numeric>` | `{numeric}` | Velocity factor (coax). |
| `:SENS{1-4}:CORR:PROP` | `…:CORRection:PROPagation …` | — | Port-extension media/propagation context. |

**Cal-kit selection & definition** (`:SENS{1-4}:CORR:COLL:CKIT…`):

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:CKIT` | `…:CKIT[:SELect] <numeric>` | `{numeric}` | Select kit 1–10. Preset 5 (50 Ω) / 6 (75 Ω). Default labels: 1=85033E, 2=85033D, 3=85052D, 4=85032F, 5=85032B, 6=85036B/E, 7=85039B, 8=85038A/F/M, 9–10=User. |
| `:CKIT:LAB` | `…:CKIT:LABel <string>` | `{string}` | Kit name (≤254). |
| `:CKIT:RES` | `…:CKIT:RESet` (no query) | — | Reset kit to factory. |
| `:CKIT:ORD:OPEN` / `:SHOR` / `:LOAD` | `…:CKIT:ORDer:OPEN\|SHORt\|LOAD <port>,<std>` | `{std}` | Assign standard (1–21) to OPEN/SHORT/LOAD of a port. |
| `:CKIT:ORD:THRU` | `…:CKIT:ORDer:THRU <p1>,<p2>,<std>` | `{std}` | Assign standard for THRU between 2 ports. |
| `:CKIT:STAN{1-21}:TYPE` | `…:STANdard{1-21}:TYPE {OPEN\|SHORt\|LOAD\|THRU\|ARBI\|NONE}` | enum | Standard type. |
| `:CKIT:STAN{1-21}:LAB` | `…:STANdard{1-21}:LABel <string>` | `{string}` | Standard name. |
| `:CKIT:STAN{1-21}:C0`/`:C1`/`:C2`/`:C3` | `…:STANdard{1-21}:C0… <numeric>` | `{numeric}` | OPEN fringe-C poly. Units: C0=fF, C1=1E-27 F/Hz, C2=1E-36 F/Hz², C3=1E-45 F/Hz³. |
| `:CKIT:STAN{1-21}:L0`/`:L1`/`:L2`/`:L3` | `…:STANdard{1-21}:L0… <numeric>` | `{numeric}` | SHORT residual-L poly. Units: L0=pH, L1=1E-24 H/Hz, L2=1E-33 H/Hz², L3=1E-42 H/Hz³. |
| `:CKIT:STAN{1-21}:DEL` | `…:STANdard{1-21}:DELay <numeric>` | `{numeric}` | Offset delay (s). |
| `:CKIT:STAN{1-21}:LOSS` | `…:STANdard{1-21}:LOSS <numeric>` | `{numeric}` | Offset loss (Ω/s). |
| `:CKIT:STAN{1-21}:Z0` | `…:STANdard{1-21}:Z0 <numeric>` | `{numeric}` | Offset Z0 (Ω). |
| `:CKIT:STAN{1-21}:ARB` | `…:STANdard{1-21}:ARBitrary <numeric>` | `{numeric}` | Arbitrary impedance (Ω). |

**Cal-type query responses** (`:METH:TYPE?` and `:CORR:TYPE{1-4}?`): `{ERES|NONE|RESPO|RESPS|RESPT|SOLT1|SOLT2}`
(enhanced-response / none / response-open / response-short / response-thru / full-1-port / full-2-port).
`:CORR:TYPE{1-4}?` additionally returns the two cal port numbers.
Other: `:SENS{1-4}:CORR:PROP {ON|OFF}` (cal-property display), `:CORR:RVEL:COAX` 0.01–10 preset 1,
`:CORR:EXT:PORT{1-2}` −10…10 s.
**E5062A frequency limits** (FREQ:STAR/STOP/CENT/SPAN/FREQ-CW): **3E5–3E9 Hz** (300 kHz–3 GHz),
span 0–2.9997E9. **E5063A spans higher** (model option to 4.5/8.5/14/18 GHz) — verify on hardware.
`:SWE:POIN` 2–1601, preset 201. `:SWE:DEL` 0–1 s. `:SEGM:DATA` header `5,<mode>,<ifbw>,<pow>,<del>,<time>,<segm>,…` (segm 1–201).

### 8.17 `:SERV` — service / topology queries (all query-only)

| Command | Query response | Notes |
|---------|----------------|-------|
| `:SERV:CHAN:ACT?` | `{numeric}` | Active channel #. |
| `:SERV:CHAN:COUN?` | `{numeric}` | Max # channels. |
| `:SERV:CHAN{1-4}:TRAC:ACT?` | `{numeric}` | Active trace # of channel. |
| `:SERV:CHAN:TRAC:COUN?` | `{numeric}` | Max # traces/channel. |
| `:SERV:PORT:COUN?` | `{numeric}` | # test ports. |

### 8.18 `:SOUR{1-4}:POW` — stimulus source / power

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:SOUR{1-4}:POW` | `:SOURce{1-4}:POWer[:LEVel][:IMMediate][:AMPLitude] <numeric>` | `{numeric}` | Power level (dBm), preset 0, res 0.05, range per power-range. |
| `:SOUR{1-4}:POW:ATT` | `…:POWer:ATTenuation <numeric>` | `{numeric}` | Power-range attenuator 0–40 dB step 10 (needs power-range option). 0dB→−5…+10, 10→−15…0, 20→−25…−10, 30→−35…−20, 40→−45…−30 dBm. |
| `:SOUR{1-4}:POW:PORT:COUP` | `…:POWer:PORT:COUPle {ON\|OFF}` | `{1\|0}` | Same power all ports (preset ON). |
| `:SOUR{1-4}:POW:PORT{1-2}` | `…:POWer:PORT{1-2}[:LEVel]… <numeric>` | `{numeric}` | Per-port power (dBm), res 0.05. |
| `:SOUR{1-4}:POW:SLOP` | `…:POWer[:LEVel]:SLOPe <numeric>` | `{numeric}` | Power slope −2…2 dB/GHz, preset 0. |
| `:SOUR{1-4}:POW:SLOP:STAT` | `…:POWer[:LEVel]:SLOPe:STATe {ON\|OFF}` | `{1\|0}` | Power-slope on/off. |
| `:SOUR{1-4}:POW:CENT` | `…:POWer:CENTer <numeric>` | `{numeric}` | Power-sweep center, preset −2.5 dBm. |
| `:SOUR{1-4}:POW:SPAN` | `…:POWer:SPAN <numeric>` | `{numeric}` | Power-sweep span, preset 5 dBm. |
| `:SOUR{1-4}:POW:STAR` | `…:POWer:STARt <numeric>` | `{numeric}` | Power-sweep start, preset −5 dBm. |
| `:SOUR{1-4}:POW:STOP` | `…:POWer:STOP <numeric>` | `{numeric}` | Power-sweep stop, preset 0 dBm. |

### 8.19 `:STAT` — status reporting

All enable/transition registers take a `<numeric>` 0–65535 (res 1); query returns `{numeric}`.
The **Operation Status** register carries the *measuring* bit (bit 4) used for sweep-completion
detection. The **Questionable** tree carries limit/ripple/bandwidth test results.

| Command | Syntax | Notes |
|---------|--------|-------|
| `:STAT:PRES` | `:STATus:PRESet` (no query) | Init all STAT enable/transition registers. |
| `:STAT:OPER?` | `:STATus:OPERation[:EVENt]?` | Operation status **event** (read+clear). |
| `:STAT:OPER:COND?` | `…:OPERation:CONDition?` | Operation **condition** (live). Bit 4 = measuring. |
| `:STAT:OPER:ENAB` | `…:OPERation:ENABle <numeric>` | Enable (preset 0; bits 0–3,6–13,15 fixed 0). |
| `:STAT:OPER:NTR` / `:PTR` | `…:OPERation:NTRansition\|PTRansition <numeric>` | Neg/pos transition filters (NTR preset 0, PTR preset 16432). **For end-of-sweep SRQ: `:OPER:NTR 16` + `:OPER:ENAB 16` + `*SRE 128`** then watch bit-4 1→0. |
| `:STAT:QUES?` / `:QUES:COND?` | `:STATus:QUEStionable[:EVENt]?` / `:CONDition?` | Questionable event/condition. Bit 10 = overall limit-test fail. |
| `:STAT:QUES:ENAB` / `:NTR` / `:PTR` | `…:QUEStionable:ENABle\|NTRansition\|PTRansition <numeric>` | Enable (preset 0) / transitions (PTR preset 3072; bits 0–9,12–15 fixed 0). |
| `:STAT:QUES:LIM?` / `:COND?` / `:ENAB` / `:NTR` / `:PTR` | `…:QUEStionable:LIMit…` | Limit-test sub-register (per-channel fail in bits 1–4). ENAB/PTR preset 30. |
| `:STAT:QUES:LIM:CHAN{1-4}?` / `:COND?` / `:ENAB` / `:NTR` / `:PTR` | `…:LIMit:CHANnel{1-4}…` | Per-channel limit register (per-trace fail in bits 1–4). |
| `:STAT:QUES:RLIM…` (`?`,`:COND?`,`:ENAB`,`:NTR`,`:PTR`, + `:CHAN{1-4}…`) | `…:QUEStionable:RLIMit…` | Ripple-limit sub-register tree (same shape as LIM). |
| `:STAT:QUES:BLIM…` (`?`,`:COND?`,`:ENAB`,`:NTR`,`:PTR`, + `:CHAN{1-4}…`) | `…:QUEStionable:BLIMit…` | Bandwidth-limit sub-register tree. |

### 8.20 `:SYST` — system

| Command | Syntax / params | Query | Notes |
|---------|-----------------|-------|-------|
| `:SYST:PRES` | `:SYSTem:PRESet` (no query) | — | Preset (ch1 continuous-init **ON** — differs from `*RST`). |
| `:SYST:ERR?` | `:SYSTem:ERRor?` | `{code},"{msg}"` | Oldest error (FIFO, queue size 100); `0,"No error"` when empty. Cleared by `*CLS`. Does not capture VBA/manual errors. |
| `:SYST:DATE` | `:SYSTem:DATE <y>,<m>,<d>` | `{y},{m},{d}` | Date (1980–2099, 1–12, 1–31). |
| `:SYST:TIME` | `:SYSTem:TIME <h>,<m>,<s>` | `{h},{m},{s}` | Time of day. |
| `:SYST:BACK` | `:SYSTem:BACKlight {ON\|OFF}` | `{1\|0}` | LCD backlight (preset ON; any key turns back on). |
| `:SYST:BEEP:COMP:IMM` / `:STAT` | `:SYSTem:BEEPer:COMPlete:IMMediate` / `:STATe {ON\|OFF}` | `{1\|0}` | Completion beep now / enable (preset ON). |
| `:SYST:BEEP:WARN:IMM` / `:STAT` | `:SYSTem:BEEPer:WARNing:IMMediate` / `:STATe {ON\|OFF}` | `{1\|0}` | Warning beep now / enable (preset ON). |
| `:SYST:KLOC:KBD` | `:SYSTem:KLOCk:KBD {ON\|OFF}` | `{1\|0}` | Lock front panel + keyboard (preset OFF). |
| `:SYST:KLOC:MOUS` | `:SYSTem:KLOCk:MOUSe {ON\|OFF}` | `{1\|0}` | Lock mouse + touchscreen. |
| `:SYST:POFF` | `:SYSTem:POFF` (no query) | — | Power off the instrument. |
| `:SYST:SEC:LEV` | `:SYSTem:SECurity[:LEVel] {NON\|LOW\|HIGH}` | `{NON\|LOW\|HIGH}` | Security level (HIGH blanks frequency display; can't downgrade from HIGH except via preset/recall). |
| `:SYST:SERV?` | `:SYSTem:SERVice?` | — | Service query. |
| `:SYST:TIME` | `:SYSTem:TIME <h>,<m>,<s>` | `{h},{m},{s}` | Clock time (0–23, 0–59, 0–59). |
| `:SYST:UPR` | `:SYSTem:UPReset` (no query) | — | User preset (loads `D:\UserPreset.sta`; falls back to `:SYST:PRES` if absent). |

### 8.21 `:TRIG` — trigger (detail; see also §8.2)

| Command | Syntax / params | Notes |
|---------|-----------------|-------|
| `:TRIG` | `:TRIGger[:SEQuence][:IMMediate]` (no query) | Immediate trigger; **command completes at trigger** (cannot `*OPC?`-wait for sweep end). Error if not in trigger-wait state. |
| `:TRIG:SING` | `:TRIGger[:SEQuence]:SINGle` (no query) | Immediate trigger; **command completes at end of all sweeps** → use `*OPC?` to wait. Error if not in trigger-wait state. |
| `:TRIG:SOUR` | `:TRIGger[:SEQuence]:SOURce {INTernal\|EXTernal\|MANual\|BUS}` | `{BUS\|EXT\|INT\|MAN}` | Source (preset INT). Changing source during a sweep cancels it. |

### 8.22 Status-register bit map (Appendix B) — for sweep-done & test-result detection

- **Operation Status Condition register:** **bit 4 = "Measuring"** (1 during sweep). End-of-sweep =
  bit-4 1→0 transition. Recipe: `:STAT:OPER:NTR 16` → `:STAT:OPER:ENAB 16` → `*SRE 128` →
  watch SRQ (or poll `:STAT:OPER:COND?` and test bit 4). `:OPER:PTR` preset 16432.
- **Questionable Status register:** **bit 10 = overall limit-test fail** (combined all channels);
  also summarizes the LIMit/RLIMit/BLIMit sub-trees. `:QUES:PTR` preset 3072.
- **Questionable Limit Status register:** bits 1–4 = channel 1–4 limit-test fail (summary of the
  per-channel registers). Preset ENAB/PTR = 30 (= bits 1–4... actually 0b11110).
- **Questionable Limit Channel{1-4} register:** bits 1–4 = trace 1–4 fail (0 at sweep start, 1 on fail).
- **Questionable Ripple/Bandwidth Limit** registers mirror the Limit tree (channel summary bits 1–4,
  per-channel trace bits 1–4).
- **Standard Event Status (`*ESR?`):** standard IEEE bits — bit 0 OPC, bit 2 query error,
  bit 3 device-dependent error, bit 4 execution error, bit 5 command error. `*ESE 60` enables
  bits 2–5 (the error bits) for SRQ-on-error.
- **Status Byte (`*STB?`/`*SRE`):** bit 7 = operation-status summary (use `*SRE 128`),
  bit 5 = standard-event summary (`*SRE 32`), bit 3 = questionable summary.

### 8.23 Error messages (Appendix C) — ones you'll actually hit

`:SYST:ERR?` returns `<code>,"<msg>"`. Positive codes are instrument-specific; negative are
IEEE-488.2 standard. Most relevant for automation:

| Code | Message | Meaning / cause |
|------|---------|-----------------|
| **−410** | **Query INTERRUPTED** | A new command/GET arrived before the prior query response was fully read. **This is the bench Variant-A failure** (cold ASCII read after a format switch) — fix by `*OPC?`+settle before the first read, and always read a query's full response before sending the next command. |
| −420 | Query UNTERMINATED | Talker addressed but no/incomplete response pending (queried something that returns nothing, or sent a set where a query was expected). |
| −430 | Query DEADLOCKED | Both I/O buffers full. |
| −400 / −100 / −200 | Query / Command / Execution error | Generic IEEE-488.2 error classes. |
| −222 | Data out of range | Numeric/port/cal-kit param outside allowed range (port/kit params are *not* clamped — they error). |
| −224 | Illegal parameter value | e.g. `CALC:PAR:DEF` S-param that doesn't exist on the model. |
| −213 | Init ignored | `:INIT` while another measurement is running. |
| −211 | Trigger ignored | `*TRG`/`:TRIG`/ext-trigger received when not in trigger-wait state. |
| −109 | Missing parameter | Too few parameters (e.g. `:SENS1:SWE:POIN` with no value). |
| −108 | Parameter not allowed | Too many parameters. |
| −113 | Undefined header | Unknown command, or a port index that doesn't exist on the model. |
| **20** | Additional standard needed | `:CORR:COLL:SAVE` before all required standards measured. |
| **22** | Calibration method not selected | `:CORR:COLL:SAVE` before `:CORR:COLL:METH:*`. |
| 21 | Specified ports overlapped | Same port given twice to a 2-port command (SOLT2/THRU/etc.). |
| 31 / 32 | ECal config failed / module not in RF path | ECal module USB/connection problem. |
| 40 / 41 | Target / Peak not found | Marker search/analysis found nothing (also bandwidth/notch not found). |
| 53 | Log sweep requires 2-octave min span | Log sweep needs stop ≥ ~4× start (auto-reverts to linear). |
| 61 | Power unleveled | Output level (after slope correction) exceeds available range. |
| 100–107 | Failed to read/write/copy/delete/create/transfer file | `:MMEM:*` failures. |
| 105 / 106 | Recall / Save failed | `:MMEM:LOAD`/`:STOR` state-file failure. |
| 200 | Option not installed | e.g. `:SOUR:POW:ATT` without power-range option. |
| 220 | Phase lock loop unlocked | PLL lost lock (bad/absent ext ref, or hardware fault). |
| 221 / 222 | Port 1 / Port 2 receiver overload | Input exceeds max level → stimulus auto-OFF. |

### 8.24 Time-domain & advanced commands (present in the command tree)

The Chapter-13 command tree also lists a **time-domain / transform** subtree under `:CALC{1-4}:TRANsform:TIME`
(`:STATe`, `[:TYPE] {BPASs|LPASs}`, `:STIMulus {IMPulse|STEP}`, `:STARt`, `:STOP`, `:CENTer`, `:SPAN`,
`:IMPulse:WIDTh`, `:STEP:RTIMe`, `:KBESsel`, `:LPFRequency`) plus gating — these are option/fixture-simulator
features not detailed in the main alphabetic reference and **may differ on the E5063A**; verify on hardware
or in the live command-finder before use. (The body reference above covers the standard measurement command set.)

---

## 9. E5063A cross-verification notes

Confirmed identical on the E5063A (per the cheat-sheet & working `scpi_commands.py`):

- IEEE common: `*IDN?`, `*CLS`, `*OPC?`, `:SYST:ERR?`.
- Freq/sweep: `:SENS1:FREQ:STAR/STOP/CENT/SPAN`, `:SENS1:SWE:POIN`,
  `:SENS1:BAND:RES` (E5063A cheat-sheet uses `:BAND:RES`; the E5061/E5062 guide
  uses `:SENS1:BAND` / `:BWID` — **both forms set IF bandwidth**; on the E5063A
  prefer `:SENS:BAND:RES`).
- Trigger: `:TRIG:SOUR BUS`, `:INIT1:IMM`, `:TRIG:SING`.
- Trace/data: `:CALC1:PAR{1-4}:DEF`, `:PAR{1-4}:SEL`, `:CALC1:FORM`,
  `:CALC1:DATA:FDAT?`, `:CALC1:DATA:SDAT?`, `:SENS1:FREQ:DATA?`.
- Format: `:FORM:DATA ASC|REAL|REAL32`, `:FORM:BORD`.
- Calibration: `:SENS1:CORR:COLL:METH:SOLT1/SOLT2`, `:COLL:OPEN/SHOR/LOAD/THRU`,
  `:COLL:SAVE`, `:COLL:ECAL:*`, `:CORR:STAT`.
- File: `:MMEM:STOR`, `:MMEM:STOR:FDAT`, `:MMEM:TRAN`, `:MMEM:LOAD`.
- Markers: `:CALC1:MARK{1-10}`, `:X`, `:Y?`, `:FUNC:*`, `:BWID:*`.

**Differences / watch-outs:**

1. **IF bandwidth mnemonic:** E5063A docs → `:SENS1:BAND:RES`. E5062A guide →
   `:SENS1:BAND` / `:SENS1:BWID`. Treat as equivalent; verify on hardware.
2. **Telnet port:** 23 (E5062A) vs 5024 (E5063A); program socket **5025** both.
3. **`:SENS:CORR:IMP`** (system Z0) requires fw ≥ 3.01 on E5062A; available on E5063A.
4. **Handler I/O (`:CONT:HAND:*`)**, power-range `:SOUR:POW:ATT`, and some
   `:DISP:COL*` items are option/model-dependent — confirm on the E5063A.
5. Numeric ranges (max frequency, power, points) differ by E5063A model/option —
   never hard-code; read them back from the instrument (or cross-check the
   E5062A Programmer's Guide §8). Do **not** consult `9018-07931…pdf` — it is a
   4155B manual (see §0).

---

## 10. Document status

This reference covers the **complete E5061A/E5062A SCPI command set** (every command in the
Programmer's Guide Chapter-13 tree, §§6 and 8), transcribed from all 28 PDF chunks in
`references/reports/20260602/`, cross-checked against the E5063A cheat-sheet and the working
`ena_qt6_suite` constants. Treat E5062A-specific numeric ranges (frequency 300 kHz–3 GHz,
IFBW 10–30 kHz, etc.) as **lower bounds vs the E5063A** — the E5063A extends frequency and IFBW
(bench-validated to 300 kHz IFBW); always confirm exact limits against the live instrument
(`:SYST:ERR?` + readback). See §0 for the ⛔ note on the mislabeled `9018-07931` PDF.

---

*Document generated for the LibreVNA→E5063A migration (`code/ena-dev/`).*
