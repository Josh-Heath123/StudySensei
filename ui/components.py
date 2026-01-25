"""UI components for StudySensei - Streamlit rendering functions."""

import time
import streamlit as st
import numpy as np
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None

from utils.helpers import format_time
from utils.image_utils import safe_display_image, validate_image

# Analytics availability
try:
    from analytics import TimeSeriesAnalyzer
    _ANALYTICS_AVAILABLE = True
    _NEW_ANALYTICS = True
except ImportError:
    try:
        from analytics import TimeSeriesAnalyzer
        _ANALYTICS_AVAILABLE = True
        _NEW_ANALYTICS = False
    except ImportError:
        _ANALYTICS_AVAILABLE = False
        _NEW_ANALYTICS = False

# Emotion availability
_EMOTION_AVAILABLE = hasattr(st.session_state.get("video_processor", None), "emotion_detector") if "video_processor" in st.session_state else False


def render_header() -> None:
    """Render app header."""
    st.markdown(
        """
        <div class="header-title">StudySensei</div>
        <div class="header-subtitle">Real-time focus and posture tracking</div>
        """,
        unsafe_allow_html=True,
    )


def render_focus_metrics() -> None:
    """Minimal focus display with live 60s metric - using persistent placeholder with error boundary."""
    try:
        # Initialize persistent placeholder ONCE
        if st.session_state.get("focus_metrics_placeholder") is None:
            st.session_state.focus_metrics_placeholder = st.empty()
        
        placeholder = st.session_state.focus_metrics_placeholder
        
        # Throttle updates to prevent flickering (max 2 updates/second)
        current_time = time.time()
        last_update = st.session_state.get("focus_metrics_last_update", 0.0)
        update_interval = 0.5  # 500ms minimum between updates
        
        if current_time - last_update < update_interval:
            return  # Skip update if too soon
        
        st.session_state.focus_metrics_last_update = current_time
        
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

        with placeholder.container():
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

            # Initialize session_duration with default value BEFORE using it
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
    except Exception as e:
        # Error boundary: log error and show fallback UI
        st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
        if st.session_state.ui_error_count <= 3:
            print(f"Error in render_focus_metrics: {e}")
        try:
            with st.session_state.get("focus_metrics_placeholder", st.empty()).container():
                st.markdown(
                    "<div style='text-align:center; margin: 2rem 0; padding: 1.5rem; background: #f5f5f7; border-radius: 18px; color: #86868b; font-size: 13px;'>Focus metrics unavailable</div>",
                    unsafe_allow_html=True,
                )
        except Exception:
            pass


