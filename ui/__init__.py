"""UI components for StudySensei PyQt5 application."""

# PyQt5 UI components
from .main_window import MainWindow
from .video_widget import VideoWidget
from .focus_circle_widget import FocusCircleWidget
from .metrics_panel import MetricsPanel
from .analytics_widget import AnalyticsWidget
from .sidebar_widget import AppleSidebar
from .sidebar_toggle_button import SidebarToggleButton

__all__ = [
    "MainWindow",
    "VideoWidget",
    "FocusCircleWidget",
    "MetricsPanel",
    "AnalyticsWidget",
    "AppleSidebar",
    "SidebarToggleButton",
]
