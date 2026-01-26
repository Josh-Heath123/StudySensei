"""
VideoWidget - QWidget for displaying OpenCV video frames.
Optimized for 30+ FPS performance.
"""

from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QFont
import cv2
import numpy as np
from typing import Optional
import time


class VideoWidget(QWidget):
    """
    Custom QWidget for displaying OpenCV video frames.
    
    Features:
    - Converts BGR (OpenCV) → RGB → QImage → QPixmap
    - Maintains aspect ratio
    - Optimized paintEvent for 30+ FPS
    - Thread-safe frame updates
    """
    
    def __init__(self, parent=None):
        # CRITICAL: Always call super().__init__ with parent to establish Qt object tree
        super().__init__(parent)
        print(f"🔍 VideoWidget.__init__() called, parent={parent}, id={id(self)}")
        
        # CRITICAL: Verify parent is set correctly
        if self.parent() is None:
            print("⚠️ WARNING: VideoWidget has no parent! This may cause premature deletion.")
        else:
            print(f"✅ VideoWidget parent set: {self.parent()}, type: {type(self.parent())}")
        
        self.setMinimumSize(640, 480)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # DEBUG: Emergency visible styling - bright red background, thick yellow border
        # CRITICAL: Use setStyleSheet with explicit background to ensure widget is visible
        # But don't use opacity or transparent backgrounds that might interfere with painting
        self.setStyleSheet("background-color: red; border: 5px solid yellow;")
        print(f"🔍 VideoWidget: Applied debug styling, widget size: {self.width()}x{self.height()}")
        
        # CRITICAL: Ensure widget is visible and can receive paint events
        # DO NOT use WA_OpaquePaintEvent - it can prevent paintEvent from being called!
        # self.setAttribute(Qt.WA_OpaquePaintEvent, True)  # DISABLED - can block paintEvent
        self.setAttribute(Qt.WA_PaintOnScreen, False)  # Use normal painting
        self.setAttribute(Qt.WA_NoSystemBackground, False)  # Allow system background
        print(f"🔍 VideoWidget: Widget attributes set, WA_OpaquePaintEvent: {self.testAttribute(Qt.WA_OpaquePaintEvent)}")
        
        # Current frame as QPixmap (cached for fast painting)
        self._pixmap: Optional[QPixmap] = None
        
        # Frame statistics
        self._frame_count = 0
        self._last_fps_time = 0.0
        self._last_frame_time = 0.0
        self._show_test_pattern = True
        self._init_time = time.time()
        
        # Test pattern timer will be set up after widget is fully initialized
        # We'll start it in a separate method or after show()
    
    def update_frame(self, frame: Optional[np.ndarray]) -> None:
        """
        Update the widget with a new OpenCV frame.
        
        Args:
            frame: OpenCV frame in BGR format (numpy array), or None to clear
        """
        if frame is None:
            if self._frame_count == 0 or self._frame_count % 30 == 0:
                print("⚠️ VideoWidget.update_frame(): Received None frame")
            self._pixmap = None
            self.update()  # Trigger repaint
            return
        
        # DEBUG: Print frame info
        self._frame_count += 1
        self._last_frame_time = time.time()
        self._show_test_pattern = False  # We have frames, disable test pattern
        
        if self._frame_count == 1 or self._frame_count % 30 == 0:
            print(f"📹 VideoWidget.update_frame(): Frame #{self._frame_count}, "
                  f"Shape: {frame.shape}, Type: {frame.dtype}, Size: {frame.size} bytes")
        
        # Validate frame
        if not isinstance(frame, np.ndarray) or len(frame.shape) < 2:
            print(f"❌ VideoWidget.update_frame(): Invalid frame type or shape")
            return
        
        # Convert BGR to RGB (OpenCV uses BGR, Qt uses RGB)
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        elif len(frame.shape) == 2:
            # Grayscale frame - convert to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        else:
            return  # Invalid frame format
        
        # Get frame dimensions
        height, width = rgb_frame.shape[:2]
        
        # Convert numpy array to QImage
        # QImage expects data in format: width, height, bytesPerLine, format
        bytes_per_line = 3 * width
        
        # CRITICAL: Ensure data is contiguous and correct format
        if not rgb_frame.flags['C_CONTIGUOUS']:
            rgb_frame = np.ascontiguousarray(rgb_frame)
        
        q_image = QImage(
            rgb_frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888
        )
        
        if q_image.isNull():
            print("❌ VideoWidget.update_frame(): QImage is null!")
            return
        
        if self._frame_count == 1:
            print(f"✅ VideoWidget.update_frame(): QImage created: {q_image.width()}x{q_image.height()}, format: {q_image.format()}")
        
        # Convert QImage to QPixmap (cached for fast painting)
        self._pixmap = QPixmap.fromImage(q_image)
        
        if self._pixmap.isNull():
            print("❌ VideoWidget.update_frame(): QPixmap is null!")
            return
        
        if self._frame_count == 1:
            print(f"✅ VideoWidget.update_frame(): QPixmap created: {self._pixmap.width()}x{self._pixmap.height()}, "
                  f"isNull: {self._pixmap.isNull()}")
        
        # Remove debug styling once we have frames
        if self._frame_count > 5:
            self.setStyleSheet("")  # Remove debug styling
        
        # CRITICAL: Trigger repaint (this will call paintEvent)
        # Use update() to schedule a paint event
        print(f"📥 VideoWidget.update_frame(): Calling update() to trigger paintEvent...")
        self.update()
        
        if self._frame_count == 1:
            print(f"✅ VideoWidget.update_frame(): update() called, paintEvent should be triggered")
            # Force immediate synchronous repaint for first frame
            print(f"📥 VideoWidget.update_frame(): Calling repaint() for immediate synchronous update...")
            self.repaint()
            print(f"✅ VideoWidget.update_frame(): repaint() completed")
            
            # Also try update() again after a short delay
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, lambda: (self.update(), print("📥 VideoWidget: Delayed update() called")))
    
    def paintEvent(self, event):
        """
        Paint the current frame on the widget.
        Optimized for 30+ FPS performance.
        """
        # CRITICAL: IMMEDIATE DEBUG - Print immediately to confirm paintEvent is called
        print(f"🎨🎨🎨 VideoWidget.paintEvent() CALLED! 🎨🎨🎨")
        
        # DEBUG: Track paint events
        if not hasattr(self, '_paint_count'):
            self._paint_count = 0
        self._paint_count += 1
        
        # CRITICAL: Always log paint events to verify they're being called
        print(f"🎨 VideoWidget.paintEvent(): Call #{self._paint_count}, "
              f"Widget size: {self.width()}x{self.height()}, "
              f"Widget visible: {self.isVisible()}, "
              f"Has pixmap: {self._pixmap is not None}, "
              f"Rect: {self.rect().x()},{self.rect().y()},{self.rect().width()}x{self.rect().height()}, "
              f"Event rect: {event.rect().x()},{event.rect().y()},{event.rect().width()}x{event.rect().height()}")
        
        # CRITICAL: Verify widget is visible and has non-zero size
        if self.width() <= 0 or self.height() <= 0:
            print(f"❌ CRITICAL: VideoWidget.paintEvent(): Widget has zero size! {self.width()}x{self.height()}")
            return
        
        if not self.isVisible():
            print(f"⚠️ VideoWidget.paintEvent(): Widget is not visible!")
        
        painter = QPainter(self)
        if not painter.isActive():
            print("❌ CRITICAL: QPainter failed to initialize!")
            return
        
        print(f"✅ VideoWidget.paintEvent(): QPainter is active, starting to paint...")
        
        # CRITICAL TEST: Fill ENTIRE widget with bright red FIRST to verify painting works at all
        widget_rect = self.rect()
        painter.fillRect(widget_rect, QColor(255, 0, 0))  # Bright red - fill entire widget
        print(f"🎨 VideoWidget.paintEvent(): TEST - Filled entire widget with RED at {widget_rect}")
        
        # Draw a bright green rectangle on top to make it even more obvious
        test_rect = widget_rect.adjusted(20, 20, -20, -20)  # 20px margin from edges
        painter.fillRect(test_rect, QColor(0, 255, 0))  # Bright green
        print(f"🎨 VideoWidget.paintEvent(): TEST - Drew GREEN rectangle at {test_rect}")
        
        # Draw white text to confirm text rendering works
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 24, QFont.Bold))
        painter.drawText(widget_rect, Qt.AlignCenter, f"PAINT EVENT #{self._paint_count}\nWidget: {self.width()}x{self.height()}")
        print(f"🎨 VideoWidget.paintEvent(): TEST - Drew white text")
        
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # Show test pattern if no frames received after 3 seconds
        elapsed = time.time() - self._init_time
        if self._show_test_pattern or (elapsed > 3 and self._pixmap is None and self._frame_count == 0):
            print("🎨 VideoWidget.paintEvent(): Drawing test pattern")
            self._draw_test_pattern(painter)
            painter.end()
            return
        
        if self._pixmap is None:
            # No frame - draw background
            print(f"🎨 VideoWidget.paintEvent(): No pixmap, filling with black. Widget rect: {self.rect()}")
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            painter.setPen(QColor(255, 255, 255))
            font = QFont()
            font.setPointSize(16)
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No video feed\nWaiting for frames..."
            )
            painter.end()
            return
        
        # CRITICAL: Verify pixmap exists and is valid
        if self._pixmap is None:
            print(f"❌ CRITICAL: VideoWidget.paintEvent(): _pixmap is None!")
            painter.setPen(QColor(255, 255, 0))  # Yellow text
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "PIXMAP IS NONE")
            painter.end()
            return
        
        if self._pixmap.isNull():
            print(f"❌ CRITICAL: VideoWidget.paintEvent(): Pixmap is null!")
            painter.setPen(QColor(255, 255, 0))  # Yellow text
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "PIXMAP IS NULL")
            painter.end()
            return
        
        # CRITICAL: Verify pixmap has valid dimensions
        pixmap_size = self._pixmap.size()
        if pixmap_size.width() <= 0 or pixmap_size.height() <= 0:
            print(f"❌ CRITICAL: VideoWidget.paintEvent(): Pixmap has invalid size: {pixmap_size.width()}x{pixmap_size.height()}")
            painter.setPen(QColor(255, 255, 0))  # Yellow text
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, f"PIXMAP SIZE INVALID\n{pixmap_size.width()}x{pixmap_size.height()}")
            painter.end()
            return
        
        # Calculate scaled size maintaining aspect ratio
        widget_size = self.size()
        
        if self._paint_count <= 5:
            print(f"🎨 VideoWidget.paintEvent(): Drawing pixmap. "
                  f"Widget: {widget_size.width()}x{widget_size.height()}, "
                  f"Pixmap: {pixmap_size.width()}x{pixmap_size.height()}, "
                  f"Pixmap isNull: {self._pixmap.isNull()}")
        
        # Calculate aspect ratios
        widget_aspect = widget_size.width() / widget_size.height() if widget_size.height() > 0 else 1.0
        pixmap_aspect = pixmap_size.width() / pixmap_size.height() if pixmap_size.height() > 0 else 1.0
        
        if pixmap_aspect > widget_aspect:
            # Frame is wider - fit to width
            scaled_width = widget_size.width()
            scaled_height = int(widget_size.width() / pixmap_aspect)
        else:
            # Frame is taller - fit to height
            scaled_height = widget_size.height()
            scaled_width = int(widget_size.height() * pixmap_aspect)
        
        # CRITICAL: Verify scaled size is valid
        if scaled_width <= 0 or scaled_height <= 0:
            print(f"❌ CRITICAL: VideoWidget.paintEvent(): Scaled size is invalid: {scaled_width}x{scaled_height}")
            painter.setPen(QColor(255, 255, 0))  # Yellow text
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, f"SCALED SIZE INVALID\n{scaled_width}x{scaled_height}")
            painter.end()
            return
        
        # Center the scaled pixmap
        x = (widget_size.width() - scaled_width) // 2
        y = (widget_size.height() - scaled_height) // 2
        
        if self._paint_count <= 5:
            print(f"🎨 VideoWidget.paintEvent(): Scaled to {scaled_width}x{scaled_height}, position: ({x}, {y})")
        
        # Draw the scaled pixmap
        try:
            scaled_pixmap = self._pixmap.scaled(
                scaled_width,
                scaled_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            if scaled_pixmap.isNull():
                print(f"❌ CRITICAL: VideoWidget.paintEvent(): Scaled pixmap is null!")
                painter.setPen(QColor(255, 255, 0))  # Yellow text
                painter.setFont(QFont("Arial", 16, QFont.Bold))
                painter.drawText(self.rect(), Qt.AlignCenter, "SCALED PIXMAP IS NULL")
                painter.end()
                return
            
            scaled_pixmap_size = scaled_pixmap.size()
            if scaled_pixmap_size.width() <= 0 or scaled_pixmap_size.height() <= 0:
                print(f"❌ CRITICAL: VideoWidget.paintEvent(): Scaled pixmap has invalid size: {scaled_pixmap_size.width()}x{scaled_pixmap_size.height()}")
                painter.setPen(QColor(255, 255, 0))  # Yellow text
                painter.setFont(QFont("Arial", 16, QFont.Bold))
                painter.drawText(self.rect(), Qt.AlignCenter, f"SCALED PIXMAP SIZE INVALID\n{scaled_pixmap_size.width()}x{scaled_pixmap_size.height()}")
                painter.end()
                return
            
            if self._paint_count <= 5:
                print(f"🎨 VideoWidget.paintEvent(): Scaled pixmap size: {scaled_pixmap_size.width()}x{scaled_pixmap_size.height()}, drawing at ({x}, {y})")
            
            # CRITICAL: Actually draw the pixmap
            painter.drawPixmap(x, y, scaled_pixmap)
            
            if self._paint_count <= 5:
                print(f"✅ VideoWidget.paintEvent(): Pixmap drawn successfully at ({x}, {y})")
            
        except Exception as e:
            print(f"❌ CRITICAL: VideoWidget.paintEvent(): Error drawing pixmap: {e}")
            import traceback
            traceback.print_exc()
            painter.setPen(QColor(255, 255, 0))  # Yellow text
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, f"ERROR DRAWING\n{str(e)}")
        
        painter.end()
    
    def showEvent(self, event):
        """Setup test timer when widget is shown."""
        super().showEvent(event)
        
        # CRITICAL: Verify widget is still valid
        try:
            widget_id = id(self)
            widget_size = self.width(), self.height()
            print(f"🔍 VideoWidget.showEvent() called, id={widget_id}, size={widget_size}, visible: {self.isVisible()}, parent={self.parent()}")
        except RuntimeError as e:
            print(f"❌ CRITICAL: VideoWidget deleted in showEvent! Error: {e}")
            return
        
        # CRITICAL: Force immediate repaint when widget is shown
        print(f"🔍 VideoWidget.showEvent(): Forcing immediate repaint() to test painting...")
        self.repaint()
        print(f"✅ VideoWidget.showEvent(): repaint() completed")
        
        # Also schedule an update
        self.update()
        print(f"✅ VideoWidget.showEvent(): update() called")
        
        # Send immediate test frame to verify widget rendering
        try:
            self._send_test_frame()
        except RuntimeError as e:
            print(f"❌ CRITICAL: Failed to send test frame in showEvent! Error: {e}")
            return
        
        # Now that widget is shown, connect the timer
        if hasattr(self, 'test_timer') and self.test_timer and not self.test_timer.isActive():
            try:
                self.test_timer.timeout.connect(self._check_for_frames)
                self.test_timer.start(3000)  # Check after 3 seconds
            except Exception as e:
                print(f"⚠️ Failed to connect test timer: {e}")
    
    def _send_test_frame(self):
        """Send a test frame (solid color with text) to verify rendering."""
        # CRITICAL: Verify widget is still valid before accessing
        try:
            widget_id = id(self)
            print(f"🔍 VideoWidget._send_test_frame() called, id={widget_id}")
        except RuntimeError as e:
            print(f"❌ CRITICAL: VideoWidget deleted in _send_test_frame! Error: {e}")
            return
        
        import numpy as np
        import cv2
        
        # Create test frame: bright green with "TEST" text
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        test_frame[:, :] = [0, 255, 0]  # Bright green (BGR)
        
        # Add "TEST" text
        cv2.putText(test_frame, "TEST FRAME", (200, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
        cv2.putText(test_frame, "If you see this, widget works!", (100, 280),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Update widget with test frame (with error handling)
        try:
            self.update_frame(test_frame)
            self.update()  # Force immediate repaint
            print("✅ VideoWidget: Test frame sent and update() called")
        except RuntimeError as e:
            print(f"❌ CRITICAL: Failed to update VideoWidget! Error: {e}")
            print("   Widget was deleted between check and update.")
    
    def _check_for_frames(self):
        """Check if frames are being received, show test pattern if not."""
        elapsed = time.time() - self._init_time
        if elapsed > 3 and self._frame_count == 0:
            print("⚠️ No frames received after 3 seconds - showing test pattern")
            self._show_test_pattern = True
            self.update()  # Trigger repaint
    
    def _draw_test_pattern(self, painter: QPainter):
        """Draw visible test pattern to verify widget is rendering."""
        rect = self.rect()
        
        # Draw colored background
        painter.fillRect(rect, QColor(100, 150, 255))  # Light blue
        
        # Draw colored rectangles
        painter.fillRect(rect.left() + 20, rect.top() + 20, 200, 100, QColor(255, 100, 100))  # Red
        painter.fillRect(rect.right() - 220, rect.top() + 20, 200, 100, QColor(100, 255, 100))  # Green
        
        # Draw text
        painter.setPen(QColor(255, 255, 255))
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        
        center_x = rect.center().x()
        center_y = rect.center().y()
        
        painter.drawText(
            center_x - 150,
            center_y - 20,
            "TEST PATTERN"
        )
        painter.drawText(
            center_x - 200,
            center_y + 20,
            f"Frames: {self._frame_count}"
        )
        painter.drawText(
            center_x - 200,
            center_y + 50,
            f"Size: {rect.width()}x{rect.height()}"
        )
    
    def sizeHint(self) -> QSize:
        """Return preferred widget size."""
        return QSize(640, 480)
    
    def clear(self) -> None:
        """Clear the video display."""
        print("🧹 VideoWidget.clear() called")
        self._pixmap = None
        self._frame_count = 0
        self._show_test_pattern = True
        self.update()
