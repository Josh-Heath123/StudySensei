import cv2
import time
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
import threading
from collections import deque

import mediapipe as mp
import streamlit as st

# Chart libraries (optional)
try:
    import pandas as pd
except ImportError:
    pd = None

# Import posture detection module
from posture import detect_posture, PostureResult, calibrate_posture

# Import experimental emotion detection (optional)
try:
    from emotion_detection import EmotionDetector
    _EMOTION_AVAILABLE = True
except ImportError:
    EmotionDetector = None
    _EMOTION_AVAILABLE = False

# Import analytics and behavior modules (optional - for advanced features)
try:
    # Try new analytics module first
    from analytics import (
        TimeSeriesAnalyzer,
        FocusDecayDetector,
        SessionStatistics,
        BehaviorModeler,
        FocusScorer,
        PatternDetector,
        PhaseDetector,
        SessionStore,
        SessionQuery,
        BreakRecommender,
        FocusDropPredictor,
    )
    from analytics.behavior_model import BehaviorPattern, StudyPattern, SessionPhase
    _ANALYTICS_AVAILABLE = True
    _NEW_ANALYTICS = True
except ImportError:
    # Fallback to old modules for backward compatibility
    try:
        from database import DatabaseManager
        from analytics import TimeSeriesAnalyzer, WindowMetrics
        from behavior import BehaviorModeler, BehaviorPattern, PatternType
        from ml_predictor import FocusPredictor
        _ANALYTICS_AVAILABLE = True
        _NEW_ANALYTICS = False
    except ImportError:
        # Analytics modules not available - posture detection will still work
        DatabaseManager = None
        TimeSeriesAnalyzer = None
        WindowMetrics = None
        BehaviorModeler = None
        BehaviorPattern = None
        PatternType = None
        FocusPredictor = None
        _ANALYTICS_AVAILABLE = False
        _NEW_ANALYTICS = False

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
mp_pose = mp.solutions.pose
_FACE_MESH = None
_POSE = None

LEFT_EYE_LANDMARKS = (33, 133)   # outer, inner corner (MediaPipe FaceMesh)
RIGHT_EYE_LANDMARKS = (362, 263) # outer, inner corner (MediaPipe FaceMesh)

# Week 2: Iris landmarks (MediaPipe FaceMesh)
LEFT_IRIS_LANDMARKS = (468, 469, 470, 471, 472)   # Left iris center and boundary points
RIGHT_IRIS_LANDMARKS = (473, 474, 475, 476, 477)  # Right iris center and boundary points

# Week 2: Eye landmarks for EAR calculation (6 points per eye)
# Using standard MediaPipe FaceMesh landmarks for EAR:
# Left eye: outer corner, top (2 points), inner corner, bottom (2 points)
LEFT_EYE_EAR_POINTS = (33, 160, 158, 133, 153, 144)   # Left eye EAR points
# Right eye: outer corner, top (2 points), inner corner, bottom (2 points)  
RIGHT_EYE_EAR_POINTS = (362, 385, 387, 263, 380, 373)  # Right eye EAR points

# Constants
WINDOW_SIZE = 60  # seconds
TARGET_FPS = 60   # Reduced for better performance on laptops

# Performance optimization: Frame skipping configuration
FRAME_SKIP_N = 3  # Process every 3rd frame for better FPS (target: >15 FPS)

# Week 2: Blink detection constants
EAR_THRESHOLD = 0.25  # Eye Aspect Ratio threshold for blink detection (lower = more sensitive)
EAR_CONSECUTIVE_FRAMES = 2  # Number of consecutive frames below threshold to register blink
EAR_NOISE_TOLERANCE = 0.05  # Tolerance for noise in EAR measurements

# Week 2: Focus score weights (must sum to 1.0)
GAZE_CONFIDENCE_WEIGHT = 0.70  # Weight for iris-based gaze confidence
BLINK_FATIGUE_WEIGHT = 0.30    # Weight for blink-rate-based fatigue signal


def _lm_to_px(landmarks, idx: int, width: int, height: int) -> Tuple[int, int]:
    lm = landmarks.landmark[idx]
    return int(lm.x * width), int(lm.y * height)


@dataclass
class FocusResult:
    focused: bool
    score: float  # 0-100
    gaze_confidence: float = 0.0  # Week 2: Iris-based gaze confidence [0.0, 1.0]
    blink_detected: bool = False  # Week 2: Whether a blink was detected in this frame


