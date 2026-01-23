"""Gaze detection and focus computation using MediaPipe FaceMesh."""

import numpy as np
from dataclasses import dataclass
from typing import Tuple
from collections import deque

from utils.constants import (
    LEFT_EYE_LANDMARKS, RIGHT_EYE_LANDMARKS,
    LEFT_EYE_EAR_POINTS, RIGHT_EYE_EAR_POINTS,
    EAR_THRESHOLD, EAR_NOISE_TOLERANCE,
    GAZE_CONFIDENCE_WEIGHT, BLINK_FATIGUE_WEIGHT
)


@dataclass
class FocusResult:
    """Result of focus computation."""
    focused: bool
    score: float  # 0-100
    gaze_confidence: float = 0.0  # Iris-based gaze confidence [0.0, 1.0]
    blink_detected: bool = False  # Whether a blink was detected in this frame


def _lm_to_px(landmarks, idx: int, width: int, height: int) -> Tuple[int, int]:
    """Convert MediaPipe landmark to pixel coordinates."""
    lm = landmarks.landmark[idx]
    return int(lm.x * width), int(lm.y * height)


def compute_iris_gaze_confidence(face_landmarks, frame_width: int, frame_height: int) -> float:
    """
    Compute iris-based gaze confidence using MediaPipe iris landmarks.
    
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
                           (right_eye_inner[1] - right_eye_inner[1]) ** 2) ** 0.5
        
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
    Compute Eye Aspect Ratio (EAR) for blink detection.
    
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
    Detect blinks using Eye Aspect Ratio with noise tolerance.
    
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
    Compute focus score combining iris-based gaze and blink-rate fatigue.
    
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
    
    # Iris-based gaze confidence
    gaze_confidence = compute_iris_gaze_confidence(face_landmarks, frame_width, frame_height)
    
    # Blink detection
    blink_detected, current_ear = detect_blink(face_landmarks, frame_width, frame_height, previous_ear_history)
    
    # Blink-rate-based fatigue signal
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
    
    # Combined focus score with configurable weights
    # Score = (gaze_confidence * GAZE_WEIGHT) + (fatigue_signal * BLINK_WEIGHT)
    combined_score = (gaze_confidence * GAZE_CONFIDENCE_WEIGHT) + (fatigue_signal * BLINK_FATIGUE_WEIGHT)
    
    # Convert to 0-100 scale
    score = combined_score * 100.0
    
    # Threshold for focused state (can be tuned)
    focused = score >= 60.0
    
    return FocusResult(focused=focused, score=score, gaze_confidence=gaze_confidence, blink_detected=blink_detected)
