import cv2
import time
import queue
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import threading
from collections import deque

import mediapipe as mp
import streamlit as st

# Prefer the canonical API: mediapipe as mp; mp.solutions.<...>
# Some environments expose solutions under mediapipe.python.solutions; we fall back to that.
if not hasattr(mp, "solutions"):
    try:
        import mediapipe.python.solutions as _solutions  # type: ignore
    except Exception as exc:
        raise ImportError(
            "MediaPipe 'solutions' module was not found. "
            "Your 'mediapipe' install may be broken or shadowed by another package.\n"
            "Try: pip uninstall -y mediapipe && pip install mediapipe"
        ) from exc
    mp.solutions = _solutions  # type: ignore[attr-defined]

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_face_mesh = mp.solutions.face_mesh
_FACE_MESH = None

LEFT_EYE_LANDMARKS = (33, 133)   # outer, inner corner (MediaPipe FaceMesh)
RIGHT_EYE_LANDMARKS = (362, 263) # outer, inner corner (MediaPipe FaceMesh)

# Constants
WINDOW_SIZE = 60  # seconds
TARGET_FPS = 60   # Reduced for better performance on laptops


def _lm_to_px(landmarks, idx: int, width: int, height: int) -> Tuple[int, int]:
    lm = landmarks.landmark[idx]
    return int(lm.x * width), int(lm.y * height)


@dataclass
class FocusResult:
    focused: bool
    score: float  # 0-100


def compute_focus(face_landmarks, frame_width: int, frame_height: int) -> FocusResult:
    """
    Heuristic 'gaze' / attention estimate using only eye-corner landmarks.
    """
    l0 = _lm_to_px(face_landmarks, LEFT_EYE_LANDMARKS[0], frame_width, frame_height)
    l1 = _lm_to_px(face_landmarks, LEFT_EYE_LANDMARKS[1], frame_width, frame_height)
    r0 = _lm_to_px(face_landmarks, RIGHT_EYE_LANDMARKS[0], frame_width, frame_height)
    r1 = _lm_to_px(face_landmarks, RIGHT_EYE_LANDMARKS[1], frame_width, frame_height)

    left_w = ((l0[0] - l1[0]) ** 2 + (l0[1] - l1[1]) ** 2) ** 0.5
    right_w = ((r0[0] - r1[0]) ** 2 + (r0[1] - r1[1]) ** 2) ** 0.5

    if left_w < 8 or right_w < 8:
        return FocusResult(False, 0.0)

    width_ratio = left_w / right_w if right_w > 0 else 0.0
    left_mid_y = (l0[1] + l1[1]) / 2.0
    right_mid_y = (r0[1] + r1[1]) / 2.0
    eye_line_delta = abs(left_mid_y - right_mid_y)

    yaw_penalty = min(1.0, abs(1.0 - width_ratio) / 0.33)
    roll_penalty = min(1.0, eye_line_delta / 20.0)

    score = max(0.0, 100.0 * (1.0 - 0.6 * yaw_penalty - 0.4 * roll_penalty))
    focused = score >= 60.0
    return FocusResult(focused, score)


def _get_face_mesh():
    global _FACE_MESH
    if _FACE_MESH is None:
        _FACE_MESH = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return _FACE_MESH


def process_frame(image_bgr: np.ndarray, prev_timestamp: float, draw_landmarks: bool = True) -> dict:
    """Process a single BGR frame and return focus info."""
    h, w, _ = image_bgr.shape
    face_mesh = _get_face_mesh()

    rgb_frame = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb_frame.flags.writeable = False
    results = face_mesh.process(rgb_frame)
    rgb_frame.flags.writeable = True

    focused = False
    score = 0.0

    if results.multi_face_landmarks:
        for face_landmarks in results.multi_face_landmarks:
            focus_result = compute_focus(face_landmarks, w, h)
            focused = focus_result.focused
            score = focus_result.score
            
            if draw_landmarks:
                mp_drawing.draw_landmarks(
                    image=image_bgr,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_TESSELATION,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style(),
                )
                mp_drawing.draw_landmarks(
                    image=image_bgr,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_CONTOURS,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_contours_style(),
                )
    else:
        # No face detected
        focused = False
        score = 0.0

    current_ts = time.time()
    elapsed = max(0.0, current_ts - prev_timestamp) if prev_timestamp else 0.0

    return {
        "focused": focused,
        "score": score,
        "timestamp": current_ts,
        "elapsed": elapsed if elapsed < 2.0 else 0.0,
        "preview": image_bgr,
    }


