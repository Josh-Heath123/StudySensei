"""
StudySensei ML Focus Predictor — optional lightweight model for focus prediction.

Architecture:
- FocusPredictor maintains a rolling window of (timestamp, focus, posture, gaze).
- If scikit-learn is available: fits a Ridge regression on recent features to predict
  focus; used for optional "predicted focus" UX or future break logic.
- If not: no-op; add_observation / reset still work, prediction always returns None.
- Minimal allocations to preserve real-time performance.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Tuple

try:
    import numpy as np
    from sklearn.linear_model import Ridge
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

# Rolling window: last N points for feature construction
PREDICTOR_WINDOW = 60
# Min samples before we attempt fit
MIN_SAMPLES = 20


class FocusPredictor:
    """
    Optional ML model for focus prediction. Updates via add_observation;
    reset clears state on new session.
    """

    def __init__(self) -> None:
        self._buffer: Deque[Tuple[float, float, float, float]] = deque(
            maxlen=PREDICTOR_WINDOW * 2
        )
        self._model: Optional["Ridge"] = Ridge(alpha=1.0) if _SKLEARN_AVAILABLE else None
        self._last_focus: float = 0.0

    def add_observation(
        self,
        timestamp: float,
        focus_score: float,
        posture_score: float,
        gaze_confidence: float,
    ) -> None:
        """Append one observation. Non-blocking."""
        self._buffer.append((timestamp, focus_score, posture_score, gaze_confidence))
        self._last_focus = focus_score

    def predict_next_focus(self) -> Optional[float]:
        """
        Return predicted focus for "next" step, or None if model unavailable
        or insufficient data.
        """
        if not _SKLEARN_AVAILABLE or self._model is None:
            return None
        if len(self._buffer) < MIN_SAMPLES:
            return None

        X, y = self._features_labels()
        if X is None or len(X) < MIN_SAMPLES:
            return None
        try:
            self._model.fit(X, y)
            last = list(self._buffer)[-1]
            x_last = self._feature_vec(
                list(self._buffer)[:-1],
                last[1],
                last[2],
                last[3],
            )
            return float(self._model.predict([x_last])[0])
        except Exception:
            return None

    def _features_labels(
        self,
    ) -> Tuple[Optional[List[List[float]]], Optional[List[float]]]:
        buf = list(self._buffer)
        if len(buf) < 2:
            return None, None
        X = []
        y = []
        for i in range(1, len(buf)):
            _, f, p, g = buf[i]
            x = self._feature_vec(buf[:i], buf[i - 1][1], buf[i - 1][2], buf[i - 1][3])
            X.append(x)
            y.append(f)
        return X, y

    @staticmethod
    def _feature_vec(
        history: List[Tuple[float, float, float, float]],
        prev_focus: float,
        prev_posture: float,
        prev_gaze: float,
    ) -> List[float]:
        """Simple features: prev focus/posture/gaze, recent means."""
        n = min(5, len(history))
        recent = history[-n:] if n else []
        f_mean = sum(h[1] for h in recent) / n if n else 0.0
        p_mean = sum(h[2] for h in recent) / n if n else 0.0
        g_mean = sum(h[3] for h in recent) / n if n else 0.0
        return [prev_focus, prev_posture, prev_gaze, f_mean, p_mean, g_mean]

    def reset(self) -> None:
        """Clear state for new session."""
        self._buffer.clear()
        self._model = Ridge(alpha=1.0) if _SKLEARN_AVAILABLE else None
        self._last_focus = 0.0
