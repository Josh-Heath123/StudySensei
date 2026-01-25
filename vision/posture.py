"""
Enhanced Posture Detection Module for StudySensei
Uses MediaPipe Pose to detect slouching, forward head posture, and calculate posture scores.
Now includes multiple metrics and calibration support.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, Dict
import time
import json
import os

# MediaPipe Pose landmark indices (33 total landmarks: 0-32)
# FIXED: Verified indices are correct for MediaPipe Pose model
# These are BODY landmarks, not face landmarks (FaceMesh uses different indices)
# Reference: https://google.github.io/mediapipe/solutions/pose.html
LEFT_SHOULDER = 11  # Left shoulder
RIGHT_SHOULDER = 12  # Right shoulder
LEFT_EAR = 7  # Left ear (body landmark, not face mesh)
RIGHT_EAR = 8  # Right ear (body landmark, not face mesh)
NOSE = 0  # Nose (body landmark, not face mesh)
LEFT_HIP = 23  # Left hip
RIGHT_HIP = 24  # Right hip
LEFT_ELBOW = 13  # Left elbow
RIGHT_ELBOW = 14  # Right elbow
LEFT_WRIST = 15  # Left wrist
RIGHT_WRIST = 16  # Right wrist

# Posture thresholds (configurable, can be calibrated)
SHOULDER_EAR_ANGLE_THRESHOLD = 15.0  # degrees - angle below which is considered slouching
FORWARD_HEAD_THRESHOLD = 0.15  # normalized distance - head forward beyond this is "text neck"
NECK_ANGLE_THRESHOLD = 10.0  # degrees - neck angle deviation from vertical
SHOULDER_ROLL_THRESHOLD = 5.0  # degrees - shoulder roll/rotation threshold
SLOUCH_ALERT_DURATION = 30.0  # seconds - alert after slouching for this long

# Calibration file path
CALIBRATION_FILE = "posture_calibration.json"


@dataclass
class PostureCalibration:
    """Calibration data for user's baseline posture."""
    shoulder_ear_angle_baseline: float = 20.0
    forward_head_ratio_baseline: float = 0.10
    neck_angle_baseline: float = 0.0
    shoulder_roll_baseline: float = 0.0
    calibrated: bool = False
    calibration_timestamp: Optional[float] = None


@dataclass
class PostureResult:
    """Enhanced posture detection result with multiple metrics."""
    good_posture: bool
    score: float  # 0-100
    shoulder_ear_angle: float  # degrees
    forward_head_ratio: float  # normalized distance
    neck_angle: float  # degrees - neck angle relative to spine
    shoulder_roll: float  # degrees - shoulder rotation/roll
    slouching: bool
    text_neck: bool
    alert_message: Optional[str] = None


# Global calibration state
_calibration: Optional[PostureCalibration] = None


def load_calibration() -> PostureCalibration:
    """Load calibration from file if it exists."""
    global _calibration
    if _calibration is not None:
        return _calibration
    
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                _calibration = PostureCalibration(**data)
                return _calibration
        except Exception:
            pass
    
    _calibration = PostureCalibration()
    return _calibration


def save_calibration(calibration: PostureCalibration) -> None:
    """Save calibration to file."""
    global _calibration
    _calibration = calibration
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump({
                'shoulder_ear_angle_baseline': calibration.shoulder_ear_angle_baseline,
                'forward_head_ratio_baseline': calibration.forward_head_ratio_baseline,
                'neck_angle_baseline': calibration.neck_angle_baseline,
                'shoulder_roll_baseline': calibration.shoulder_roll_baseline,
                'calibrated': calibration.calibrated,
                'calibration_timestamp': calibration.calibration_timestamp,
            }, f)
    except Exception:
        pass