class VideoProcessor:
    """Continuous video processor that runs in a background thread."""
    
    def __init__(self):
        self.running = False
        self.cap = None
        self.thread = None
        self.latest_result = None
        self.lock = threading.Lock()
        self.frame_count = 0
        self.start_time = 0
        self.draw_landmarks = True
        
    def start(self):
        """Start video processing thread."""
        if self.running:
            return
            
        self.running = True
        self.cap = cv2.VideoCapture(0)
        # Set lower resolution for better performance
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.frame_count = 0
        self.start_time = time.time()
        
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop video processing thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        self.cap = None
        self.thread = None
        
    def _process_loop(self):
        """Main processing loop running in background thread."""
        last_process_time = time.time()
        frame_interval = 1.0 / TARGET_FPS
        
        while self.running and self.cap:
            current_time = time.time()
            
            # Control processing rate
            if current_time - last_process_time < frame_interval:
                time.sleep(0.001)  # Small sleep to prevent CPU spinning
                continue
                
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue
                
            # Process frame
            result = process_frame(frame.copy(), last_process_time, self.draw_landmarks)
            last_process_time = current_time
            self.frame_count += 1
            
            # Update latest result
            with self.lock:
                self.latest_result = result
                
            # Calculate FPS
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                result["fps"] = self.frame_count / elapsed
            else:
                result["fps"] = 0.0
                
    def get_latest_result(self):
        """Get the latest processing result."""
        with self.lock:
            return self.latest_result
            
    def toggle_landmarks(self):
        """Toggle face mesh landmarks display."""
        self.draw_landmarks = not self.draw_landmarks


