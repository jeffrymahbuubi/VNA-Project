---
name: scipy-signal
description: Time-series signal processing with scipy.signal. Use for peak detection, digital filtering (Butterworth, FIR/IIR), power spectral density (Welch method), and cross-correlation on numpy arrays. Ideal for VNA sweep data analysis, RF signal characterisation, and any task involving noisy or periodic time-series signals.
license: https://github.com/scipy/scipy/blob/main/LICENSE.txt
metadata:
    skill-author: K-Dense Inc.
context: fork
agent: vna-data-analyst, rf-data-analyst
---

# scipy-signal-time-series-processing

Teaches peak detection, filtering, and statistical analysis of time-series signals using scipy.signal

## Instructions

# Time-Series Signal Processing with scipy.signal

## Overview
This skill covers essential signal processing operations: peak detection, filtering, and statistical analysis using scipy.signal.

## Step-by-Step Instructions

### 1. Import Required Libraries
```python
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
```

### 2. Peak Detection
Use `signal.find_peaks()` to identify local maxima:
- Set `height` parameter for minimum peak height
- Use `distance` to enforce minimum separation between peaks
- Add `prominence` to filter out small peaks

```python
# Example: Find peaks in noisy signal
t = np.linspace(0, 10, 1000)
y = np.sin(t) + 0.1 * np.random.randn(1000)
peaks, properties = signal.find_peaks(y, height=0.5, distance=20, prominence=0.3)
```

### 3. Signal Filtering
Apply filters to remove noise:
- Use `signal.butter()` and `signal.filtfilt()` for Butterworth filters
- Choose filter type: 'low', 'high', 'band', 'bandstop'
- Always use `filtfilt()` for zero-phase filtering

```python
# Low-pass filter example
b, a = signal.butter(4, 0.1, btype='low')
filtered = signal.filtfilt(b, a, y)
```

### 4. Statistical Analysis
Compute signal statistics:
- Use `np.std()` and `np.mean()` for basic statistics
- Apply `signal.correlate()` for cross-correlation
- Use `signal.welch()` for power spectral density

```python
# Power spectral density
f, psd = signal.welch(y, fs=100, nperseg=256)
```

## Best Practices
- Always visualize results with matplotlib
- Validate filter parameters before applying
- Use appropriate sampling frequency for Welch method