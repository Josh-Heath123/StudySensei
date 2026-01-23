"""Frame processing pipeline combining gaze, posture, and emotion detection."""

import cv2
import time
import numpy as np
from typing import Optional
from collections import deque

from .gaze import compute_focus
from .posture import detect_posture
from .mediapipe_setup import get_face_mesh, get_pose
from .mediapipe_setup import mp_drawing, mp_drawing_styles, mp_pose, mp_face_mesh


def process_frame(
    image_bgr: np.ndarray,
    prev_timestamp: float,
    draw_landmarks: bool = True,
    previous_ear_history: deque = None,
    blink_rate_per_min: float = 0.0,
    enable_posture: bool = True,
    draw_pose: bool = False,
    slouch_start_time: Optional[float] = None,
    emotion_detector = None
) -> dict:
    """
    Process a single BGR frame for both focus and posture.
    
    Args:
        image_bgr: BGR image frame
        prev_timestamp: Previous frame timestamp
        draw_landmarks: Whether to draw face mesh landmarks
        previous_ear_history: Deque for EAR temporal smoothing
        blink_rate_per_min: Current blink rate for fatigue signal
        enable_posture: Whether to enable posture detection (toggleable for performance)
        draw_pose: Whether to draw pose landmarks on preview
        slouch_start_time: Timestamp when slouching started (for alerts)
        emotion_detector: Optional emotion detector instance
    
    Returns:
        Dictionary with focus, posture, and emotion results
    """
    h, w, _ = image_bgr.shape
    face_mesh = get_face_mesh()

    # Convert to RGB once (reused for both face and pose)
    rgb_frame = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb_frame.flags.writeable = False
    
    # Process face mesh
    face_results = face_mesh.process(rgb_frame)
    
    # Process pose (if enabled) - reuse same RGB frame for minimal overhead
    posture_result = None
    pose_landmarks_stored = None
    if enable_posture:
        pose = get_pose()
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
            # Use enhanced focus computation with iris gaze and blink detection
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
        "gaze_confidence": gaze_confidence,
        "blink_detected": blink_detected,
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
