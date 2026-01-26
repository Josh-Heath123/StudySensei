"""
FocusCircleWidget - Circular progress indicator for focus score (0-100%).
Apple-inspired design with smooth animations.
"""

from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer
from PyQt5.QtGui import QPainter, QPen, QFont, QColor, QLinearGradient, QRadialGradient, QBrush


class FocusCircleWidget(QWidget):
    """
    Circular progress widget displaying focus score (0-100%).
    
    Features:
    - Circular progress ring
    - Percentage text in center
    - Status text below circle
    - Smooth updates
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(250, 280)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        # Data - Initialize ALL attributes before creating animations
        self._focus_score = 0.0  # 0-100 (actual value)
        self._animated_score = 0.0  # 0-100 (animated value for display)
        self._circle_progress = 0.0  # 0-100 for smooth fill animation (MUST be before animation creation)
        self._status_text = "WAITING"
        self._is_focused = False
        
        # Colors - Apple Dark Theme
        self._track_color = QColor(255, 255, 255, 20)  # Subtle white track (20% opacity)
        self._text_color = QColor(255, 255, 255)  # White text
        self._status_color_focused = QColor(255, 255, 255)  # White when focused
        self._status_color_unfocused = QColor(255, 255, 255, 100)  # Dimmed white when unfocused
        
        # Gradient colors for progress ring (Apple blue gradient)
        self._gradient_start = QColor(0, 122, 255)  # #007AFF
        self._gradient_end = QColor(88, 86, 214)  # #5856D6
        
        # Pulsing glow effect
        self._glow_opacity = 0.0  # 0.0 to 1.0
        self._glow_direction = 1  # 1 for increasing, -1 for decreasing
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._update_glow)
        self._glow_timer.setInterval(50)  # Update every 50ms for smooth pulse
        
        # Animation for focus score transition
        self._focus_animation = QPropertyAnimation(self, b"animatedScore")
        self._focus_animation.setDuration(400)  # Apple-like speed
        self._focus_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Animation for circular progress fill
        self._circle_animation = QPropertyAnimation(self, b"circleProgress")
        self._circle_animation.setDuration(400)
        self._circle_animation.setEasingCurve(QEasingCurve.OutCubic)
    
    def _update_glow(self) -> None:
        """Update pulsing glow effect when focused."""
        if self._is_focused and self._focus_score > 70:
            # Pulse between 0.3 and 0.7 opacity
            self._glow_opacity += self._glow_direction * 0.05
            if self._glow_opacity >= 0.7:
                self._glow_opacity = 0.7
                self._glow_direction = -1
            elif self._glow_opacity <= 0.3:
                self._glow_opacity = 0.3
                self._glow_direction = 1
            self.update()
        else:
            # Fade out when not focused
            if self._glow_opacity > 0:
                self._glow_opacity = max(0, self._glow_opacity - 0.1)
                self.update()
    
    def set_focus_score(self, score: float, status: str = "FOCUSED") -> None:
        """
        Update focus score and status with smooth animation.
        
        Args:
            score: Focus score (0-100)
            status: Status text (e.g., "FOCUSED", "DISTRACTED")
        """
        target_score = max(0.0, min(100.0, score))
        self._focus_score = target_score
        self._status_text = status
        self._is_focused = (status == "FOCUSED")
        
        # Start/stop glow animation based on focus state
        if self._is_focused and target_score > 70:
            if not self._glow_timer.isActive():
                self._glow_timer.start()
        else:
            if self._glow_timer.isActive():
                self._glow_timer.stop()
                self._glow_opacity = 0.0
        
        # Animate focus percentage text transition
        if self._focus_animation.state() == QPropertyAnimation.Running:
            self._focus_animation.stop()
        
        self._focus_animation.setStartValue(self._animated_score)
        self._focus_animation.setEndValue(target_score)
        self._focus_animation.start()
        
        # Animate circular progress fill
        if self._circle_animation.state() == QPropertyAnimation.Running:
            self._circle_animation.stop()
        
        self._circle_animation.setStartValue(self._circle_progress)
        self._circle_animation.setEndValue(target_score)
        self._circle_animation.start()
    
    def get_animated_score(self) -> float:
        """Get animated score value (for QPropertyAnimation)."""
        return self._animated_score
    
    def set_animated_score(self, value: float) -> None:
        """Set animated score value (for QPropertyAnimation)."""
        self._animated_score = value
        self.update()  # Trigger repaint
    
    def get_circle_progress(self) -> float:
        """Get circle progress value (for QPropertyAnimation)."""
        return self._circle_progress
    
    def set_circle_progress(self, value: float) -> None:
        """Set circle progress value (for QPropertyAnimation)."""
        self._circle_progress = value
        self.update()  # Trigger repaint
    
    # Properties for QPropertyAnimation
    animatedScore = pyqtProperty(float, get_animated_score, set_animated_score)
    circleProgress = pyqtProperty(float, get_circle_progress, set_circle_progress)
    
    def paintEvent(self, event):
        """Paint the circular progress indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get widget dimensions
        width = self.width()
        height = self.height()
        
        # Calculate circle dimensions (leave padding)
        padding = 20
        circle_diameter = min(width - 2 * padding, height - 80)  # Leave space for status text
        circle_radius = circle_diameter / 2
        center_x = width / 2
        center_y = (height - 40) / 2  # Offset for status text
        
        # Draw pulsing glow effect (if focused and score > 70)
        if self._is_focused and self._circle_progress > 70 and self._glow_opacity > 0:
            glow_radius = circle_radius + 8  # Slightly larger than circle
            glow_gradient = QRadialGradient(center_x, center_y, glow_radius)
            glow_gradient.setColorAt(0.0, QColor(0, 122, 255, int(100 * self._glow_opacity)))
            glow_gradient.setColorAt(0.7, QColor(88, 86, 214, int(50 * self._glow_opacity)))
            glow_gradient.setColorAt(1.0, QColor(0, 122, 255, 0))
            
            glow_pen = QPen(QBrush(glow_gradient), 12)
            glow_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                int(center_x - glow_radius),
                int(center_y - glow_radius),
                int(glow_radius * 2),
                int(glow_radius * 2)
            )
        
        # Draw track circle (background) - Thin 3px ring
        pen = QPen(self._track_color)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(
            int(center_x - circle_radius),
            int(center_y - circle_radius),
            int(circle_diameter),
            int(circle_diameter)
        )
        
        # Draw progress arc with gradient (use animated circle_progress for smooth fill)
        if self._circle_progress > 0:
            # Create linear gradient for progress ring (Apple blue gradient)
            gradient = QLinearGradient(
                center_x - circle_radius, center_y - circle_radius,
                center_x + circle_radius, center_y + circle_radius
            )
            gradient.setColorAt(0.0, self._gradient_start)
            gradient.setColorAt(1.0, self._gradient_end)
            
            pen = QPen(QBrush(gradient), 3)  # Thin 3px ring
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            
            # Calculate arc span (0-360 degrees, but Qt uses 1/16th degree units)
            # Start at top (-90 degrees), progress clockwise
            span_angle = int(16 * 360 * (self._circle_progress / 100.0))
            
            painter.drawArc(
                int(center_x - circle_radius),
                int(center_y - circle_radius),
                int(circle_diameter),
                int(circle_diameter),
                -90 * 16,  # Start at top (-90 degrees)
                -span_angle  # Negative for clockwise
            )
        
        # Draw percentage text (use animated_score for smooth transition) - 48pt Semibold
        painter.setPen(self._text_color)
        font = QFont()
        font.setPointSize(48)
        font.setWeight(QFont.DemiBold)  # Semibold (600)
        painter.setFont(font)
        
        percentage_text = f"{int(self._animated_score)}%"
        text_rect = painter.fontMetrics().boundingRect(percentage_text)
        painter.drawText(
            int(center_x - text_rect.width() / 2),
            int(center_y + text_rect.height() / 2),
            percentage_text
        )
        
        # Draw status text
        status_color = self._status_color_focused if self._is_focused else self._status_color_unfocused
        painter.setPen(status_color)
        font = QFont()
        font.setPointSize(16)
        font.setWeight(QFont.Normal)
        painter.setFont(font)
        
        status_rect = painter.fontMetrics().boundingRect(self._status_text)
        painter.drawText(
            int(center_x - status_rect.width() / 2),
            int(height - 20),
            self._status_text
        )
    
    def sizeHint(self) -> QSize:
        """Return preferred widget size."""
        return QSize(250, 280)