def render_posture_metrics() -> None:
    """Render posture status and score with alerts - using persistent placeholder with error boundary."""
    try:
        # Initialize persistent placeholder ONCE
        if st.session_state.get("posture_metrics_placeholder") is None:
            st.session_state.posture_metrics_placeholder = st.empty()
        
        placeholder = st.session_state.posture_metrics_placeholder
        
        posture_score = st.session_state.get("posture_score", 0.0)
        posture_status = st.session_state.get("posture_status", "WAITING")
        posture_alert = st.session_state.get("posture_alert")
        
        # Always render content to prevent flickering
        if not st.session_state.get("video_processor") or not st.session_state.video_processor.enable_posture:
            placeholder.empty()
            return
        
        if st.session_state.get("session_start_time", 0) == 0:
            with placeholder.container():
                st.markdown(
                    "<div style='text-align:center; margin: 2rem 0; padding: 1.5rem; background: #f5f5f7; border-radius: 18px; color: #86868b; font-size: 13px;'>Waiting for session to start...</div>",
                    unsafe_allow_html=True,
                )
            return
        
        with placeholder.container():
            st.markdown(
                f"""
                <div style='text-align:center; margin: 2rem 0; padding: 1.5rem; background: #ffffff; border-radius: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);'>
                    <div style='color:#86868b; font-size: 13px; font-weight: 400; letter-spacing: 0.3px; margin-bottom: 0.5rem;'>POSTURE</div>
                    <div style='color:#1d1d1f; font-size: 36px; font-weight: 300; letter-spacing: -0.5px; margin-bottom: 0.5rem;'>{posture_score:.0f}%</div>
                    <div style='color:#86868b; font-size: 15px; font-weight: 400; letter-spacing: 0.3px;'>{posture_status}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            
            if posture_alert:
                st.markdown(
                    f"""
                    <div style='padding: 1rem 1.25rem; background: #fff3cd; border-radius: 12px; margin: 1rem 0;'>
                        <div style='color: #856404; font-size: 15px; font-weight: 400; line-height: 1.5;'>
                            {posture_alert}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    except Exception as e:
        st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
        if st.session_state.ui_error_count <= 3:
            print(f"Error in render_posture_metrics: {e}")
        try:
            st.session_state.posture_metrics_placeholder.empty()
        except Exception:
            pass


def render_interactive_analytics() -> None:
    """Optimized interactive analytics dashboard with throttled updates."""
    try:
        # Always render something to maintain widget count
        if not _ANALYTICS_AVAILABLE:
            st.markdown("<div></div>", unsafe_allow_html=True)
            return
        if st.session_state.get("session_start_time", 0) == 0:
            st.markdown("<div></div>", unsafe_allow_html=True)
            return
        
        current_fps = st.session_state.get("latest_fps", 0.0)
        if current_fps > 0 and current_fps < 15.0:
            st.markdown(
                "<div style='padding: 1rem; background: #fff3cd; border-radius: 12px; color: #856404; font-size: 14px;'>Analytics disabled due to low FPS. Charts will resume when performance improves.</div>",
                unsafe_allow_html=True,
            )
            return
        
        if "chart_data" not in st.session_state:
            st.session_state.chart_data = {
                "focus_scores": np.array([], dtype=np.float32),
                "posture_scores": np.array([], dtype=np.float32),
                "timestamps": np.array([], dtype=np.float32),
                "last_chart_update": 0.0,
                "last_chart_render": 0.0,
                "cached_chart_data": None,
            }
        
        current_time = time.time()
        last_update = st.session_state.chart_data.get("last_chart_update", 0.0)
        last_render = st.session_state.chart_data.get("last_chart_render", 0.0)
        data_update_interval = 4.0
        render_update_interval = 5.0
        data_sampling_rate = 5
        
        # Data collection
        if current_time - last_update >= data_update_interval:
            if st.session_state.get("latest_focus_score") is not None:
                if "data_point_counter" not in st.session_state.chart_data:
                    st.session_state.chart_data["data_point_counter"] = 0
                
                st.session_state.chart_data["data_point_counter"] += 1
                
                if st.session_state.chart_data["data_point_counter"] >= data_sampling_rate:
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
                    
                    st.session_state.chart_data["data_point_counter"] = 0
                    st.session_state.chart_data["cached_chart_data"] = None
                
                st.session_state.chart_data["last_chart_update"] = current_time
        
        data_length = len(st.session_state.chart_data["timestamps"])
        if data_length < 2:
            st.markdown(
                "<div style='padding: 1rem; background: #f5f5f7; border-radius: 12px; color: #86868b; font-size: 14px; text-align: center;'>Collecting data... Charts will appear when enough data is available.</div>",
                unsafe_allow_html=True,
            )
            return
        
        # Use cached content when available
        if current_time - last_render < render_update_interval:
            cached = st.session_state.chart_data.get("cached_chart_data")
            if cached is not None:
                col_metrics = st.columns(3)
                with col_metrics[0]:
                    st.metric("Focus Avg", f"{cached['stats']['focus_mean']:.1f}%", f"±{cached['stats']['focus_std']:.1f}%")
                with col_metrics[1]:
                    st.metric("Posture Avg", f"{cached['stats']['posture_mean']:.1f}%")
                with col_metrics[2]:
                    st.metric("Data Points", f"{cached['data_length']}/100")
                
                chart_type = st.radio(
                    "Chart Type",
                    ["Focus Trend", "Posture Trend", "None"],
                    horizontal=True,
                    key="chart_type_selector",
                    index=2
                )
                
                if chart_type == "Focus Trend" and cached['data_length'] >= 2:
                    if pd is not None:
                        chart_df = pd.DataFrame({"Focus": cached['focus_scores']})
                        st.line_chart(chart_df, height=250, width='stretch')
                elif chart_type == "Posture Trend" and cached['data_length'] >= 2:
                    if pd is not None:
                        chart_df = pd.DataFrame({"Posture": cached['posture_scores']})
                        st.line_chart(chart_df, height=250, width='stretch')
                
                time_until_render = render_update_interval - (current_time - last_render)
                if time_until_render > 0:
                    st.caption(f"Next chart update in {time_until_render:.1f}s")
                
                return
        
        focus_scores = st.session_state.chart_data["focus_scores"]
        posture_scores = st.session_state.chart_data["posture_scores"]
        
        # Cache statistics
        if "chart_stats" not in st.session_state or st.session_state.chart_data.get("cached_chart_data") is None:
            st.session_state.chart_stats = {
                "focus_mean": float(np.mean(focus_scores)) if len(focus_scores) > 0 else 0.0,
                "focus_std": float(np.std(focus_scores)) if len(focus_scores) > 0 else 0.0,
                "posture_mean": float(np.mean(posture_scores)) if len(posture_scores) > 0 else 0.0,
            }
        
        stats = st.session_state.chart_stats
        
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
        
        # Update render timestamp and cache
        st.session_state.chart_data["last_chart_render"] = current_time
        st.session_state.chart_data["cached_chart_data"] = {
            "stats": stats,
            "data_length": data_length,
            "focus_scores": focus_scores.copy(),
            "posture_scores": posture_scores.copy(),
        }
        
        time_until_render = render_update_interval - (current_time - last_render)
        if time_until_render > 0:
            st.caption(f"Next chart update in {time_until_render:.1f}s")
    except Exception as e:
        st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
        if st.session_state.ui_error_count <= 3:
            print(f"Error in render_interactive_analytics: {e}")


def render_analytics() -> None:
    """Render advanced analytics: trends, predictions, session phase, break suggestions."""
    try:
        # Initialize placeholder ONCE
        if st.session_state.get("analytics_content_placeholder") is None:
            st.session_state.analytics_content_placeholder = st.empty()
        
        placeholder = st.session_state.analytics_content_placeholder
        
        if not _ANALYTICS_AVAILABLE:
            placeholder.empty()
            return
        if st.session_state.get("session_start_time", 0) == 0:
            placeholder.empty()
            return
        
        # Throttle updates
        current_time = time.time()
        last_update = st.session_state.get("analytics_content_last_update", 0.0)
        update_interval = 0.5
        
        if current_time - last_update < update_interval:
            return
        
        st.session_state.analytics_content_last_update = current_time
        
        with placeholder.container():
            if _NEW_ANALYTICS:
                wm = st.session_state.get("window_metrics") or {}
                wm_10min = wm.get("10min", {})
                
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
                
                break_suggestion = st.session_state.get("break_suggestion")
                if break_suggestion:
                    if "Focus has dropped" not in break_suggestion or not st.session_state.get("break_suggestion_shown", False):
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
                        if "Focus has dropped" in break_suggestion:
                            st.session_state.break_suggestion_shown = True
    except Exception as e:
        st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
        if st.session_state.ui_error_count <= 3:
            print(f"Error in render_analytics: {e}")


def render_preview() -> None:
    """Render webcam preview with safe image display."""
    try:
        # Initialize placeholders ONCE
        if st.session_state.get("preview_placeholder") is None:
            st.session_state.preview_placeholder = st.empty()
        if st.session_state.get("preview_caption_placeholder") is None:
            st.session_state.preview_caption_placeholder = st.empty()
        
        preview_placeholder = st.session_state.preview_placeholder
        caption_placeholder = st.session_state.preview_caption_placeholder
        
        if st.session_state.show_preview:
            preview_image = st.session_state.get("preview_image")
            is_valid_image = validate_image(preview_image)
            
            if is_valid_image:
                success = safe_display_image(
                    preview_image,
                    placeholder=preview_placeholder,
                    width="stretch",
                    channels="BGR",
                    output_format="JPEG"
                )
                if not success:
                    preview_placeholder.empty()
            else:
                preview_placeholder.empty()
            
            # Always render caption
            with caption_placeholder.container():
                if is_valid_image:
                    caption_text = "Live Preview" + (" (with face mesh)" if st.session_state.video_processor.draw_landmarks else " (clean)")
                    st.caption(caption_text)
                else:
                    st.caption("Waiting for camera feed...")
        else:
            preview_placeholder.empty()
            caption_placeholder.empty()
    except Exception as e:
        st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
        if st.session_state.ui_error_count <= 3:
            print(f"Error in render_preview: {e}")
        try:
            if "preview_placeholder" in st.session_state:
                st.session_state.preview_placeholder.empty()
            if "preview_caption_placeholder" in st.session_state:
                st.session_state.preview_caption_placeholder.empty()
        except Exception:
            pass