def compute_iris_gaze_confidence(face_landmarks, frame_width: int, frame_height: int) -> float:
    """
    Week 2: Compute iris-based gaze confidence using MediaPipe iris landmarks.
    
    Algorithm:
    1. Extract iris center points (landmark 468 for left, 473 for right)
    2. Extract eye corner points for normalization
    3. Compute normalized iris position relative to eye corners
    4. When iris is centered (looking forward), confidence is high
    5. When iris is offset (looking away), confidence decreases
    
    Returns:
        Continuous gaze confidence in range [0.0, 1.0]
        - 1.0 = looking directly at screen (iris centered)
        - 0.0 = looking away (iris at edge of eye)
    """
    try:
        # Get iris center points
        left_iris_center = _lm_to_px(face_landmarks, 468, frame_width, frame_height)
        right_iris_center = _lm_to_px(face_landmarks, 473, frame_width, frame_height)
        
        # Get eye corners for normalization
        left_eye_outer = _lm_to_px(face_landmarks, LEFT_EYE_LANDMARKS[0], frame_width, frame_height)
        left_eye_inner = _lm_to_px(face_landmarks, LEFT_EYE_LANDMARKS[1], frame_width, frame_height)
        right_eye_outer = _lm_to_px(face_landmarks, RIGHT_EYE_LANDMARKS[0], frame_width, frame_height)
        right_eye_inner = _lm_to_px(face_landmarks, RIGHT_EYE_LANDMARKS[1], frame_width, frame_height)
        
        # Compute eye widths for normalization
        left_eye_width = ((left_eye_outer[0] - left_eye_inner[0]) ** 2 + 
                          (left_eye_outer[1] - left_eye_inner[1]) ** 2) ** 0.5
        right_eye_width = ((right_eye_outer[0] - right_eye_inner[0]) ** 2 + 
                           (right_eye_outer[1] - right_eye_inner[1]) ** 2) ** 0.5
        
        if left_eye_width < 8 or right_eye_width < 8:
            return 0.0
        
        # Compute iris offset from eye center (normalized)
        left_eye_center_x = (left_eye_outer[0] + left_eye_inner[0]) / 2.0
        left_eye_center_y = (left_eye_outer[1] + left_eye_inner[1]) / 2.0
        left_iris_offset_x = abs(left_iris_center[0] - left_eye_center_x) / left_eye_width
        left_iris_offset_y = abs(left_iris_center[1] - left_eye_center_y) / left_eye_width
        
        right_eye_center_x = (right_eye_outer[0] + right_eye_inner[0]) / 2.0
        right_eye_center_y = (right_eye_outer[1] + right_eye_inner[1]) / 2.0
        right_iris_offset_x = abs(right_iris_center[0] - right_eye_center_x) / right_eye_width
        right_iris_offset_y = abs(right_iris_center[1] - right_eye_center_y) / right_eye_width
        
        # Combined offset (Euclidean distance in normalized space)
        left_offset = (left_iris_offset_x ** 2 + left_iris_offset_y ** 2) ** 0.5
        right_offset = (right_iris_offset_x ** 2 + right_iris_offset_y ** 2) ** 0.5
        
        # Convert offset to confidence (inverse relationship)
        # When offset = 0 (centered), confidence = 1.0
        # When offset = 0.5 (halfway to edge), confidence = 0.0
        left_confidence = max(0.0, 1.0 - (left_offset / 0.5))
        right_confidence = max(0.0, 1.0 - (right_offset / 0.5))
        
        # Robust combination: use minimum (both eyes must be focused) with slight averaging
        combined_confidence = 0.7 * min(left_confidence, right_confidence) + 0.3 * (left_confidence + right_confidence) / 2.0
        
        return min(1.0, max(0.0, combined_confidence))
    except (IndexError, KeyError, AttributeError):
        # Fallback if iris landmarks not available
        return 0.0


def compute_eye_aspect_ratio(face_landmarks, eye_points: Tuple[int, ...], frame_width: int, frame_height: int) -> float:
    """
    Week 2: Compute Eye Aspect Ratio (EAR) for blink detection.
    
    Standard EAR formula: (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    Where:
        p1 = outer corner
        p2, p3 = top points
        p4 = inner corner  
        p5, p6 = bottom points
    
    Lower EAR indicates eye closure (blink).
    Normal open eye EAR is typically 0.2-0.4.
    
    Args:
        face_landmarks: MediaPipe face landmarks
        eye_points: Tuple of 6 landmark indices [outer, top1, top2, inner, bottom1, bottom2]
        frame_width: Frame width
        frame_height: Frame height
    
    Returns:
        EAR value (typically 0.15-0.4 for open eyes)
    """
    try:
        # Extract 6 eye points in order: [outer, top1, top2, inner, bottom1, bottom2]
        points = [_lm_to_px(face_landmarks, idx, frame_width, frame_height) for idx in eye_points]
        
        if len(points) != 6:
            return 0.0
        
        # Compute vertical distances (top to bottom)
        # |p2 - p6|: distance between top point 1 and bottom point 2
        vertical_1 = ((points[1][0] - points[5][0]) ** 2 + (points[1][1] - points[5][1]) ** 2) ** 0.5
        # |p3 - p5|: distance between top point 2 and bottom point 1
        vertical_2 = ((points[2][0] - points[4][0]) ** 2 + (points[2][1] - points[4][1]) ** 2) ** 0.5
        
        # Compute horizontal distance (outer to inner corner) |p1 - p4|
        horizontal = ((points[0][0] - points[3][0]) ** 2 + (points[0][1] - points[3][1]) ** 2) ** 0.5
        
        if horizontal < 1.0:  # Avoid division by zero
            return 0.0
        
        # Standard EAR formula
        ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
        return ear
    except (IndexError, KeyError, AttributeError):
        return 0.0


def detect_blink(face_landmarks, frame_width: int, frame_height: int, 
                 previous_ear_history: deque) -> Tuple[bool, float]:
    """
    Week 2: Detect blinks using Eye Aspect Ratio with noise tolerance.
    
    Algorithm:
    1. Compute EAR for both eyes
    2. Average the EAR values
    3. Compare to threshold with noise tolerance
    4. Track consecutive low-EAR frames to avoid false positives
    
    Args:
        face_landmarks: MediaPipe face landmarks
        frame_width: Frame width
        frame_height: Frame height
        previous_ear_history: Deque of recent EAR values for temporal smoothing
    
    Returns:
        Tuple of (blink_detected: bool, current_ear: float)
    """
    left_ear = compute_eye_aspect_ratio(face_landmarks, LEFT_EYE_EAR_POINTS, frame_width, frame_height)
    right_ear = compute_eye_aspect_ratio(face_landmarks, RIGHT_EYE_EAR_POINTS, frame_width, frame_height)
    
    if left_ear < 0.01 or right_ear < 0.01:
        # Invalid measurement
        return False, 0.0
    
    # Average both eyes for robustness
    current_ear = (left_ear + right_ear) / 2.0
    
    # Add to history for temporal smoothing
    previous_ear_history.append(current_ear)
    if len(previous_ear_history) > 10:  # Keep last 10 frames
        previous_ear_history.popleft()
    
    # Temporal smoothing: use median of recent values to reduce noise
    if len(previous_ear_history) >= 3:
        smoothed_ear = np.median(list(previous_ear_history))
    else:
        smoothed_ear = current_ear
    
    # Detect blink: EAR below threshold with noise tolerance
    blink_threshold = EAR_THRESHOLD - EAR_NOISE_TOLERANCE
    blink_detected = smoothed_ear < blink_threshold
    
    return blink_detected, current_ear


