"""
AnalyticsWidget - Qt Charts for focus history and session analytics.
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt, QTimer
try:
    from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
    _QT_CHARTS_AVAILABLE = True
except ImportError:
    # Qt Charts not available - create dummy classes
    _QT_CHARTS_AVAILABLE = False
    QChart = None
    QChartView = None
    QLineSeries = None
    QValueAxis = None
    QDateTimeAxis = None
from PyQt5.QtGui import QPen, QColor, QPainter
from typing import List, Tuple, Optional
import time
from datetime import datetime, timedelta


class AnalyticsWidget(QWidget):
    """
    Analytics widget with Qt Charts for focus history visualization.
    
    Features:
    - Real-time focus history line chart
    - Posture history line chart
    - Session statistics
    - Data export functionality
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize data storage attributes (always, even if charts not available)
        self.focus_history: List[Tuple[float, float]] = []  # [(timestamp, score), ...]
        self.posture_history: List[Tuple[float, float]] = []  # [(timestamp, score), ...]
        self.max_data_points = 100  # Keep last 100 points
        
        # Check if Qt Charts is available
        if not _QT_CHARTS_AVAILABLE:
            self._setup_no_charts_ui()
            return
        
        # Setup UI
        self._setup_ui()
        
        # Update timer (update chart every 2 seconds)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_charts)
        self.update_timer.start(2000)  # 2 seconds
    
    def _setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Analytics Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: 400; color: #1d1d1f;")
        layout.addWidget(title)
        
        # Focus chart
        self.focus_chart_view = self._create_focus_chart()
        layout.addWidget(self.focus_chart_view, stretch=1)
        
        # Posture chart
        self.posture_chart_view = self._create_posture_chart()
        layout.addWidget(self.posture_chart_view, stretch=1)
        
        # Statistics and export
        stats_layout = QHBoxLayout()
        
        # Statistics labels
        self.stats_label = QLabel("Session Statistics\nFocus Avg: --%\nPosture Avg: --%")
        self.stats_label.setStyleSheet("""
            QLabel {
                padding: 15px;
                background-color: #f5f5f7;
                border-radius: 12px;
                color: #1d1d1f;
                font-size: 14px;
            }
        """)
        stats_layout.addWidget(self.stats_label, stretch=1)
        
        # Export button
        self.export_btn = QPushButton("Export Data")
        self.export_btn.setMinimumHeight(40)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 15px;
                font-weight: 400;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:pressed {
                background-color: #0040AA;
            }
        """)
        self.export_btn.clicked.connect(self._export_data)
        stats_layout.addWidget(self.export_btn)
        
        layout.addLayout(stats_layout)
    
    def _create_focus_chart(self) -> QChartView:
        """Create focus history line chart."""
        chart = QChart()
        chart.setTitle("Focus History")
        chart.setTitleBrush(QColor("#1d1d1f"))
        chart.setBackgroundBrush(QColor("#ffffff"))
        chart.legend().setVisible(False)
        
        # Create line series
        self.focus_series = QLineSeries()
        self.focus_series.setName("Focus Score")
        pen = QPen(QColor("#007AFF"))
        pen.setWidth(2)
        self.focus_series.setPen(pen)
        
        chart.addSeries(self.focus_series)
        
        # Create axes
        axis_x = QValueAxis()
        axis_x.setTitleText("Time (seconds)")
        axis_x.setLabelFormat("%.0f")
        axis_x.setRange(0, 60)  # 60 second window
        
        axis_y = QValueAxis()
        axis_y.setTitleText("Focus Score (%)")
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%.0f")
        
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        
        self.focus_series.attachAxis(axis_x)
        self.focus_series.attachAxis(axis_y)
        
        # Create chart view
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.setMinimumHeight(200)
        
        return chart_view
    
    def _create_posture_chart(self) -> QChartView:
        """Create posture history line chart."""
        chart = QChart()
        chart.setTitle("Posture History")
        chart.setTitleBrush(QColor("#1d1d1f"))
        chart.setBackgroundBrush(QColor("#ffffff"))
        chart.legend().setVisible(False)
        
        # Create line series
        self.posture_series = QLineSeries()
        self.posture_series.setName("Posture Score")
        pen = QPen(QColor("#34c759"))
        pen.setWidth(2)
        self.posture_series.setPen(pen)
        
        chart.addSeries(self.posture_series)
        
        # Create axes
        axis_x = QValueAxis()
        axis_x.setTitleText("Time (seconds)")
        axis_x.setLabelFormat("%.0f")
        axis_x.setRange(0, 60)  # 60 second window
        
        axis_y = QValueAxis()
        axis_y.setTitleText("Posture Score (%)")
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%.0f")
        
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        
        self.posture_series.attachAxis(axis_x)
        self.posture_series.attachAxis(axis_y)
        
        # Create chart view
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.setMinimumHeight(200)
        
        return chart_view
    
    def add_focus_data_point(self, timestamp: float, score: float) -> None:
        """Add a focus data point to history."""
        if not hasattr(self, 'focus_history'):
            return
        
        self.focus_history.append((timestamp, score))
        
        # Keep only last N points
        if len(self.focus_history) > self.max_data_points:
            self.focus_history.pop(0)
    
    def add_posture_data_point(self, timestamp: float, score: float) -> None:
        """Add a posture data point to history."""
        if not hasattr(self, 'posture_history'):
            return
        
        self.posture_history.append((timestamp, score))
        
        # Keep only last N points
        if len(self.posture_history) > self.max_data_points:
            self.posture_history.pop(0)
    
    def _update_charts(self) -> None:
        """Update charts with latest data."""
        try:
            if not _QT_CHARTS_AVAILABLE:
                return
            
            # Check if chart components are initialized
            if not hasattr(self, 'focus_series') or not self.focus_series:
                return
            
            if not hasattr(self, 'posture_series') or not self.posture_series:
                return
            
            # Update focus chart
            if self.focus_history:
                self.focus_series.clear()
                
                # Get relative timestamps (last 60 seconds)
                current_time = time.time()
                cutoff_time = current_time - 60.0
                
                for timestamp, score in self.focus_history:
                    # Convert to relative time (seconds from start of window)
                    relative_time = timestamp % 60.0  # Show last 60 seconds
                    self.focus_series.append(relative_time, score)
                
                # Update statistics
                if self.focus_history and hasattr(self, 'stats_label') and self.stats_label:
                    avg_focus = sum(score for _, score in self.focus_history) / len(self.focus_history)
                    avg_posture = 0.0
                    if self.posture_history:
                        avg_posture = sum(score for _, score in self.posture_history) / len(self.posture_history)
                    
                    self.stats_label.setText(
                        f"Session Statistics\n"
                        f"Focus Avg: {avg_focus:.1f}%\n"
                        f"Posture Avg: {avg_posture:.1f}%"
                    )
            
            # Update posture chart
            if self.posture_history:
                self.posture_series.clear()
                
                for timestamp, score in self.posture_history:
                    relative_time = timestamp % 60.0
                    self.posture_series.append(relative_time, score)
        except Exception as e:
            # Silently handle errors to prevent crashes
            print(f"Error updating charts: {e}")
            pass
    
    def _export_data(self) -> None:
        """Export session data to CSV."""
        from PyQt5.QtWidgets import QFileDialog
        import csv
        
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Session Data",
            f"studysensei_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Timestamp', 'Focus Score', 'Posture Score'])
                
                # Merge focus and posture data by timestamp
                all_timestamps = sorted(set(
                    [t for t, _ in self.focus_history] +
                    [t for t, _ in self.posture_history]
                ))
                
                focus_dict = dict(self.focus_history)
                posture_dict = dict(self.posture_history)
                
                for timestamp in all_timestamps:
                    focus_score = focus_dict.get(timestamp, '')
                    posture_score = posture_dict.get(timestamp, '')
                    writer.writerow([timestamp, focus_score, posture_score])
            
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Export Successful",
                f"Session data exported to:\n{filename}"
            )
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Error exporting data:\n{str(e)}"
            )
    
    def _setup_no_charts_ui(self):
        """Setup UI when Qt Charts is not available."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Analytics Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: 400; color: #1d1d1f;")
        layout.addWidget(title)
        
        message = QLabel(
            "Qt Charts not available.\n"
            "Install PyQtChart to enable analytics charts:\n"
            "pip install PyQtChart"
        )
        message.setStyleSheet("""
            QLabel {
                padding: 20px;
                background-color: #fff3cd;
                border-radius: 12px;
                color: #856404;
                font-size: 14px;
            }
        """)
        message.setAlignment(Qt.AlignCenter)
        layout.addWidget(message)
        
        # Dummy attributes for compatibility (data storage already initialized in __init__)
        self.focus_series = None
        self.posture_series = None
        self.stats_label = QLabel("Session Statistics\nFocus Avg: --%\nPosture Avg: --%")
        layout.addWidget(self.stats_label)
    
    def reset(self) -> None:
        """Reset all data for new session."""
        if not _QT_CHARTS_AVAILABLE:
            return
        
        self.focus_history.clear()
        self.posture_history.clear()
        if self.focus_series:
            self.focus_series.clear()
        if self.posture_series:
            self.posture_series.clear()
        if self.stats_label:
            self.stats_label.setText("Session Statistics\nFocus Avg: --%\nPosture Avg: --%")
