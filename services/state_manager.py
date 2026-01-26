"""
State management and initialization for StudySensei.

NOTE: This module is Streamlit-specific and is not used by the PyQt version.
It is kept for backward compatibility if Streamlit support is needed in the future.
"""

# Conditional Streamlit import (only for Streamlit app, not PyQt)
try:
    import streamlit as st
    _STREAMLIT_AVAILABLE = True
except (ImportError, RuntimeError):
    # PyQt mode or Streamlit not available
    _STREAMLIT_AVAILABLE = False
    # Create dummy st object to prevent AttributeError
    class _DummyStreamlit:
        class session_state:
            def __getitem__(self, key):
                raise KeyError(f"Streamlit not available: {key}")
            def __setitem__(self, key, value):
                pass
            def __contains__(self, key):
                return False
            def get(self, key, default=None):
                return default
            def keys(self):
                return []
        def __getattr__(self, name):
            return self.session_state()
    st = _DummyStreamlit()

import numpy as np
from collections import deque
from utils.constants import WINDOW_SIZE, TARGET_FPS

# Analytics imports (optional)
try:
    from analytics import (
        TimeSeriesAnalyzer,
        FocusDecayDetector,
        SessionStatistics,
        BehaviorModeler,
        SessionStore,
        BreakRecommender,
        FocusDropPredictor,
    )
    from analytics.behavior_model import BehaviorPattern, StudyPattern, SessionPhase
    _ANALYTICS_AVAILABLE = True
    _NEW_ANALYTICS = True
except ImportError:
    # Analytics not available
    _ANALYTICS_AVAILABLE = False
    _NEW_ANALYTICS = False


def initialize_session_state():
    """
    Initialize all session state variables.
    
    NOTE: This function is Streamlit-specific and is not used by the PyQt version.
    """
    # Only initialize if Streamlit is available and running
    if not _STREAMLIT_AVAILABLE:
        return  # PyQt mode - state_manager not used
    
    # Additional check: verify Streamlit is actually running
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is None:
            return  # Streamlit imported but not running (PyQt mode)
    except (ImportError, RuntimeError, AttributeError):
        return  # Can't check context - assume PyQt mode
    
    # Video processor
    if "video_processor" not in st.session_state:
        from services.video_processor import VideoProcessor
        st.session_state.video_processor = VideoProcessor()
    
    # Focus tracking
    if "focus_history" not in st.session_state:
        st.session_state.focus_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)
    
    if "focus_pct_60s" not in st.session_state:
        st.session_state.focus_pct_60s = 0.0
    
    if "current_focus_score" not in st.session_state:
        st.session_state.current_focus_score = 0.0
    
    if "is_focused" not in st.session_state:
        st.session_state.is_focused = False
    
    # Posture tracking
    if "posture_score" not in st.session_state:
        st.session_state.posture_score = 0.0
    
    if "posture_status" not in st.session_state:
        st.session_state.posture_status = "WAITING"
    
    if "posture_history" not in st.session_state:
        st.session_state.posture_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)
    
    if "posture_alert" not in st.session_state:
        st.session_state.posture_alert = None
    
    # Session tracking
    if "session_start_time" not in st.session_state:
        st.session_state.session_start_time = 0.0
    
    if "session_duration" not in st.session_state:
        st.session_state.session_duration = 0.0
    
    # UI state
    if "show_preview" not in st.session_state:
        st.session_state.show_preview = True
    
    if "preview_image" not in st.session_state:
        st.session_state.preview_image = None
    
    # Analytics state
    if _ANALYTICS_AVAILABLE:
        if "time_series_analyzer" not in st.session_state:
            st.session_state.time_series_analyzer = TimeSeriesAnalyzer()
        
        if "session_store" not in st.session_state:
            st.session_state.session_store = SessionStore()
        
        if "behavior_modeler" not in st.session_state:
            st.session_state.behavior_modeler = BehaviorModeler()
    
    # Emotion detection (optional)
    if "current_emotion" not in st.session_state:
        st.session_state.current_emotion = None
    
    if "emotion_confidence" not in st.session_state:
        st.session_state.emotion_confidence = 0.0
    
    # Chart data caching
    if "chart_data" not in st.session_state:
        st.session_state.chart_data = {}
    
    if "last_chart_update" not in st.session_state:
        st.session_state.last_chart_update = 0.0