def calibrate_posture(pose_landmarks, frame_width: int, frame_height: int) -> bool:
    """
    Calibrate posture baseline from current pose.
    
    Args:
        pose_landmarks: MediaPipe Pose landmarks
        frame_width: Frame width
        frame_height: Frame height
    
    Returns:
        True if calibration successful, False otherwise
    """
    try:
        # Calculate all metrics
        shoulder_ear_angle = compute_shoulder_ear_angle(pose_landmarks, frame_width, frame_height)
        forward_head_ratio = compute_forward_head_ratio(pose_landmarks, frame_width, frame_height)
        neck_angle = compute_neck_angle(pose_landmarks, frame_width, frame_height)
        shoulder_roll = compute_shoulder_roll(pose_landmarks, frame_width, frame_height)
        
        if (shoulder_ear_angle is None or forward_head_ratio is None or 
            neck_angle is None or shoulder_roll is None):
            return False
        
        # Create calibration
        calibration = PostureCalibration(
            shoulder_ear_angle_baseline=shoulder_ear_angle,
            forward_head_ratio_baseline=forward_head_ratio,
            neck_angle_baseline=neck_angle,
            shoulder_roll_baseline=shoulder_roll,
            calibrated=True,
            calibration_timestamp=time.time()
        )
        
        save_calibration(calibration)
        return True
    except Exception:
        return False


def _pose_lm_to_px(landmarks, idx: int, width: int, height: int) -> Tuple[int, int]:
    """Convert MediaPipe Pose landmark to pixel coordinates."""
    lm = landmarks.landmark[idx]
    return int(lm.x * width), int(lm.y * height)


def calculate_angle(p1: Tuple[int, int], p2: Tuple[int, int], p3: Tuple[int, int]) -> float:
    """
    Calculate angle at p2 formed by p1-p2-p3.
    
    Args:
        p1: First point
        p2: Vertex point (angle is calculated here)
        p3: Third point
    
    Returns:
        Angle in degrees (0-180)
    """
    # Convert to numpy arrays
    a = np.array(p1)
    b = np.array(p2)
    c = np.array(p3)
    
    # Calculate vectors
    ba = a - b
    bc = c - b
    
    # Calculate angle using dot product
    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)  # Avoid numerical errors
    angle = np.arccos(cosine_angle)
    
    return np.degrees(angle)


def compute_shoulder_ear_angle(pose_landmarks, frame_width: int, frame_height: int) -> Optional[float]:
    """
    Calculate shoulder-ear angle for slouch detection.
    
    FIXED: Added validation to ensure landmarks are valid and visible.
    MediaPipe Pose landmarks: 0-32 (33 total)
    - Shoulders: 11 (left), 12 (right)
    - Ears: 7 (left), 8 (right) - these are body landmarks, not face
    
    Algorithm:
    - Get left/right shoulder and ear positions
    - Calculate angle between shoulder line and ear-to-shoulder line
    - Lower angle indicates slouching (head forward and down)
    
    Returns:
        Angle in degrees, or None if landmarks not available
    """
    try:
        # FIXED: Validate landmark indices are within MediaPipe Pose range (0-32)
        if len(pose_landmarks.landmark) < 33:
            return None  # Invalid pose data
        
        # Get landmarks with visibility check
        left_shoulder_lm = pose_landmarks.landmark[LEFT_SHOULDER]
        right_shoulder_lm = pose_landmarks.landmark[RIGHT_SHOULDER]
        left_ear_lm = pose_landmarks.landmark[LEFT_EAR]
        
        # FIXED: Check visibility - MediaPipe provides visibility score (0-1)
        # Only use landmarks that are actually visible
        if (left_shoulder_lm.visibility < 0.5 or 
            right_shoulder_lm.visibility < 0.5 or 
            left_ear_lm.visibility < 0.5):
            return None  # Landmarks not visible enough
        
        left_shoulder = _pose_lm_to_px(pose_landmarks, LEFT_SHOULDER, frame_width, frame_height)
        right_shoulder = _pose_lm_to_px(pose_landmarks, RIGHT_SHOULDER, frame_width, frame_height)
        left_ear = _pose_lm_to_px(pose_landmarks, LEFT_EAR, frame_width, frame_height)
        
        # Validate coordinates are reasonable (within frame bounds)
        if (left_shoulder[0] < 0 or left_shoulder[0] > frame_width or
            left_shoulder[1] < 0 or left_shoulder[1] > frame_height or
            right_shoulder[0] < 0 or right_shoulder[0] > frame_width or
            right_shoulder[1] < 0 or right_shoulder[1] > frame_height or
            left_ear[0] < 0 or left_ear[0] > frame_width or
            left_ear[1] < 0 or left_ear[1] > frame_height):
            return None  # Invalid coordinates
        
        # Calculate shoulder midpoint
        shoulder_mid = ((left_shoulder[0] + right_shoulder[0]) / 2,
                        (left_shoulder[1] + right_shoulder[1]) / 2)
        
        # Calculate angle: shoulder_mid -> left_ear -> left_shoulder
        angle = calculate_angle(shoulder_mid, left_ear, left_shoulder)
        
        return angle
    except (IndexError, KeyError, AttributeError, ValueError):
        return None


