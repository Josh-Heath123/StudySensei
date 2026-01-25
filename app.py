"""
StudySensei - Thin entry point that wires components together.
Refactored with clear separation of concerns.
"""

import time
import cv2
import numpy as np
import streamlit as st

# Import from new modular structure
from services.video_processor import VideoProcessor
from services.state_manager import initialize_session_state
from ui.components import (
    render_header,
    render_focus_metrics,
    render_posture_metrics,
    render_interactive_analytics,
    render_analytics,
    render_preview
)
from styles.theme import get_app_styles
from core.focus_history import update_focus_history
# Calibration removed - using simplified grey zone approach

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
    _ANALYTICS_AVAILABLE = True
    _NEW_ANALYTICS = True
except ImportError:
    try:
        from database import DatabaseManager
        from analytics import TimeSeriesAnalyzer
        from behavior import BehaviorModeler
        from ml_predictor import FocusPredictor
        _ANALYTICS_AVAILABLE = True
        _NEW_ANALYTICS = False
    except ImportError:
        _ANALYTICS_AVAILABLE = False
        _NEW_ANALYTICS = False

# Emotion availability
try:
    from vision.emotion import EmotionDetector
    _EMOTION_AVAILABLE = True
except ImportError:
    _EMOTION_AVAILABLE = False