def compute_focus(face_landmarks, frame_width: int, frame_height: int, 
                 previous_ear_history: deque = None, blink_rate_per_min: float = 0.0) -> FocusResult:
    """
    Week 2 Enhanced: Compute focus score combining iris-based gaze and blink-rate fatigue.
    
    Algorithm:
    1. Compute iris-based gaze confidence (0.0-1.0)
    2. Compute blink-rate-based fatigue signal (normalized 0.0-1.0)
    3. Combine with configurable weights
    4. Convert to 0-100 score
    
    Args:
        face_landmarks: MediaPipe face landmarks
        frame_width: Frame width
        frame_height: Frame height
        previous_ear_history: Deque for EAR temporal smoothing (optional)
        blink_rate_per_min: Current blink rate in blinks per minute (for fatigue signal)
    
    Returns:
        FocusResult with enhanced score combining gaze and fatigue
    """
    if previous_ear_history is None:
        previous_ear_history = deque(maxlen=10)
    
    # Week 2: Iris-based gaze confidence
    gaze_confidence = compute_iris_gaze_confidence(face_landmarks, frame_width, frame_height)
    
    # Week 2: Blink detection
    blink_detected, current_ear = detect_blink(face_landmarks, frame_width, frame_height, previous_ear_history)
    
    # Week 2: Blink-rate-based fatigue signal
    # Normal blink rate: ~15-20 blinks/min
    # Fatigue indicators: <10 (too low, drowsy) or >30 (too high, strained)
    # Optimal range: 15-25 blinks/min
    if blink_rate_per_min > 0:
        if 15 <= blink_rate_per_min <= 25:
            fatigue_signal = 1.0  # Optimal blink rate
        elif blink_rate_per_min < 15:
            # Too low: drowsiness indicator
            fatigue_signal = max(0.0, blink_rate_per_min / 15.0)
        else:
            # Too high: eye strain indicator
            fatigue_signal = max(0.0, 1.0 - (blink_rate_per_min - 25) / 20.0)
    else:
        fatigue_signal = 1.0  # Default: no fatigue data available
    
    # Week 2: Combined focus score with configurable weights
    # Score = (gaze_confidence * GAZE_WEIGHT) + (fatigue_signal * BLINK_WEIGHT)
    combined_score = (gaze_confidence * GAZE_CONFIDENCE_WEIGHT) + (fatigue_signal * BLINK_FATIGUE_WEIGHT)
    
    # Convert to 0-100 scale
    score = combined_score * 100.0
    
    # Threshold for focused state (can be tuned)
    focused = score >= 60.0
    
    return FocusResult(focused=focused, score=score, gaze_confidence=gaze_confidence, blink_detected=blink_detected)


def _get_face_mesh():
    """
    Week 2: Get or create FaceMesh instance with iris landmarks enabled.
    
    Note: refine_landmarks=True is required for iris landmark detection (468-477).
    """
    global _FACE_MESH
    if _FACE_MESH is None:
        _FACE_MESH = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,  # Week 2: Enable iris landmarks (468-477)
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return _FACE_MESH


def _get_pose():
    """
    Posture Detection: Get or create MediaPipe Pose instance.
    Reuses same instance for performance.
    """
    global _POSE
    if _POSE is None:
        _POSE = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=0,  # 0=fast (optimized for FPS >15)
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            enable_segmentation=False,  # Disable segmentation for better performance
        )
    return _POSE


