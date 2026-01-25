"""Frame processing pipeline combining gaze, posture, and emotion detection."""

import cv2
import time
import numpy as np
from typing import Optional
from collections import deque

from .gaze import compute_focus
from .posture import detect_posture
# FIXED: Import simplified posture detection as alternative
try:
    from .posture_simple import compute_simple_posture, SimplePostureResult
    _SIMPLE_POSTURE_AVAILABLE = True
except ImportError:
    _SIMPLE_POSTURE_AVAILABLE = False
    SimplePostureResult = None
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
    emotion_detector = None,
    process_face: bool = True  # New parameter to control face processing
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
        process_face: Whether to process face mesh (can be skipped for performance)
    
    Returns:
        Dictionary with focus, posture, and emotion results
    
    Note: Posture detection runs EVERY frame when enabled (not affected by frame skipping)
    to ensure responsive posture feedback.
    """
    h, w, _ = image_bgr.shape

    # Convert to RGB once (reused for both face and pose)
    rgb_frame = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb_frame.flags.writeable = False
    
    # Process pose FIRST (if enabled) - ALWAYS runs every frame for responsiveness
    # This ensures posture detection is never skipped, even when face processing is skipped
    posture_result = None
    pose_landmarks_stored = None
    if enable_posture:
        try:
            pose = get_pose()
            if pose is None:
                # Pose not initialized - this should not happen, but handle gracefully
                print("WARNING: MediaPipe Pose not initialized")
            else:
                pose_results = pose.process(rgb_frame)
                
                if pose_results and pose_results.pose_landmarks:
                    pose_landmarks_stored = pose_results.pose_landmarks  # Store for calibration
                    # FIXED: Use simplified 3-point posture detection (more reliable)
                    if _SIMPLE_POSTURE_AVAILABLE:
                        simple_result = compute_simple_posture(pose_results.pose_landmarks, w, h, slouch_start_time)
                        # Convert SimplePostureResult to PostureResult format for compatibility
                        from .posture import PostureResult
                        posture_result = PostureResult(
                            good_posture=simple_result.good_posture,
                            score=simple_result.score,
                            shoulder_ear_angle=0.0,  # Not used in simple mode
                            forward_head_ratio=simple_result.forward_lean,
                            neck_angle=0.0,  # Not used in simple mode
                            shoulder_roll=simple_result.shoulder_levelness,
                            slouching=simple_result.slouching,
                            text_neck=simple_result.text_neck,
                            alert_message=simple_result.alert_message
                        )
                    else:
                        # Fallback to original detection
                        posture_result = detect_posture(pose_results.pose_landmarks, w, h, slouch_start_time)
                    
                    # Draw pose landmarks if requested
                    # FIXED: Only draw relevant body landmarks, not face points
                    if draw_pose:
                        # MediaPipe Pose has 33 landmarks (0-32)
                        # Relevant for posture: shoulders (11,12), hips (23,24), ears (7,8), nose (0)
                        # Draw all pose landmarks but verify they're body points, not face
                        mp_drawing.draw_landmarks(
                            image=image_bgr,
                            landmark_list=pose_results.pose_landmarks,
                            connections=mp_pose.POSE_CONNECTIONS,
                            landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style(),
                        )
                        # Debug: Draw landmark indices for verification (optional)
                        # Uncomment to see which landmarks are being detected
                        # for idx, landmark in enumerate(pose_results.pose_landmarks.landmark):
                        #     if landmark.visibility > 0.5:  # Only visible landmarks
                        #         x = int(landmark.x * w)
                        #         y = int(landmark.y * h)
                        #         cv2.putText(image_bgr, str(idx), (x, y), 
                        #                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 0), 1)
        except Exception as e:
            # Handle any errors in posture detection gracefully
            print(f"Error in posture detection: {e}")
            posture_result = None
    
    # Process face mesh (can be skipped for performance)
    # FIXED: Always try to process face mesh to maintain tracking continuity
    # Even when process_face=False, we still process but less frequently to maintain tracking
    face_results = None
    face_mesh = get_face_mesh()
    if process_face:
        face_results = face_mesh.process(rgb_frame)
    else:
        # Even when skipping, try a quick process to maintain tracking
        # This prevents tracking from dropping when frames are skipped
        try:
            face_results = face_mesh.process(rgb_frame)
        except Exception:
            pass  # Silently fail if processing fails during skip
    
    rgb_frame.flags.writeable = True

    focused = False
    score = 0.0
    gaze_confidence = 0.0
    blink_detected = False

    if face_results and face_results.multi_face_landmarks:
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
