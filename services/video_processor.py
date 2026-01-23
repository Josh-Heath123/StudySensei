"""Video processing service with frame skipping and blink tracking."""

import cv2
import time
import threading
from collections import deque
from typing import Optional

from vision.frame_processor import process_frame
from utils.constants import TARGET_FPS, FRAME_SKIP_N

# Check if emotion detection is available
try:
    from vision.emotion import EmotionDetector
    _EMOTION_AVAILABLE = True
except ImportError:
    EmotionDetector = None
    _EMOTION_AVAILABLE = False


class VideoProcessor:
    """Continuous video processor with frame skipping and blink tracking."""
    
    def __init__(self):
        self.running = False
        self.cap = None
        self.thread = None
        self.latest_result = None
        self.lock = threading.Lock()
        self.frame_count = 0
        self.start_time = 0
        self.draw_landmarks = True
        # Frame skipping
        self.frame_skip_counter = 0
        # Blink tracking
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
        """Start video processing thread with tracking reset."""
        if self.running:
            return
            
        self.running = True
        self.cap = cv2.VideoCapture(0)
        # Set lower resolution for better performance (target: >15 FPS)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
        self.cap.set(cv2.CAP_PROP_FPS, 15)  # Request 15 FPS from camera
        self.frame_count = 0
        self.frame_skip_counter = 0
        self.start_time = time.time()
        # Reset blink tracking
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
        Main processing loop with frame skipping and blink tracking.
        
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
            
            # Frame skipping - only process every Nth frame
            self.frame_skip_counter += 1
            if self.frame_skip_counter < FRAME_SKIP_N:
                # Skip this frame but still update timestamp for next frame
                continue
            
            self.frame_skip_counter = 0  # Reset counter
            
            # Compute blink rate (blinks per minute) over last 60 seconds
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
            
            # Track blinks
            if result.get("blink_detected", False):
                self.blink_timestamps.append(current_timestamp)
            
            # Add blink rate to result for potential display
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
        Get current blink rate (blinks per minute) over last 60 seconds.
        
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
