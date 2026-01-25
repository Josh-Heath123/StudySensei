"""State management and initialization for StudySensei."""

import streamlit as st
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
    try:
        from database import DatabaseManager
        from analytics import TimeSeriesAnalyzer, WindowMetrics
        from behavior import BehaviorModeler, BehaviorPattern, PatternType
        from ml_predictor import FocusPredictor
        _ANALYTICS_AVAILABLE = True
        _NEW_ANALYTICS = False
    except ImportError:
        DatabaseManager = None
        TimeSeriesAnalyzer = None
        WindowMetrics = None
        BehaviorModeler = None
        BehaviorPattern = None
        PatternType = None
        FocusPredictor = None
        _ANALYTICS_AVAILABLE = False
        _NEW_ANALYTICS = False


def initialize_session_state():
    """Initialize all session state variables."""
    # Video processor
    if "video_processor" not in st.session_state:
        from services.video_processor import VideoProcessor
        st.session_state.video_processor = VideoProcessor()
    
    # Basic session state
    if "session_start_time" not in st.session_state:
        st.session_state.session_start_time = 0.0
    if "total_focused_time" not in st.session_state:
        st.session_state.total_focused_time = 0.0
    if "total_not_focused_time" not in st.session_state:
        st.session_state.total_not_focused_time = 0.0
    if "focus_pct_60s" not in st.session_state:
        st.session_state.focus_pct_60s = 0.0
    if "latest_status_text" not in st.session_state:
        st.session_state.latest_status_text = "WAITING"
    if "show_preview" not in st.session_state:
        st.session_state.show_preview = True
    if "latest_fps" not in st.session_state:
        st.session_state.latest_fps = 0.0
    if "preview_image" not in st.session_state:
        st.session_state.preview_image = None
    # Clear any invalid preview images on initialization
    if st.session_state.get("preview_image") is not None:
        preview = st.session_state.preview_image
        if not isinstance(preview, np.ndarray):
            st.session_state.preview_image = None
        elif len(preview.shape) < 2 or preview.size == 0:
            st.session_state.preview_image = None
        elif preview.shape[0] == 0 or preview.shape[1] == 0:
            st.session_state.preview_image = None
    
    # Initialize persistent placeholders ONCE to prevent flickering
    if "preview_placeholder" not in st.session_state:
        st.session_state.preview_placeholder = None
    if "preview_caption_placeholder" not in st.session_state:
        st.session_state.preview_caption_placeholder = None
    if "focus_metrics_placeholder" not in st.session_state:
        st.session_state.focus_metrics_placeholder = None
    if "posture_metrics_placeholder" not in st.session_state:
        st.session_state.posture_metrics_placeholder = None
    if "analytics_placeholder" not in st.session_state:
        st.session_state.analytics_placeholder = None
    if "analytics_section_placeholder" not in st.session_state:
        st.session_state.analytics_section_placeholder = None
    if "emotion_placeholder" not in st.session_state:
        st.session_state.emotion_placeholder = None
    if "calibration_message_placeholder" not in st.session_state:
        st.session_state.calibration_message_placeholder = None
    if "analytics_content_placeholder" not in st.session_state:
        st.session_state.analytics_content_placeholder = None
    
    # UI update throttling
    if "last_ui_update" not in st.session_state:
        st.session_state.last_ui_update = 0.0
    if "ui_update_interval" not in st.session_state:
        st.session_state.ui_update_interval = 0.5
    if "ui_update_queue" not in st.session_state:
        st.session_state.ui_update_queue = []
    if "ui_error_count" not in st.session_state:
        st.session_state.ui_error_count = 0
    
    # Image cache cleanup tracking
    if "last_image_cleanup" not in st.session_state:
        st.session_state.last_image_cleanup = 0.0
    # Memory management tracking
    if "last_memory_cleanup" not in st.session_state:
        st.session_state.last_memory_cleanup = 0.0
    if "memory_tracker" not in st.session_state:
        st.session_state.memory_tracker = {
            "recent": [],
            "last_cleanup": 0.0,
            "cleanup_count": 0
        }
    if "gc_counter" not in st.session_state:
        st.session_state.gc_counter = 0
    if "last_cache_cleanup" not in st.session_state:
        st.session_state.last_cache_cleanup = 0.0
    # Frame-based cleanup counter
    if "frame_cleanup_counter" not in st.session_state:
        st.session_state.frame_cleanup_counter = 0
    # UI update throttling timestamps
    if "focus_metrics_last_update" not in st.session_state:
        st.session_state.focus_metrics_last_update = 0.0
    if "analytics_last_update" not in st.session_state:
        st.session_state.analytics_last_update = 0.0
    if "analytics_content_last_update" not in st.session_state:
        st.session_state.analytics_content_last_update = 0.0
    if "emotion_error_message" not in st.session_state:
        st.session_state.emotion_error_message = None
    
    # Break suggestion tracking
    if "break_suggestion_shown" not in st.session_state:
        st.session_state.break_suggestion_shown = False
    
    # Focus history
    if "focus_history" not in st.session_state:
        st.session_state.focus_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)
    
    # Posture Detection state
    if "posture_score" not in st.session_state:
        st.session_state.posture_score = 0.0
    if "posture_status" not in st.session_state:
        st.session_state.posture_status = "WAITING"
    if "posture_history" not in st.session_state:
        st.session_state.posture_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)
    if "posture_alert" not in st.session_state:
        st.session_state.posture_alert = None
    
    # Experimental Emotion Detection state
    if "current_emotion" not in st.session_state:
        st.session_state.current_emotion = None
    if "emotion_confidence" not in st.session_state:
        st.session_state.emotion_confidence = 0.0
    
    # Analytics and Behavior Modeling initialization (optional)
    if _ANALYTICS_AVAILABLE:
        if _NEW_ANALYTICS:
            if "session_store" not in st.session_state:
                st.session_state.session_store = SessionStore()
                st.session_state.session_store.initialize()
            if "analyzer" not in st.session_state:
                st.session_state.analyzer = TimeSeriesAnalyzer()
            if "decay_detector" not in st.session_state:
                st.session_state.decay_detector = FocusDecayDetector()
            if "session_stats" not in st.session_state:
                st.session_state.session_stats = SessionStatistics()
            if "behavior_modeler" not in st.session_state:
                st.session_state.behavior_modeler = BehaviorModeler()
            if "break_recommender" not in st.session_state:
                st.session_state.break_recommender = BreakRecommender()
            if "ml_predictor" not in st.session_state:
                st.session_state.ml_predictor = FocusDropPredictor()
            if "current_session_id" not in st.session_state:
                st.session_state.current_session_id = None
            if "window_metrics" not in st.session_state:
                st.session_state.window_metrics = {}
            if "break_suggestion" not in st.session_state:
                st.session_state.break_suggestion = None
            if "focus_prediction" not in st.session_state:
                st.session_state.focus_prediction = None
            if "session_phase" not in st.session_state:
                st.session_state.session_phase = None
        else:
            if "db_manager" not in st.session_state:
                st.session_state.db_manager = DatabaseManager()
            if "analyzer" not in st.session_state:
                st.session_state.analyzer = TimeSeriesAnalyzer()
            if "behavior_modeler" not in st.session_state:
                st.session_state.behavior_modeler = BehaviorModeler()
            if "ml_predictor" not in st.session_state:
                st.session_state.ml_predictor = FocusPredictor()
            if "current_session_id" not in st.session_state:
                st.session_state.current_session_id = None
            if "window_metrics" not in st.session_state:
                st.session_state.window_metrics = {}
            if "break_suggestion" not in st.session_state:
                st.session_state.break_suggestion = None