def process_frame(image_bgr: np.ndarray, prev_timestamp: float, draw_landmarks: bool = True,
                 previous_ear_history: deque = None, blink_rate_per_min: float = 0.0,
                 enable_posture: bool = True, draw_pose: bool = False,
                 slouch_start_time: Optional[float] = None,
                 emotion_detector = None) -> dict:
    """
    Week 2 Enhanced + Posture: Process a single BGR frame for both focus and posture.
    
    Args:
        image_bgr: BGR image frame
        prev_timestamp: Previous frame timestamp
        draw_landmarks: Whether to draw face mesh landmarks
        previous_ear_history: Deque for EAR temporal smoothing
        blink_rate_per_min: Current blink rate for fatigue signal
        enable_posture: Whether to enable posture detection (toggleable for performance)
        draw_pose: Whether to draw pose landmarks on preview
        slouch_start_time: Timestamp when slouching started (for alerts)
    """
    h, w, _ = image_bgr.shape
    face_mesh = _get_face_mesh()

    # Convert to RGB once (reused for both face and pose)
    rgb_frame = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb_frame.flags.writeable = False
    
    # Process face mesh
    face_results = face_mesh.process(rgb_frame)
    
    # Process pose (if enabled) - reuse same RGB frame for minimal overhead
    posture_result = None
    pose_landmarks_stored = None
    if enable_posture:
        pose = _get_pose()
        pose_results = pose.process(rgb_frame)
        
        if pose_results.pose_landmarks:
            pose_landmarks_stored = pose_results.pose_landmarks  # Store for calibration
            # Detect posture
            posture_result = detect_posture(pose_results.pose_landmarks, w, h, slouch_start_time)
            
            # Draw pose landmarks if requested
            if draw_pose:
                mp_drawing.draw_landmarks(
                    image=image_bgr,
                    landmark_list=pose_results.pose_landmarks,
                    connections=mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style(),
                )
    
    rgb_frame.flags.writeable = True

    focused = False
    score = 0.0
    gaze_confidence = 0.0
    blink_detected = False

    if face_results.multi_face_landmarks:
        for face_landmarks in face_results.multi_face_landmarks:
            # Week 2: Use enhanced focus computation with iris gaze and blink detection
            focus_result = compute_focus(face_landmarks, w, h, previous_ear_history, blink_rate_per_min)
            focused = focus_result.focused
            score = focus_result.score
            gaze_confidence = focus_result.gaze_confidence
            blink_detected = focus_result.blink_detected
            
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
        gaze_confidence = 0.0
        blink_detected = False

    current_ts = time.time()
    elapsed = max(0.0, current_ts - prev_timestamp) if prev_timestamp else 0.0

    result = {
        "focused": focused,
        "score": score,
        "gaze_confidence": gaze_confidence,  # Week 2: Iris-based gaze confidence
        "blink_detected": blink_detected,    # Week 2: Blink detection flag
        "timestamp": current_ts,
        "elapsed": elapsed if elapsed < 2.0 else 0.0,
        "preview": image_bgr,
        "pose_landmarks": pose_landmarks_stored,  # Store for calibration
    }
    
    # Add posture data if available
    if posture_result:
        result["posture"] = {
            "good_posture": posture_result.good_posture,
            "score": posture_result.score,
            "slouching": posture_result.slouching,
            "text_neck": posture_result.text_neck,
            "alert_message": posture_result.alert_message,
            "shoulder_ear_angle": posture_result.shoulder_ear_angle,
            "forward_head_ratio": posture_result.forward_head_ratio,
            "neck_angle": posture_result.neck_angle,
            "shoulder_roll": posture_result.shoulder_roll,
        }
    else:
        result["posture"] = None
    
    # Experimental: Emotion detection (every 5th frame, if enabled)
    if emotion_detector and emotion_detector.is_enabled():
        emotion_state, emotion_confidence = emotion_detector.detect_emotion(image_bgr)
        result["emotion"] = {
            "state": emotion_state,
            "confidence": emotion_confidence,
        }
    else:
        result["emotion"] = None

    return result


