"""
Experimental Emotion Detection Module

Uses FER (Facial Emotion Recognition) library to detect emotions.
Maps to 3 states: neutral, frustrated, tired.

WARNING: This is an EXPERIMENTAL feature. Accuracy varies by:
- Lighting conditions
- Face angle/visibility
- Camera quality
- Individual facial expressions

Use with caution and always label as experimental in UI.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import FER, but make it optional
try:
    from fer import FER
    import cv2
    _FER_AVAILABLE = True
except ImportError:
    _FER_AVAILABLE = False
    FER = None
    logger.warning("FER library not available. Emotion detection disabled.")


class EmotionDetector:
    """
    Experimental emotion detector using FER.
    Maps FER emotions to 3 states: neutral, frustrated, tired.
    """

    # Emotion mapping: FER emotion → Our state
    EMOTION_MAP = {
        "neutral": "neutral",
        "happy": "neutral",  # Happy = good state, map to neutral
        "angry": "frustrated",
        "disgust": "frustrated",
        "sad": "tired",
        "fear": "tired",
        "surprise": "neutral",  # Surprise can be positive or negative, default to neutral
    }

    def __init__(self):
        self.detector: Optional["FER"] = None
        self.enabled = False
        self.frame_count = 0
        self.process_every_n = 5  # Process every 5th frame
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize FER detector.
        Returns True if successful, False otherwise.
        """
        if not _FER_AVAILABLE:
            logger.warning("FER not available, emotion detection cannot be initialized")
            return False

        try:
            logger.info("Loading emotion detection model (this may take a moment)...")
            print("🧪 Loading emotion detection model (EXPERIMENTAL)...")
            # Use MTCNN for better accuracy, but it's slower
            # For performance, we could use 'opencv' instead of 'mtcnn'
            self.detector = FER(mtcnn=True)  # Use MTCNN for better accuracy
            self._initialized = True
            logger.info("Emotion detection model loaded successfully")
            print("✅ Emotion detection model loaded (EXPERIMENTAL)")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize emotion detection: {e}")
            print(f"❌ Failed to load emotion detection: {e}")
            print("💡 Tip: Make sure FER library is installed: pip install fer")
            self._initialized = False
            return False

    def detect_emotion(self, frame) -> Tuple[Optional[str], float]:
        """
        Detect emotion in frame.
        Returns: (emotion_state, confidence) or (None, 0.0) if detection fails.
        
        Args:
            frame: BGR image (numpy array) from OpenCV
        
        Returns:
            Tuple of (emotion_state: "neutral"|"frustrated"|"tired"|None, confidence: float 0-1)
        """
        if not self.enabled or not self._initialized or self.detector is None:
            return None, 0.0

        # Process every Nth frame for performance
        self.frame_count += 1
        if self.frame_count % self.process_every_n != 0:
            return None, 0.0

        try:
            # FER expects RGB, but OpenCV gives BGR
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Detect emotions
            emotions = self.detector.detect_emotions(frame_rgb)
            
            if not emotions or len(emotions) == 0:
                return None, 0.0

            # Get the first face's emotions (most confident)
            first_face = emotions[0]
            emotion_scores = first_face.get("emotions", {})

            if not emotion_scores:
                return None, 0.0

            # Find dominant emotion
            dominant_emotion = max(emotion_scores, key=emotion_scores.get)
            confidence = emotion_scores[dominant_emotion]

            # Map to our 3-state system
            mapped_emotion = self.EMOTION_MAP.get(dominant_emotion, "neutral")
            
            # Only return if confidence is reasonable (>30%)
            if confidence < 0.3:
                return None, 0.0

            return mapped_emotion, float(confidence)

        except Exception as e:
            logger.debug(f"Emotion detection error (non-critical): {e}")
            return None, 0.0

    def enable(self) -> bool:
        """Enable emotion detection. Returns True if successful."""
        if not _FER_AVAILABLE:
            logger.warning("FER not available, cannot enable emotion detection")
            return False

        if not self._initialized:
            success = self.initialize()
            if not success:
                return False

        self.enabled = True
        logger.info("Emotion detection enabled (EXPERIMENTAL)")
        return True

    def disable(self) -> None:
        """Disable emotion detection."""
        self.enabled = False
        logger.info("Emotion detection disabled")

    def is_available(self) -> bool:
        """Check if emotion detection is available."""
        return _FER_AVAILABLE

    def is_enabled(self) -> bool:
        """Check if emotion detection is currently enabled."""
        return self.enabled and self._initialized
