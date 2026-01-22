"""
ML Focus Drop Predictor

Features:
- Random Forest model to predict "focus drop in next 5 minutes"
- Features: recent focus trend, posture score, session duration
- Save/load model with joblib, retrain weekly
- Confidence scores for predictions
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    import joblib

    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    RandomForestClassifier = None
    joblib = None

# Model configuration
MODEL_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = MODEL_DIR / "focus_drop_model.joblib"
RETRAIN_INTERVAL_DAYS = 7
PREDICTION_WINDOW_SEC = 300  # 5 minutes


class FocusDropPredictor:
    """
    Random Forest model to predict focus drop in next 5 minutes.
    Features: recent focus trend, posture score, session duration, volatility
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_PATH
        self.model: Optional["RandomForestClassifier"] = None
        self.feature_buffer: List[Dict[str, float]] = []
        self.label_buffer: List[bool] = []
        self.last_retrain_time: Optional[float] = None

        if _SKLEARN_AVAILABLE:
            self._load_model()
            if self.model is None:
                self.model = RandomForestClassifier(
                    n_estimators=100, max_depth=10, random_state=42
                )
        else:
            logger.warning("scikit-learn not available, ML predictions disabled")

    def _load_model(self) -> None:
        """Load saved model if available."""
        if not _SKLEARN_AVAILABLE:
            return
        if self.model_path.exists():
            try:
                self.model = joblib.load(self.model_path)
                logger.info(f"Loaded model from {self.model_path}")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")

    def _save_model(self) -> None:
        """Save model to disk."""
        if not _SKLEARN_AVAILABLE or self.model is None:
            return
        try:
            joblib.dump(self.model, self.model_path)
            logger.info(f"Saved model to {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")

    def extract_features(
        self,
        recent_focus_scores: List[float],
        posture_score: float,
        session_duration: float,
        focus_volatility: float,
    ) -> np.ndarray:
        """
        Extract features for prediction.
        Features:
        1. Recent focus trend (slope)
        2. Current focus score
        3. Posture score (normalized)
        4. Session duration (normalized)
        5. Focus volatility
        6. Recent mean focus
        7. Recent std focus
        """
        if len(recent_focus_scores) < 2:
            # Not enough data, return default features
            return np.array([
                0.0,  # trend
                0.0,  # current
                posture_score / 100.0,  # posture
                min(session_duration / 3600.0, 1.0),  # duration (normalized to 1 hour)
                focus_volatility,  # volatility
                0.0,  # mean
                0.0,  # std
            ])

        focus_arr = np.array(recent_focus_scores)
        times = np.arange(len(focus_arr))

        # Trend (slope)
        trend = float(np.polyfit(times, focus_arr, 1)[0]) / 100.0  # Normalize

        # Current focus
        current = recent_focus_scores[-1] / 100.0

        # Mean and std
        mean_focus = float(np.mean(focus_arr)) / 100.0
        std_focus = float(np.std(focus_arr)) / 100.0

        return np.array([
            trend,
            current,
            posture_score / 100.0,
            min(session_duration / 3600.0, 1.0),
            focus_volatility,
            mean_focus,
            std_focus,
        ])

    def add_observation(
        self,
        timestamp: float,
        focus_score: float,
        posture_score: float,
        session_duration: float,
        focus_volatility: float,
        recent_focus_scores: List[float],
    ) -> None:
        """
        Add an observation for training.
        We'll label it later when we know if focus dropped.
        """
        features = self.extract_features(
            recent_focus_scores, posture_score, session_duration, focus_volatility
        )
        self.feature_buffer.append({
            "timestamp": timestamp,
            "features": features,
            "focus_score": focus_score,
        })

    def label_observation(self, timestamp: float, future_focus: float, threshold: float = 0.15) -> None:
        """
        Label a past observation based on whether focus dropped.
        threshold: 15% drop = positive label (focus drop predicted)
        """
        # Find observation closest to timestamp
        if not self.feature_buffer:
            return

        # Find observation from ~5 minutes ago
        target_time = timestamp - PREDICTION_WINDOW_SEC
        closest_idx = None
        min_diff = float("inf")

        for i, obs in enumerate(self.feature_buffer):
            diff = abs(obs["timestamp"] - target_time)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i

        if closest_idx is None or min_diff > 600:  # More than 10 min off
            return

        obs = self.feature_buffer[closest_idx]
        past_focus = obs["focus_score"]
        drop = (past_focus - future_focus) / past_focus if past_focus > 0 else 0.0

        # Label: True if drop >= threshold
        label = drop >= threshold

        # Store feature-label pair
        self.label_buffer.append((obs["features"], label))

        # Clean old observations
        self.feature_buffer = [
            o for o in self.feature_buffer if o["timestamp"] > timestamp - 3600
        ]

    def predict(
        self,
        recent_focus_scores: List[float],
        posture_score: float,
        session_duration: float,
        focus_volatility: float,
    ) -> Optional[Dict[str, float]]:
        """
        Predict if focus will drop in next 5 minutes.
        Returns dict with prediction and confidence, or None if model unavailable.
        """
        if not _SKLEARN_AVAILABLE or self.model is None:
            return None

        if len(recent_focus_scores) < 2:
            return None

        features = self.extract_features(
            recent_focus_scores, posture_score, session_duration, focus_volatility
        )
        features = features.reshape(1, -1)

        try:
            prediction = self.model.predict(features)[0]
            probabilities = self.model.predict_proba(features)[0]
            confidence = float(max(probabilities))

            return {
                "will_drop": bool(prediction),
                "confidence": confidence,
                "drop_probability": float(probabilities[1]) if len(probabilities) > 1 else 0.0,
            }
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return None

    def train(self) -> bool:
        """
        Train model on collected observations.
        Returns True if training successful.
        """
        if not _SKLEARN_AVAILABLE:
            return False

        if len(self.label_buffer) < 50:  # Need at least 50 samples
            logger.warning("Not enough training data")
            return False

        X = np.array([f for f, _ in self.label_buffer])
        y = np.array([l for _, l in self.label_buffer])

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Train
        self.model = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42
        )
        self.model.fit(X_train, y_train)

        # Evaluate
        train_score = self.model.score(X_train, y_train)
        test_score = self.model.score(X_test, y_test)

        logger.info(f"Model trained: train_acc={train_score:.3f}, test_acc={test_score:.3f}")

        # Save model
        self._save_model()

        return True

    def should_retrain(self) -> bool:
        """Check if model should be retrained (weekly)."""
        import time

        if self.last_retrain_time is None:
            return True

        days_since = (time.time() - self.last_retrain_time) / (24 * 3600)
        return days_since >= RETRAIN_INTERVAL_DAYS

    def reset(self) -> None:
        """Reset predictor for new session."""
        # Keep feature buffer for training, but could clear if needed
        pass