def compute_forward_head_ratio(pose_landmarks, frame_width: int, frame_height: int) -> Optional[float]:
    """
    Detect forward head posture (text neck).
    
    FIXED: Added validation for landmark visibility and coordinates.
    MediaPipe Pose nose landmark (0) is a body landmark, not face mesh.
    
    Algorithm:
    - Measure horizontal distance from nose to shoulder line
    - Normalize by shoulder width
    - Higher ratio = more forward head posture
    
    Returns:
        Normalized forward head ratio, or None if landmarks not available
    """
    try:
        # FIXED: Validate landmark count and visibility
        if len(pose_landmarks.landmark) < 33:
            return None
        
        left_shoulder_lm = pose_landmarks.landmark[LEFT_SHOULDER]
        right_shoulder_lm = pose_landmarks.landmark[RIGHT_SHOULDER]
        nose_lm = pose_landmarks.landmark[NOSE]
        
        # Check visibility
        if (left_shoulder_lm.visibility < 0.5 or 
            right_shoulder_lm.visibility < 0.5 or 
            nose_lm.visibility < 0.5):
            return None
        
        left_shoulder = _pose_lm_to_px(pose_landmarks, LEFT_SHOULDER, frame_width, frame_height)
        right_shoulder = _pose_lm_to_px(pose_landmarks, RIGHT_SHOULDER, frame_width, frame_height)
        nose = _pose_lm_to_px(pose_landmarks, NOSE, frame_width, frame_height)
        
        # Calculate shoulder width
        shoulder_width = ((left_shoulder[0] - right_shoulder[0]) ** 2 + 
                          (left_shoulder[1] - right_shoulder[1]) ** 2) ** 0.5
        
        if shoulder_width < 10:  # Too small, invalid
            return None
        
        # Calculate shoulder midpoint
        shoulder_mid_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        shoulder_mid_y = (left_shoulder[1] + right_shoulder[1]) / 2.0
        
        # Horizontal distance from nose to shoulder midpoint
        forward_distance = abs(nose[0] - shoulder_mid_x)
        
        # Normalize by shoulder width
        forward_ratio = forward_distance / shoulder_width
        
        return forward_ratio
    except (IndexError, KeyError, AttributeError):
        return None


def compute_neck_angle(pose_landmarks, frame_width: int, frame_height: int) -> Optional[float]:
    """
    Calculate neck angle relative to spine (vertical alignment).
    
    Algorithm:
    - Use ear midpoint and shoulder midpoint to define neck line
    - Calculate angle of neck line relative to vertical (spine)
    - 0 degrees = perfectly vertical, higher = more deviation
    
    Returns:
        Neck angle in degrees, or None if landmarks not available
    """
    try:
        left_shoulder = _pose_lm_to_px(pose_landmarks, LEFT_SHOULDER, frame_width, frame_height)
        right_shoulder = _pose_lm_to_px(pose_landmarks, RIGHT_SHOULDER, frame_width, frame_height)
        left_ear = _pose_lm_to_px(pose_landmarks, LEFT_EAR, frame_width, frame_height)
        right_ear = _pose_lm_to_px(pose_landmarks, RIGHT_EAR, frame_width, frame_height)
        
        # Calculate midpoints
        shoulder_mid = ((left_shoulder[0] + right_shoulder[0]) / 2,
                       (left_shoulder[1] + right_shoulder[1]) / 2)
        ear_mid = ((left_ear[0] + right_ear[0]) / 2,
                   (left_ear[1] + right_ear[1]) / 2)
        
        # Calculate neck vector (from shoulder to ear)
        neck_vector = np.array([ear_mid[0] - shoulder_mid[0], 
                               ear_mid[1] - shoulder_mid[1]])
        
        # Vertical vector (pointing up)
        vertical_vector = np.array([0, -1])
        
        # Calculate angle between neck vector and vertical
        dot_product = np.dot(neck_vector, vertical_vector)
        neck_magnitude = np.linalg.norm(neck_vector)
        
        if neck_magnitude < 1e-6:
            return None
        
        cosine_angle = dot_product / neck_magnitude
        cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
        angle = np.arccos(cosine_angle)
        
        # Convert to degrees and calculate deviation from vertical
        angle_degrees = np.degrees(angle)
        deviation = abs(90.0 - angle_degrees)  # Deviation from vertical
        
        return deviation
    except (IndexError, KeyError, AttributeError):
        return None


