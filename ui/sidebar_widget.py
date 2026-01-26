"""
AppleSidebar - Collapsible left sidebar with Apple aesthetic.

Features:
- Slides in from left (300ms animation)
- Auto-sizes to widest button text
- Subtle shadow, backdrop blur, rounded corners
- Smooth transitions
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import (
    QPropertyAnimation, QEasingCurve, QRect, Qt, pyqtProperty, pyqtSignal
)
from PyQt5.QtGui import QCursor, QPainter, QColor, QBrush, QPen, QFont
from typing import Optional
from .apple_styler import AppleStyler


class AppleSidebar(QWidget):
    """Collapsible sidebar with Apple aesthetic."""
    
    # Signal emitted when a button is clicked
    main_clicked = pyqtSignal()
    analytics_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_open = False
        self._sidebar_width = 0  # Current width (animated)
        self._target_width = 0  # Target width when open
        
        self.setup_ui()
        self.setup_animations()
        self.apply_apple_style()
        
        # Initially hidden
        self.setFixedWidth(0)
    
    def setup_ui(self):
        """Setup sidebar UI components."""
        # Main layout
        self.layout = QVBoxLayout(self)
        AppleStyler.apply_spacing(self.layout, size="small", margins="medium")
        
        # Buttons - Main and Analytics
        self.main_button = QPushButton("Main")
        self.main_button.setObjectName("sidebar_main_btn")
        self.main_button.clicked.connect(self.main_clicked.emit)
        
        self.analytics_button = QPushButton("Analytics")
        self.analytics_button.setObjectName("sidebar_analytics_btn")
        self.analytics_button.clicked.connect(self.analytics_clicked.emit)
        
        # Style buttons as Apple-style
        for btn in [self.main_button, self.analytics_button]:
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            btn.setMinimumHeight(44)  # Apple tap target size
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.layout.addWidget(self.main_button)
        self.layout.addWidget(self.analytics_button)
        self.layout.addStretch()
        
        # Calculate target width based on button text
        self._calculate_target_width()
    
    def _calculate_target_width(self):
        """Calculate sidebar width based on widest button text."""
        max_width = 0
        for btn in [self.main_button, self.analytics_button]:
            font_metrics = btn.fontMetrics()
            text_width = font_metrics.boundingRect(btn.text()).width()
            # Add padding: 16px left + 16px right + button padding
            button_width = text_width + 32 + 40  # Text + margins + button padding
            max_width = max(max_width, button_width)
        
        # Minimum width for comfortable spacing
        self._target_width = max(max_width, 180)
    
    def setup_animations(self):
        """Setup slide animations."""
        # Width animation
        self.width_animation = QPropertyAnimation(self, b"sidebarWidth")
        self.width_animation.setDuration(300)  # 300ms as specified
        self.width_animation.setEasingCurve(QEasingCurve.OutCubic)
    
    def apply_apple_style(self):
        """Apply Apple styling to sidebar."""
        # Subtle shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(4, 0)
        self.setGraphicsEffect(shadow)
        
        # Set background with backdrop blur effect (simulated with semi-transparent)
        self.setStyleSheet("""
            AppleSidebar {
                background-color: rgba(28, 28, 30, 0.95);
                border: none;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            
            QPushButton#sidebar_main_btn,
            QPushButton#sidebar_analytics_btn {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                padding: 12px 16px;
                text-align: left;
                color: rgba(255, 255, 255, 0.8);
                font-size: 13px;
                font-weight: 500;
            }
            
            QPushButton#sidebar_main_btn:hover,
            QPushButton#sidebar_analytics_btn:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
            }
            
            QPushButton#sidebar_main_btn:pressed,
            QPushButton#sidebar_analytics_btn:pressed {
                background-color: rgba(255, 255, 255, 0.15);
            }
        """)
    
    def get_sidebar_width(self) -> int:
        """Get current sidebar width (for animation)."""
        return self._sidebar_width
    
    def set_sidebar_width(self, width: int) -> None:
        """Set sidebar width (for animation)."""
        self._sidebar_width = max(0, int(width))
        self.setFixedWidth(self._sidebar_width)
    
    # Property for QPropertyAnimation
    sidebarWidth = pyqtProperty(int, get_sidebar_width, set_sidebar_width)
    
    def toggle(self) -> None:
        """Toggle sidebar open/closed."""
        if self.is_open:
            self.close_sidebar()
        else:
            self.open_sidebar()
    
    def open_sidebar(self) -> None:
        """Open sidebar with animation."""
        if self.is_open:
            return
        
        self.is_open = True
        
        # Animate to target width
        self.width_animation.setStartValue(self._sidebar_width)
        self.width_animation.setEndValue(self._target_width)
        self.width_animation.start()
    
    def close_sidebar(self) -> None:
        """Close sidebar with animation."""
        if not self.is_open:
            return
        
        self.is_open = False
        
        # Animate to 0 width
        self.width_animation.setStartValue(self._sidebar_width)
        self.width_animation.setEndValue(0)
        self.width_animation.start()
    
    def paintEvent(self, event):
        """Paint sidebar with rounded corners."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw rounded rectangle background
        rect = self.rect()
        painter.setBrush(QBrush(QColor(28, 28, 30, 243)))  # rgba(28, 28, 30, 0.95)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 8, 8, Qt.SizeMode.RelativeSize)
    
    def set_active_button(self, button_name: str) -> None:
        """Set active button (highlight it)."""
        # Reset all buttons
        for btn in [self.main_button, self.analytics_button]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: rgba(255, 255, 255, 0.8);
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                    color: white;
                }
            """)
        
        # Highlight active button
        if button_name == "main":
            self.main_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 122, 255, 0.2);
                    color: #007AFF;
                }
                QPushButton:hover {
                    background-color: rgba(0, 122, 255, 0.3);
                }
            """)
        elif button_name == "analytics":
            self.analytics_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 122, 255, 0.2);
                    color: #007AFF;
                }
                QPushButton:hover {
                    background-color: rgba(0, 122, 255, 0.3);
                }
            """)
