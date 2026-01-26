"""
StudySenseiEngine - Adapter class connecting existing logic to PyQt UI.
Uses QTimer for frame processing and Qt signals for UI updates.
"""

import cv2
import time
import numpy as np
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from typing import Optional, Dict, Any

from vision.frame_processor import process_frame
from core.focus_history import update_focus_history, reset_focus_history
from utils.constants import FRAME_SKIP_N
from utils.pyqt_memory_manager import get_memory_manager
from collections import deque

# Check if emotion detection is available
try:
    from vision.emotion import EmotionDetector
    _EMOTION_AVAILABLE = True
except ImportError:
    EmotionDetector = None
    _EMOTION_AVAILABLE = False


class StudySenseiEngine(QObject):
    """
    Engine adapter connecting existing StudySensei logic to PyQt UI.
    
    Features:
    - Frame processing using existing vision modules
    - QTimer-based processing loop
    - Qt signals for UI updates
    - Preserves all detection algorithms
    """
    
    # Signals emitted when frame is processed
    frame_processed = pyqtSignal(dict)  # Emits result dictionary
    frame_ready = pyqtSignal(np.ndarray)  # Emits BGR frame for preview
    error_occurred = pyqtSignal(str)  # Emits error message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Video capture
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        
        # Processing state
        self.frame_count = 0
        self.start_time = 0.0
        self.prev_timestamp = 0.0
        
        # Frame skipping
        self.frame_skip_counter = 0
        
        # Blink tracking (from existing logic)
        self.ear_history = deque(maxlen=10)
        self.blink_timestamps = deque(maxlen=100)
        self.blink_rate_per_min = 0.0
        
        # Posture detection state
        self.enable_posture = True
        self.draw_pose = False
        self.slouch_start_time: Optional[float] = None
        self.latest_pose_landmarks = None
        
        # Emotion detection
        self.emotion_detector = EmotionDetector() if _EMOTION_AVAILABLE else None
        self.enable_emotion = False
        
        # Processing timer (~30 FPS = 33ms interval)
        self.processing_timer = QTimer(self)
        self.processing_timer.timeout.connect(self._process_frame)
        
        # FPS tracking
        self.fps_frame_count = 0
        self.fps_start_time = time.time()
        self.current_fps = 0.0
    
    def start(self, camera_index: int = 0) -> bool:
        """
        Start video processing.
        
        Args:
            camera_index: Camera device index (default: 0)
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.running:
            return True
        
        try:
            # Initialize video capture
            self.cap = cv2.VideoCapture(camera_index)
            
            if not self.cap.isOpened():
                self.error_occurred.emit("Could not open camera")
                return False
            
            # Register video capture with memory manager
            memory_manager = get_memory_manager()
            memory_manager.register_video_capture(self.cap)
            memory_manager.register_timer(self.processing_timer)
            
            # Set camera properties for performance
            # Set resolution (usually works)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            # Try to set FPS (might fail on some cameras - continue if it fails)
            fps_success = self.cap.set(cv2.CAP_PROP_FPS, 30)
            if not fps_success:
                # Get actual FPS that camera is using
                actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
                print(f"Warning: Could not set camera FPS to 30. Using default: {actual_fps}")
            
            # Reset state
            self.running = True
            self.frame_count = 0
            self.start_time = time.time()
            self.prev_timestamp = 0.0
            self.frame_skip_counter = 0
            self.ear_history.clear()
            self.blink_timestamps.clear()
            self.blink_rate_per_min = 0.0
            self.slouch_start_time = None
            self.fps_frame_count = 0
            self.fps_start_time = time.time()
            
            # Reset focus history for new session
            reset_focus_history()
            
            # Start processing timer (~30 FPS)
            self.processing_timer.start(33)  # 33ms = ~30 FPS
            
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Error starting camera: {str(e)}")
            if self.cap:
                self.cap.release()
                self.cap = None
            return False
    
    def stop(self) -> None:
        """Stop video processing."""
        if not self.running:
            return
        
        # Stop timer
        if self.processing_timer.isActive():
            self.processing_timer.stop()
        
        # Release camera
        if self.cap:
            self.cap.release()
            self.cap = None
        
        self.running = False
        
        # Trigger cleanup after stopping
        memory_manager = get_memory_manager()
        memory_manager.cleanup()
    
    def _process_frame(self) -> None:
        """Process a single frame (called by QTimer)."""
        if not self.running or not self.cap or not self.cap.isOpened():
            if self.frame_count == 0 or self.frame_count % 60 == 0:
                print(f"⚠️ StudySenseiEngine._process_frame(): Not running or cap not opened. "
                      f"Running: {self.running}, Cap: {self.cap}, IsOpened: {self.cap.isOpened() if self.cap else None}")
            return
        
        # Periodic memory check and cleanup (every 30 seconds)
        memory_manager = get_memory_manager()
        memory_manager.check_memory()
        memory_manager.periodic_cleanup()
        
        try:
            # Read frame
            ret, frame = self.cap.read()
            
            if not ret or frame is None:
                if self.frame_count == 0 or self.frame_count % 60 == 0:
                    print(f"⚠️ StudySenseiEngine._process_frame(): Failed to read frame. ret: {ret}, frame: {frame}")
                return
            
            # DEBUG: Print frame info
            if self.frame_count == 0 or self.frame_count % 30 == 0:
                print(f"📹 StudySenseiEngine._process_frame(): Frame #{self.frame_count}, "
                      f"Shape: {frame.shape}, Type: {frame.dtype}, "
                      f"Size: {frame.size} bytes")
            
            # Frame skipping (process every Nth frame for performance)
            self.frame_skip_counter += 1
            if self.frame_skip_counter < FRAME_SKIP_N:
                # Still emit frame for preview, but skip processing
                self.frame_ready.emit(frame)
                return
            
            self.frame_skip_counter = 0
            
            # Calculate timestamp
            current_time = time.time()
            timestamp = current_time - self.start_time
            
            # Process frame using existing logic
            result = process_frame(
                image_bgr=frame,
                prev_timestamp=self.prev_timestamp,
                draw_landmarks=self.draw_pose,  # Use draw_pose flag
                previous_ear_history=self.ear_history,
                blink_rate_per_min=self.blink_rate_per_min,
                enable_posture=self.enable_posture,
                draw_pose=self.draw_pose,
                slouch_start_time=self.slouch_start_time,
                emotion_detector=self.emotion_detector if self.enable_emotion else None,
                process_face=True
            )
            
            # Update blink tracking
            if result.get("blink_detected"):
                self.blink_timestamps.append(current_time)
            
            # Calculate blink rate (blinks per minute)
            if len(self.blink_timestamps) > 1:
                time_span = self.blink_timestamps[-1] - self.blink_timestamps[0]
                if time_span > 0:
                    self.blink_rate_per_min = (len(self.blink_timestamps) - 1) / (time_span / 60.0)
                else:
                    self.blink_rate_per_min = 0.0
            
            # Update slouch tracking
            if result.get("posture"):
                posture_data = result["posture"]
                if posture_data.get("slouching"):
                    if self.slouch_start_time is None:
                        self.slouch_start_time = current_time
                else:
                    self.slouch_start_time = None
                
                # Store pose landmarks for potential calibration
                if "pose_landmarks" in result:
                    self.latest_pose_landmarks = result["pose_landmarks"]
            
            # Update focus history (for 60s window calculation)
            if result.get("focused") is not None:
                update_focus_history(result["focused"], timestamp)
            
            # Add metadata to result
            result["timestamp"] = timestamp
            result["frame_count"] = self.frame_count
            result["fps"] = self._calculate_fps()
            result["preview"] = result.get("preview", frame)  # Use processed frame or original
            
            # Update previous timestamp
            self.prev_timestamp = timestamp
            self.frame_count += 1
            
            # Emit signals
            self.frame_processed.emit(result)
            self.frame_ready.emit(result.get("preview", frame))
            
        except Exception as e:
            self.error_occurred.emit(f"Error processing frame: {str(e)}")
    
    def _calculate_fps(self) -> float:
        """Calculate current FPS."""
        self.fps_frame_count += 1
        current_time = time.time()
        elapsed = current_time - self.fps_start_time
        
        if elapsed >= 1.0:
            self.current_fps = self.fps_frame_count / elapsed
            self.fps_frame_count = 0
            self.fps_start_time = current_time
        
        return self.current_fps
    
    def toggle_posture(self) -> None:
        """Toggle posture detection on/off."""
        self.enable_posture = not self.enable_posture
    
    def toggle_pose_drawing(self) -> None:
        """Toggle pose landmark drawing."""
        self.draw_pose = not self.draw_pose
    
    def toggle_landmarks(self) -> None:
        """Toggle face mesh landmark drawing."""
        self.draw_pose = not self.draw_pose  # Reuse draw_pose for face mesh
    
    def toggle_emotion(self) -> bool:
        """Toggle emotion detection on/off."""
        if not _EMOTION_AVAILABLE:
            return False
        
        self.enable_emotion = not self.enable_emotion
        
        if self.enable_emotion and self.emotion_detector is None:
            try:
                self.emotion_detector = EmotionDetector()
            except Exception:
                self.enable_emotion = False
                return False
        
        return True
    
    def get_session_duration(self) -> float:
        """Get current session duration in seconds."""
        if not self.running or self.start_time == 0:
            return 0.0
        return time.time() - self.start_time
    
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self.running
