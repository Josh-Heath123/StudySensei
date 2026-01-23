"""
Advanced Time-Series Analysis Module

Features:
- Efficient sliding windows with numpy circular buffers
- Focus decay pattern detection
- Session-level statistics (mean, std, trends, volatility)
- Rolling aggregates for real-time performance
"""

from __future__ import annotations

import logging
import numpy as np
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Window configurations
WINDOW_1MIN = 60
WINDOW_5MIN = 300
WINDOW_10MIN = 600
WINDOW_30MIN = 1800


@dataclass
class WindowMetrics:
    """Aggregate metrics over a time window."""

    mean: float
    std: float
    min: float
    max: float
    trend: float  # Slope of linear regression
    volatility: float  # Coefficient of variation
    sample_count: int
    window_duration_sec: float


class CircularBuffer:
    """
    Efficient circular buffer using numpy arrays.
    O(1) append, O(1) access, memory-efficient.
    """

    def __init__(self, max_size: int, dtype=np.float32):
        self.max_size = max_size
        self.buffer = np.zeros(max_size, dtype=dtype)
        self.timestamps = np.zeros(max_size, dtype=np.float64)
        self.size = 0
        self.head = 0

    def append(self, timestamp: float, value: float) -> None:
        """Append a value, overwriting oldest if full."""
        idx = (self.head + self.size) % self.max_size
        self.buffer[idx] = value
        self.timestamps[idx] = timestamp
        if self.size < self.max_size:
            self.size += 1
        else:
            self.head = (self.head + 1) % self.max_size

    def get_window(self, cutoff_time: float) -> Tuple[np.ndarray, np.ndarray]:
        """Get values and timestamps within window (after cutoff_time)."""
        if self.size == 0:
            return np.array([]), np.array([])
        valid_mask = self.timestamps >= cutoff_time
        return self.buffer[valid_mask], self.timestamps[valid_mask]

    def get_all(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get all current values and timestamps."""
        if self.size == 0:
            return np.array([]), np.array([])
        if self.size < self.max_size:
            return self.buffer[:self.size], self.timestamps[:self.size]
        # Circular buffer is full, need to reorder
        indices = np.arange(self.head, self.head + self.size) % self.max_size
        return self.buffer[indices], self.timestamps[indices]


class TimeSeriesAnalyzer:
    """
    Advanced time-series analyzer with multiple sliding windows.
    Uses numpy circular buffers for efficient memory usage.
    """

    def __init__(
        self,
        window_1min: int = WINDOW_1MIN,
        window_5min: int = WINDOW_5MIN,
        window_10min: int = WINDOW_10MIN,
    ):
        # Estimate max samples: assume 2 samples/sec, add 20% buffer
        max_samples_1min = int(window_1min * 2.4)
        max_samples_5min = int(window_5min * 2.4)
        max_samples_10min = int(window_10min * 2.4)

        self.buffer_1min = CircularBuffer(max_samples_1min)
        self.buffer_5min = CircularBuffer(max_samples_5min)
        self.buffer_10min = CircularBuffer(max_samples_10min)

        self.window_1min = window_1min
        self.window_5min = window_5min
        self.window_10min = window_10min

    def add_data_point(self, timestamp: float, focus_score: float, posture_score: float) -> None:
        """Add a data point to all windows."""
        self.buffer_1min.append(timestamp, focus_score)
        self.buffer_5min.append(timestamp, focus_score)
        self.buffer_10min.append(timestamp, focus_score)

    def get_window_metrics(self, timestamp: float, window_sec: int) -> WindowMetrics:
        """Calculate metrics for a specific window."""
        cutoff = timestamp - window_sec
        if window_sec <= self.window_1min:
            values, times = self.buffer_1min.get_window(cutoff)
        elif window_sec <= self.window_5min:
            values, times = self.buffer_5min.get_window(cutoff)
        else:
            values, times = self.buffer_10min.get_window(cutoff)

        return self._compute_metrics(values, times, window_sec)

    def get_all_window_metrics(self, timestamp: float) -> dict:
        """Get metrics for all windows as a dict."""
        m1 = self.get_window_metrics(timestamp, self.window_1min)
        m5 = self.get_window_metrics(timestamp, self.window_5min)
        m10 = self.get_window_metrics(timestamp, self.window_10min)

        return {
            "1min": {
                "mean": m1.mean,
                "std": m1.std,
                "trend": m1.trend,
                "volatility": m1.volatility,
                "samples": m1.sample_count,
            },
            "5min": {
                "mean": m5.mean,
                "std": m5.std,
                "trend": m5.trend,
                "volatility": m5.volatility,
                "samples": m5.sample_count,
            },
            "10min": {
                "mean": m10.mean,
                "std": m10.std,
                "trend": m10.trend,
                "volatility": m10.volatility,
                "samples": m10.sample_count,
            },
        }

    @staticmethod
    def _compute_metrics(values: np.ndarray, times: np.ndarray, window_sec: int) -> WindowMetrics:
        """Compute statistical metrics from values and times."""
        if len(values) == 0:
            return WindowMetrics(
                mean=0.0,
                std=0.0,
                min=0.0,
                max=0.0,
                trend=0.0,
                volatility=0.0,
                sample_count=0,
                window_duration_sec=window_sec,
            )

        # Remove NaN/Inf for basic statistics
        valid_mask = ~np.isnan(values) & ~np.isinf(values)
        if np.sum(valid_mask) == 0:
            return WindowMetrics(
                mean=0.0,
                std=0.0,
                min=0.0,
                max=0.0,
                trend=0.0,
                volatility=0.0,
                sample_count=0,
                window_duration_sec=window_sec,
            )
        values_clean = values[valid_mask]
        
        mean = float(np.mean(values_clean))
        std = float(np.std(values_clean))
        min_val = float(np.min(values_clean))
        max_val = float(np.max(values_clean))

        # Linear trend (slope) with robust error handling
        trend = 0.0
        if len(times) >= 2 and len(values) >= 2:
            # Remove NaN/Inf values for both values and times
            trend_valid_mask = ~np.isnan(values) & ~np.isinf(values) & ~np.isnan(times) & ~np.isinf(times)
            if np.sum(trend_valid_mask) >= 2:
                values_trend = values[trend_valid_mask]
                times_trend = times[trend_valid_mask]
                
                # Normalize times to avoid numerical issues
                times_normalized = times_trend - times_trend[0]
                
                # Check for sufficient variation
                if np.std(times_normalized) >= 1e-10:
                    try:
                        trend = float(np.polyfit(times_normalized, values_trend, 1)[0])
                    except (np.linalg.LinAlgError, ValueError):
                        trend = 0.0

        # Volatility (coefficient of variation)
        volatility = std / mean if mean > 0 else 0.0

        duration = float(times[-1] - times[0]) if len(times) > 1 else 0.0

        return WindowMetrics(
            mean=mean,
            std=std,
            min=min_val,
            max=max_val,
            trend=trend,
            volatility=volatility,
            sample_count=len(values),
            window_duration_sec=duration,
        )

    def reset(self) -> None:
        """Clear all buffers."""
        self.buffer_1min = CircularBuffer(self.buffer_1min.max_size)
        self.buffer_5min = CircularBuffer(self.buffer_5min.max_size)
        self.buffer_10min = CircularBuffer(self.buffer_10min.max_size)


class FocusDecayDetector:
    """
    Detects when focus drops below baseline (decay pattern).
    Uses statistical methods to identify significant drops.
    """

    def __init__(self, baseline_window: int = 300, decay_threshold: float = 0.15):
        """
        Args:
            baseline_window: Seconds to use for baseline calculation
            decay_threshold: Fraction drop (0.15 = 15% drop) to trigger decay
        """
        self.baseline_window = baseline_window
        self.decay_threshold = decay_threshold
        self.baseline_mean: Optional[float] = None
        self.baseline_std: Optional[float] = None
        self.buffer = CircularBuffer(int(baseline_window * 2.4))

    def update(self, timestamp: float, focus_score: float) -> Optional[dict]:
        """
        Update with new focus score.
        Returns decay event dict if detected, None otherwise.
        """
        self.buffer.append(timestamp, focus_score)

        # Update baseline if we have enough data
        cutoff = timestamp - self.baseline_window
        values, _ = self.buffer.get_window(cutoff)

        if len(values) >= 10:  # Minimum samples for baseline
            self.baseline_mean = float(np.mean(values))
            self.baseline_std = float(np.std(values))

        # Check for decay
        if self.baseline_mean is not None and focus_score > 0:
            drop = (self.baseline_mean - focus_score) / self.baseline_mean
            if drop >= self.decay_threshold:
                return {
                    "decay_detected": True,
                    "baseline": self.baseline_mean,
                    "current": focus_score,
                    "drop_percent": drop * 100,
                    "timestamp": timestamp,
                }

        return None

    def reset(self) -> None:
        """Reset baseline."""
        self.baseline_mean = None
        self.baseline_std = None
        self.buffer = CircularBuffer(self.buffer.max_size)


class SessionStatistics:
    """
    Calculate session-level statistics: mean, std, trends, volatility.
    Pre-computes aggregates for efficient querying.
    """

    def __init__(self):
        self.all_focus_scores: List[float] = []
        self.all_posture_scores: List[float] = []
        self.all_timestamps: List[float] = []
        self.start_time: Optional[float] = None

    def add_point(self, timestamp: float, focus_score: float, posture_score: float) -> None:
        """Add a data point."""
        if self.start_time is None:
            self.start_time = timestamp
        self.all_focus_scores.append(focus_score)
        self.all_posture_scores.append(posture_score)
        self.all_timestamps.append(timestamp)

    def get_statistics(self) -> dict:
        """Get comprehensive session statistics."""
        if len(self.all_focus_scores) == 0:
            return {
                "focus_mean": 0.0,
                "focus_std": 0.0,
                "focus_trend": 0.0,
                "focus_volatility": 0.0,
                "posture_mean": 0.0,
                "posture_std": 0.0,
                "duration_sec": 0.0,
                "total_samples": 0,
            }

        focus_arr = np.array(self.all_focus_scores)
        posture_arr = np.array(self.all_posture_scores)
        times_arr = np.array(self.all_timestamps)

        # Focus statistics (handle NaN/Inf)
        focus_valid = focus_arr[~np.isnan(focus_arr) & ~np.isinf(focus_arr)]
        if len(focus_valid) == 0:
            focus_mean = 0.0
            focus_std = 0.0
        else:
            focus_mean = float(np.mean(focus_valid))
            focus_std = float(np.std(focus_valid))
        
        # Focus trend with robust error handling
        focus_trend = 0.0
        if len(times_arr) >= 2 and len(focus_arr) >= 2:
            # Remove NaN/Inf values
            valid_mask = ~np.isnan(focus_arr) & ~np.isinf(focus_arr) & ~np.isnan(times_arr) & ~np.isinf(times_arr)
            if np.sum(valid_mask) >= 2:
                focus_clean = focus_arr[valid_mask]
                times_clean = times_arr[valid_mask]
                
                # Normalize times to avoid numerical issues
                times_normalized = times_clean - times_clean[0]
                
                # Check for sufficient variation
                if np.std(times_normalized) >= 1e-10:
                    try:
                        focus_trend = float(np.polyfit(times_normalized, focus_clean, 1)[0])
                    except (np.linalg.LinAlgError, ValueError):
                        focus_trend = 0.0
        
        focus_volatility = focus_std / focus_mean if focus_mean > 0 else 0.0

        # Posture statistics (handle NaN/Inf)
        posture_valid = posture_arr[~np.isnan(posture_arr) & ~np.isinf(posture_arr)]
        if len(posture_valid) == 0:
            posture_mean = 0.0
            posture_std = 0.0
        else:
            posture_mean = float(np.mean(posture_valid))
            posture_std = float(np.std(posture_valid))

        duration = float(times_arr[-1] - times_arr[0]) if len(times_arr) > 1 else 0.0

        return {
            "focus_mean": focus_mean,
            "focus_std": focus_std,
            "focus_trend": focus_trend,
            "focus_volatility": focus_volatility,
            "posture_mean": posture_mean,
            "posture_std": posture_std,
            "duration_sec": duration,
            "total_samples": len(self.all_focus_scores),
        }

    def reset(self) -> None:
        """Reset statistics."""
        self.all_focus_scores.clear()
        self.all_posture_scores.clear()
        self.all_timestamps.clear()
        self.start_time = None
