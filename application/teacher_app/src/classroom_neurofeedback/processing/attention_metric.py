from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, List

import numpy as np


class AttentionMetric:
    """Python port of the attention logic from EEGRecorder.cs."""

    def __init__(
        self,
        fs: int = 250,
        window_size: int = 256,
        attention_scale: float = 2.0,
        attention_offset: float = 0.0,
        attention_clamp_max: float = 100.0,
    ) -> None:
        self.fs = fs
        self.window_size = window_size
        self.attention_scale = attention_scale
        self.attention_offset = attention_offset
        self.attention_clamp_max = attention_clamp_max

        self._fz_buffer: Deque[float] = deque()
        self._previous_attention = 50.0

    def add_sample(self, sample: float) -> List[float]:
        self._fz_buffer.append(float(sample))
        return self._process_available_windows()

    def add_samples(self, samples: Iterable[float]) -> List[float]:
        for sample in samples:
            self._fz_buffer.append(float(sample))
        return self._process_available_windows()

    def _process_available_windows(self) -> List[float]:
        results: List[float] = []
        while len(self._fz_buffer) >= self.window_size:
            window = np.array(
                [self._fz_buffer.popleft() for _ in range(self.window_size)],
                dtype=np.float64,
            )
            results.append(self._compute_attention(window))
        return results

    def _compute_attention(self, window: np.ndarray) -> float:
        # Remove DC offset exactly like EEGRecorder.cs.
        window = window - np.mean(window)

        fft = np.fft.fft(window)

        theta_power = self._band_power(fft, 4.0, 7.0)
        alpha_power = self._band_power(fft, 8.0, 12.0)
        beta_power = self._band_power(fft, 13.0, 30.0)

        ratio = beta_power / (alpha_power + theta_power + 1e-6)
        attention_raw = (np.clip(ratio / 0.5, 0.0, 1.0) ** 1.5) * 100.0

        attention = 0.5 * self._previous_attention + 0.5 * attention_raw
        self._previous_attention = float(attention)

        calibrated = attention * self.attention_scale + self.attention_offset
        calibrated = float(np.clip(calibrated, 0.0, min(self.attention_clamp_max, 100.0)))
        return calibrated

    def _band_power(self, fft: np.ndarray, f_low: float, f_high: float) -> float:
        n = fft.shape[0]
        df = self.fs / float(n)

        i_low = int(np.floor(f_low / df))
        i_high = int(np.ceil(f_high / df))

        i_low = max(0, i_low)
        i_high = min(i_high, (n // 2) - 1)

        if i_high < i_low:
            return 0.0

        band = fft[i_low : i_high + 1]
        power = np.abs(band) ** 2
        return float(np.sum(power) / (i_high - i_low + 1))
