# Understanding Basic Spectrum Analyzer Operation

**Source:** [Understanding Basic Spectrum Analyzer Operation — Rohde & Schwarz](https://www.youtube.com/watch?v=P5gxNGckjLc)

---

## What is a Spectrum Analyzer

A spectrum analyzer is a **frequency-domain instrument** — it displays **power versus frequency**. This is its most fundamental measurement. It can also automate more complex measurements such as AM modulation depth, third-order intercept, occupied bandwidth, and adjacent channel leakage ratio (ACLR).

---

## The Four Essential Parameters

Every spectrum analyzer measurement relies on four core settings:

1. **Center and Span** — defines the frequency range
2. **Reference Level** — defines the maximum expected power
3. **Resolution Bandwidth (RBW)** — controls signal separation and noise floor
4. **Video Bandwidth (VBW)** — controls trace smoothing

---

## 1. Center and Span

These two parameters define **what frequency range** is displayed.

| Parameter | What it means |
|---|---|
| **Center** | The middle frequency of the display |
| **Span** | The total width of the frequency range shown |

**Example:** Measuring between 840 MHz and 860 MHz is the same as setting Center = 850 MHz and Span = 20 MHz. Adjusting span is the easiest way to zoom in or out around a signal of interest.

---

## 2. Reference Level

Reference level is the **top edge of the display**, representing the maximum expected input power.

- Set it so the strongest signal sits **slightly below** this level
- **Too high:** reduces dynamic range, making small amplitude changes harder to see
- **Too low:** the trace clips above the screen, and more critically, internal components (mixers, amplifiers) can go into **compression**, causing distortion and measurement errors

The spectrum analyzer uses the reference level to automatically adjust the **input attenuator** and **IF amplifier gain** to protect internal components from overload.

---

## 3. Resolution Bandwidth (RBW)

RBW is the **most important setting** for basic spectrum measurements. It controls two things: **signal separation** and **noise floor**.

### How RBW Works

The spectrum analyzer uses the heterodyne principle and sweeps across the span. RBW acts as a **moving filter window** that measures power as it slides across the frequency range. In reality, the filter has a Gaussian shape (not perfectly square), and the spectrum is shifted past the fixed filter rather than the filter moving.

### Signal Separation

RBW determines whether two closely spaced signals can be **resolved** (seen as separate peaks). The RBW must be **narrower than the spacing** between the two signals — otherwise they merge into a single peak.

### Noise Floor (DANL)

RBW directly affects the **displayed average noise level (DANL)**. Narrower RBW lowers the noise floor:

| Resolution Bandwidth | Noise Floor |
|---|---|
| 3 MHz | −73 dBm |
| 300 kHz | −84 dBm |
| 30 kHz | −93 dBm |
| 3 kHz | −104 dBm |

**Rule of thumb:** decreasing RBW by a factor of 10 lowers the noise floor by approximately **10 dB**.

### The Trade-off: RBW vs Sweep Time

Narrower filters take longer to settle, so **sweep time increases** as RBW decreases. Sweeping too fast causes both amplitude and frequency errors. Most spectrum analyzers **auto-calculate sweep time** based on the current RBW and span — do not reduce it below the calculated value.

### Choosing RBW

- Narrower RBW → better signal separation + lower noise floor, but longer sweep time
- Wider RBW → faster sweeps, but poor separation and higher noise floor
- The optimal RBW depends on the signal being measured and often requires experimentation
- RBW is typically selectable in discrete steps: 1 kHz, 3 kHz, 10 kHz, 30 kHz, 100 kHz, etc.

---

## 4. Video Bandwidth (VBW)

VBW is a **post-detection filter** that smooths or averages the displayed trace.

### Key Distinction from RBW

| | RBW | VBW |
|---|---|---|
| Affects measurement? | Yes | No — display only |
| Affects noise floor? | Yes | No |
| Affects signal separation? | Yes | No |
| Affects sweep time? | Yes | Yes |

VBW only changes **how the trace looks**, not the underlying measurement. Lowering VBW reduces the visual noise (grassy appearance) on the trace but does **not** lower the noise floor or improve signal resolution.

### Choosing VBW

- Narrower VBW → smoother trace, but longer sweep time
- Most modern analyzers auto-configure VBW based on RBW
- The "correct" VBW depends on the application

---

## Summary: Quick Setup Reference

```
1. Set Center and Span   → define the frequency range of interest
2. Set Reference Level   → slightly above the strongest expected signal
3. Set RBW               → narrow enough to separate signals; check sweep time
4. Set VBW               → adjust for trace clarity if needed
```

Most analyzers will auto-calculate sweep time and VBW — trust the defaults unless the application specifically requires otherwise.
