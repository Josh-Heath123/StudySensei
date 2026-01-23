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

# MediaPipe Pose landmark indices
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_EAR = 7
RIGHT_EAR = 8
NOSE = 0
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16

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
    
    Algorithm:
    - Get left/right shoulder and ear positions
    - Calculate angle between shoulder line and ear-to-shoulder line
    - Lower angle indicates slouching (head forward and down)
    
    Returns:
        Angle in degrees, or None if landmarks not available
    """
    try:
        left_shoulder = _pose_lm_to_px(pose_landmarks, LEFT_SHOULDER, frame_width, frame_height)
        right_shoulder = _pose_lm_to_px(pose_landmarks, RIGHT_SHOULDER, frame_width, frame_height)
        left_ear = _pose_lm_to_px(pose_landmarks, LEFT_EAR, frame_width, frame_height)
        
        # Calculate shoulder midpoint
        shoulder_mid = ((left_shoulder[0] + right_shoulder[0]) / 2,
                        (left_shoulder[1] + right_shoulder[1]) / 2)
        
        # Calculate angle: shoulder_mid -> left_ear -> left_shoulder
        angle = calculate_angle(shoulder_mid, left_ear, left_shoulder)
        
        return angle
    except (IndexError, KeyError, AttributeError):
        return None


def compute_forward_head_ratio(pose_landmarks, frame_width: int, frame_height: int) -> Optional[float]:
    """
    Detect forward head posture (text neck).
    
    Algorithm:
    - Measure horizontal distance from nose to shoulder line
    - Normalize by shoulder width
    - Higher ratio = more forward head posture
    
    Returns:
        Normalized forward head ratio, or None if landmarks not available
    """
    try:
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
    Compute overall posture score (0-100) from multiple metrics with calibration support.
    
    Uses weighted combination of:
    1. Shoulder-ear angle (30% weight) - primary slouch indicator
    2. Forward head ratio (25% weight) - text neck indicator
    3. Neck angle (25% weight) - neck alignment
    4. Shoulder roll (20% weight) - shoulder symmetry
    
    Args:
        shoulder_ear_angle: Angle in degrees (lower = more slouching)
        forward_head_ratio: Normalized forward head distance (higher = more text neck)
        neck_angle: Neck angle deviation from vertical (higher = worse)
        shoulder_roll: Shoulder roll/rotation angle (higher = worse)
        calibration: Optional calibration data for baseline adjustment
    
    Returns:
        Tuple of (score: float, slouching: bool, text_neck: bool)
    """
    if all(x is None for x in [shoulder_ear_angle, forward_head_ratio, neck_angle, shoulder_roll]):
        return 0.0, False, False
    
    calibration = calibration or load_calibration()
    
    scores = []
    weights = []
    slouching = False
    text_neck = False
    
    # Adjust thresholds based on calibration
    shoulder_ear_threshold = (calibration.shoulder_ear_angle_baseline * 0.75 
                             if calibration.calibrated else SHOULDER_EAR_ANGLE_THRESHOLD)
    forward_head_threshold = (calibration.forward_head_ratio_baseline * 1.5 
                             if calibration.calibrated else FORWARD_HEAD_THRESHOLD)
    neck_angle_threshold = (NECK_ANGLE_THRESHOLD + abs(calibration.neck_angle_baseline) 
                           if calibration.calibrated else NECK_ANGLE_THRESHOLD)
    shoulder_roll_threshold = (SHOULDER_ROLL_THRESHOLD + abs(calibration.shoulder_roll_baseline) 
                              if calibration.calibrated else SHOULDER_ROLL_THRESHOLD)
    
    # Validate thresholds to prevent division by zero
    if forward_head_threshold < 0.01:
        forward_head_threshold = FORWARD_HEAD_THRESHOLD  # Use default if too small
    if neck_angle_threshold < 0.01:
        neck_angle_threshold = NECK_ANGLE_THRESHOLD  # Use default if too small
    if shoulder_roll_threshold < 0.01:
        shoulder_roll_threshold = SHOULDER_ROLL_THRESHOLD  # Use default if too small
    
    # 1. Shoulder-ear angle (30% weight)
    if shoulder_ear_angle is not None:
        baseline = calibration.shoulder_ear_angle_baseline if calibration.calibrated else 20.0
        deviation = abs(shoulder_ear_angle - baseline)
        
        if shoulder_ear_angle < shoulder_ear_threshold:
            slouching = True
            # Prevent division by zero
            if abs(shoulder_ear_threshold) > 0.01:
                score = max(0.0, 50.0 * (shoulder_ear_angle / shoulder_ear_threshold))
            else:
                score = 0.0  # Invalid threshold, penalize
        else:
            # Good range: threshold to baseline+5 = 50 to 100 score
            max_angle = baseline + 5.0
            if shoulder_ear_angle >= max_angle:
                score = 100.0
            else:
                # Prevent division by zero
                denominator = max_angle - shoulder_ear_threshold
                if abs(denominator) > 0.01:
                    score = 50.0 + ((shoulder_ear_angle - shoulder_ear_threshold) / denominator) * 50.0
                else:
                    score = 50.0  # Neutral score if denominator invalid
        
        scores.append(score)
        weights.append(0.30)
    
    # 2. Forward head ratio (25% weight)
    if forward_head_ratio is not None:
        baseline = calibration.forward_head_ratio_baseline if calibration.calibrated else 0.10
        deviation = abs(forward_head_ratio - baseline)
        
        if forward_head_ratio > forward_head_threshold:
            text_neck = True
            max_ratio = forward_head_threshold * 2.0
            if forward_head_ratio >= max_ratio:
                score = 0.0
            else:
                # Prevent division by zero
                denominator = max_ratio - forward_head_threshold
                if abs(denominator) > 0.01:
                    score = 50.0 * (1.0 - (forward_head_ratio - forward_head_threshold) / denominator)
                else:
                    score = 0.0  # Invalid threshold, penalize
        else:
            # Good range: 0 to threshold = 50 to 100 score
            # Prevent division by zero
            if abs(forward_head_threshold) > 0.01:
                score = 50.0 + (1.0 - forward_head_ratio / forward_head_threshold) * 50.0
            else:
                score = 50.0  # Neutral score if threshold invalid
        
        scores.append(score)
        weights.append(0.25)
    
    # 3. Neck angle (25% weight)
    if neck_angle is not None:
        baseline = abs(calibration.neck_angle_baseline) if calibration.calibrated else 0.0
        deviation = abs(neck_angle - baseline)
        
        if neck_angle > neck_angle_threshold:
            # Penalize large deviations
            max_deviation = neck_angle_threshold * 2.0
            if neck_angle >= max_deviation:
                score = 0.0
            else:
                # Prevent division by zero
                denominator = max_deviation - neck_angle_threshold
                if abs(denominator) > 0.01:
                    score = 50.0 * (1.0 - (neck_angle - neck_angle_threshold) / denominator)
                else:
                    score = 0.0  # Invalid threshold, penalize
        else:
            # Good range: 0 to threshold = 50 to 100 score
            # Prevent division by zero
            if abs(neck_angle_threshold) > 0.01:
                score = 50.0 + (1.0 - neck_angle / neck_angle_threshold) * 50.0
            else:
                score = 50.0  # Neutral score if threshold invalid
        
        scores.append(score)
        weights.append(0.25)
    
    # 4. Shoulder roll (20% weight)
    if shoulder_roll is not None:
        baseline = abs(calibration.shoulder_roll_baseline) if calibration.calibrated else 0.0
        deviation = abs(shoulder_roll - baseline)
        
        if shoulder_roll > shoulder_roll_threshold:
            # Penalize large deviations
            max_deviation = shoulder_roll_threshold * 2.0
            if shoulder_roll >= max_deviation:
                score = 0.0
            else:
                # Prevent division by zero
                denominator = max_deviation - shoulder_roll_threshold
                if abs(denominator) > 0.01:
                    score = 50.0 * (1.0 - (shoulder_roll - shoulder_roll_threshold) / denominator)
                else:
                    score = 0.0  # Invalid threshold, penalize
        else:
            # Good range: 0 to threshold = 50 to 100 score
            # Prevent division by zero
            if abs(shoulder_roll_threshold) > 0.01:
                score = 50.0 + (1.0 - shoulder_roll / shoulder_roll_threshold) * 50.0
            else:
                score = 50.0  # Neutral score if threshold invalid
        
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
    
    # Load calibration
    calibration = load_calibration()
    
    # Compute score with calibration
    score, slouching, text_neck = compute_posture_score(
        shoulder_ear_angle, forward_head_ratio, neck_angle, shoulder_roll, calibration
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
