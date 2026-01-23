"""MediaPipe initialization and setup."""

import mediapipe as mp

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


def initialize_mediapipe():
    """Initialize MediaPipe solutions."""
    pass  # Already initialized via module-level imports


def get_face_mesh():
    """
    Get or create FaceMesh instance with iris landmarks enabled.
    
    Note: refine_landmarks=True is required for iris landmark detection (468-477).
    """
    global _FACE_MESH
    if _FACE_MESH is None:
        _FACE_MESH = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,  # Enable iris landmarks (468-477)
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return _FACE_MESH


def get_pose():
    """
    Get or create MediaPipe Pose instance.
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


# Export drawing utilities
__all__ = ['get_face_mesh', 'get_pose', 'initialize_mediapipe', 'mp_drawing', 'mp_drawing_styles', 'mp_pose']