def compute_shoulder_roll(pose_landmarks, frame_width: int, frame_height: int) -> Optional[float]:
    """
    Calculate shoulder roll/rotation (asymmetry).
    
    Algorithm:
    - Compare left and right shoulder heights
    - Calculate angle of shoulder line relative to horizontal
    - Higher angle = more shoulder roll/rotation
    
    Returns:
        Shoulder roll angle in degrees, or None if landmarks not available
    """
    try:
        left_shoulder = _pose_lm_to_px(pose_landmarks, LEFT_SHOULDER, frame_width, frame_height)
        right_shoulder = _pose_lm_to_px(pose_landmarks, RIGHT_SHOULDER, frame_width, frame_height)
        
        # Calculate shoulder line vector
        shoulder_vector = np.array([right_shoulder[0] - left_shoulder[0],
                                   right_shoulder[1] - left_shoulder[1]])
        
        # Horizontal vector (pointing right)
        horizontal_vector = np.array([1, 0])
        
        # Calculate angle between shoulder line and horizontal
        dot_product = np.dot(shoulder_vector, horizontal_vector)
        shoulder_magnitude = np.linalg.norm(shoulder_vector)
        
        if shoulder_magnitude < 1e-6:
            return None
        
        cosine_angle = dot_product / shoulder_magnitude
        cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
        angle = np.arccos(cosine_angle)
        
        # Convert to degrees and calculate deviation from horizontal
        angle_degrees = np.degrees(angle)
        deviation = abs(90.0 - angle_degrees)  # Deviation from horizontal
        
        return deviation
    except (IndexError, KeyError, AttributeError):
        return None