def main() -> None:
    """Main application entry point - wires all components together."""
    st.set_page_config(
        page_title="StudySensei Focus", 
        layout="centered", 
        initial_sidebar_state="collapsed"
    )
    
    # Apply styles
    st.markdown(get_app_styles(), unsafe_allow_html=True)
    
    # Initialize session state
    initialize_session_state()
    
    # FIXED: Initialize memory tracking on app start
    try:
        from utils.memory_manager import initialize_memory_tracking
        initialize_memory_tracking()
    except Exception:
        pass  # Don't crash if memory manager not available
    
    # Render header
    render_header()
    
    # Controls section
    with st.container():
        st.markdown('<div class="card" style="margin-bottom: 3rem;">', unsafe_allow_html=True)
        
        col_controls = st.columns([1, 1, 1])
        with col_controls[0]:
            st.markdown('<div class="start-btn">', unsafe_allow_html=True)
            if st.button("Start", key="start_btn"):
                st.session_state.video_processor.start()
                session_start = time.time()
                st.session_state.session_start_time = session_start
                st.session_state.total_focused_time = 0.0
                st.session_state.total_not_focused_time = 0.0
                st.session_state.focus_history.clear()
                st.session_state.focus_pct_60s = 0.0
                st.session_state.latest_fps = 0.0
                # Initialize frame cleanup counter
                st.session_state.frame_cleanup_counter = 0
                
                # Create new database session (if analytics available)
                if _ANALYTICS_AVAILABLE:
                    if _NEW_ANALYTICS:
                        st.session_state.current_session_id = st.session_state.session_store.create_session(
                            metadata={"app_version": "2.0", "analytics_version": "advanced"}
                        )
                        st.session_state.analyzer.reset()
                        st.session_state.decay_detector.reset()
                        st.session_state.session_stats.reset()
                        st.session_state.behavior_modeler.start_session(session_start)
                        st.session_state.break_recommender.start_session(session_start)
                        st.session_state.ml_predictor.reset()
                        st.session_state.window_metrics = {}
                        st.session_state.break_suggestion = None
                        st.session_state.focus_prediction = None
                        st.session_state.session_phase = None
                    else:
                        st.session_state.current_session_id = st.session_state.db_manager.create_session(
                            metadata={"app_version": "1.0"}
                        )
                        st.session_state.analyzer.reset()
                        st.session_state.behavior_modeler.reset()
                        st.session_state.ml_predictor.reset()
                        st.session_state.window_metrics = {}
                        st.session_state.break_suggestion = None
                else:
                    st.session_state.current_session_id = None
                
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_controls[1]:
            st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
            if st.button("Stop", key="stop_btn"):
                # End database session (if analytics available)
                if _ANALYTICS_AVAILABLE and st.session_state.current_session_id:
                    session_duration = time.time() - st.session_state.session_start_time
                    if _NEW_ANALYTICS:
                        focus_stats = st.session_state.session_stats.get_statistics()
                        session_stats = {
                            'total_duration': session_duration,
                            'avg_focus_score': st.session_state.get('latest_focus_score', 0),
                            'avg_posture_score': st.session_state.get('posture_score', 0),
                            'total_blinks': len([h for h in st.session_state.focus_history if h[1]]),
                            'total_slouch_alerts': len([h for h in st.session_state.posture_history if not h[1]])
                        }
                        st.session_state.session_store.end_session(
                            st.session_state.current_session_id,
                            session_stats,
                            focus_statistics=focus_stats
                        )
                    else:
                        session_stats = {
                            'total_duration': session_duration,
                            'avg_focus_score': st.session_state.get('latest_focus_score', 0),
                            'avg_posture_score': st.session_state.get('posture_score', 0),
                            'total_blinks': len([h for h in st.session_state.focus_history if h[1]]),
                            'total_slouch_alerts': len([h for h in st.session_state.posture_history if not h[1]])
                        }
                        st.session_state.db_manager.end_session(
                            st.session_state.current_session_id,
                            session_stats
                        )
                    st.session_state.current_session_id = None
                
                # FIXED: Comprehensive cleanup on stop to prevent memory leaks
                st.session_state.video_processor.stop()
                
                # Perform aggressive memory cleanup
                try:
                    from utils.memory_manager import comprehensive_cleanup
                    comprehensive_cleanup(
                        video_processor=st.session_state.video_processor,
                        aggressive=True  # Aggressive cleanup on stop
                    )
                except Exception:
                    pass  # Don't crash on cleanup errors
                
                st.session_state.session_start_time = 0.0
                st.session_state.preview_image = None
                st.session_state.frame_cleanup_counter = 0
                
                # Clear placeholders but keep the objects (don't set to None)
                # This prevents recreation and flickering
                if "preview_placeholder" in st.session_state:
                    st.session_state.preview_placeholder.empty()
                if "preview_caption_placeholder" in st.session_state:
                    st.session_state.preview_caption_placeholder.empty()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_controls[2]:
            st.markdown('<div class="toggle-btn">', unsafe_allow_html=True)
            if st.button("Toggle Mesh", key="toggle_mesh"):
                st.session_state.video_processor.toggle_landmarks()
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Additional toggles
        st.markdown(
            """
            <div style='margin: 1.5rem 0; padding-top: 1.5rem; border-top: 0.5px solid #d2d2d7;'></div>
            """,
            unsafe_allow_html=True,
        )
        col_toggles = st.columns([2, 2, 1])
        with col_toggles[0]:
            st.session_state.show_preview = st.checkbox(
                "Show Preview", 
                value=st.session_state.show_preview,
                key="show_preview_cb"
            )
        with col_toggles[1]:
            posture_enabled = st.checkbox(
                "Posture Detection",
                value=st.session_state.video_processor.enable_posture,
                key="posture_enable_cb"
            )
            if posture_enabled != st.session_state.video_processor.enable_posture:
                st.session_state.video_processor.toggle_posture()
                st.session_state.preview_image = None
                st.rerun()
        # Additional toggles row - ALWAYS render to maintain consistent widget structure
        col_toggles2 = st.columns([2, 1])
        with col_toggles2[0]:
            # Always render checkbox, but disable it if posture is not enabled
            # This prevents delta path errors from conditional widget creation
            pose_draw = st.checkbox(
                "Draw Pose",
                value=st.session_state.video_processor.draw_pose if st.session_state.video_processor.enable_posture else False,
                key="pose_draw_cb",
                disabled=not st.session_state.video_processor.enable_posture
            )
            if st.session_state.video_processor.enable_posture and pose_draw != st.session_state.video_processor.draw_pose:
                st.session_state.video_processor.toggle_pose_drawing()
                st.session_state.preview_image = None
                st.rerun()
        
        # Experimental Emotion Detection toggle - ALWAYS render container
        # FIXED: Always render same structure to prevent delta path errors
        if st.session_state.get("emotion_placeholder") is None:
            st.session_state.emotion_placeholder = st.empty()
        
        with st.session_state.emotion_placeholder.container():
            # ALWAYS render separator to maintain widget count
            st.markdown(
                """
                <div style='margin: 1.5rem 0; padding-top: 1.5rem; border-top: 0.5px solid #d2d2d7;'></div>
                """,
                unsafe_allow_html=True,
            )
            # ALWAYS render columns to maintain widget structure
            col_emotion = st.columns([3, 1])
            with col_emotion[0]:
                # ALWAYS render checkbox (disabled if emotion not available)
                emotion_enabled = st.checkbox(
                    "Emotion Detection",
                    value=st.session_state.video_processor.enable_emotion if _EMOTION_AVAILABLE else False,
                    key="emotion_enable_cb",
                    disabled=not _EMOTION_AVAILABLE,
                    help="Experimental feature - accuracy varies by lighting and face visibility. May impact performance." if _EMOTION_AVAILABLE else "Emotion detection not available"
                )
                # FIXED: Always render error message to maintain widget count
                # Use st.markdown() directly but always render (empty div if no error)
                error_message = None
                if _EMOTION_AVAILABLE and emotion_enabled != st.session_state.video_processor.enable_emotion:
                    success = st.session_state.video_processor.toggle_emotion()
                    if not success and emotion_enabled:
                        error_message = "Failed to enable emotion detection. Check console for details."
                
                # ALWAYS render error message widget (empty div if no error) to maintain widget count
                if error_message:
                    st.markdown(
                        f"""
                        <div style='padding: 1rem 1.25rem; background: #fff3cd; border-radius: 12px; margin: 0.5rem 0;'>
                            <div style='color: #856404; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                                {error_message}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    # Always render empty div to maintain widget structure
                    st.markdown("<div></div>", unsafe_allow_html=True)
            with col_emotion[1]:
                # ALWAYS render this section (empty if not enabled)
                if _EMOTION_AVAILABLE and st.session_state.video_processor.enable_emotion:
                    st.markdown(
                        """
                        <div style='padding-top: 0.5rem;'>
                            <span style='color: #86868b; font-size: 12px; font-weight: 300;'>Experimental</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    # Empty div to maintain widget structure
                    st.markdown("<div></div>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # Process video results and update state
    if st.session_state.session_start_time > 0:
        result = st.session_state.video_processor.get_latest_result()
        
        if result:
            # Update session state with latest results
            focused = result["focused"]
            score = result.get("score", 0.0)
            elapsed = result.get("elapsed", 0.0)
            fps = result.get("fps", 0.0)
            
            st.session_state.latest_status_text = "FOCUSED" if focused else "DISTRACTED"
            st.session_state.latest_focus_score = score
            st.session_state.latest_fps = fps if fps > 0 else st.session_state.latest_fps
            
            # Update counters and history
            if st.session_state.session_start_time > 0:
                if focused:
                    st.session_state.total_focused_time += elapsed
                else:
                    st.session_state.total_not_focused_time += elapsed
                
                # Update sliding window history
                update_focus_history(focused, result["timestamp"])
            
            # FIXED: Save preview with proper validation and copy to prevent reference issues
            if st.session_state.show_preview and result.get("preview") is not None:
                preview_frame = result["preview"]
                
                # Use safe validation utility
                from utils.image_utils import validate_image
                
                if validate_image(preview_frame):
                    # Create a copy to prevent reference issues with Streamlit's cache
                    # This prevents MediaFileStorageError from stale references
                    try:
                        st.session_state.preview_image = preview_frame.copy()
                    except Exception:
                        # If copy fails, try to use original (fallback)
                        st.session_state.preview_image = preview_frame
                else:
                    # Invalid image - clear it
                    st.session_state.preview_image = None
            
            # FIXED: Frame-based memory cleanup (every 50 frames to prevent accumulation)
            frame_count = result.get("frame_count", 0) if hasattr(result, "get") else 0
            if "frame_cleanup_counter" not in st.session_state:
                st.session_state.frame_cleanup_counter = 0
            
            st.session_state.frame_cleanup_counter += 1
            if st.session_state.frame_cleanup_counter >= 50:  # Every 50 frames
                try:
                    from utils.memory_manager import manage_frame_memory, force_garbage_collection
                    manage_frame_memory()
                    force_garbage_collection(threshold=50)  # Trigger GC every 50 frames
                    st.session_state.frame_cleanup_counter = 0
                except Exception:
                    pass  # Don't crash on cleanup errors
            
            # Update posture state
            if result.get("posture") and result["posture"]:
                posture_data = result["posture"]
                st.session_state.posture_score = posture_data["score"]
                st.session_state.posture_status = "Good Posture" if posture_data["good_posture"] else "Needs Adjustment"
                st.session_state.posture_alert = posture_data.get("alert_message")
                st.session_state.posture_neck_angle = posture_data.get("neck_angle", 0.0)
                st.session_state.posture_shoulder_roll = posture_data.get("shoulder_roll", 0.0)
                
                if st.session_state.session_start_time > 0:
                    st.session_state.posture_history.append((
                        result["timestamp"],
                        posture_data["good_posture"]
                    ))
            else:
                st.session_state.posture_score = 0.0
                st.session_state.posture_status = "WAITING"
                st.session_state.posture_alert = None
            
            # Update emotion state
            if result.get("emotion") and result["emotion"]:
                emotion_data = result["emotion"]
                st.session_state.current_emotion = emotion_data.get("state")
                st.session_state.emotion_confidence = emotion_data.get("confidence", 0.0)
            else:
                st.session_state.current_emotion = None
                st.session_state.emotion_confidence = 0.0
            
            # Analytics integration (if available) - moved to services/analytics_processor.py would be ideal
            if _ANALYTICS_AVAILABLE and st.session_state.current_session_id and st.session_state.session_start_time > 0:
                timestamp = result["timestamp"]
                focus_score = score
                posture_score = st.session_state.get("posture_score", 0.0)
                gaze_confidence = result.get("gaze_confidence", 0.0)
                is_slouching = result.get("posture", {}).get("slouching", False) if result.get("posture") else False
                is_present = focused or score > 0
                session_duration = timestamp - st.session_state.session_start_time
                
                if _NEW_ANALYTICS:
                    try:
                        st.session_state.analyzer.add_data_point(timestamp, focus_score, posture_score)
                        st.session_state.decay_detector.update(timestamp, focus_score)
                        st.session_state.session_stats.add_point(timestamp, focus_score, posture_score)
                        
                        emotion_score = 0.5
                        if st.session_state.get("current_emotion"):
                            emotion = st.session_state.current_emotion
                            if emotion == "neutral":
                                emotion_score = 0.7
                            elif emotion == "frustrated":
                                emotion_score = 0.3
                            elif emotion == "tired":
                                emotion_score = 0.4
                        
                        behavior_result = st.session_state.behavior_modeler.update(
                            timestamp, gaze_confidence, posture_score, emotion_score, is_slouching, is_present
                        )
                        computed_focus = behavior_result.get("focus_score", focus_score)
                        
                        if st.session_state.get("current_emotion") and st.session_state.video_processor.enable_emotion:
                            emotion = st.session_state.current_emotion
                            if emotion == "frustrated":
                                computed_focus = max(0, computed_focus * 0.9)
                            elif emotion == "tired":
                                computed_focus = max(0, computed_focus * 0.95)
                        
                        session_phase = behavior_result.get("session_phase")
                        st.session_state.session_phase = session_phase
                        
                        if int(timestamp) % 2 == 0:
                            try:
                                st.session_state.session_store.insert_time_series_point(
                                    st.session_state.current_session_id,
                                    timestamp,
                                    {
                                        'focus_score': computed_focus,
                                        'posture_score': posture_score,
                                        'gaze_confidence': gaze_confidence,
                                        'blink_detected': result.get("blink_detected", False),
                                        'slouching': is_slouching,
                                        'text_neck': result.get("posture", {}).get("text_neck", False) if result.get("posture") else False,
                                        'fps': fps
                                    }
                                )
                            except Exception:
                                pass
                        
                        if int(timestamp) % 5 == 0:
                            try:
                                wm = st.session_state.analyzer.get_all_window_metrics(timestamp)
                                st.session_state.window_metrics = wm
                                focus_trend = wm.get("10min", {}).get("trend", 0.0)
                                baseline_focus = wm.get("10min", {}).get("mean", focus_score)
                                
                                break_rec = st.session_state.break_recommender.suggest_break(
                                    timestamp, focus_trend, session_phase, session_duration,
                                    computed_focus, baseline_focus
                                )
                                if break_rec:
                                    st.session_state.break_suggestion = break_rec.get("message")
                            except Exception:
                                pass
                        
                        if int(timestamp) % 10 == 0:
                            try:
                                recent_scores = [f for _, f in st.session_state.focus_history[-20:]] if len(st.session_state.focus_history) >= 20 else [focus_score]
                                volatility = st.session_state.window_metrics.get("10min", {}).get("volatility", 0.0)
                                
                                prediction = st.session_state.ml_predictor.predict(
                                    recent_scores, posture_score, session_duration, volatility
                                )
                                if prediction:
                                    st.session_state.focus_prediction = prediction
                                    st.session_state.ml_predictor.add_observation(
                                        timestamp, computed_focus, posture_score, session_duration, volatility, recent_scores
                                    )
                            except Exception:
                                pass
                    except Exception:
                        pass
                else:
                    # Old analytics (backward compatibility)
                    if int(timestamp) % 2 == 0:
                        try:
                            st.session_state.db_manager.insert_time_series_point(
                                st.session_state.current_session_id,
                                timestamp,
                                {
                                    'focus_score': focus_score,
                                    'posture_score': posture_score,
                                    'gaze_confidence': gaze_confidence,
                                    'blink_detected': result.get("blink_detected", False),
                                    'slouching': is_slouching,
                                    'text_neck': result.get("posture", {}).get("text_neck", False) if result.get("posture") else False,
                                    'fps': fps
                                }
                            )
                        except Exception:
                            pass
                    
                    try:
                        st.session_state.analyzer.add_data_point(timestamp, focus_score, posture_score)
                        behavior_pattern = st.session_state.behavior_modeler.update(
                            timestamp, focus_score, posture_score, is_slouching, is_present
                        )
                        if behavior_pattern:
                            try:
                                st.session_state.db_manager.insert_behavior_pattern(
                                    st.session_state.current_session_id,
                                    behavior_pattern.pattern_type.value,
                                    behavior_pattern.start_time,
                                    behavior_pattern.end_time,
                                    behavior_pattern.metadata
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass
                    
                    try:
                        st.session_state.ml_predictor.add_observation(
                            timestamp, focus_score, posture_score, gaze_confidence
                        )
                    except Exception:
                        pass
                    
                    if int(timestamp) % 5 == 0:
                        try:
                            st.session_state.window_metrics = st.session_state.analyzer.get_all_window_metrics(timestamp)
                        except Exception:
                            pass
                    
                    if int(timestamp) % 30 == 0:
                        try:
                            st.session_state.break_suggestion = st.session_state.behavior_modeler.suggest_break(timestamp)
                        except Exception:
                            pass
    
    # UI Update Throttling: Prevent rapid DOM updates that cause delta path errors
    current_time = time.time()
    last_ui_update = st.session_state.get("last_ui_update", 0.0)
    ui_update_interval = st.session_state.get("ui_update_interval", 0.5)  # Max 2 updates/sec
    
    # FIXED: Comprehensive memory leak prevention
    # Perform periodic memory cleanup every 30 seconds
    last_memory_cleanup = st.session_state.get("last_memory_cleanup", 0.0)
    if current_time - last_memory_cleanup > 30.0:  # Clean up every 30 seconds
        try:
            from utils.memory_manager import comprehensive_cleanup, initialize_memory_tracking
            initialize_memory_tracking()
            
            # Perform comprehensive cleanup
            stats = comprehensive_cleanup(
                video_processor=st.session_state.get("video_processor"),
                aggressive=False  # Normal cleanup
            )
            
            st.session_state.last_memory_cleanup = current_time
            
            # Log cleanup stats (only if significant)
            if stats.get("session_state_removed", 0) > 0 or stats.get("frames_cleared", 0) > 0:
                if st.session_state.get("ui_error_count", 0) <= 3:
                    print(f"🧹 Memory cleanup: {stats['session_state_removed']} items removed, "
                          f"{stats['frames_cleared']} frames cleared")
        except Exception:
            pass  # Don't crash on cleanup errors
    
    # FIXED: Periodic image cache cleanup to prevent MediaFileStorageError
    # Clean up old image references every 60 seconds
    last_cleanup = st.session_state.get("last_image_cleanup", 0.0)
    if current_time - last_cleanup > 60.0:  # Clean up every 60 seconds
        try:
            from utils.image_utils import cleanup_image_cache
            cleanup_image_cache()
            st.session_state.last_image_cleanup = current_time
        except Exception:
            pass  # Don't crash on cleanup errors
    
    # Only update UI if enough time has passed (throttling)
    should_update_ui = (current_time - last_ui_update) >= ui_update_interval
    
    # CRITICAL: Always render UI in FIXED order with FIXED element count
    # This prevents delta path index errors by ensuring consistent widget structure
    try:
        # Initialize ALL placeholders ONCE - always exist, even if empty
        # This ensures fixed UI element count regardless of content
        if st.session_state.get("analytics_section_placeholder") is None:
            st.session_state.analytics_section_placeholder = st.empty()
        if st.session_state.get("calibration_message_placeholder") is None:
            st.session_state.calibration_message_placeholder = st.empty()
        
        # FIXED: Render UI components in fixed order with persistent placeholders
        # This prevents flickering and layout shifts
        # CRITICAL: Always render in same order, even if content is empty
        # This ensures Streamlit's widget indices remain stable
        # FIXED: Only render if enough time has passed (throttling prevents duplicates)
        
        # 1. Focus metrics (always rendered to prevent flickering) - SINGLE INSTANCE
        render_focus_metrics()
        
        # 2. Posture metrics (always rendered to prevent flickering) - SINGLE INSTANCE
        render_posture_metrics()
        
        # 3. Webcam feed (always rendered to prevent flickering) - SINGLE INSTANCE
        render_preview()
        
        # Analytics dashboard - ALWAYS render placeholder to maintain fixed structure
        # Analytics data collection runs in background always
        # Expander controls visibility only - data is always being collected
        # CRITICAL: Always create the expander in the same position to prevent delta path errors
        # FIXED: Use single container to prevent duplicate boxes
        # FIXED: Always render expander (even if empty) to maintain widget count
        if st.session_state.get("analytics_section_placeholder") is None:
            st.session_state.analytics_section_placeholder = st.empty()
        
        with st.session_state.analytics_section_placeholder.container():
            # Always create expander in the same position - never conditionally create
            # This ensures the expander widget is always at the same index
            # FIXED: Single expander instance prevents duplicates
            # Note: key parameter not supported in older Streamlit versions
            with st.expander("Analytics Dashboard", expanded=False):
                # Analytics always runs in background - expander only controls visibility
                # FIXED: Render in single container to prevent duplicate boxes
                # FIXED: Always render content (even if empty) to maintain widget structure
                try:
                    # Both functions render in the same expander - no duplicates
                    render_interactive_analytics()
                    render_analytics()
                except Exception as e:
                    # Error boundary for analytics section
                    st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
                    if st.session_state.ui_error_count <= 3:
                        print(f"Error rendering analytics: {e}")
                    # Render empty content to maintain widget structure
                    st.markdown("<div></div>", unsafe_allow_html=True)
        
        # Update last UI update timestamp only if we actually rendered
        if should_update_ui:
            st.session_state.last_ui_update = current_time
    except Exception as e:
        # Global error boundary for UI rendering - don't crash, just log
        st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
        if st.session_state.ui_error_count <= 3:
            print(f"Critical UI rendering error: {e}")
        # Reset error count after a delay to allow recovery
        if st.session_state.ui_error_count > 10:
            st.session_state.ui_error_count = 0
    
    # Auto-refresh for real-time updates - reduced frequency to prevent delta path errors
    # Use adaptive sleep based on update interval
    sleep_time = max(0.1, ui_update_interval * 0.5)  # Sleep for half the update interval
    time.sleep(sleep_time)
    
    # Only rerun if we're in an active session or need to update UI
    if st.session_state.session_start_time > 0 or should_update_ui:
        try:
            st.rerun()
        except Exception as e:
            # Handle rerun errors gracefully (e.g., during hot reload)
            if st.session_state.get("ui_error_count", 0) <= 3:
                print(f"Error during rerun (non-critical): {e}")
            # Don't crash - just wait and try again next cycle
            time.sleep(0.5)


if __name__ == "__main__":
    main()