def format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def render_focus_metrics() -> None:
    """Minimal focus display with live 60s metric."""
    focus_pct_60 = st.session_state.get("focus_pct_60s", 0.0)
    status_text = st.session_state.get("latest_status_text", "WAITING")
    is_focused = status_text == "FOCUSED"

    # Monochrome palette only
    circle_color = "#ffffff"
    track_color = "#404040"
    status_color = "#d3d3d3" if is_focused else "#808080"

    # SVG progress ring: must use the true circumference for the chosen radius
    progress = max(0.0, min(1.0, focus_pct_60 / 100.0))
    r = 85
    circumference = 2 * 3.141592653589793 * r  # ~534.07
    stroke_dasharray = f"{progress * circumference:.3f} {circumference:.3f}"

    st.markdown(
        f"""
        <div style='display:flex; justify-content:center; margin: 1rem 0; position: relative;'>
            <svg width="200" height="200" style="transform: rotate(-90deg);">
                 <circle cx="100" cy="100" r="{r}" stroke="{track_color}" stroke-width="8" fill="transparent"/>
                 <circle cx="100" cy="100" r="{r}" stroke="{circle_color}" stroke-width="8" 
                        fill="transparent" stroke-dasharray="{stroke_dasharray}" 
                        stroke-linecap="round"/>
            </svg>
            <div style='
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                color: #ffffff;
                font-size: 48px;
                font-weight: 800;
                text-shadow: 0 2px 10px rgba(0,0,0,0.3);
            '>
                {focus_pct_60:.0f}%
            </div>
        </div>
        <div style='text-align:center; margin-bottom: 0.5rem; font-size: 22px; font-weight: 700; color: {status_color};'>
            {status_text}
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
        <div style='display: flex; justify-content: center; gap: 1rem; margin: 1rem 0;'>
            <div style='text-align:center;'>
                <div style='color:#d1d5db; font-size: 12px;'>SESSION</div>
                <div style='color:#ffffff; font-size: 16px; font-weight: 600;'>{format_time(session_duration)}</div>
            </div>
            <div style='text-align:center;'>
                <div style='color:#d1d5db; font-size: 12px;'>FPS</div>
                <div style='color:#ffffff; font-size: 16px; font-weight: 600;'>{fps:.1f}</div>
            </div>
            <div style='text-align:center;'>
                <div style='color:#d1d5db; font-size: 12px;'>WINDOW</div>
                <div style='color:#ffffff; font-size: 16px; font-weight: 600;'>60s</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def update_focus_history(focused: bool, timestamp: float):
    """Update focus history with sliding window."""
    if "focus_history" not in st.session_state:
        st.session_state.focus_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)
    
    st.session_state.focus_history.append((timestamp, focused))
    
    # Calculate 60-second focus percentage
    cutoff = timestamp - WINDOW_SIZE
    valid_samples = [(t, f) for t, f in st.session_state.focus_history if t >= cutoff]
    
    if valid_samples:
        total_frames = len(valid_samples)
        focused_frames = sum(1 for _, f in valid_samples if f)
        st.session_state.focus_pct_60s = (focused_frames / total_frames) * 100.0
    else:
        st.session_state.focus_pct_60s = 0.0


def main() -> None:
    st.set_page_config(
        page_title="StudySensei Focus", 
        layout="centered", 
        initial_sidebar_state="collapsed"
    )
    
    st.markdown(
        """
        <style>
         body { background: #000000; color: #ffffff; }
         .stApp { background: #000000; }
        .stButton>button { 
            width: 100%; 
            border-radius: 10px; 
            padding: 0.65rem 1rem; 
            font-weight: 600;
            border: none;
            transition: all 0.2s;
        }
        .stButton>button:hover {
            transform: translateY(-1px);
             box-shadow: 0 4px 12px rgba(0,0,0,0.6);
        }
         /* Monochrome controls */
         .start-btn>button { background: #ffffff; color: #000000; }
         .stop-btn>button { background: #d3d3d3; color: #000000; }
         .toggle-btn>button { background: #808080; color: #000000; }
        .card { 
             background: #000000; 
            padding: 1.5rem; 
            border-radius: 16px; 
            box-shadow: 0 10px 25px rgba(0,0,0,0.35);
             border: 1px solid #404040;
        }
        .header-title { 
            font-size: 34px; 
            font-weight: 800; 
             color: #ffffff; 
            text-align:center; 
            margin-bottom: 0.25rem;
        }
        .header-subtitle { 
            font-size: 16px; 
             color: #d3d3d3; 
            text-align:center;
            margin-bottom: 2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Initialize VideoProcessor in session state
    if "video_processor" not in st.session_state:
        st.session_state.video_processor = VideoProcessor()
    
    # Session state initialization
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
    if "focus_history" not in st.session_state:
        st.session_state.focus_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)

    # Header
    st.markdown('<div class="header-title">StudySensei Focus</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-subtitle">Continuous real-time focus tracking (last 60 seconds)</div>', unsafe_allow_html=True)

    # Controls in a card
    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        
        col_controls = st.columns([1, 1, 1])
        with col_controls[0]:
            st.markdown('<div class="start-btn">', unsafe_allow_html=True)
            if st.button("▶ Start", key="start_btn"):
                st.session_state.video_processor.start()
                st.session_state.session_start_time = time.time()
                st.session_state.total_focused_time = 0.0
                st.session_state.total_not_focused_time = 0.0
                st.session_state.focus_history.clear()
                st.session_state.focus_pct_60s = 0.0
                st.session_state.latest_fps = 0.0
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_controls[1]:
            st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
            if st.button("■ Stop", key="stop_btn"):
                st.session_state.video_processor.stop()
                st.session_state.session_start_time = 0.0
                st.session_state.preview_image = None
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_controls[2]:
            st.markdown('<div class="toggle-btn">', unsafe_allow_html=True)
            if st.button("👁️ Toggle Mesh", key="toggle_mesh"):
                st.session_state.video_processor.toggle_landmarks()
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Toggle preview checkbox
        col1, col2 = st.columns([3, 1])
        with col2:
            st.session_state.show_preview = st.checkbox(
                "Show Preview", 
                value=st.session_state.show_preview,
                key="show_preview_cb"
            )
        
        st.markdown('</div>', unsafe_allow_html=True)

    # Get latest result from video processor
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
    
    # Focus Metrics Display
    render_focus_metrics()
    
    # Preview Image (if enabled)
    if st.session_state.show_preview and st.session_state.preview_image is not None:
        st.image(
            st.session_state.preview_image, 
            channels="BGR", 
            caption="Live Preview (with face mesh)" if st.session_state.video_processor.draw_landmarks else "Live Preview (clean)",
             use_container_width=True
        )
    
    # Auto-refresh for real-time updates
    time.sleep(0.1)  # Small delay to prevent excessive CPU usage
    st.rerun()


if __name__ == "__main__":
    main()