def compute_posture_score(shoulder_ear_angle: Optional[float], 
                         forward_head_ratio: Optional[float],
                         neck_angle: Optional[float],
                         shoulder_roll: Optional[float],
                         calibration: Optional[PostureCalibration] = None) -> Tuple[float, bool, bool]:
    """
    Compute overall posture score (0-100) using simplified grey zone approach.
    
    SIMPLIFIED: No calibration - uses fixed ideal ranges with tolerance zones.
    Grey zone approach: Within acceptable range = 95-100%, outside = proportional penalty.
    
    Uses weighted combination of:
    1. Shoulder-ear angle (30% weight) - primary slouch indicator
    2. Forward head ratio (25% weight) - text neck indicator
    3. Neck angle (25% weight) - neck alignment
    4. Shoulder roll (20% weight) - shoulder symmetry
    
    Args:
        shoulder_ear_angle: Angle in degrees (ideal: 85-95°, lower = more slouching)
        forward_head_ratio: Normalized forward head distance (ideal: <0.10, higher = more text neck)
        neck_angle: Neck angle deviation from vertical (ideal: <5°, higher = worse)
        shoulder_roll: Shoulder roll/rotation angle (ideal: <3°, higher = worse)
        calibration: Ignored (kept for API compatibility)
    
    Returns:
        Tuple of (score: float, slouching: bool, text_neck: bool)
    """
    if all(x is None for x in [shoulder_ear_angle, forward_head_ratio, neck_angle, shoulder_roll]):
        return 0.0, False, False
    
    scores = []
    weights = []
    slouching = False
    text_neck = False
    
    # SIMPLIFIED: Fixed ideal ranges with grey zones (no calibration)
    # Ideal shoulder-ear angle: 85-95° (grey zone: ±5° from 90°)
    IDEAL_SHOULDER_EAR_ANGLE = 90.0
    SHOULDER_EAR_GREY_ZONE = 5.0  # ±5° tolerance for 95-100% score
    SHOULDER_EAR_MIN = 15.0  # Below this is definitely slouching
    
    # Ideal forward head ratio: <0.10 (grey zone: 0.0-0.10 for 95-100%)
    IDEAL_FORWARD_HEAD_RATIO = 0.05
    FORWARD_HEAD_GREY_ZONE = 0.05  # ±0.05 tolerance
    FORWARD_HEAD_MAX = 0.20  # Above this is definitely text neck
    
    # Ideal neck angle: <5° (grey zone: 0-5° for 95-100%)
    IDEAL_NECK_ANGLE = 0.0
    NECK_ANGLE_GREY_ZONE = 5.0
    NECK_ANGLE_MAX = 15.0  # Above this is definitely bad
    
    # Ideal shoulder roll: <3° (grey zone: 0-3° for 95-100%)
    IDEAL_SHOULDER_ROLL = 0.0
    SHOULDER_ROLL_GREY_ZONE = 3.0
    SHOULDER_ROLL_MAX = 10.0  # Above this is definitely bad
    
    # 1. Shoulder-ear angle (30% weight) - SIMPLIFIED GREY ZONE
    if shoulder_ear_angle is not None:
        deviation = abs(shoulder_ear_angle - IDEAL_SHOULDER_EAR_ANGLE)
        
        # Grey zone: within ±5° of ideal = 95-100% score
        if deviation <= SHOULDER_EAR_GREY_ZONE:
            # Perfect posture: 95-100% with small variation for natural movement
            score = 95.0 + (5.0 * (1.0 - deviation / SHOULDER_EAR_GREY_ZONE))
            score = min(100.0, score)
        elif shoulder_ear_angle < SHOULDER_EAR_MIN:
            # Definitely slouching
            slouching = True
            score = max(0.0, 50.0 * (shoulder_ear_angle / SHOULDER_EAR_MIN))
        else:
            # Outside grey zone but not slouching - proportional penalty
            # Score decreases from 95% to 50% as deviation increases
            max_deviation = 30.0  # Max deviation before hitting 50% score
            if deviation >= max_deviation:
                score = 50.0
            else:
                score = 95.0 - (45.0 * (deviation - SHOULDER_EAR_GREY_ZONE) / (max_deviation - SHOULDER_EAR_GREY_ZONE))
                score = max(50.0, score)
        
        scores.append(score)
        weights.append(0.30)
    
    # 2. Forward head ratio (25% weight) - SIMPLIFIED GREY ZONE
    if forward_head_ratio is not None:
        deviation = abs(forward_head_ratio - IDEAL_FORWARD_HEAD_RATIO)
        
        # Grey zone: within ±0.05 of ideal = 95-100% score
        if deviation <= FORWARD_HEAD_GREY_ZONE:
            # Perfect posture: 95-100%
            score = 95.0 + (5.0 * (1.0 - deviation / FORWARD_HEAD_GREY_ZONE))
            score = min(100.0, score)
        elif forward_head_ratio > FORWARD_HEAD_MAX:
            # Definitely text neck
            text_neck = True
            score = max(0.0, 50.0 * (1.0 - (forward_head_ratio - FORWARD_HEAD_MAX) / FORWARD_HEAD_MAX))
        else:
            # Outside grey zone but not text neck - proportional penalty
            max_deviation = 0.15
            if deviation >= max_deviation:
                score = 50.0
            else:
                score = 95.0 - (45.0 * (deviation - FORWARD_HEAD_GREY_ZONE) / (max_deviation - FORWARD_HEAD_GREY_ZONE))
                score = max(50.0, score)
        
        scores.append(score)
        weights.append(0.25)
    
    # 3. Neck angle (25% weight) - SIMPLIFIED GREY ZONE
    if neck_angle is not None:
        deviation = abs(neck_angle - IDEAL_NECK_ANGLE)
        
        # Grey zone: within ±5° of ideal = 95-100% score
        if deviation <= NECK_ANGLE_GREY_ZONE:
            score = 95.0 + (5.0 * (1.0 - deviation / NECK_ANGLE_GREY_ZONE))
            score = min(100.0, score)
        elif neck_angle > NECK_ANGLE_MAX:
            # Definitely bad neck angle
            score = max(0.0, 50.0 * (1.0 - (neck_angle - NECK_ANGLE_MAX) / NECK_ANGLE_MAX))
        else:
            # Outside grey zone - proportional penalty
            max_deviation = 20.0
            if deviation >= max_deviation:
                score = 50.0
            else:
                score = 95.0 - (45.0 * (deviation - NECK_ANGLE_GREY_ZONE) / (max_deviation - NECK_ANGLE_GREY_ZONE))
                score = max(50.0, score)
        
        scores.append(score)
        weights.append(0.25)
    
    # 4. Shoulder roll (20% weight) - SIMPLIFIED GREY ZONE
    if shoulder_roll is not None:
        deviation = abs(shoulder_roll - IDEAL_SHOULDER_ROLL)
        
        # Grey zone: within ±3° of ideal = 95-100% score
        if deviation <= SHOULDER_ROLL_GREY_ZONE:
            score = 95.0 + (5.0 * (1.0 - deviation / SHOULDER_ROLL_GREY_ZONE))
            score = min(100.0, score)
        elif shoulder_roll > SHOULDER_ROLL_MAX:
            # Definitely bad shoulder roll
            score = max(0.0, 50.0 * (1.0 - (shoulder_roll - SHOULDER_ROLL_MAX) / SHOULDER_ROLL_MAX))
        else:
            # Outside grey zone - proportional penalty
            max_deviation = 15.0
            if deviation >= max_deviation:
                score = 50.0
            else:
                score = 95.0 - (45.0 * (deviation - SHOULDER_ROLL_GREY_ZONE) / (max_deviation - SHOULDER_ROLL_GREY_ZONE))
                score = max(50.0, score)
        
        scores.append(score)
        weights.append(0.20)
    
    # Weighted average
    if scores and weights:
        total_weight = sum(weights)
        if total_weight > 0:
            final_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
        else:
            final_score = 0.0
    else:
        final_score = 0.0
    
    return max(0.0, min(100.0, final_score)), slouching, text_neck


