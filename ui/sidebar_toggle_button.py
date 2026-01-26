"""
SidebarToggleButton - Circular hamburger menu button for Apple sidebar.

Features:
- 40px circular button
- Hamburger icon (3 lines)
- Stays vertically centered
- Smooth hover effects
"""

from PyQt5.QtWidgets import QPushButton, QSizePolicy
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush


class SidebarToggleButton(QPushButton):
    """Circular hamburger menu button."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        
        # Apple-style styling
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
    
    def paintEvent(self, event):
        """Draw hamburger icon (3 horizontal lines)."""
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw 3 horizontal lines (hamburger icon)
        pen = QPen(QColor(255, 255, 255), 2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        
        center_x = self.width() / 2
        center_y = self.height() / 2
        line_spacing = 4
        line_length = 16
        
        # Top line
        painter.drawLine(
            int(center_x - line_length / 2),
            int(center_y - line_spacing),
            int(center_x + line_length / 2),
            int(center_y - line_spacing)
        )
        
        # Middle line
        painter.drawLine(
            int(center_x - line_length / 2),
            int(center_y),
            int(center_x + line_length / 2),
            int(center_y)
        )
        
        # Bottom line
        painter.drawLine(
            int(center_x - line_length / 2),
            int(center_y + line_spacing),
            int(center_x + line_length / 2),
            int(center_y + line_spacing)
        )
    
    def sizeHint(self) -> QSize:
        """Return preferred size."""
        return QSize(40, 40)
