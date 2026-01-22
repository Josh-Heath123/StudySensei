"""
StudySensei Behavior Modeling — pattern detection and break logic.

Architecture:
- BehaviorModeler is stateful: tracks slouch intervals, focus drops, and last break time.
- Pattern detection: prolonged slouch, sustained focus drop, extended distraction.
- Break logic: suggest breaks after ~25–30 min continuous work, or after detected patterns.
- Emits BehaviorPattern when a pattern ends; suggest_break returns a user-facing message or None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

# Thresholds
SLOUCH_DURATION_SEC = 45.0       # continuous slouch → pattern
FOCUS_DROP_THRESHOLD = 40.0     # focus score below this = "low"
FOCUS_DROP_DURATION_SEC = 90.0  # sustained low focus → pattern
MIN_BREAK_INTERVAL_SEC = 20 * 60   # don't suggest another break within 20 min
SUGGEST_BREAK_AFTER_SEC = 25 * 60  # suggest break after ~25 min continuous work
DISTRACTION_DURATION_SEC = 60.0  # extended away → pattern


class PatternType(str, Enum):
    PROLONGED_SLOUCH = "prolonged_slouch"
    FOCUS_DROP = "focus_drop"
    EXTENDED_DISTRACTION = "extended_distraction"


@dataclass
class BehaviorPattern:
    pattern_type: PatternType
    start_time: float
    end_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class BehaviorModeler:
    """
    Tracks behavior over time, detects patterns (slouch, focus drop, distraction),
    and suggests breaks. Reset on new session.
    """

    def __init__(self) -> None:
        self._slouch_start: Optional[float] = None
        self._focus_drop_start: Optional[float] = None
        self._distraction_start: Optional[float] = None
        self._last_break_at: Optional[float] = None
        self._work_start: Optional[float] = None
        self._last_suggestion_at: Optional[float] = None
        self._pattern_break_message: Optional[str] = None

    def update(
        self,
        timestamp: float,
        focus_score: float,
        posture_score: float,
        is_slouching: bool,
        is_present: bool,
    ) -> Optional[BehaviorPattern]:
        """
        Update state and optionally emit a completed BehaviorPattern.
        Returns None if no pattern just completed.
        """
        out: Optional[BehaviorPattern] = None

        # Slouch
        if is_slouching:
            if self._slouch_start is None:
                self._slouch_start = timestamp
            elif timestamp - self._slouch_start >= SLOUCH_DURATION_SEC:
                out = BehaviorPattern(
                    pattern_type=PatternType.PROLONGED_SLOUCH,
                    start_time=self._slouch_start,
                    end_time=timestamp,
                    metadata={"posture_score": posture_score},
                )
                self._slouch_start = None
                self._pattern_break_message = (
                    "Prolonged slouching detected. Consider a short break to adjust your posture."
                )
        else:
            self._slouch_start = None

        # Focus drop (low focus while present)
        if is_present and focus_score < FOCUS_DROP_THRESHOLD:
            if self._focus_drop_start is None:
                self._focus_drop_start = timestamp
            elif timestamp - self._focus_drop_start >= FOCUS_DROP_DURATION_SEC:
                out = out or BehaviorPattern(
                    pattern_type=PatternType.FOCUS_DROP,
                    start_time=self._focus_drop_start,
                    end_time=timestamp,
                    metadata={"avg_focus": focus_score, "posture_score": posture_score},
                )
                self._focus_drop_start = None
        else:
            self._focus_drop_start = None

        # Extended distraction (not present)
        if not is_present:
            if self._distraction_start is None:
                self._distraction_start = timestamp
            elif timestamp - self._distraction_start >= DISTRACTION_DURATION_SEC:
                out = out or BehaviorPattern(
                    pattern_type=PatternType.EXTENDED_DISTRACTION,
                    start_time=self._distraction_start,
                    end_time=timestamp,
                    metadata={},
                )
                self._distraction_start = None
        else:
            self._distraction_start = None

        if self._work_start is None and (is_present or focus_score > 0):
            self._work_start = timestamp

        return out

    def suggest_break(self, timestamp: float) -> Optional[str]:
        """
        Return a user-facing break suggestion message, or None.
        Throttled: won't suggest again within MIN_BREAK_INTERVAL_SEC.
        Pattern-triggered messages (e.g. prolonged slouch) can override throttle.
        """
        now = timestamp
        if self._last_break_at is not None and (now - self._last_break_at) < MIN_BREAK_INTERVAL_SEC:
            return None
        throttled = (
            self._last_suggestion_at is not None
            and (now - self._last_suggestion_at) < MIN_BREAK_INTERVAL_SEC
        )
        if throttled:
            if self._pattern_break_message:
                msg = self._pattern_break_message
                self._pattern_break_message = None
                self._last_suggestion_at = now
                return msg
            return None
        work_duration = (now - self._work_start) if self._work_start else 0.0
        if work_duration >= SUGGEST_BREAK_AFTER_SEC:
            self._last_suggestion_at = now
            self._pattern_break_message = (
                "You've been studying for over 25 minutes. Consider a short break: "
                "stand up, look away from the screen, or stretch."
            )
        if self._pattern_break_message:
            msg = self._pattern_break_message
            self._pattern_break_message = None
            return msg
        return None

    def record_break_taken(self, timestamp: float) -> None:
        """Call when user explicitly takes a break (e.g. future UI action)."""
        self._last_break_at = timestamp
        self._work_start = timestamp  # reset work clock

    def reset(self) -> None:
        """Clear state for a new session."""
        self._slouch_start = None
        self._focus_drop_start = None
        self._distraction_start = None
        self._last_break_at = None
        self._work_start = None
        self._last_suggestion_at = None
        self._pattern_break_message = None