class VideoProcessor:
    """Week 2 Enhanced: Continuous video processor with frame skipping and blink tracking."""
    
    def __init__(self):
        self.running = False
        self.cap = None
        self.thread = None
        self.latest_result = None
        self.lock = threading.Lock()
        self.frame_count = 0
        self.start_time = 0
        self.draw_landmarks = True
        # Week 2: Frame skipping
        self.frame_skip_counter = 0
        # Week 2: Blink tracking
        self.ear_history = deque(maxlen=10)  # For temporal smoothing
        self.blink_timestamps = deque(maxlen=100)  # Store last 100 blink timestamps
        # Posture Detection
        self.enable_posture = True  # Toggleable for performance
        self.draw_pose = False  # Draw pose landmarks on preview
        self.slouch_start_time = None  # Track when slouching started
        self.latest_pose_landmarks = None  # Store for calibration
        # Experimental Emotion Detection
        self.emotion_detector = EmotionDetector() if _EMOTION_AVAILABLE else None
        self.enable_emotion = False  # Default OFF (experimental)
        
    def start(self):
        """Week 2 Enhanced + Posture: Start video processing thread with tracking reset."""
        if self.running:
            return
            
        self.running = True
        self.cap = cv2.VideoCapture(0)
        # Set lower resolution for better performance (target: >15 FPS)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
        self.cap.set(cv2.CAP_PROP_FPS, 15)  # Request 15 FPS from camera
        self.frame_count = 0
        self.frame_skip_counter = 0  # Week 2: Reset frame skip counter
        self.start_time = time.time()
        # Week 2: Reset blink tracking
        self.ear_history.clear()
        self.blink_timestamps.clear()
        # Posture: Reset slouch tracking
        self.slouch_start_time = None
        
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
        """
        Week 2 Enhanced: Main processing loop with frame skipping and blink tracking.
        
        Frame skipping: Process every Nth frame (FRAME_SKIP_N) to reduce CPU load.
        Timestamps are preserved correctly by using the actual frame capture time.
        """
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
            
            # Week 2: Frame skipping - only process every Nth frame
            self.frame_skip_counter += 1
            if self.frame_skip_counter < FRAME_SKIP_N:
                # Skip this frame but still update timestamp for next frame
                continue
            
            self.frame_skip_counter = 0  # Reset counter
            
            # Week 2: Compute blink rate (blinks per minute) over last 60 seconds
            current_timestamp = time.time()
            cutoff_time = current_timestamp - 60.0
            # Prune old blink timestamps
            while self.blink_timestamps and self.blink_timestamps[0] < cutoff_time:
                self.blink_timestamps.popleft()
            
            # Calculate blink rate
            if len(self.blink_timestamps) > 0:
                time_span = current_timestamp - min(self.blink_timestamps)
                if time_span > 0:
                    blink_rate_per_min = (len(self.blink_timestamps) / time_span) * 60.0
                else:
                    blink_rate_per_min = 0.0
            else:
                blink_rate_per_min = 0.0
                
            # Process frame with enhanced features (face + posture + emotion)
            result = process_frame(
                frame.copy(), 
                last_process_time, 
                self.draw_landmarks,
                self.ear_history,
                blink_rate_per_min,
                self.enable_posture,
                self.draw_pose,
                self.slouch_start_time,
                self.emotion_detector if self.enable_emotion else None
            )
            
            # Posture: Track slouching duration for alerts
            if result.get("posture") and result["posture"]:
                if result["posture"]["slouching"]:
                    if self.slouch_start_time is None:
                        self.slouch_start_time = current_timestamp
                else:
                    self.slouch_start_time = None  # Reset if not slouching
            
            # Week 2: Track blinks
            if result.get("blink_detected", False):
                self.blink_timestamps.append(current_timestamp)
            
            # Week 2: Add blink rate to result for potential display
            result["blink_rate_per_min"] = blink_rate_per_min
            
            last_process_time = current_time
            self.frame_count += 1
            
            # Store pose landmarks for calibration
            if result.get("pose_landmarks"):
                self.latest_pose_landmarks = result["pose_landmarks"]
            
            # Update latest result
            with self.lock:
                self.latest_result = result
                
            # Calculate FPS (accounting for frame skipping)
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                # FPS = processed_frames / elapsed_time
                result["fps"] = self.frame_count / elapsed
            else:
                result["fps"] = 0.0
            
            # Auto-disable emotion detection if FPS drops too low (performance protection)
            if self.enable_emotion and result["fps"] < 10.0 and elapsed > 5.0:
                # Only disable after 5 seconds of low FPS to avoid false positives
                print(f"⚠️ FPS dropped to {result['fps']:.1f}. Auto-disabling emotion detection for performance.")
                self.emotion_detector.disable()
                self.enable_emotion = False
                
    def get_latest_result(self):
        """Get the latest processing result."""
        with self.lock:
            return self.latest_result
    
    def toggle_emotion(self) -> bool:
        """
        Toggle emotion detection (experimental feature).
        Returns True if enabled, False if disabled.
        """
        if not _EMOTION_AVAILABLE or self.emotion_detector is None:
            print("⚠️ Emotion detection is not available. Install FER library: pip install fer")
            return False
        
        if self.enable_emotion:
            self.emotion_detector.disable()
            self.enable_emotion = False
            print("Emotion detection disabled")
            return False
        else:
            print("🧪 Loading emotion detection model (EXPERIMENTAL - may take a moment)...")
            print("⚠️ Emotion detection is experimental. Accuracy varies by lighting conditions.")
            success = self.emotion_detector.enable()
            if success:
                self.enable_emotion = True
                print("✅ Emotion detection enabled (EXPERIMENTAL)")
            else:
                print("❌ Failed to enable emotion detection. Check console for details.")
            return success
    
    def get_blink_rate(self) -> float:
        """
        Week 2: Get current blink rate (blinks per minute) over last 60 seconds.
        
        Returns:
            Blink rate in blinks per minute, or 0.0 if insufficient data
        """
        current_timestamp = time.time()
        cutoff_time = current_timestamp - 60.0
        
        # Count blinks in last 60 seconds
        recent_blinks = [ts for ts in self.blink_timestamps if ts >= cutoff_time]
        
        if len(recent_blinks) > 0:
            time_span = current_timestamp - min(recent_blinks)
            if time_span > 0:
                return (len(recent_blinks) / time_span) * 60.0
        
        return 0.0
            
    def toggle_landmarks(self):
        """Toggle face mesh landmarks display."""
        self.draw_landmarks = not self.draw_landmarks
    
    def toggle_posture(self):
        """Toggle posture detection (for performance)."""
        self.enable_posture = not self.enable_posture
    
    def toggle_pose_drawing(self):
        """Toggle pose landmark drawing on preview."""
        self.draw_pose = not self.draw_pose


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

    # Apple-style: subtle colors, single accent
    circle_color = "#007AFF"  # Single accent color
    track_color = "#e5e5ea"   # Light gray track
    status_color = "#1d1d1f" if is_focused else "#86868b"  # Near-black / gray

    # SVG progress ring: must use the true circumference for the chosen radius
    progress = max(0.0, min(1.0, focus_pct_60 / 100.0))
    r = 85
    circumference = 2 * 3.141592653589793 * r  # ~534.07
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
    if _EMOTION_AVAILABLE and st.session_state.video_processor.enable_emotion:
        emotion = st.session_state.get("current_emotion")
        emotion_conf = st.session_state.get("emotion_confidence", 0.0)
        
        if emotion:
            # Apple-style: subtle emotion colors
            emotion_colors = {
                "neutral": "#86868b",
                "frustrated": "#ff3b30",
                "tired": "#ff9500",
            }
            emotion_color = emotion_colors.get(emotion, "#86868b")
            # Show confidence warning if low
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
    
    # Only show if posture detection is enabled and session is running
    if not st.session_state.get("video_processor") or not st.session_state.video_processor.enable_posture:
        return
    
    if st.session_state.get("session_start_time", 0) == 0:
        return
    
    # Apple-style: clean, minimal posture display
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
    
    # Show alert if present (Apple-style subtle warning)
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
    
    # Performance check: Disable charts if FPS is too low
    current_fps = st.session_state.get("latest_fps", 0.0)
    if current_fps > 0 and current_fps < 15.0:
        # FPS is below target, skip charts to maintain performance
        return
    
    # Initialize chart data storage (optimized: 100 points, numpy arrays)
    if "chart_data" not in st.session_state:
        st.session_state.chart_data = {
            "focus_scores": np.array([], dtype=np.float32),
            "posture_scores": np.array([], dtype=np.float32),
            "timestamps": np.array([], dtype=np.float32),
            "last_chart_update": 0.0,
        }
    
    # Throttle updates: Only update data every 5 seconds
    current_time = time.time()
    last_update = st.session_state.chart_data.get("last_chart_update", 0.0)
    update_interval = 5.0  # Update every 5 seconds
    
    # Update data only if enough time has passed
    if current_time - last_update >= update_interval:
        if st.session_state.get("latest_focus_score") is not None:
            focus_score = float(st.session_state.get("latest_focus_score", 0))
            posture_score = float(st.session_state.get("posture_score", 0))
            
            # Append to numpy arrays (efficient)
            st.session_state.chart_data["focus_scores"] = np.append(
                st.session_state.chart_data["focus_scores"], focus_score
            )[-100:]  # Keep only last 100 points
            st.session_state.chart_data["posture_scores"] = np.append(
                st.session_state.chart_data["posture_scores"], posture_score
            )[-100:]
            st.session_state.chart_data["timestamps"] = np.append(
                st.session_state.chart_data["timestamps"], current_time
            )[-100:]
            
            st.session_state.chart_data["last_chart_update"] = current_time
    
    # Only render charts if we have enough data
    data_length = len(st.session_state.chart_data["timestamps"])
    if data_length < 2:
        return  # Need at least 2 data points
    
    # Use lightweight Streamlit native charts (no Plotly for real-time)
    # Pre-calculate statistics for efficiency
    focus_scores = st.session_state.chart_data["focus_scores"]
    posture_scores = st.session_state.chart_data["posture_scores"]
    
    # Calculate simple statistics (cached in session state)
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
    
    # Show live metrics (lightweight, no chart overhead)
    col_metrics = st.columns(3)
    with col_metrics[0]:
        st.metric("Focus Avg", f"{stats['focus_mean']:.1f}%", f"±{stats['focus_std']:.1f}%")
    with col_metrics[1]:
        st.metric("Posture Avg", f"{stats['posture_mean']:.1f}%")
    with col_metrics[2]:
        st.metric("Data Points", f"{data_length}/100")
    
    # Chart type selector (only render if user selects)
    chart_type = st.radio(
        "Chart Type",
        ["Focus Trend", "Posture Trend", "None"],
        horizontal=True,
        key="chart_type_selector",
        index=2  # Default to "None" to save performance
    )
    
    # Only render chart if user explicitly selects one
    if chart_type == "Focus Trend" and data_length >= 2:
        # Use lightweight Streamlit native chart
        if pd is not None:
            # Convert numpy arrays to DataFrame (only when needed)
            chart_df = pd.DataFrame({
                "Focus": focus_scores,
            })
            st.line_chart(chart_df, height=250, width='stretch')
        else:
            # Fallback: show simple text representation
            st.write(f"Focus trend: {stats['focus_mean']:.1f}% average")
    
    elif chart_type == "Posture Trend" and data_length >= 2:
        # Use lightweight Streamlit native chart
        if pd is not None:
            chart_df = pd.DataFrame({
                "Posture": posture_scores,
            })
            st.line_chart(chart_df, height=250, width='stretch')
        else:
            st.write(f"Posture trend: {stats['posture_mean']:.1f}% average")
    
    # Show update frequency info
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
        # Advanced analytics display
        wm = st.session_state.get("window_metrics") or {}
        wm_10min = wm.get("10min", {})
        wm_5min = wm.get("5min", {})
        wm_1min = wm.get("1min", {})
        
        # Session phase
        session_phase = st.session_state.get("session_phase")
        if session_phase:
            # Apple-style: subtle phase indicator
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
        
        # Window metrics - Apple-style clean grid
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
        
        # ML Prediction
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
        
        # Break suggestion - Apple-style subtle info
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
        # Old analytics display (backward compatibility)
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
        /* Apple-style Minimalist Design */
        
        /* Base colors - light, calm palette */
        body { 
            background: #f5f5f7; 
            color: #1d1d1f; 
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
        }
        .stApp { 
            background: #f5f5f7; 
        }
        
        /* Typography - light weight, generous spacing */
        .header-title { 
            font-size: 48px; 
            font-weight: 300; 
            color: #1d1d1f; 
            text-align: center; 
            margin-bottom: 0.5rem;
            letter-spacing: -0.5px;
            line-height: 1.1;
        }
        .header-subtitle { 
            font-size: 17px; 
            font-weight: 400;
            color: #86868b; 
            text-align: center;
            margin-bottom: 3rem;
            line-height: 1.5;
        }
        
        /* Buttons - clean, subtle, single accent */
        .stButton>button { 
            width: 100%; 
            border-radius: 12px; 
            padding: 0.875rem 1.5rem; 
            font-weight: 400;
            font-size: 17px;
            border: none;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .stButton>button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }
        .stButton>button:active {
            transform: translateY(0);
            box-shadow: 0 1px 2px rgba(0,0,0,0.08);
        }
        
        /* Button variants - single accent color */
        .start-btn>button { 
            background: #007AFF; 
            color: #1d1d1f; 
        }
        .start-btn>button:hover {
            background: #0051D5;
        }
        .stop-btn>button { 
            background: #f5f5f7; 
            color: #1d1d1f;
            border: 1px solid #d2d2d7;
        }
        .stop-btn>button:hover {
            background: #e8e8ed;
        }
        .toggle-btn>button { 
            background: #f5f5f7; 
            color: #1d1d1f;
            border: 1px solid #d2d2d7;
        }
        .toggle-btn>button:hover {
            background: #e8e8ed;
        }
        
        /* Card - subtle depth, no borders */
        .card { 
            background: #ffffff; 
            padding: 2rem; 
            border-radius: 18px; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border: none;
            margin-bottom: 2rem;
        }
        
        /* Checkboxes - clean styling with black text */
        .stCheckbox label {
            font-weight: 400;
            font-size: 15px;
            color: #1d1d1f !important;
            line-height: 1.5;
        }
        .stCheckbox label p {
            color: #1d1d1f !important;
        }
        .stCheckbox {
            color: #1d1d1f !important;
        }
        .stCheckbox > label {
            color: #1d1d1f !important;
        }
        .stCheckbox > label > div {
            color: #1d1d1f !important;
        }
        /* Override Streamlit default white text */
        div[data-testid="stCheckbox"] label {
            color: #1d1d1f !important;
        }
        div[data-testid="stCheckbox"] label p {
            color: #1d1d1f !important;
        }
        
        /* Dividers - subtle */
        hr {
            border: none;
            border-top: 0.5px solid #d2d2d7;
            margin: 2rem 0;
        }
        
        /* Info/Warning boxes - subtle */
        .stAlert {
            border-radius: 12px;
            border: none;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        
        /* Streamlit default overrides */
        .stMarkdown {
            color: #1d1d1f;
        }
        
        /* Remove default Streamlit borders */
        .element-container {
            margin-bottom: 1.5rem;
        }
        
        /* Image styling - rounded corners */
        .stImage img {
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        /* Smooth transitions for all interactive elements */
        * {
            transition: background-color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
                        color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
                        transform 0.2s cubic-bezier(0.4, 0, 0.2, 1),
                        box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        /* Input fields - Apple-style */
        .stTextInput>div>div>input,
        .stNumberInput>div>div>input {
            border-radius: 8px;
            border: 0.5px solid #d2d2d7;
            padding: 0.75rem 1rem;
            font-size: 15px;
        }
        
        /* Select boxes */
        .stSelectbox>div>div>select {
            border-radius: 8px;
            border: 0.5px solid #d2d2d7;
        }
        
        /* Consistent spacing throughout */
        .main .block-container {
            padding-top: 4rem;
            padding-bottom: 4rem;
            max-width: 900px;
        }
        
        /* Remove Streamlit default styling */
        .stMarkdown p {
            margin-bottom: 0.5rem;
        }
        
        /* Focus states - subtle */
        .stButton>button:focus {
            outline: none;
            box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.1);
        }
        
        /* Checkbox styling */
        .stCheckbox {
            margin-bottom: 1rem;
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
    # Initialize persistent placeholder for preview (prevents duplicate panels)
    if "preview_placeholder" not in st.session_state:
        st.session_state.preview_placeholder = None
    if "preview_caption_placeholder" not in st.session_state:
        st.session_state.preview_caption_placeholder = None
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
            # New advanced analytics engine
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
            # Old analytics (backward compatibility)
            if "db_manager" not in st.session_state:
                st.session_state.db_manager = DatabaseManager()
                st.session_state.db_manager.initialize()
            
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
    else:
        # Analytics not available - set defaults
        st.session_state.current_session_id = None
        st.session_state.window_metrics = {}
        st.session_state.break_suggestion = None

    # Header - Apple-style minimal
    st.markdown('<div class="header-title">StudySensei</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="header-subtitle">Real-time focus tracking with advanced analytics</div>',
        unsafe_allow_html=True,
    )

    # Controls in a card - Apple-style clean container
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
                        
                        # Reset analytics modules
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
                        
                        # Reset analytics modules
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
                        # Get session statistics
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
                # Clear placeholders when stopping
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
        
        # Additional toggles - Apple-style clean layout
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
                # Clear preview immediately to prevent frozen frame display
                st.session_state.preview_image = None
                # Force rerun to clear any cached display
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
                    # Clear preview immediately to prevent frozen frame display
                    st.session_state.preview_image = None
                    # Force rerun to clear any cached display
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
        
        # Experimental Emotion Detection toggle - Apple-style
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
            
            # Update posture state
            if result.get("posture") and result["posture"]:
                posture_data = result["posture"]
                st.session_state.posture_score = posture_data["score"]
                st.session_state.posture_status = "Good Posture" if posture_data["good_posture"] else "Needs Adjustment"
                st.session_state.posture_alert = posture_data.get("alert_message")
                # Store new metrics
                st.session_state.posture_neck_angle = posture_data.get("neck_angle", 0.0)
                st.session_state.posture_shoulder_roll = posture_data.get("shoulder_roll", 0.0)
                
                # Update posture history for analytics
                if st.session_state.session_start_time > 0:
                    st.session_state.posture_history.append((
                        result["timestamp"],
                        posture_data["good_posture"]
                    ))
            else:
                st.session_state.posture_score = 0.0
                st.session_state.posture_status = "WAITING"
                st.session_state.posture_alert = None
            
            # Update emotion state (experimental)
            if result.get("emotion") and result["emotion"]:
                emotion_data = result["emotion"]
                st.session_state.current_emotion = emotion_data.get("state")
                st.session_state.emotion_confidence = emotion_data.get("confidence", 0.0)
            else:
                st.session_state.current_emotion = None
                st.session_state.emotion_confidence = 0.0
            
            # Analytics and Database Integration (if available)
            if _ANALYTICS_AVAILABLE and st.session_state.current_session_id and st.session_state.session_start_time > 0:
                timestamp = result["timestamp"]
                focus_score = score
                posture_score = st.session_state.get("posture_score", 0.0)
                gaze_confidence = result.get("gaze_confidence", 0.0)
                is_slouching = result.get("posture", {}).get("slouching", False) if result.get("posture") else False
                is_present = focused or score > 0  # User is present if we have any focus data
                session_duration = timestamp - st.session_state.session_start_time
                
                if _NEW_ANALYTICS:
                    # Advanced analytics engine
                    try:
                        # Update time-series analyzer
                        st.session_state.analyzer.add_data_point(timestamp, focus_score, posture_score)
                        
                        # Update focus decay detector
                        decay_event = st.session_state.decay_detector.update(timestamp, focus_score)
                        
                        # Update session statistics
                        st.session_state.session_stats.add_point(timestamp, focus_score, posture_score)
                        
                        # Update behavior modeler (weighted focus scoring)
                        # Map emotion to score: neutral=0.7, frustrated=0.3, tired=0.4
                        emotion_score = 0.5  # Default neutral
                        if st.session_state.get("current_emotion"):
                            emotion = st.session_state.current_emotion
                            if emotion == "neutral":
                                emotion_score = 0.7
                            elif emotion == "frustrated":
                                emotion_score = 0.3  # Reduces focus
                            elif emotion == "tired":
                                emotion_score = 0.4  # Reduces focus
                        
                        behavior_result = st.session_state.behavior_modeler.update(
                            timestamp, gaze_confidence, posture_score, emotion_score, is_slouching, is_present
                        )
                        computed_focus = behavior_result.get("focus_score", focus_score)
                        
                        # If emotion is enabled and detected, apply adjustment
                        if st.session_state.get("current_emotion") and st.session_state.video_processor.enable_emotion:
                            emotion = st.session_state.current_emotion
                            if emotion == "frustrated":
                                # Reduce focus by 10% if frustrated
                                computed_focus = max(0, computed_focus * 0.9)
                            elif emotion == "tired":
                                # Reduce focus by 5% if tired
                                computed_focus = max(0, computed_focus * 0.95)
                        detected_pattern = behavior_result.get("detected_pattern")
                        session_phase = behavior_result.get("session_phase")
                        st.session_state.session_phase = session_phase
                        
                        # Save to database (chunked, every 2 seconds)
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
                        
                        # Compute window metrics (every 5 seconds)
                        if int(timestamp) % 5 == 0:
                            try:
                                wm = st.session_state.analyzer.get_all_window_metrics(timestamp)
                                st.session_state.window_metrics = wm
                                
                                # Get focus trend for break recommendation
                                focus_trend = wm.get("10min", {}).get("trend", 0.0)
                                baseline_focus = wm.get("10min", {}).get("mean", focus_score)
                                
                                # Break recommendation (prioritize if tired/frustrated)
                                break_priority = "normal"
                                if st.session_state.get("current_emotion") in ["tired", "frustrated"]:
                                    break_priority = "high"
                                
                                break_rec = st.session_state.break_recommender.suggest_break(
                                    timestamp,
                                    focus_trend,
                                    session_phase,
                                    session_duration,
                                    computed_focus,
                                    baseline_focus,
                                )
                                if break_rec:
                                    st.session_state.break_suggestion = break_rec.get("message")
                            except Exception:
                                pass
                        
                        # ML prediction (every 10 seconds)
                        if int(timestamp) % 10 == 0:
                            try:
                                # Get recent focus scores for prediction
                                recent_scores = [f for _, f in st.session_state.focus_history[-20:]] if len(st.session_state.focus_history) >= 20 else [focus_score]
                                volatility = st.session_state.window_metrics.get("10min", {}).get("volatility", 0.0)
                                
                                prediction = st.session_state.ml_predictor.predict(
                                    recent_scores,
                                    posture_score,
                                    session_duration,
                                    volatility,
                                )
                                if prediction:
                                    st.session_state.focus_prediction = prediction
                                    
                                    # Add observation for training
                                    st.session_state.ml_predictor.add_observation(
                                        timestamp, computed_focus, posture_score, session_duration, volatility, recent_scores
                                    )
                            except Exception:
                                pass
                    except Exception as e:
                        pass  # Silently handle errors
                else:
                    # Old analytics (backward compatibility)
                    # Save to database (async-like: batch every few seconds)
                    if int(timestamp) % 2 == 0:  # Save every 2 seconds to reduce DB writes
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
                        except Exception as e:
                            pass  # Silently handle DB errors to maintain real-time performance
                    
                    # Update time-series analyzer
                    try:
                        st.session_state.analyzer.add_data_point(timestamp, focus_score, posture_score)
                    except Exception:
                        pass
                    
                    # Update behavior modeler
                    try:
                        behavior_pattern = st.session_state.behavior_modeler.update(
                            timestamp, focus_score, posture_score, is_slouching, is_present
                        )
                        
                        if behavior_pattern:
                            # Save behavior pattern to database
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
                    
                    # Update ML predictor
                    try:
                        st.session_state.ml_predictor.add_observation(
                            timestamp, focus_score, posture_score, gaze_confidence
                        )
                    except Exception:
                        pass
                    
                    # Compute window metrics (update every 5 seconds for performance)
                    if int(timestamp) % 5 == 0:
                        try:
                            st.session_state.window_metrics = st.session_state.analyzer.get_all_window_metrics(timestamp)
                        except Exception:
                            pass
                    
                    # Check for break suggestions (every 30 seconds)
                    if int(timestamp) % 30 == 0:
                        try:
                            st.session_state.break_suggestion = st.session_state.behavior_modeler.suggest_break(timestamp)
                        except Exception:
                            pass
    
    # Focus Metrics Display
    render_focus_metrics()
    
    # Posture Metrics Display
    render_posture_metrics()
    
    # Interactive Analytics Dashboard
    render_interactive_analytics()
    
    # Analytics Display
    render_analytics()
    
    # Preview Image (if enabled) - Apple-style subtle container
    # Use persistent placeholder to prevent duplicate panels
    # Always create placeholders in the same location (prevents layout shifts)
    if st.session_state.preview_placeholder is None:
        st.session_state.preview_placeholder = st.empty()
    if st.session_state.preview_caption_placeholder is None:
        st.session_state.preview_caption_placeholder = st.empty()
    
    # Update or clear placeholders based on preview state
    if st.session_state.show_preview and st.session_state.preview_image is not None:
        caption_text = "Live Preview" + (" (with face mesh)" if st.session_state.video_processor.draw_landmarks else " (clean)")
        
        # Update existing placeholders (don't create new components)
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
        # Clear placeholders when preview is disabled (but keep placeholder objects)
        st.session_state.preview_caption_placeholder.empty()
        st.session_state.preview_placeholder.empty()
    
    # Auto-refresh for real-time updates
    time.sleep(0.1)  # Small delay to prevent excessive CPU usage
    st.rerun()


if __name__ == "__main__":
    main()