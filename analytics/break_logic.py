"""
Intelligent Break Recommendation Engine

Features:
- Break suggestions based on focus decay rate
- Adaptive timing based on session phase
- Pattern-aware recommendations
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Break recommendation thresholds
MIN_BREAK_INTERVAL_SEC = 20 * 60  # 20 minutes
SUGGEST_BREAK_AFTER_SEC = 25 * 60  # 25 minutes
FOCUS_DECAY_THRESHOLD = 0.20  # 20% drop triggers break suggestion
FATIGUE_BREAK_THRESHOLD = 15 * 60  # Suggest break after 15 min in fatigue phase


class BreakRecommender:
    """
    Intelligent break recommendation system.
    Considers focus decay rate, session phase, and patterns.
    """

    def __init__(self):
        self.last_break_at: Optional[float] = None
        self.last_suggestion_at: Optional[float] = None
        self.work_start: Optional[float] = None

    def suggest_break(
        self,
        timestamp: float,
        focus_decay_rate: float,
        session_phase: Optional[str],
        session_duration: float,
        focus_score: float,
        baseline_focus: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest a break based on multiple factors.
        Returns dict with recommendation or None.
        """
        now = timestamp

        # Throttle: don't suggest too frequently
        if (
            self.last_suggestion_at is not None
            and (now - self.last_suggestion_at) < MIN_BREAK_INTERVAL_SEC
        ):
            return None

        # Check if user just took a break
        if (
            self.last_break_at is not None
            and (now - self.last_break_at) < MIN_BREAK_INTERVAL_SEC
        ):
            return None

        reasons = []

        # 1. Time-based: after 25 minutes of work
        if session_duration >= SUGGEST_BREAK_AFTER_SEC:
            reasons.append("You've been studying for over 25 minutes")

        # 2. Focus decay: significant drop in focus
        # Safe division: check for zero baseline_focus to prevent division by zero
        if baseline_focus is not None and focus_score > 0 and baseline_focus > 0.01:
            drop = (baseline_focus - focus_score) / baseline_focus
            if drop >= FOCUS_DECAY_THRESHOLD:
                reasons.append(f"Focus has dropped by {drop*100:.0f}%")

        # 3. Decay rate: rapid decline
        if focus_decay_rate < -0.5:  # Declining at >0.5 points/second
            reasons.append("Focus is declining rapidly")

        # 4. Fatigue phase: extended time in fatigue
        if session_phase == "fatigue":
            # This would require tracking time in fatigue phase
            # Simplified: if in fatigue and duration > 15 min, suggest break
            if session_duration >= FATIGUE_BREAK_THRESHOLD:
                reasons.append("You're in a fatigue phase")

        if not reasons:
            return None

        # Generate recommendation message
        if len(reasons) == 1:
            message = f"{reasons[0]}. Consider a short break."
        else:
            message = f"{', '.join(reasons[:-1])}, and {reasons[-1]}. Consider a short break."

        self.last_suggestion_at = now

        return {
            "suggest_break": True,
            "message": message,
            "urgency": "high" if focus_decay_rate < -1.0 else "medium",
            "recommended_duration_sec": 300,  # 5 minutes
        }

    def record_break_taken(self, timestamp: float) -> None:
        """Record that user took a break."""
        self.last_break_at = timestamp
        self.work_start = timestamp  # Reset work clock

    def start_session(self, timestamp: float) -> None:
        """Start a new session."""
        self.work_start = timestamp
        self.last_break_at = None
        self.last_suggestion_at = None

    def reset(self) -> None:
        """Reset break recommender."""
        self.last_break_at = None
        self.last_suggestion_at = None
        self.work_start = None
