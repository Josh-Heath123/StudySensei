"""
StudySensei - Thin entry point that wires components together.
Refactored with clear separation of concerns.
"""

import time
import cv2
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
from vision.posture import calibrate_posture

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
                
                st.session_state.video_processor.stop()
                st.session_state.session_start_time = 0.0
                st.session_state.preview_image = None
                if st.session_state.preview_placeholder is not None:
                    st.session_state.preview_placeholder.empty()
                    st.session_state.preview_placeholder = None
                if st.session_state.preview_caption_placeholder is not None:
                    st.session_state.preview_caption_placeholder.empty()
                    st.session_state.preview_caption_placeholder = None
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
        with col_toggles[2]:
            if st.session_state.video_processor.enable_posture:
                pose_draw = st.checkbox(
                    "Draw Pose",
                    value=st.session_state.video_processor.draw_pose,
                    key="pose_draw_cb"
                )
                if pose_draw != st.session_state.video_processor.draw_pose:
                    st.session_state.video_processor.toggle_pose_drawing()
                    st.session_state.preview_image = None
                    st.rerun()
        
        # Posture Calibration Button
        if st.session_state.video_processor.enable_posture:
            st.markdown(
                """
                <div style='margin: 1rem 0; padding-top: 1rem; border-top: 0.5px solid #d2d2d7;'></div>
                """,
                unsafe_allow_html=True,
            )
            col_calib = st.columns([2, 1])
            with col_calib[0]:
                st.markdown(
                    "<div style='color: #86868b; font-size: 13px; font-weight: 400; padding-top: 0.5rem;'>Calibrate your baseline posture</div>",
                    unsafe_allow_html=True,
                )
            with col_calib[1]:
                if st.button("Calibrate Posture", key="calibrate_posture_btn"):
                    if st.session_state.session_start_time > 0:
                        result = st.session_state.video_processor.get_latest_result()
                        if result and result.get("pose_landmarks"):
                            pose_landmarks = result["pose_landmarks"]
                            frame_width = int(st.session_state.video_processor.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if st.session_state.video_processor.cap else 480
                            frame_height = int(st.session_state.video_processor.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if st.session_state.video_processor.cap else 360
                            
                            success = calibrate_posture(pose_landmarks, frame_width, frame_height)
                            if success:
                                st.success("Posture calibrated! Your current position is now the baseline.")
                            else:
                                st.error("Calibration failed. Make sure your full upper body is visible.")
                        else:
                            st.warning("Please wait for posture detection to initialize.")
                    else:
                        st.warning("Please start a session first.")
        
        # Experimental Emotion Detection toggle
        if _EMOTION_AVAILABLE:
            st.markdown(
                """
                <div style='margin: 1.5rem 0; padding-top: 1.5rem; border-top: 0.5px solid #d2d2d7;'></div>
                """,
                unsafe_allow_html=True,
            )
            col_emotion = st.columns([3, 1])
            with col_emotion[0]:
                emotion_enabled = st.checkbox(
                    "Emotion Detection",
                    value=st.session_state.video_processor.enable_emotion,
                    key="emotion_enable_cb",
                    help="Experimental feature - accuracy varies by lighting and face visibility. May impact performance."
                )
                if emotion_enabled != st.session_state.video_processor.enable_emotion:
                    success = st.session_state.video_processor.toggle_emotion()
                    if not success and emotion_enabled:
                        st.markdown(
                            """
                            <div style='padding: 1rem 1.25rem; background: #fff3cd; border-radius: 12px; margin: 0.5rem 0;'>
                                <div style='color: #856404; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                                    Failed to enable emotion detection. Check console for details.
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
            with col_emotion[1]:
                if st.session_state.video_processor.enable_emotion:
                    st.markdown(
                        """
                        <div style='padding-top: 0.5rem;'>
                            <span style='color: #86868b; font-size: 12px; font-weight: 300;'>Experimental</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        
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
            
            # Save preview if enabled
            if st.session_state.show_preview and result.get("preview") is not None:
                st.session_state.preview_image = result["preview"]
            
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
    
    # Render UI components
    render_focus_metrics()
    render_posture_metrics()
    render_interactive_analytics()
    render_analytics()
    render_preview()
    
    # Auto-refresh for real-time updates
    time.sleep(0.1)
    st.rerun()


if __name__ == "__main__":
    main()
