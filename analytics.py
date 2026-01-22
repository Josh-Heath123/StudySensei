"""
StudySensei Time-Series Analytics — 10-minute sliding-window metrics.

Architecture:
- In-memory sliding window (10 min) over (timestamp, focus_score, posture_score).
- TimeSeriesAnalyzer.add_data_point() updates the buffer; get_all_window_metrics() returns
  aggregates for the current window without touching the DB.
- WindowMetrics: typed dict for avg/min/max focus and posture, sample count, window duration.
- Reset on new session; minimal allocation to preserve real-time performance.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Tuple

# 10-minute sliding window in seconds
WINDOW_DURATION_SEC = 600


@dataclass
class WindowMetrics:
    """Aggregate metrics over the current sliding window (e.g. 10 min)."""

    focus_avg: float
    focus_min: float
    focus_max: float
    posture_avg: float
    posture_min: float
    posture_max: float
    sample_count: int
    window_duration_sec: float

    def to_dict(self) -> dict:
        return {
            "focus_avg_10m": self.focus_avg,
            "focus_min_10m": self.focus_min,
            "focus_max_10m": self.focus_max,
            "posture_avg_10m": self.posture_avg,
            "posture_min_10m": self.posture_min,
            "posture_max_10m": self.posture_max,
            "sample_count_10m": self.sample_count,
            "window_duration_sec": self.window_duration_sec,
        }


def _trim_to_window(
    buf: Deque[Tuple[float, float, float]],
    now: float,
    window_sec: float,
) -> None:
    cutoff = now - window_sec
    while buf and buf[0][0] < cutoff:
        buf.popleft()


def _compute_metrics(
    buf: Deque[Tuple[float, float, float]],
    now: float,
    window_sec: float,
) -> WindowMetrics:
    _trim_to_window(buf, now, window_sec)
    if not buf:
        return WindowMetrics(
            focus_avg=0.0,
            focus_min=0.0,
            focus_max=0.0,
            posture_avg=0.0,
            posture_min=0.0,
            posture_max=0.0,
            sample_count=0,
            window_duration_sec=window_sec,
        )
    focus = [x[1] for x in buf]
    posture = [x[2] for x in buf]
    duration = buf[-1][0] - buf[0][0] if len(buf) > 1 else 0.0
    return WindowMetrics(
        focus_avg=sum(focus) / len(focus),
        focus_min=min(focus),
        focus_max=max(focus),
        posture_avg=sum(posture) / len(posture),
        posture_min=min(posture),
        posture_max=max(posture),
        sample_count=len(buf),
        window_duration_sec=duration,
    )


class TimeSeriesAnalyzer:
    """
    Maintains a 10-minute sliding window of (ts, focus_score, posture_score) and
    provides aggregate metrics. Optimized for frequent add_data_point and
    occasional get_all_window_metrics calls.
    """

    def __init__(self, window_sec: float = WINDOW_DURATION_SEC) -> None:
        self._window_sec = window_sec
        # (timestamp, focus_score, posture_score); trim by timestamp
        self._buffer: Deque[Tuple[float, float, float]] = deque(maxlen=12000)

    def add_data_point(self, timestamp: float, focus_score: float, posture_score: float) -> None:
        """Append a single observation. Does not block."""
        self._buffer.append((timestamp, focus_score, posture_score))

    def get_all_window_metrics(self, timestamp: float) -> dict:
        """
        Return metrics for the current 10-min window as a dict (e.g. for UI).
        Keys: focus_avg_10m, focus_min_10m, focus_max_10m, posture_avg_10m, etc.
        """
        m = _compute_metrics(self._buffer, timestamp, self._window_sec)
        return m.to_dict()

    def get_window_metrics(self, timestamp: float) -> WindowMetrics:
        """Return WindowMetrics for the current window."""
        return _compute_metrics(self._buffer, timestamp, self._window_sec)

    def reset(self) -> None:
        """Clear buffer on new session."""
        self._buffer.clear()