def detect_posture(pose_landmarks, frame_width: int, frame_height: int,
                  slouch_start_time: Optional[float] = None) -> PostureResult:
    """
    Enhanced posture detection with multiple metrics.
    
    Args:
        pose_landmarks: MediaPipe Pose landmarks
        frame_width: Frame width
        frame_height: Frame height
        slouch_start_time: Timestamp when slouching started (for alerts)
    
    Returns:
        PostureResult with all metrics and alerts
    """
    # Calculate all metrics
    shoulder_ear_angle = compute_shoulder_ear_angle(pose_landmarks, frame_width, frame_height)
    forward_head_ratio = compute_forward_head_ratio(pose_landmarks, frame_width, frame_height)
    neck_angle = compute_neck_angle(pose_landmarks, frame_width, frame_height)
    shoulder_roll = compute_shoulder_roll(pose_landmarks, frame_width, frame_height)
    
    # SIMPLIFIED: No calibration - use grey zone approach
    # Compute score without calibration (calibration parameter ignored)
    score, slouching, text_neck = compute_posture_score(
        shoulder_ear_angle, forward_head_ratio, neck_angle, shoulder_roll, None
    )
    
    # Realistic threshold: 65% is good posture (allows minor variations)
    good_posture = score >= 65.0 and not slouching and not text_neck
    
    # Generate alert if slouching for too long
    alert_message = None
    if slouching and slouch_start_time is not None:
        slouch_duration = time.time() - slouch_start_time
        if slouch_duration >= SLOUCH_ALERT_DURATION:
            alert_message = (
                f"You've been slouching for {int(slouch_duration)}s. "
                "Try: Sit up straight, align ears with shoulders, pull shoulders back."
            )
    
    return PostureResult(
        good_posture=good_posture,
        score=score,
        shoulder_ear_angle=shoulder_ear_angle if shoulder_ear_angle is not None else 0.0,
        forward_head_ratio=forward_head_ratio if forward_head_ratio is not None else 0.0,
        neck_angle=neck_angle if neck_angle is not None else 0.0,
        shoulder_roll=shoulder_roll if shoulder_roll is not None else 0.0,
        slouching=slouching,
        text_neck=text_neck,
        alert_message=alert_message
    )
