"""
StudySensei Advanced Analytics Module

FAANG-grade time-series analytics and behavior modeling engine.
"""

from .time_series import TimeSeriesAnalyzer, FocusDecayDetector, SessionStatistics
from .behavior_model import BehaviorModeler, FocusScorer, PatternDetector, PhaseDetector
from .session_store import SessionStore, SessionQuery
from .break_logic import BreakRecommender
from .ml_predictor import FocusDropPredictor

__all__ = [
    "TimeSeriesAnalyzer",
    "FocusDecayDetector",
    "SessionStatistics",
    "BehaviorModeler",
    "FocusScorer",
    "PatternDetector",
    "PhaseDetector",
    "SessionStore",
    "SessionQuery",
    "BreakRecommender",
    "FocusDropPredictor",
]
