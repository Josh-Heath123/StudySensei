"""UI components for StudySensei - all render functions."""

import time
import numpy as np
import streamlit as st

# Chart libraries (optional)
try:
    import pandas as pd
except ImportError:
    pd = None

# Analytics availability check
try:
    from analytics import TimeSeriesAnalyzer
    _ANALYTICS_AVAILABLE = True
    try:
        from analytics.behavior_model import BehaviorPattern, StudyPattern, SessionPhase
        _NEW_ANALYTICS = True
    except ImportError:
        _NEW_ANALYTICS = False
except ImportError:
    _ANALYTICS_AVAILABLE = False
    _NEW_ANALYTICS = False

# Emotion availability - check via video processor
_EMOTION_AVAILABLE = hasattr(st.session_state.get("video_processor", None), "emotion_detector") if "video_processor" in st.session_state else False

from utils.helpers import format_time


def render_focus_metrics() -> None:
    """Minimal focus display with live 60s metric."""
    focus_pct_60 = st.session_state.get("focus_pct_60s", 0.0)
    status_text = st.session_state.get("latest_status_text", "WAITING")
    is_focused = status_text == "FOCUSED"

    # Apple-style: subtle colors, single accent
    circle_color = "#007AFF"
    track_color = "#e5e5ea"
    status_color = "#1d1d1f" if is_focused else "#86868b"

    # SVG progress ring
    progress = max(0.0, min(1.0, focus_pct_60 / 100.0))
    r = 85
    circumference = 2 * 3.141592653589793 * r
    stroke_dasharray = f"{progress * circumference:.3f} {circumference:.3f}"

    st.markdown(
        f"""
        <div style='display:flex; justify-content:center; margin: 2rem 0 1.5rem; position: relative;'>
            <svg width="200" height="200" style="transform: rotate(-90deg);">
                 <circle cx="100" cy="100" r="{r}" stroke="{track_color}" stroke-width="6" fill="transparent" opacity="0.3"/>
                 <circle cx="100" cy="100" r="{r}" stroke="{circle_color}" stroke-width="6" 
                        fill="transparent" stroke-dasharray="{stroke_dasharray}" 
                        stroke-linecap="round" opacity="0.9"/>
            </svg>
            <div style='
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                color: #1d1d1f;
                font-size: 56px;
                font-weight: 300;
                letter-spacing: -1px;
            '>
                {focus_pct_60:.0f}%
            </div>
        </div>
        <div style='text-align:center; margin-bottom: 2rem; font-size: 20px; font-weight: 400; color: {status_color}; letter-spacing: 0.3px;'>
            {status_text}
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Experimental: Emotion indicator (if enabled)
    try:
        emotion_available = hasattr(st.session_state.get("video_processor", None), "emotion_detector") and st.session_state.video_processor.enable_emotion
    except (AttributeError, KeyError):
        emotion_available = False
    
    if emotion_available:
        emotion = st.session_state.get("current_emotion")
        emotion_conf = st.session_state.get("emotion_confidence", 0.0)
        
        if emotion:
            emotion_colors = {
                "neutral": "#86868b",
                "frustrated": "#ff3b30",
                "tired": "#ff9500",
            }
            emotion_color = emotion_colors.get(emotion, "#86868b")
            conf_warning = ""
            if emotion_conf < 0.7:
                conf_warning = f" <span style='color:#86868b; font-size: 11px; font-weight: 300;'>({emotion_conf*100:.0f}%)</span>"
            
            st.markdown(
                f"""
                <div style='text-align:center; margin: 1.5rem 0; padding: 1rem; background: #f5f5f7; border-radius: 12px;'>
                    <div style='font-size: 15px; font-weight: 400; color: {emotion_color}; margin-bottom: 0.5rem; letter-spacing: 0.3px;'>
                        {emotion.capitalize()}{conf_warning}
                    </div>
                    <div style='color:#86868b; font-size: 12px; font-weight: 300; letter-spacing: 0.2px;'>Experimental</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    session_duration = 0.0
    if st.session_state.get("session_start_time", 0) > 0:
        session_duration = time.time() - st.session_state.session_start_time

    fps = st.session_state.get("latest_fps", 0.0)
    
    st.markdown(
        f"""
        <div style='display: flex; justify-content: center; gap: 2rem; margin: 2rem 0;'>
            <div style='text-align:center;'>
                <div style='color:#86868b; font-size: 13px; font-weight: 400; letter-spacing: 0.3px; margin-bottom: 0.5rem;'>SESSION</div>
                <div style='color:#1d1d1f; font-size: 20px; font-weight: 300; letter-spacing: -0.3px;'>{format_time(session_duration)}</div>
            </div>
            <div style='text-align:center;'>
                <div style='color:#86868b; font-size: 13px; font-weight: 400; letter-spacing: 0.3px; margin-bottom: 0.5rem;'>FPS</div>
                <div style='color:#1d1d1f; font-size: 20px; font-weight: 300; letter-spacing: -0.3px;'>{fps:.1f}</div>
            </div>
            <div style='text-align:center;'>
                <div style='color:#86868b; font-size: 13px; font-weight: 400; letter-spacing: 0.3px; margin-bottom: 0.5rem;'>WINDOW</div>
                <div style='color:#1d1d1f; font-size: 20px; font-weight: 300; letter-spacing: -0.3px;'>60s</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_posture_metrics() -> None:
    """Render posture status and score with alerts."""
    posture_score = st.session_state.get("posture_score", 0.0)
    posture_status = st.session_state.get("posture_status", "WAITING")
    posture_alert = st.session_state.get("posture_alert")
    
    if not st.session_state.get("video_processor") or not st.session_state.video_processor.enable_posture:
        return
    
    if st.session_state.get("session_start_time", 0) == 0:
        return
    
    is_good = posture_status == "Good Posture"
    status_color = "#1d1d1f" if is_good else "#86868b"
    
    st.markdown(
        f"""
        <div style='text-align:center; margin: 2rem 0; padding: 1.5rem; background: #ffffff; border-radius: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);'>
            <div style='font-size: 17px; font-weight: 400; color: {status_color}; margin-bottom: 0.75rem; letter-spacing: 0.3px;'>
                {posture_status}
            </div>
            <div style='font-size: 36px; font-weight: 300; color: #1d1d1f; letter-spacing: -0.5px;'>
                {posture_score:.0f}%
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    if posture_alert:
        st.markdown(
            f"""
            <div style='padding: 1rem 1.25rem; background: #fff3cd; border-radius: 12px; border: none; margin: 1rem 0;'>
                <div style='color: #856404; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                    {posture_alert}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_interactive_analytics() -> None:
    """Optimized interactive analytics dashboard with throttled updates."""
    if not _ANALYTICS_AVAILABLE:
        return
    if st.session_state.get("session_start_time", 0) == 0:
        return
    
    current_fps = st.session_state.get("latest_fps", 0.0)
    if current_fps > 0 and current_fps < 15.0:
        return
    
    if "chart_data" not in st.session_state:
        st.session_state.chart_data = {
            "focus_scores": np.array([], dtype=np.float32),
            "posture_scores": np.array([], dtype=np.float32),
            "timestamps": np.array([], dtype=np.float32),
            "last_chart_update": 0.0,
        }
    
    current_time = time.time()
    last_update = st.session_state.chart_data.get("last_chart_update", 0.0)
    update_interval = 5.0
    
    if current_time - last_update >= update_interval:
        if st.session_state.get("latest_focus_score") is not None:
            focus_score = float(st.session_state.get("latest_focus_score", 0))
            posture_score = float(st.session_state.get("posture_score", 0))
            
            st.session_state.chart_data["focus_scores"] = np.append(
                st.session_state.chart_data["focus_scores"], focus_score
            )[-100:]
            st.session_state.chart_data["posture_scores"] = np.append(
                st.session_state.chart_data["posture_scores"], posture_score
            )[-100:]
            st.session_state.chart_data["timestamps"] = np.append(
                st.session_state.chart_data["timestamps"], current_time
            )[-100:]
            
            st.session_state.chart_data["last_chart_update"] = current_time
    
    data_length = len(st.session_state.chart_data["timestamps"])
    if data_length < 2:
        return
    
    focus_scores = st.session_state.chart_data["focus_scores"]
    posture_scores = st.session_state.chart_data["posture_scores"]
    
    if "chart_stats" not in st.session_state or current_time - last_update >= update_interval:
        st.session_state.chart_stats = {
            "focus_mean": float(np.mean(focus_scores)) if len(focus_scores) > 0 else 0.0,
            "focus_std": float(np.std(focus_scores)) if len(focus_scores) > 0 else 0.0,
            "posture_mean": float(np.mean(posture_scores)) if len(posture_scores) > 0 else 0.0,
        }
    
    stats = st.session_state.chart_stats
    
    st.markdown(
        """
        <div style='margin: 2rem 0 1rem; padding: 1.5rem; background: #ffffff; border-radius: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);'>
            <div style='font-size: 17px; font-weight: 400; color: #1d1d1f; margin-bottom: 1rem; text-align: center; letter-spacing: 0.3px;'>
                Analytics Dashboard
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    col_metrics = st.columns(3)
    with col_metrics[0]:
        st.metric("Focus Avg", f"{stats['focus_mean']:.1f}%", f"±{stats['focus_std']:.1f}%")
    with col_metrics[1]:
        st.metric("Posture Avg", f"{stats['posture_mean']:.1f}%")
    with col_metrics[2]:
        st.metric("Data Points", f"{data_length}/100")
    
    chart_type = st.radio(
        "Chart Type",
        ["Focus Trend", "Posture Trend", "None"],
        horizontal=True,
        key="chart_type_selector",
        index=2
    )
    
    if chart_type == "Focus Trend" and data_length >= 2:
        if pd is not None:
            chart_df = pd.DataFrame({"Focus": focus_scores})
            st.line_chart(chart_df, height=250, width='stretch')
        else:
            st.write(f"Focus trend: {stats['focus_mean']:.1f}% average")
    
    elif chart_type == "Posture Trend" and data_length >= 2:
        if pd is not None:
            chart_df = pd.DataFrame({"Posture": posture_scores})
            st.line_chart(chart_df, height=250, width='stretch')
        else:
            st.write(f"Posture trend: {stats['posture_mean']:.1f}% average")
    
    if current_time - last_update < update_interval:
        time_until_update = update_interval - (current_time - last_update)
        st.caption(f"Next chart update in {time_until_update:.1f}s")


def render_analytics() -> None:
    """Render advanced analytics: trends, predictions, session phase, break suggestions."""
    if not _ANALYTICS_AVAILABLE:
        return
    if st.session_state.get("session_start_time", 0) == 0:
        return
    
    if _NEW_ANALYTICS:
        wm = st.session_state.get("window_metrics") or {}
        wm_10min = wm.get("10min", {})
        wm_5min = wm.get("5min", {})
        wm_1min = wm.get("1min", {})
        
        session_phase = st.session_state.get("session_phase")
        if session_phase:
            phase_colors = {
                "warm_up": "#ff9500",
                "peak": "#007AFF",
                "fatigue": "#86868b",
                "recovery": "#34c759",
            }
            phase_color = phase_colors.get(session_phase, "#86868b")
            st.markdown(
                f"""
                <div style='text-align: center; margin: 2rem 0 1.5rem; padding: 1rem; background: #f5f5f7; border-radius: 12px;'>
                    <div style='color:#86868b; font-size: 13px; font-weight: 400; letter-spacing: 0.3px; margin-bottom: 0.5rem;'>SESSION PHASE</div>
                    <div style='color:{phase_color}; font-size: 18px; font-weight: 400; letter-spacing: 0.5px; text-transform: capitalize;'>
                        {session_phase.replace('_', ' ')}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        
        st.markdown(
            f"""
            <div style='padding: 1.5rem; background: #ffffff; border-radius: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin: 1.5rem 0;'>
                <div style='font-size: 15px; font-weight: 400; color: #86868b; margin-bottom: 1.25rem; text-align: center; letter-spacing: 0.3px;'>
                    Multi-Window Analytics
                </div>
                <div style='display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap;'>
                    <div style='text-align:center; min-width: 90px;'>
                        <div style='color:#86868b; font-size: 12px; font-weight: 400; margin-bottom: 0.5rem; letter-spacing: 0.3px;'>1MIN</div>
                        <div style='color:#1d1d1f; font-size: 24px; font-weight: 300; letter-spacing: -0.5px; margin-bottom: 0.25rem;'>{wm_1min.get('mean', 0):.0f}%</div>
                        <div style='color:#86868b; font-size: 11px; font-weight: 300;'>trend: {wm_1min.get('trend', 0):.1f}</div>
                    </div>
                    <div style='text-align:center; min-width: 90px;'>
                        <div style='color:#86868b; font-size: 12px; font-weight: 400; margin-bottom: 0.5rem; letter-spacing: 0.3px;'>5MIN</div>
                        <div style='color:#1d1d1f; font-size: 24px; font-weight: 300; letter-spacing: -0.5px; margin-bottom: 0.25rem;'>{wm_5min.get('mean', 0):.0f}%</div>
                        <div style='color:#86868b; font-size: 11px; font-weight: 300;'>trend: {wm_5min.get('trend', 0):.1f}</div>
                    </div>
                    <div style='text-align:center; min-width: 90px;'>
                        <div style='color:#86868b; font-size: 12px; font-weight: 400; margin-bottom: 0.5rem; letter-spacing: 0.3px;'>10MIN</div>
                        <div style='color:#1d1d1f; font-size: 24px; font-weight: 300; letter-spacing: -0.5px; margin-bottom: 0.25rem;'>{wm_10min.get('mean', 0):.0f}%</div>
                        <div style='color:#86868b; font-size: 11px; font-weight: 300;'>vol: {wm_10min.get('volatility', 0):.2f}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        prediction = st.session_state.get("focus_prediction")
        if prediction:
            will_drop = prediction.get("will_drop", False)
            confidence = prediction.get("confidence", 0.0)
            drop_prob = prediction.get("drop_probability", 0.0)
            
            if will_drop and drop_prob > 0.6:
                st.markdown(
                    f"""
                    <div style='padding: 1rem 1.25rem; background: #fff3cd; border-radius: 12px; margin: 1rem 0;'>
                        <div style='color: #856404; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                            Focus likely to drop in next 5 min (confidence: {confidence*100:.0f}%)
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif will_drop:
                st.markdown(
                    f"""
                    <div style='padding: 1rem 1.25rem; background: #e3f2fd; border-radius: 12px; margin: 1rem 0;'>
                        <div style='color: #1565c0; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                            Focus may drop soon (probability: {drop_prob*100:.0f}%)
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        
        break_suggestion = st.session_state.get("break_suggestion")
        if break_suggestion:
            st.markdown(
                f"""
                <div style='padding: 1rem 1.25rem; background: #e3f2fd; border-radius: 12px; margin: 1rem 0;'>
                    <div style='color: #1565c0; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                        {break_suggestion}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        wm = st.session_state.get("window_metrics") or {}
        focus_avg = wm.get("focus_avg_10m", 0.0)
        posture_avg = wm.get("posture_avg_10m", 0.0)
        samples = wm.get("sample_count_10m", 0)
        st.markdown(
            f"""
            <div style='padding: 1.5rem; background: #ffffff; border-radius: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin: 1.5rem 0;'>
                <div style='font-size: 15px; font-weight: 400; color: #86868b; margin-bottom: 1.25rem; text-align: center; letter-spacing: 0.3px;'>
                    10‑min sliding window
                </div>
                <div style='display: flex; justify-content: center; gap: 2rem;'>
                    <div style='text-align:center;'>
                        <div style='color:#86868b; font-size: 12px; font-weight: 400; margin-bottom: 0.5rem; letter-spacing: 0.3px;'>FOCUS AVG</div>
                        <div style='color:#1d1d1f; font-size: 24px; font-weight: 300; letter-spacing: -0.5px;'>{focus_avg:.0f}%</div>
                    </div>
                    <div style='text-align:center;'>
                        <div style='color:#86868b; font-size: 12px; font-weight: 400; margin-bottom: 0.5rem; letter-spacing: 0.3px;'>POSTURE AVG</div>
                        <div style='color:#1d1d1f; font-size: 24px; font-weight: 300; letter-spacing: -0.5px;'>{posture_avg:.0f}%</div>
                    </div>
                    <div style='text-align:center;'>
                        <div style='color:#86868b; font-size: 12px; font-weight: 400; margin-bottom: 0.5rem; letter-spacing: 0.3px;'>SAMPLES</div>
                        <div style='color:#1d1d1f; font-size: 24px; font-weight: 300; letter-spacing: -0.5px;'>{samples}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        break_suggestion = st.session_state.get("break_suggestion")
        if break_suggestion:
            st.markdown(
                f"""
                <div style='padding: 1rem 1.25rem; background: #e3f2fd; border-radius: 12px; margin: 1rem 0;'>
                    <div style='color: #1565c0; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                        {break_suggestion}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_preview() -> None:
    """Render preview image with persistent placeholders."""
    if st.session_state.preview_placeholder is None:
        st.session_state.preview_placeholder = st.empty()
    if st.session_state.preview_caption_placeholder is None:
        st.session_state.preview_caption_placeholder = st.empty()
    
    if st.session_state.show_preview and st.session_state.preview_image is not None:
        caption_text = "Live Preview" + (" (with face mesh)" if st.session_state.video_processor.draw_landmarks else " (clean)")
        
        st.session_state.preview_caption_placeholder.markdown(
            f"""
            <div style='margin: 2rem 0; padding: 1.5rem; background: #ffffff; border-radius: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);'>
                <div style='color: #86868b; font-size: 13px; font-weight: 400; margin-bottom: 1rem; text-align: center; letter-spacing: 0.3px;'>
                    {caption_text}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.session_state.preview_placeholder.image(
            st.session_state.preview_image, 
            channels="BGR", 
            width='stretch'
        )
    else:
        st.session_state.preview_caption_placeholder.empty()
        st.session_state.preview_placeholder.empty()


def render_header() -> None:
    """Render app header."""
    st.markdown('<div class="header-title">StudySensei</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="header-subtitle">Real-time focus tracking with advanced analytics</div>',
        unsafe_allow_html=True,
    )
