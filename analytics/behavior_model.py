"""
Behavior Modeling Engine

Features:
- Focus scoring model: weighted gaze + posture + emotion
- Study pattern detection: Morning focus, Afternoon slump, Pomodoro rhythm
- Session phase detection: warm-up, peak, fatigue, recovery
- Pattern recognition for interview discussions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class StudyPattern(str, Enum):
    MORNING_FOCUS = "morning_focus"
    AFTERNOON_SLUMP = "afternoon_slump"
    POMODORO_RHYTHM = "pomodoro_rhythm"
    CONSISTENT = "consistent"
    VARIABLE = "variable"


class SessionPhase(str, Enum):
    WARM_UP = "warm_up"
    PEAK = "peak"
    FATIGUE = "fatigue"
    RECOVERY = "recovery"


@dataclass
class BehaviorPattern:
    pattern_type: str
    start_time: float
    end_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class FocusScorer:
    """
    Weighted focus scoring model:
    - Gaze confidence: 40%
    - Posture score: 30%
    - Emotion (placeholder): 30%
    """

    def __init__(
        self,
        gaze_weight: float = 0.40,
        posture_weight: float = 0.30,
        emotion_weight: float = 0.30,
    ):
        if abs(gaze_weight + posture_weight + emotion_weight - 1.0) > 0.01:
            raise ValueError("Weights must sum to 1.0")
        self.gaze_weight = gaze_weight
        self.posture_weight = posture_weight
        self.emotion_weight = emotion_weight

    def compute_focus_score(
        self,
        gaze_confidence: float,
        posture_score: float,
        emotion_score: float = 0.5,  # 0-1, where 0.5 = neutral, <0.5 = negative, >0.5 = positive
    ) -> float:
        """
        Compute weighted focus score (0-100).
        Args:
            gaze_confidence: 0-1, how well user is looking at screen
            posture_score: 0-100, posture quality
            emotion_score: 0-1, emotional state (0.5 = neutral, lower = frustrated/tired, higher = positive)
        """
        # Normalize posture to 0-1
        posture_norm = posture_score / 100.0

        # Weighted combination
        score = (
            self.gaze_weight * gaze_confidence * 100
            + self.posture_weight * posture_norm * 100
            + self.emotion_weight * emotion_score * 100
        )

        return max(0.0, min(100.0, score))


class PatternDetector:
    """
    Detects study patterns: Morning focus, Afternoon slump, Pomodoro rhythm.
    Uses time-of-day analysis and focus rhythm detection.
    """

    def __init__(self):
        self.focus_history: List[Tuple[float, float]] = []  # (timestamp, focus_score)
        self.patterns_detected: List[StudyPattern] = []

    def update(self, timestamp: float, focus_score: float) -> Optional[StudyPattern]:
        """Update with new focus score, return detected pattern if any."""
        self.focus_history.append((timestamp, focus_score))

        # Keep last 2 hours of history
        cutoff = timestamp - 7200
        self.focus_history = [(t, f) for t, f in self.focus_history if t >= cutoff]

        # Detect patterns
        pattern = self._detect_patterns(timestamp)
        if pattern and pattern not in self.patterns_detected:
            self.patterns_detected.append(pattern)
            return pattern

        return None

    def _detect_patterns(self, timestamp: float) -> Optional[StudyPattern]:
        """Detect study patterns from history."""
        if len(self.focus_history) < 20:
            return None

        # Time of day analysis
        import datetime

        dt = datetime.datetime.fromtimestamp(timestamp)
        hour = dt.hour

        # Morning focus (8-11 AM, high focus)
        if 8 <= hour <= 11:
            recent_focus = np.mean([f for _, f in self.focus_history[-20:]])
            if recent_focus > 75:
                return StudyPattern.MORNING_FOCUS

        # Afternoon slump (2-4 PM, lower focus)
        if 14 <= hour <= 16:
            recent_focus = np.mean([f for _, f in self.focus_history[-20:]])
            if recent_focus < 60:
                return StudyPattern.AFTERNOON_SLUMP

        # Pomodoro rhythm detection (25-min cycles with breaks)
        if len(self.focus_history) >= 100:
            pattern = self._detect_pomodoro_rhythm()
            if pattern:
                return pattern

        return None

    def _detect_pomodoro_rhythm(self) -> Optional[StudyPattern]:
        """Detect 25-minute focus cycles (Pomodoro technique)."""
        if len(self.focus_history) < 50:
            return None

        # Look for periodic drops (breaks) every ~25 minutes
        timestamps = np.array([t for t, _ in self.focus_history])
        focus_scores = np.array([f for _, f in self.focus_history])

        # Find low-focus periods (potential breaks)
        low_focus_mask = focus_scores < 30
        if np.sum(low_focus_mask) < 3:
            return None

        # Check if breaks are roughly periodic (25 min = 1500 sec)
        low_focus_times = timestamps[low_focus_mask]
        if len(low_focus_times) >= 2:
            intervals = np.diff(low_focus_times)
            # Check if intervals are around 1500 seconds (25 min) ± 5 min
            pomodoro_intervals = intervals[
                (intervals > 1200) & (intervals < 1800)
            ]
            if len(pomodoro_intervals) >= 2:
                return StudyPattern.POMODORO_RHYTHM

        return None

    def get_detected_patterns(self) -> List[StudyPattern]:
        """Get all detected patterns."""
        return self.patterns_detected.copy()

    def reset(self) -> None:
        """Reset pattern detection."""
        self.focus_history.clear()
        self.patterns_detected.clear()


class PhaseDetector:
    """
    Detects session phases: warm-up, peak, fatigue, recovery.
    Uses focus trend analysis and duration.
    """

    def __init__(self):
        self.focus_history: List[Tuple[float, float]] = []
        self.current_phase: Optional[SessionPhase] = None
        self.phase_transitions: List[Tuple[float, SessionPhase]] = []

    def update(self, timestamp: float, focus_score: float, session_duration: float) -> Optional[SessionPhase]:
        """Update phase detection, return new phase if transition occurred."""
        self.focus_history.append((timestamp, focus_score))

        # Keep last 10 minutes
        cutoff = timestamp - 600
        self.focus_history = [(t, f) for t, f in self.focus_history if t >= cutoff]

        new_phase = self._detect_phase(session_duration)
        if new_phase != self.current_phase:
            self.phase_transitions.append((timestamp, new_phase))
            self.current_phase = new_phase
            return new_phase

        return None

    def _detect_phase(self, session_duration: float) -> SessionPhase:
        """Detect current session phase."""
        if len(self.focus_history) < 10:
            return SessionPhase.WARM_UP

        recent_focus = np.array([f for _, f in self.focus_history[-20:]])
        mean_focus = np.mean(recent_focus)

        # Warm-up: first 5 minutes
        if session_duration < 300:
            return SessionPhase.WARM_UP

        # Peak: high focus (75+), stable
        if mean_focus >= 75 and np.std(recent_focus) < 10:
            return SessionPhase.PEAK

        # Fatigue: declining trend, lower focus
        if len(self.focus_history) >= 20:
            timestamps = np.array([t for t, _ in self.focus_history[-20:]])
            focus_scores = np.array([f for _, f in self.focus_history[-20:]])
            trend = np.polyfit(timestamps - timestamps[0], focus_scores, 1)[0]

            if trend < -0.1 and mean_focus < 60:  # Declining, low focus
                return SessionPhase.FATIGUE

        # Recovery: focus increasing after fatigue
        if self.current_phase == SessionPhase.FATIGUE:
            if len(self.focus_history) >= 10:
                recent_trend = np.polyfit(
                    np.array([t for t, _ in self.focus_history[-10:]]) - self.focus_history[-10][0],
                    np.array([f for _, f in self.focus_history[-10:]]),
                    1,
                )[0]
                if recent_trend > 0.1:  # Recovering
                    return SessionPhase.RECOVERY

        # Default: maintain current or peak
        return self.current_phase or SessionPhase.PEAK

    def get_current_phase(self) -> Optional[SessionPhase]:
        """Get current session phase."""
        return self.current_phase

    def get_phase_transitions(self) -> List[Tuple[float, SessionPhase]]:
        """Get all phase transitions."""
        return self.phase_transitions.copy()

    def reset(self) -> None:
        """Reset phase detection."""
        self.focus_history.clear()
        self.current_phase = None
        self.phase_transitions.clear()


class BehaviorModeler:
    """
    Main behavior modeling engine combining all components.
    """

    def __init__(self):
        self.focus_scorer = FocusScorer()
        self.pattern_detector = PatternDetector()
        self.phase_detector = PhaseDetector()
        self.session_start_time: Optional[float] = None

    def update(
        self,
        timestamp: float,
        gaze_confidence: float,
        posture_score: float,
        emotion_score: float = 0.5,
        is_slouching: bool = False,
        is_present: bool = True,
    ) -> Dict[str, Any]:
        """
        Update behavior model with new observations.
        Returns dict with computed focus score, detected patterns, phase, etc.
        """
        # Compute weighted focus score
        focus_score = self.focus_scorer.compute_focus_score(
            gaze_confidence, posture_score, emotion_score
        )

        # Update pattern detector
        pattern = self.pattern_detector.update(timestamp, focus_score)

        # Update phase detector
        session_duration = (
            timestamp - self.session_start_time if self.session_start_time else 0.0
        )
        phase = self.phase_detector.update(timestamp, focus_score, session_duration)

        return {
            "focus_score": focus_score,
            "detected_pattern": pattern.value if pattern else None,
            "session_phase": phase.value if phase else None,
            "is_slouching": is_slouching,
            "is_present": is_present,
        }

    def start_session(self, timestamp: float) -> None:
        """Start a new session."""
        self.session_start_time = timestamp
        self.pattern_detector.reset()
        self.phase_detector.reset()

    def reset(self) -> None:
        """Reset all components."""
        self.pattern_detector.reset()
        self.phase_detector.reset()
        self.session_start_time = None
