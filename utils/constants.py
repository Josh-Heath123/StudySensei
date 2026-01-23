"""Constants and configuration for StudySensei."""

# Window and FPS configuration
WINDOW_SIZE = 60  # seconds
TARGET_FPS = 60   # Reduced for better performance on laptops
FRAME_SKIP_N = 3  # Process every 3rd frame for better FPS (target: >15 FPS)

# Blink detection constants
EAR_THRESHOLD = 0.25  # Eye Aspect Ratio threshold for blink detection (lower = more sensitive)
EAR_CONSECUTIVE_FRAMES = 2  # Number of consecutive frames below threshold to register blink
EAR_NOISE_TOLERANCE = 0.05  # Tolerance for noise in EAR measurements

# Focus score weights (must sum to 1.0)
GAZE_CONFIDENCE_WEIGHT = 0.70  # Weight for iris-based gaze confidence
BLINK_FATIGUE_WEIGHT = 0.30    # Weight for blink-rate-based fatigue signal

# MediaPipe FaceMesh landmark indices
LEFT_EYE_LANDMARKS = (33, 133)   # outer, inner corner
RIGHT_EYE_LANDMARKS = (362, 263) # outer, inner corner

# Iris landmarks (MediaPipe FaceMesh)
LEFT_IRIS_LANDMARKS = (468, 469, 470, 471, 472)   # Left iris center and boundary points
RIGHT_IRIS_LANDMARKS = (473, 474, 475, 476, 477)  # Right iris center and boundary points

# Eye landmarks for EAR calculation (6 points per eye)
LEFT_EYE_EAR_POINTS = (33, 160, 158, 133, 153, 144)   # Left eye EAR points
RIGHT_EYE_EAR_POINTS = (362, 385, 387, 263, 380, 373)  # Right eye EAR points
