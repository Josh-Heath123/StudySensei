"""
MetricsPanel - Grid layout widget displaying session metrics.
"""

from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont
from typing import Optional
from .apple_styler import AppleStyler


class MetricsPanel(QWidget):
    """
    Panel displaying session metrics in a grid layout.
    
    Metrics:
    - Posture score
    - FPS
    - Session timer
    - Window duration (60s)
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 150)
        
        # Create grid layout - Apple spacing
        layout = QGridLayout(self)
        AppleStyler.apply_spacing(layout, size="medium", margins="large")
        
        # Fonts - Apple typography system
        label_font = QFont()
        label_font.setPointSize(11)  # Metrics label
        label_font.setWeight(QFont.Medium)  # Medium (500)
        
        value_font = QFont()
        value_font.setPointSize(13)  # Body size for values
        value_font.setWeight(QFont.Normal)
        
        # Posture metrics
        posture_label = QLabel("POSTURE")
        posture_label.setFont(label_font)
        posture_label.setProperty("class", "metric")  # For QSS styling
        posture_label.setAlignment(Qt.AlignCenter)
        
        self.posture_value = QLabel("--%")
        self.posture_value.setFont(value_font)
        self.posture_value.setProperty("class", "body")  # For QSS styling
        self.posture_value.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(posture_label, 0, 0)
        layout.addWidget(self.posture_value, 1, 0)
        
        # FPS metrics
        fps_label = QLabel("FPS")
        fps_label.setFont(label_font)
        fps_label.setProperty("class", "metric")  # For QSS styling
        fps_label.setAlignment(Qt.AlignCenter)
        
        self.fps_value = QLabel("--")
        self.fps_value.setFont(value_font)
        self.fps_value.setProperty("class", "body")  # For QSS styling
        self.fps_value.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(fps_label, 0, 1)
        layout.addWidget(self.fps_value, 1, 1)
        
        # Session timer
        session_label = QLabel("SESSION")
        session_label.setFont(label_font)
        session_label.setProperty("class", "metric")  # For QSS styling
        session_label.setAlignment(Qt.AlignCenter)
        
        self.session_value = QLabel("00:00:00")
        self.session_value.setFont(value_font)
        self.session_value.setProperty("class", "body")  # For QSS styling
        self.session_value.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(session_label, 0, 2)
        layout.addWidget(self.session_value, 1, 2)
        
        # Window duration (fixed at 60s)
        window_label = QLabel("WINDOW")
        window_label.setFont(label_font)
        window_label.setProperty("class", "metric")  # For QSS styling
        window_label.setAlignment(Qt.AlignCenter)
        
        window_value = QLabel("60s")
        window_value.setFont(value_font)
        window_value.setProperty("class", "body")  # For QSS styling
        window_value.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(window_label, 0, 3)
        layout.addWidget(window_value, 1, 3)
        
        # Set column stretch for equal spacing
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 1)
    
    def set_posture_score(self, score: float) -> None:
        """Update posture score."""
        self.posture_value.setText(f"{int(score)}%")
    
    def set_fps(self, fps: float) -> None:
        """Update FPS value."""
        self.fps_value.setText(f"{fps:.1f}")
    
    def set_session_time(self, seconds: float) -> None:
        """Update session timer (format: HH:MM:SS)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        self.session_value.setText(f"{hours:02d}:{minutes:02d}:{secs:02d}")
    
    def reset(self) -> None:
        """Reset all metrics to default values."""
        self.posture_value.setText("--%")
        self.fps_value.setText("--")
        self.session_value.setText("00:00:00")
