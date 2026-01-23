"""Computer vision modules for StudySensei."""

from .gaze import compute_iris_gaze_confidence, detect_blink, compute_eye_aspect_ratio, compute_focus, FocusResult
from .frame_processor import process_frame
from .mediapipe_setup import get_face_mesh, get_pose, initialize_mediapipe
from .posture import detect_posture, PostureResult, calibrate_posture

# Emotion detection (optional)
try:
    from .emotion import EmotionDetector
    _EMOTION_AVAILABLE = True
except ImportError:
    EmotionDetector = None
    _EMOTION_AVAILABLE = False
